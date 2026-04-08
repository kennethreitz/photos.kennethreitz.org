import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True)
    website = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # email is inherited from AbstractUser but we want it required
    email = models.EmailField("email address", unique=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.username


class Camera(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    manufacturer = models.CharField(max_length=255, db_index=True)
    model = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    display_name = models.CharField(max_length=512)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['manufacturer', 'model']
        unique_together = [('manufacturer', 'model')]

    def __str__(self) -> str:
        return self.display_name


class Lens(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    manufacturer = models.CharField(max_length=255, db_index=True)
    model = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    display_name = models.CharField(max_length=512)
    focal_length_min = models.PositiveIntegerField(
        null=True, blank=True, help_text="Minimum focal length in mm"
    )
    focal_length_max = models.PositiveIntegerField(
        null=True, blank=True, help_text="Maximum focal length in mm (same as min for primes)"
    )
    max_aperture = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'lenses'
        ordering = ['manufacturer', 'model']
        unique_together = [('manufacturer', 'model')]

    def __str__(self) -> str:
        return self.display_name


class Image(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = 'public', "Public"
        PRIVATE = 'private', "Private"
        UNLISTED = 'unlisted', "Unlisted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='images')
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    slug = models.SlugField(max_length=255)
    original = models.ImageField(upload_to='originals/%Y/%m/')
    thumbnail_small = models.ImageField(upload_to='thumbs/small/', blank=True)
    thumbnail_medium = models.ImageField(upload_to='thumbs/medium/', blank=True)
    thumbnail_large = models.ImageField(upload_to='thumbs/large/', blank=True)
    visibility = models.CharField(
        max_length=10, choices=Visibility.choices, default=Visibility.PUBLIC
    )
    content_hash = models.CharField(
        max_length=64, blank=True, db_index=True,
        help_text="SHA-256 hash of the original file for deduplication"
    )
    view_count = models.PositiveIntegerField(default=0)
    is_processing = models.BooleanField(default=True)
    upload_date = models.DateTimeField(auto_now_add=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-upload_date']
        indexes = [
            models.Index(fields=['user', 'upload_date']),
            models.Index(fields=['visibility', 'upload_date']),
        ]

    def __str__(self) -> str:
        return self.title or f"Image {self.id}"


class ExifData(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.OneToOneField(Image, on_delete=models.CASCADE, related_name='exif')
    raw_data = models.JSONField(
        default=dict, help_text="Complete raw EXIF blob — never discard this"
    )
    camera = models.ForeignKey(
        Camera, on_delete=models.SET_NULL, null=True, blank=True, related_name='images'
    )
    lens = models.ForeignKey(
        Lens, on_delete=models.SET_NULL, null=True, blank=True, related_name='images'
    )
    focal_length = models.DecimalField(
        max_digits=7, decimal_places=1, null=True, blank=True,
        help_text="Focal length in mm"
    )
    aperture = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True,
        help_text="f-number"
    )
    shutter_speed = models.CharField(
        max_length=20, blank=True, help_text="e.g. 1/250, 2.5\""
    )
    iso = models.PositiveIntegerField(null=True, blank=True)
    date_taken = models.DateTimeField(null=True, blank=True, db_index=True)
    gps_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    gps_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'EXIF data'
        verbose_name_plural = 'EXIF data'
        indexes = [
            models.Index(fields=['camera', 'date_taken']),
            models.Index(fields=['lens', 'date_taken']),
            models.Index(fields=['focal_length']),
            models.Index(fields=['aperture']),
            models.Index(fields=['iso']),
        ]

    def __str__(self) -> str:
        return f"EXIF for {self.image}"
