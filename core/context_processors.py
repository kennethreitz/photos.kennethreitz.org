from django.conf import settings


def site_context(request):
    return {
        'SINGLE_TENANT': settings.SINGLE_TENANT,
    }
