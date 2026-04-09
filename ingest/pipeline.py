"""
Image processing pipeline — orchestrates EXIF extraction, normalization,
and thumbnail generation for uploaded images.
"""

from __future__ import annotations

from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image as PILImage

from core.exif import extract_exif
from core.models import ExifData, Image
from core.normalization import get_or_create_camera, get_or_create_lens

# Countries with known bad GPS data — skip geocoding
INVALID_COUNTRIES = {'CN', 'IN', 'JP', 'KG', 'MN', 'RU'}

THUMBNAIL_SIZES = {
    'small': (300, 300),
    'medium': (800, 800),
    'large': (1600, 1600),
}

ALLOWED_FORMATS = {'JPEG', 'PNG', 'WEBP', 'TIFF', 'MPO'}


def process_image(image: Image) -> None:
    """
    Run the full ingest pipeline on an uploaded Image.

    1. Extract EXIF
    2. Normalize camera/lens
    3. Generate thumbnails
    4. Create ExifData record
    5. Mark image as processed
    """
    file = image.original

    # 1. Extract EXIF
    exif = extract_exif(file)

    # 2. Normalize camera/lens
    camera = None
    if exif['make'] or exif['model']:
        camera = get_or_create_camera(exif['make'], exif['model'])

    lens = None
    if exif['lens_model']:
        lens = get_or_create_lens(exif['lens_model'], exif['make'])

    # 3. Compute perceptual hash
    file.seek(0)
    compute_phash(image, file)

    # 4. Generate thumbnails
    file.seek(0)
    generate_thumbnails(image, file)

    # 5. Create ExifData
    ExifData.objects.update_or_create(
        image=image,
        defaults={
            'raw_data': exif['raw'],
            'camera': camera,
            'lens': lens,
            'focal_length': exif['focal_length'],
            'aperture': exif['aperture'],
            'shutter_speed': exif['shutter_speed'],
            'iso': exif['iso'],
            'date_taken': exif['date_taken'],
            'gps_latitude': exif['gps_latitude'],
            'gps_longitude': exif['gps_longitude'],
        },
    )

    # 6. Reverse geocode to city
    if exif['gps_latitude'] and exif['gps_longitude']:
        try:
            from core.models import City
            city = City.from_coordinates(
                float(exif['gps_latitude']), float(exif['gps_longitude'])
            )
            if city and city.country_code not in INVALID_COUNTRIES:
                image.city = city
        except Exception:
            pass

    # 7. Apply cleanup rules to this image (may delete it)
    if _cleanup_image(image, exif):
        return  # Image was deleted by cleanup

    # 8. Mark as processed
    image.is_processing = False
    image.save(update_fields=['is_processing', 'city', 'updated_at'])


def compute_phash(image: Image, file) -> None:
    """Compute perceptual hash for visual deduplication."""
    import imagehash

    file.seek(0)
    with PILImage.open(file) as img:
        phash = str(imagehash.phash(img))
        image.perceptual_hash = phash
        image.save(update_fields=['perceptual_hash'])


def generate_thumbnails(image: Image, file) -> None:
    """Generate small, medium, and large thumbnails from the original."""
    file.seek(0)
    with PILImage.open(file) as img:
        # Validate format
        if img.format and img.format not in ALLOWED_FORMATS:
            raise ValueError(f"Unsupported image format: {img.format}")

        # Preserve orientation from EXIF
        img = _apply_exif_orientation(img)

        # Convert to RGB if needed (for JPEG output)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        for size_name, dimensions in THUMBNAIL_SIZES.items():
            thumb = img.copy()
            thumb.thumbnail(dimensions, PILImage.LANCZOS)

            buffer = BytesIO()
            thumb.save(buffer, format='JPEG', quality=92, optimize=True)
            buffer.seek(0)

            filename = f"{image.id}_{size_name}.jpg"
            field = getattr(image, f'thumbnail_{size_name}')
            field.save(filename, ContentFile(buffer.read()), save=False)

    image.save(update_fields=['thumbnail_small', 'thumbnail_medium', 'thumbnail_large'])


def _cleanup_image(image: Image, exif: dict) -> bool:
    """Apply cleanup rules inline during processing. Returns True if image was deleted."""
    date_taken = exif.get('date_taken')
    if not date_taken:
        return False

    year = date_taken.year
    date_str = date_taken.strftime('%Y-%m-%d')

    # Delete rules
    DELETE_DATES = {'2014-12-26', '2017-12-22', '2019-09-28'}
    DELETE_YEARS = {2008, 2020}

    if year in DELETE_YEARS or date_str in DELETE_DATES:
        image.delete()
        return True

    # Fix rules — clear bad dates
    if year < 2008 or year >= 2021:
        from core.models import ExifData
        ExifData.objects.filter(image=image).update(date_taken=None)

    return False


def _apply_exif_orientation(img: PILImage.Image) -> PILImage.Image:
    """Rotate/flip image according to EXIF orientation tag."""
    from PIL import ExifTags

    try:
        exif = img.getexif()
        orientation_key = next(
            k for k, v in ExifTags.TAGS.items() if v == 'Orientation'
        )
        orientation = exif.get(orientation_key)

        rotations = {
            3: 180,
            6: 270,
            8: 90,
        }
        if orientation in rotations:
            img = img.rotate(rotations[orientation], expand=True)
        elif orientation == 2:
            img = img.transpose(PILImage.FLIP_LEFT_RIGHT)
        elif orientation == 4:
            img = img.transpose(PILImage.FLIP_TOP_BOTTOM)
        elif orientation == 5:
            img = img.rotate(270, expand=True).transpose(PILImage.FLIP_LEFT_RIGHT)
        elif orientation == 7:
            img = img.rotate(90, expand=True).transpose(PILImage.FLIP_LEFT_RIGHT)
    except (StopIteration, AttributeError, KeyError):
        pass

    return img
