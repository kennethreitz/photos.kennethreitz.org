"""
Reverse geocode images with GPS data to assign cities.

Usage:
  manage.py geocode
  manage.py geocode --force  # Re-geocode all images
"""

from django.core.management.base import BaseCommand

from core.models import City, ExifData, Image


class Command(BaseCommand):
    help = "Reverse geocode images to assign cities"

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help="Re-geocode images that already have a city",
        )

    def handle(self, *args, **options):
        import reverse_geocoder as rg
        from django.utils.text import slugify
        from core.models import CONTINENT_MAP, COUNTRY_NAMES, COUNTRY_TO_CONTINENT

        qs = ExifData.objects.filter(
            gps_latitude__isnull=False, gps_longitude__isnull=False,
        ).select_related('image')

        if not options['force']:
            qs = qs.filter(image__city__isnull=True)

        exif_list = list(qs)
        self.stdout.write(f"Found {len(exif_list)} images to geocode")
        if not exif_list:
            return

        # Batch geocode all at once
        coords = [(float(e.gps_latitude), float(e.gps_longitude)) for e in exif_list]
        self.stdout.write("Reverse geocoding (batch)...")
        results = rg.search(coords)

        # Build city cache and image assignments
        city_cache = {}
        assignments = []  # (image_id, city)

        for exif, r in zip(exif_list, results):
            cc = r['cc']
            region = r.get('admin1', '')
            city_name = r['name']
            admin2 = r.get('admin2', '')

            if cc != 'US' and admin2 and admin2 != city_name:
                city_name = admin2

            for prefix in ['City of ', 'Town of ', 'Village of ']:
                if city_name.startswith(prefix):
                    city_name = city_name[len(prefix):]
            if cc == 'US' and city_name.endswith(' County'):
                city_name = city_name[:-7]

            slug = slugify(f"{city_name}-{region}-{cc}" if region else f"{city_name}-{cc}")

            if slug not in city_cache:
                continent_code = COUNTRY_TO_CONTINENT.get(cc, 'NA')
                city_cache[slug] = {
                    'name': city_name,
                    'region': region,
                    'country_code': cc,
                    'country': COUNTRY_NAMES.get(cc, cc),
                    'continent': CONTINENT_MAP.get(continent_code, 'Unknown'),
                    'latitude': float(r['lat']),
                    'longitude': float(r['lon']),
                }

            # Skip invalid countries
        if cc in ('CN', 'IN', 'JP', 'KG', 'MN', 'RU'):
            continue

        assignments.append((exif.image_id, slug))

        # Bulk create cities
        self.stdout.write(f"Creating {len(city_cache)} cities...")
        for slug, data in city_cache.items():
            City.objects.get_or_create(slug=slug, defaults=data)

        # Bulk update images
        self.stdout.write(f"Assigning cities to {len(assignments)} images...")
        slug_to_city = {c.slug: c for c in City.objects.filter(slug__in=city_cache.keys())}

        batch = []
        for image_id, slug in assignments:
            city = slug_to_city.get(slug)
            if city:
                batch.append(Image(id=image_id, city=city))

        Image.objects.bulk_update(batch, ['city'], batch_size=500)
        self.stdout.write(self.style.SUCCESS(f"Done: {len(batch)} images geocoded to {len(city_cache)} cities"))
