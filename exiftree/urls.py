from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps import Sitemap
from django.contrib.sitemaps.views import sitemap
from django.http import HttpResponse
from django.urls import include, path
from django.views.generic import TemplateView

from core.views import embed, home, image_detail, oembed


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
        return ['/', '/cameras/', '/lenses/', '/tags/', '/cities/', '/years/', '/search/']

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


class YearSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.7

    def items(self):
        from core.models import ExifData
        from django.db.models.functions import ExtractYear
        return (
            ExifData.objects.filter(date_taken__isnull=False)
            .annotate(year=ExtractYear('date_taken'))
            .values_list('year', flat=True)
            .distinct()
            .order_by('-year')
        )

    def location(self, year):
        return f'/years/{year}/'


sitemaps = {
    'static': StaticSitemap,
    'images': ImageSitemap,
    'cameras': CameraSitemap,
    'lenses': LensSitemap,
    'tags': TagSitemap,
    'cities': CitySitemap,
    'years': YearSitemap,
}

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sitemap.xml", sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path("robots.txt", TemplateView.as_view(template_name='robots.txt', content_type='text/plain')),
    path("health", lambda r: HttpResponse("ok")),
    path("favicon.ico", lambda r: HttpResponse(status=204)),
    path("apple-touch-icon.png", lambda r: HttpResponse(status=204)),
    path("apple-touch-icon-precomposed.png", lambda r: HttpResponse(status=204)),
    path("", home, name="home"),
    path("oembed", oembed, name="oembed"),
    path("embed/", embed, name="embed"),
    path("images/<uuid:image_id>/", image_detail, name="image-detail"),
    path("", include("tree.urls")),
    path("", include("gallery.urls")),
    path("", include("search.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
