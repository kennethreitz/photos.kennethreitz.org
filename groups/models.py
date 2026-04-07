import uuid

from django.db import models

from core.models import Image, User


class Group(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = 'public', "Public"
        PRIVATE = 'private', "Private"
        INVITE_ONLY = 'invite_only', "Invite Only"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    cover_image = models.ImageField(upload_to='groups/covers/', blank=True)
    visibility = models.CharField(
        max_length=12, choices=Visibility.choices, default=Visibility.PUBLIC
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.name


class GroupMembership(models.Model):
    class Role(models.TextChoices):
        MEMBER = 'member', "Member"
        MODERATOR = 'moderator', "Moderator"
        ADMIN = 'admin', "Admin"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_memberships')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.MEMBER
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'group')]

    def __str__(self) -> str:
        return f"{self.user} in {self.group} ({self.role})"


class GroupImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.ForeignKey(Image, on_delete=models.CASCADE, related_name='group_entries')
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='group_images')
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('image', 'group')]
        ordering = ['-submitted_at']

    def __str__(self) -> str:
        return f"{self.image} in {self.group}"
