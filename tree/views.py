from django.db.models import Count
from django.shortcuts import get_object_or_404, render

from collections import OrderedDict

from core.models import Camera, City, Image, Lens, Tag

import random

PAGE_SIZE = 48


def _paginate_shuffled(request, qs):
    """Paginate with a stable random shuffle per session."""
    page = int(request.GET.get('page', 1))

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

    images = list(
        qs.model.objects.filter(id__in=page_ids)
        .select_related('user', 'exif', 'exif__camera', 'exif__lens')
    )
    id_order = {uid: i for i, uid in enumerate(page_ids)}
    images.sort(key=lambda img: id_order[img.id])

    return images, page, has_more


def camera_list(request):
    brand = request.GET.get('brand', '')
    q = request.GET.get('q', '')
    cameras = Camera.objects.annotate(
        image_count=Count('images')
    ).filter(image_count__gte=5).order_by('manufacturer', 'model')

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


def camera_list_all(request):
    cameras = Camera.objects.annotate(
        image_count=Count('images')
    ).filter(image_count__gt=0).order_by('manufacturer', 'model')
    brands = list(cameras.values_list('manufacturer', flat=True).distinct().order_by('manufacturer'))
    return render(request, 'tree/camera_list.html', {
        'cameras': cameras, 'brands': brands, 'selected_brand': '', 'query': '', 'show_all': True,
    })


def camera_detail(request, slug):
    camera = get_object_or_404(Camera, slug=slug)
    qs = (
        Image.objects.filter(
            exif__camera=camera, visibility=Image.Visibility.PUBLIC, is_processing=False,
        )
        .select_related('user', 'exif', 'exif__camera', 'exif__lens')
        .order_by('-upload_date')
    )
    images, page, has_more = _paginate_shuffled(request, qs)

    if request.headers.get('HX-Request'):
        return render(request, 'includes/image_grid_page.html', {
            'images': images, 'page': page, 'has_more': has_more,
        })
    return render(request, 'tree/camera_detail.html', {
        'camera': camera, 'images': images, 'page': page, 'has_more': has_more,
    })


def lens_list(request):
    brand = request.GET.get('brand', '')
    q = request.GET.get('q', '')
    lenses = Lens.objects.annotate(
        image_count=Count('images')
    ).filter(image_count__gte=5).order_by('manufacturer', 'model')

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


def lens_list_all(request):
    lenses = Lens.objects.annotate(
        image_count=Count('images')
    ).filter(image_count__gt=0).order_by('manufacturer', 'model')
    brands = list(lenses.values_list('manufacturer', flat=True).distinct().order_by('manufacturer'))
    return render(request, 'tree/lens_list.html', {
        'lenses': lenses, 'brands': brands, 'selected_brand': '', 'query': '', 'show_all': True,
    })


def tag_cloud(request):
    import math
    import random

    tags = list(
        Tag.objects.annotate(image_count=Count('images'))
        .filter(image_count__gte=5)
        .order_by('-image_count')
    )

    if tags:
        max_count = tags[0].image_count
        min_count = tags[-1].image_count
        count_range = max(max_count - min_count, 1)

        min_size = 0.75   # rem
        max_size = 2.8    # rem

        for tag in tags:
            # Log scale feels more natural for word clouds
            if count_range > 1:
                weight = math.log(tag.image_count - min_count + 1) / math.log(count_range + 1)
            else:
                weight = 0.5
            tag.font_size = round(min_size + weight * (max_size - min_size), 2)

        # Shuffle so it doesn't just go big→small
        random.shuffle(tags)

    return render(request, 'tree/tag_cloud.html', {'tags': tags})


def tag_detail(request, slug):
    tag = get_object_or_404(Tag, slug=slug)
    qs = (
        Image.objects.filter(
            tags=tag, visibility=Image.Visibility.PUBLIC, is_processing=False,
        )
        .select_related('user', 'exif', 'exif__camera', 'exif__lens')
        .order_by('-upload_date')
    )
    images, page, has_more = _paginate_shuffled(request, qs)

    if request.headers.get('HX-Request'):
        return render(request, 'includes/image_grid_page.html', {
            'images': images, 'page': page, 'has_more': has_more,
        })
    return render(request, 'tree/tag_detail.html', {
        'tag': tag, 'images': images, 'page': page, 'has_more': has_more,
    })


def city_list(request):
    cities = (
        City.objects.annotate(image_count=Count('images'))
        .filter(image_count__gte=5)
        .order_by('continent', 'country', 'region', 'name')
    )

    # Group by continent > country > (state for US)
    grouped = OrderedDict()
    us_states = OrderedDict()

    for city in cities:
        if city.continent not in grouped:
            grouped[city.continent] = OrderedDict()

        if city.country_code == 'US':
            state = city.region or 'Other'
            if state not in us_states:
                us_states[state] = []
            us_states[state].append(city)
        else:
            if city.country not in grouped[city.continent]:
                grouped[city.continent][city.country] = []
            grouped[city.continent][city.country].append(city)

    # All cities for the map (no minimum)
    all_cities = (
        City.objects.annotate(image_count=Count('images'))
        .filter(image_count__gt=0)
    )

    return render(request, 'tree/city_list.html', {
        'grouped': grouped,
        'us_states': us_states,
        'all_cities': all_cities,
    })


def city_detail(request, slug):
    city = get_object_or_404(City, slug=slug)
    qs = (
        Image.objects.filter(
            city=city, visibility=Image.Visibility.PUBLIC, is_processing=False,
        )
        .select_related('user', 'exif', 'exif__camera', 'exif__lens')
    )
    images, page, has_more = _paginate_shuffled(request, qs)

    if request.headers.get('HX-Request'):
        return render(request, 'includes/image_grid_page.html', {
            'images': images, 'page': page, 'has_more': has_more,
        })
    return render(request, 'tree/city_detail.html', {
        'city': city, 'images': images, 'page': page, 'has_more': has_more,
    })


def lens_detail(request, slug):
    lens = get_object_or_404(Lens, slug=slug)
    qs = (
        Image.objects.filter(
            exif__lens=lens, visibility=Image.Visibility.PUBLIC, is_processing=False,
        )
        .select_related('user', 'exif', 'exif__camera', 'exif__lens')
        .order_by('-upload_date')
    )
    images, page, has_more = _paginate_shuffled(request, qs)

    if request.headers.get('HX-Request'):
        return render(request, 'includes/image_grid_page.html', {
            'images': images, 'page': page, 'has_more': has_more,
        })
    return render(request, 'tree/lens_detail.html', {
        'lens': lens, 'images': images, 'page': page, 'has_more': has_more,
    })
