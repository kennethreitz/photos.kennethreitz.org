"""
Import photos and sets from a Flickr account.

Usage:
  manage.py import_flickr <flickr_username> --api-key=<key>
  manage.py import_flickr <flickr_username> --api-key=<key> --sets-only
  manage.py import_flickr <flickr_username> --api-key=<key> --set=<set_id>
  manage.py import_flickr <flickr_username> --api-key=<key> --resume

Requires a free Flickr API key from https://www.flickr.com/services/api/keys/
Set FLICKR_API_KEY in .env to avoid passing it every time.
"""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from core.models import Image, User
from gallery.models import Collection, CollectionImage
from ingest.pipeline import process_image

FLICKR_API = "https://www.flickr.com/services/rest/"
RESUME_FILE = Path("/tmp/exiftree-flickr-resume.json")


class Command(BaseCommand):
    help = "Import photos and photosets from a Flickr account"

    def add_arguments(self, parser):
        parser.add_argument('flickr_user', help="Flickr username or NSID")
        parser.add_argument('--api-key', default=os.environ.get('FLICKR_API_KEY', ''),
                            help="Flickr API key (or set FLICKR_API_KEY env var)")
        parser.add_argument('--user', default=settings.SINGLE_TENANT or '',
                            help="ExifTree username to import as")
        parser.add_argument('--sets-only', action='store_true',
                            help="Only list sets, don't import")
        parser.add_argument('--set', dest='set_id',
                            help="Import only this photoset ID")
        parser.add_argument('--max', type=int, default=0,
                            help="Max photos to import (0 = all)")
        parser.add_argument('--workers', type=int, default=6,
                            help="Parallel download workers (default: 6)")
        parser.add_argument('--resume', action='store_true',
                            help="Resume from last interrupted import")
        parser.add_argument('--reset', action='store_true',
                            help="Clear resume state and start fresh")

    def handle(self, *args, **options):
        api_key = options['api_key']
        if not api_key:
            self.stderr.write(self.style.ERROR(
                "Flickr API key required. Get one at https://www.flickr.com/services/api/keys/\n"
                "Pass --api-key=KEY or set FLICKR_API_KEY in .env"
            ))
            return

        if options['reset'] and RESUME_FILE.exists():
            RESUME_FILE.unlink()
            self.stdout.write("Resume state cleared.")

        username = options['user']
        if not username:
            self.stderr.write(self.style.ERROR("ExifTree --user required (or set SINGLE_TENANT)"))
            return

        try:
            self.exiftree_user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"ExifTree user '{username}' not found"))
            return

        self.session = requests.Session()
        self.api_key = api_key
        self.workers = options['workers']

        # Load resume state
        self.imported_ids = set()
        if options['resume'] and RESUME_FILE.exists():
            data = json.loads(RESUME_FILE.read_text())
            self.imported_ids = set(data.get('imported', []))
            self.stdout.write(f"Resuming — {len(self.imported_ids)} photos already imported")

        # Resolve Flickr user ID
        nsid = self._get_nsid(options['flickr_user'])
        if not nsid:
            self.stderr.write(self.style.ERROR(f"Flickr user '{options['flickr_user']}' not found"))
            return
        self.stdout.write(f"Flickr user: {nsid}")

        # Get sets
        sets = self._get_sets(nsid)
        self.stdout.write(f"Found {len(sets)} photosets")

        if options['sets_only']:
            for s in sets:
                self.stdout.write(f"  {s['id']}: {s['title']['_content']} ({s['photos']} photos)")
            return

        if options['set_id']:
            sets = [s for s in sets if s['id'] == options['set_id']]
            if not sets:
                self.stderr.write(self.style.ERROR(f"Set {options['set_id']} not found"))
                return

        max_photos = options['max']
        total_imported = 0

        try:
            for photoset in sets:
                set_title = photoset['title']['_content']
                set_id = photoset['id']
                set_desc = photoset.get('description', {}).get('_content', '')
                set_date = photoset.get('date_create', '')
                self.stdout.write(f"\nImporting set: {set_title} ({photoset['photos']} photos)")

                # Create collection
                collection = self._get_or_create_collection(set_title, set_id, set_desc, set_date)

                # Get photos in set with extra info
                photos = self._get_set_photos(set_id, nsid)
                self.stdout.write(f"  {len(photos)} photos in set")

                # Filter already imported
                pending = []
                for i, photo in enumerate(photos):
                    if photo['id'] in self.imported_ids:
                        continue
                    if max_photos and total_imported + len(pending) >= max_photos:
                        break
                    pending.append((i, photo))

                if not pending:
                    self.stdout.write("  All photos already imported, skipping.")
                    continue

                # Parallel download + import
                imported = self._import_batch(pending, photos, collection)
                total_imported += imported

                if max_photos and total_imported >= max_photos:
                    self.stdout.write(f"\nReached max ({max_photos}), stopping.")
                    break

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nInterrupted! Progress saved."))
        finally:
            self._save_resume()

        self.stdout.write(self.style.SUCCESS(f"\nDone. Imported {total_imported} photos total."))

    def _import_batch(self, pending, all_photos, collection):
        """Download and import a batch of photos using a thread pool."""
        imported = 0

        def fetch_one(item):
            i, photo = item
            photo_id = photo['id']
            title = photo.get('title', '')

            # Get photo info for description and dates
            info = self._get_photo_info(photo_id)
            description = ''
            date_taken = None
            if info:
                description = info.get('description', {}).get('_content', '')
                dt_str = info.get('dates', {}).get('taken', '')
                if dt_str:
                    try:
                        date_taken = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        pass

            # Get best URL
            sizes = self._get_sizes(photo_id)
            if not sizes:
                return None, i, photo_id, title, "no sizes"

            url = None
            for label in ['Original', 'Large 2048', 'Large 1600', 'Large', 'Medium 800', 'Medium']:
                for s in sizes:
                    if s['label'] == label:
                        url = s['source']
                        break
                if url:
                    break
            if not url:
                url = sizes[-1]['source']

            # Download
            try:
                resp = self.session.get(url, timeout=60)
                resp.raise_for_status()
                return resp.content, i, photo_id, title, description, date_taken
            except Exception as e:
                return None, i, photo_id, title, str(e)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(fetch_one, item): item for item in pending}

            for future in as_completed(futures):
                result = future.result()

                if result is None or result[0] is None:
                    if len(result) == 5:
                        _, i, photo_id, title, error = result
                        self.stdout.write(self.style.WARNING(
                            f"    [{i+1}/{len(all_photos)}] {title or photo_id} — skipped: {error}"
                        ))
                    continue

                contents, i, photo_id, title, description, date_taken = result

                # Dedup
                content_hash = hashlib.sha256(contents).hexdigest()
                existing = Image.objects.filter(content_hash=content_hash).first()
                if existing:
                    CollectionImage.objects.get_or_create(
                        collection=collection, image=existing,
                        defaults={'sort_order': i},
                    )
                    self.imported_ids.add(photo_id)
                    self.stdout.write(
                        f"    [{i+1}/{len(all_photos)}] {title or photo_id} — exists, added to set"
                    )
                    continue

                # Create image
                filename = f"{slugify(title) or photo_id}.jpg"
                img = Image.objects.create(
                    user=self.exiftree_user,
                    title=title,
                    description=description,
                    slug=slugify(title) or f"flickr-{photo_id}",
                    original=ContentFile(contents, name=filename),
                    content_hash=content_hash,
                    is_processing=True,
                )

                # Process
                try:
                    process_image(img)

                    # Fill missing EXIF date with Flickr date
                    if date_taken and hasattr(img, 'exif'):
                        exif = img.exif
                        if not exif.date_taken:
                            from django.utils import timezone
                            exif.date_taken = timezone.make_aware(date_taken)
                            exif.save(update_fields=['date_taken'])

                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"    Processing error: {e}"))

                # Add to collection
                CollectionImage.objects.get_or_create(
                    collection=collection, image=img,
                    defaults={'sort_order': i},
                )

                self.imported_ids.add(photo_id)
                imported += 1
                self.stdout.write(f"    [{i+1}/{len(all_photos)}] {title or photo_id} — imported")

        return imported

    def _get_or_create_collection(self, title, set_id, description, date_create):
        slug = slugify(title) or f"flickr-{set_id}"
        collection, created = Collection.objects.get_or_create(
            user=self.exiftree_user,
            slug=slug,
            defaults={
                'title': title,
                'description': description,
            },
        )
        # Set date from Flickr
        if created and date_create:
            try:
                from datetime import date
                dt = datetime.fromtimestamp(int(date_create))
                collection.date = dt.date()
                collection.save(update_fields=['date'])
            except (ValueError, TypeError):
                pass
        if created:
            self.stdout.write(f"  Created collection: {title}")
        return collection

    def _save_resume(self):
        RESUME_FILE.write_text(json.dumps({
            'imported': list(self.imported_ids),
        }))

    def _flickr(self, method, **kwargs):
        params = {
            'method': method,
            'api_key': self.api_key,
            'format': 'json',
            'nojsoncallback': '1',
            **kwargs,
        }
        resp = self.session.get(FLICKR_API, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _get_nsid(self, username):
        if '@' in username:
            return username
        try:
            data = self._flickr('flickr.people.findByUsername', username=username)
            return data['user']['nsid']
        except Exception:
            return None

    def _get_sets(self, nsid):
        data = self._flickr('flickr.photosets.getList', user_id=nsid, per_page='500')
        return data.get('photosets', {}).get('photoset', [])

    def _get_set_photos(self, set_id, nsid):
        photos = []
        page = 1
        while True:
            data = self._flickr(
                'flickr.photosets.getPhotos',
                photoset_id=set_id, user_id=nsid,
                extras='url_o,date_taken,description,tags',
                per_page='500', page=str(page),
            )
            batch = data.get('photoset', {}).get('photo', [])
            photos.extend(batch)
            pages = int(data.get('photoset', {}).get('pages', 1))
            if page >= pages:
                break
            page += 1
        return photos

    def _get_sizes(self, photo_id):
        try:
            data = self._flickr('flickr.photos.getSizes', photo_id=photo_id)
            return data.get('sizes', {}).get('size', [])
        except Exception:
            return []

    def _get_photo_info(self, photo_id):
        try:
            data = self._flickr('flickr.photos.getInfo', photo_id=photo_id)
            return data.get('photo', {})
        except Exception:
            return {}
