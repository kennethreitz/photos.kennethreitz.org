from django.db.models import Count
from django.shortcuts import get_object_or_404, render

from core.models import Camera, Image, Lens


def camera_list(request):
    brand = request.GET.get('brand', '')
    q = request.GET.get('q', '')
    cameras = Camera.objects.annotate(
        image_count=Count('images')
    ).filter(image_count__gt=0).order_by('manufacturer', 'model')

    brands = list(cameras.values_list('manufacturer', flat=True).distinct().order_by('manufacturer'))

    if brand:
        cameras = cameras.filter(manufacturer=brand)
    if q:
        cameras = cameras.filter(display_name__icontains=q)

    return render(request, 'tree/camera_list.html', {
        'cameras': cameras,
        'brands': brands,
        'selected_brand': brand,
        'query': q,
    })


def camera_detail(request, slug):
    camera = get_object_or_404(Camera, slug=slug)
    images = (
        Image.objects.filter(
            exif__camera=camera, visibility=Image.Visibility.PUBLIC, is_processing=False,
        )
        .select_related('user', 'exif', 'exif__camera', 'exif__lens')
        .order_by('-upload_date')[:50]
    )
    return render(request, 'tree/camera_detail.html', {'camera': camera, 'images': images})


def lens_list(request):
    brand = request.GET.get('brand', '')
    q = request.GET.get('q', '')
    lenses = Lens.objects.annotate(
        image_count=Count('images')
    ).filter(image_count__gt=0).order_by('manufacturer', 'model')

    brands = list(lenses.values_list('manufacturer', flat=True).distinct().order_by('manufacturer'))

    if brand:
        lenses = lenses.filter(manufacturer=brand)
    if q:
        lenses = lenses.filter(display_name__icontains=q)

    return render(request, 'tree/lens_list.html', {
        'lenses': lenses,
        'brands': brands,
        'selected_brand': brand,
        'query': q,
    })


def lens_detail(request, slug):
    lens = get_object_or_404(Lens, slug=slug)
    images = (
        Image.objects.filter(
            exif__lens=lens, visibility=Image.Visibility.PUBLIC, is_processing=False,
        )
        .select_related('user', 'exif', 'exif__camera', 'exif__lens')
        .order_by('-upload_date')[:50]
    )
    return render(request, 'tree/lens_detail.html', {'lens': lens, 'images': images})
