from django.shortcuts import get_object_or_404, render

from core.models import Camera, Lens


def camera_list(request):
    return render(request, 'tree/camera_list.html')


def camera_manufacturer(request, manufacturer):
    cameras = Camera.objects.filter(slug__startswith=manufacturer)
    manufacturer_name = cameras.first().manufacturer if cameras.exists() else manufacturer
    return render(request, 'tree/camera_manufacturer.html', {
        'manufacturer': manufacturer_name,
        'cameras': cameras,
    })


def camera_detail(request, manufacturer, model):
    # Try combined slug first, then model-only
    camera = (
        Camera.objects.filter(slug=f"{manufacturer}-{model}").first()
        or Camera.objects.filter(slug=model).first()
    )
    if not camera:
        from django.http import Http404
        raise Http404("No Camera matches the given query.")
    return render(request, 'tree/camera_detail.html', {'camera': camera})


def lens_list(request):
    return render(request, 'tree/lens_list.html')


def lens_detail(request, manufacturer, model):
    lens = (
        Lens.objects.filter(slug=model).first()
        or Lens.objects.filter(slug=f"{manufacturer}-{model}").first()
    )
    if not lens:
        from django.http import Http404
        raise Http404("No Lens matches the given query.")
    return render(request, 'tree/lens_detail.html', {'lens': lens})
