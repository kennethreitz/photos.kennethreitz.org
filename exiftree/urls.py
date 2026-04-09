from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.http import HttpResponse
from django.views.generic import TemplateView

from core.views import (
    dashboard,
    dashboard_create_collection,
    dashboard_delete_collection,
    dashboard_delete_image,
    flickr_import,
    home,
    image_detail,
    manage,
    manage_add_to_collection,
    manage_delete_images,
    manage_set_visibility,
)

class ImageSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.8

    def items(self):
        from core.models import Image
        return Image.objects.filter(
            visibility='public', is_processing=False,
        ).order_by('-upload_date')[:5000]

    def location(self, obj):
        return f'/images/{obj.id}/'

    def lastmod(self, obj):
        return obj.updated_at


class StaticSitemap(Sitemap):
    changefreq = 'daily'
    priority = 1.0

    def items(self):
        return ['/', '/cameras/', '/lenses/', '/tags/', '/cities/', '/search/']

    def location(self, item):
        return item


class CameraSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.7

    def items(self):
        from core.models import Camera
        return Camera.objects.all()

    def location(self, obj):
        return f'/cameras/{obj.slug}/'


class LensSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.7

    def items(self):
        from core.models import Lens
        return Lens.objects.all()

    def location(self, obj):
        return f'/lenses/{obj.slug}/'


class TagSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.5

    def items(self):
        from core.models import Tag
        from django.db.models import Count
        return Tag.objects.annotate(c=Count('images')).filter(c__gte=5).order_by('-c')[:500]

    def location(self, obj):
        return f'/tags/{obj.slug}/'


class CitySitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        from core.models import City
        from django.db.models import Count
        return City.objects.annotate(c=Count('images')).filter(c__gte=5)

    def location(self, obj):
        return f'/cities/{obj.slug}/'


sitemaps = {
    'static': StaticSitemap,
    'images': ImageSitemap,
    'cameras': CameraSitemap,
    'lenses': LensSitemap,
    'tags': TagSitemap,
    'cities': CitySitemap,
}

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sitemap.xml", sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path("robots.txt", TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
    path("favicon.ico", lambda r: HttpResponse(status=204)),
    path("apple-touch-icon.png", lambda r: HttpResponse(status=204)),
    path("apple-touch-icon-precomposed.png", lambda r: HttpResponse(status=204)),
    path("", home, name="home"),
    path("login/", LoginView.as_view(template_name='registration/login.html'), name="login"),
    path("logout/", LogoutView.as_view(next_page='/'), name="logout"),
    path("dashboard/", dashboard, name="dashboard"),
    path("dashboard/collections/create/", dashboard_create_collection, name="dashboard-create-collection"),
    path("dashboard/collections/<uuid:collection_id>/delete/", dashboard_delete_collection, name="dashboard-delete-collection"),
    path("dashboard/images/<uuid:image_id>/delete/", dashboard_delete_image, name="dashboard-delete-image"),
    path("manage/", manage, name="manage"),
    path("manage/visibility/", manage_set_visibility, name="manage-set-visibility"),
    path("manage/delete/", manage_delete_images, name="manage-delete-images"),
    path("manage/add-to-collection/", manage_add_to_collection, name="manage-add-to-collection"),
    path("import/flickr/", flickr_import, name="flickr-import"),
    path("images/<uuid:image_id>/", image_detail, name="image-detail"),
    path("", include("tree.urls")),
    path("", include("gallery.urls")),
    path("", include("ingest.urls")),
    path("", include("search.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
