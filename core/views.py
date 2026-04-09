import random

from django.db.models import Count
from django.db.models.functions import ExtractYear
from django.shortcuts import get_object_or_404, render

from core.models import ExifData, Image

PAGE_SIZE = 48


def home(request):
    year = request.GET.get('year')
    page = int(request.GET.get('page', 1))

    qs = Image.objects.filter(
        visibility=Image.Visibility.PUBLIC, is_processing=False,
    )

    if year:
        qs = qs.filter(exif__date_taken__year=year)

    # Shuffle with a stable seed per session
    seed = request.session.get('shuffle_seed')
    if not seed or request.GET.get('reshuffle'):
        seed = random.randint(0, 2**31)
        request.session['shuffle_seed'] = seed

    all_ids = list(qs.values_list('id', flat=True))
    rng = random.Random(seed)
    rng.shuffle(all_ids)

    start = (page - 1) * PAGE_SIZE
    page_ids = all_ids[start:start + PAGE_SIZE]
    has_more = start + PAGE_SIZE < len(all_ids)

    images = (
        Image.objects.filter(id__in=page_ids)
        .select_related('user', 'exif', 'exif__camera', 'exif__lens')
    )
    id_order = {uid: i for i, uid in enumerate(page_ids)}
    images = sorted(images, key=lambda img: id_order[img.id])

    years = (
        ExifData.objects.filter(date_taken__isnull=False)
        .annotate(year=ExtractYear('date_taken'))
        .values_list('year', flat=True)
        .distinct()
        .order_by('-year')
    )

    if request.headers.get('HX-Request'):
        return render(request, 'includes/image_grid_page.html', {
            'images': images,
            'page': page,
            'has_more': has_more,
            'selected_year': year,
        })

    return render(request, 'home.html', {
        'images': images,
        'years': list(years),
        'selected_year': year,
        'page': page,
        'has_more': has_more,
        'total_count': len(all_ids),
    })


def image_detail(request, image_id):
    image = get_object_or_404(
        Image.objects.select_related('user', 'exif', 'exif__camera', 'exif__lens'),
        id=image_id, visibility=Image.Visibility.PUBLIC,
    )
    from django.db import models as m
    Image.objects.filter(id=image_id).update(view_count=m.F('view_count') + 1)
    image.view_count += 1

    # Prev/next navigation
    base_qs = Image.objects.filter(
        visibility=Image.Visibility.PUBLIC, is_processing=False,
    ).order_by('-upload_date')
    prev_image = base_qs.filter(upload_date__gt=image.upload_date).order_by('upload_date').first()
    next_image = base_qs.filter(upload_date__lt=image.upload_date).first()

    return render(request, 'image_detail.html', {
        'image': image,
        'prev_image': prev_image,
        'next_image': next_image,
    })
