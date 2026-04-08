from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from core.models import Camera, ExifData, Image, Lens, SiteConfig, Tag, User


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ['site_title', 'tagline']
    fieldsets = [
        ("Site", {'fields': ('site_title', 'tagline', 'analytics_code')}),
        ("AI", {'fields': ('openai_api_key', 'ai_prompt')}),
    ]

    def has_add_permission(self, request):
        return not SiteConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'date_joined', 'is_staff']
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Profile", {'fields': ('bio', 'avatar', 'website')}),
    )


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'manufacturer', 'model', 'slug']
    list_filter = ['manufacturer']
    search_fields = ['manufacturer', 'model', 'display_name']
    prepopulated_fields = {'slug': ('manufacturer', 'model')}


@admin.register(Lens)
class LensAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'manufacturer', 'model', 'max_aperture', 'slug']
    list_filter = ['manufacturer']
    search_fields = ['manufacturer', 'model', 'display_name']
    prepopulated_fields = {'slug': ('manufacturer', 'model')}


class ExifDataInline(admin.StackedInline):
    model = ExifData
    extra = 0
    readonly_fields = ['raw_data']


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'visibility', 'is_processing', 'upload_date']
    list_filter = ['visibility', 'is_processing']
    search_fields = ['title', 'description', 'user__username']
    inlines = [ExifDataInline]


@admin.register(ExifData)
class ExifDataAdmin(admin.ModelAdmin):
    list_display = ['image', 'camera', 'lens', 'focal_length', 'aperture', 'iso', 'date_taken']
    list_filter = ['camera', 'lens']
    search_fields = ['image__title', 'camera__display_name', 'lens__display_name']
