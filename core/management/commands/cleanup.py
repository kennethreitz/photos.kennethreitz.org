"""
Cleanup rules for unwanted photos. Rerun safely at any time.

Usage:
  manage.py cleanup
  manage.py cleanup --dry-run
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from core.models import City, ExifData, Image


# ---------------------------------------------------------------------------
# Delete rules — images matching these filters get deleted
# ---------------------------------------------------------------------------

DELETE_RULES = [
    {
        'name': "All photos from 2008",
        'filter': Q(exif__date_taken__year=2008),
    },
    {
        'name': "All photos from 2020",
        'filter': Q(exif__date_taken__year=2020),
    },
    {
        'name': "Photos from Dec 26, 2014",
        'filter': Q(exif__date_taken__date='2014-12-26'),
    },
    {
        'name': "Photos from Dec 22, 2017",
        'filter': Q(exif__date_taken__date='2017-12-22'),
    },
    {
        'name': "Photos from Sep 28, 2019",
        'filter': Q(exif__date_taken__date='2019-09-28'),
    },
]

# ---------------------------------------------------------------------------
# Fix rules — EXIF data matching these filters gets corrected
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# City rules — clear city for images in countries you've never visited
# ---------------------------------------------------------------------------

INVALID_COUNTRIES = ['CN', 'JP', 'KG', 'MN', 'RU']  # Bad GPS data — never visited
ALLOWED_CITIES = {'Bangalore', 'Mysore', 'Bengaluru', 'Mysuru'}  # Valid Indian cities

PRIVACY_RULES = [
    {
        'name': "Make Jan 5, 2019 photos private",
        'filter': Q(exif__date_taken__date='2019-01-05'),
    },
]

FIX_RULES = [
    {
        'name': "Clear incorrect dates before 2008",
        'filter': Q(date_taken__year__lt=2008),
        'update': {'date_taken': None},
    },
    {
        'name': "Clear incorrect dates 2021+",
        'filter': Q(date_taken__year__gte=2021),
        'update': {'date_taken': None},
    },
]


class Command(BaseCommand):
    help = "Delete or fix photos matching cleanup rules"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Show what would change without changing",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write("Delete rules:")
        total_deleted = 0
        for rule in DELETE_RULES:
            qs = Image.objects.filter(rule['filter'])
            count = qs.count()

            if count == 0:
                self.stdout.write(f"  {rule['name']}: 0 matches")
                continue

            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"  {rule['name']}: {count} would be deleted"
                ))
            else:
                qs.delete()
                total_deleted += count
                self.stdout.write(self.style.SUCCESS(
                    f"  {rule['name']}: {count} deleted"
                ))

        self.stdout.write("\nFix rules:")
        total_fixed = 0
        for rule in FIX_RULES:
            qs = ExifData.objects.filter(rule['filter'])
            count = qs.count()

            if count == 0:
                self.stdout.write(f"  {rule['name']}: 0 matches")
                continue

            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"  {rule['name']}: {count} would be fixed"
                ))
            else:
                qs.update(**rule['update'])
                total_fixed += count
                self.stdout.write(self.style.SUCCESS(
                    f"  {rule['name']}: {count} fixed"
                ))

        # Privacy rules
        self.stdout.write("\nPrivacy rules:")
        for rule in PRIVACY_RULES:
            qs = Image.objects.filter(rule['filter']).exclude(visibility='private')
            count = qs.count()
            if count == 0:
                self.stdout.write(f"  {rule['name']}: 0 matches")
                continue
            if dry_run:
                self.stdout.write(self.style.WARNING(f"  {rule['name']}: {count} would be made private"))
            else:
                qs.update(visibility='private')
                self.stdout.write(self.style.SUCCESS(f"  {rule['name']}: {count} made private"))

        # City cleanup
        self.stdout.write("\nCity rules:")

        # India: clear non-Bangalore/Mysore cities
        in_images = Image.objects.filter(city__country_code='IN').exclude(city__name__in=ALLOWED_CITIES)
        in_count = in_images.count()
        if in_count:
            if dry_run:
                self.stdout.write(self.style.WARNING(f"  Clear non-allowed IN cities: {in_count} would be cleared"))
            else:
                in_images.update(city=None)
                self.stdout.write(self.style.SUCCESS(f"  Clear non-allowed IN cities: {in_count} cleared"))
        else:
            self.stdout.write(f"  Clear non-allowed IN cities: 0 matches")

        for cc in INVALID_COUNTRIES:
            images = Image.objects.filter(city__country_code=cc)
            count = images.count()
            if count == 0:
                self.stdout.write(f"  Clear cities in {cc}: 0 matches")
                continue
            if dry_run:
                self.stdout.write(self.style.WARNING(f"  Clear cities in {cc}: {count} would be cleared"))
            else:
                images.update(city=None)
                self.stdout.write(self.style.SUCCESS(f"  Clear cities in {cc}: {count} cleared"))

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run — nothing changed."))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"\nDone: {total_deleted} deleted, {total_fixed} fixed."
            ))
