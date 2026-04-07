import uuid

from django.db import models

from core.models import Image, User


class Collection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='collections')
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    cover_image = models.ForeignKey(
        Image, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+'
    )
    visibility = models.CharField(
        max_length=10,
        choices=Image.Visibility.choices,
        default=Image.Visibility.PUBLIC,
    )
    images = models.ManyToManyField(
        Image, through='CollectionImage', related_name='collections'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('user', 'slug')]

    def __str__(self) -> str:
        return self.title


class CollectionImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(
        Collection, on_delete=models.CASCADE, related_name='collection_images'
    )
    image = models.ForeignKey(
        Image, on_delete=models.CASCADE, related_name='collection_entries'
    )
    sort_order = models.PositiveIntegerField(default=0)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['sort_order']
        unique_together = [('collection', 'image')]

    def __str__(self) -> str:
        return f"{self.collection} — {self.image}"
