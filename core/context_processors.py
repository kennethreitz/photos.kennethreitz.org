import hashlib
from pathlib import Path

from django.conf import settings

from core.models import SiteConfig
from gallery.models import Collection

_cache_bust = None


def _get_cache_bust() -> str:
    global _cache_bust
    if _cache_bust is None or settings.DEBUG:
        css = Path(settings.STATICFILES_DIRS[0]) / 'css' / 'style.css'
        if css.exists():
            _cache_bust = hashlib.md5(css.read_bytes()).hexdigest()[:8]
        else:
            _cache_bust = '0'
    return _cache_bust


def site_context(request):
    config = SiteConfig.load()
    return {
        'site_title': config.site_title,
        'site_tagline': config.tagline,
        'analytics_code': config.analytics_code,
        'has_collections': Collection.objects.exists(),
        'cache_bust': _get_cache_bust(),
    }
