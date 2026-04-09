import json
import random

from django.db.models import Count
from django.db.models.functions import ExtractYear
from django.http import JsonResponse
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


def oembed(request):
    """oEmbed endpoint — returns rich embed data for image URLs."""
    url = request.GET.get('url', '')
    maxwidth = int(request.GET.get('maxwidth', 800))
    maxheight = int(request.GET.get('maxheight', 600))
    fmt = request.GET.get('format', 'json')

    import re
    from core.models import SiteConfig
    config = SiteConfig.load()

    # Homepage embed — grid of random photos
    # Collection embed
    col_match = re.search(r'/collections/([^/]+)/', url)
    if col_match:
        from gallery.models import Collection
        col = Collection.objects.filter(slug=col_match.group(1)).first()
        if not col:
            return JsonResponse({'error': 'Not found'}, status=404)

        photos = list(
            Image.objects.filter(
                collection_entries__collection=col, is_processing=False,
            ).exclude(thumbnail_small='')[:45]
        )
        grid_html = f'<div style="max-width:500px;"><p><strong>{col.title}</strong></p>'
        grid_html += '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:4px;max-width:500px;">'
        for img in photos:
            thumb = img.thumbnail_small or img.thumbnail_medium
            if thumb:
                grid_html += f'<a href="https://photos.kennethreitz.org/images/{img.id}/"><img src="{thumb.url}" style="width:100%;aspect-ratio:1;object-fit:cover;border-radius:4px;"></a>'
        grid_html += '</div>'
        grid_html += f'<p style="text-align:center;margin-top:8px;"><a href="https://photos.kennethreitz.org/collections/{col.slug}/" style="color:#888;">See more at photos.kennethreitz.org</a></p></div>'

        return JsonResponse({
            'version': '1.0',
            'type': 'rich',
            'title': col.title,
            'author_name': config.site_title,
            'author_url': 'https://photos.kennethreitz.org',
            'provider_name': config.site_title,
            'provider_url': 'https://photos.kennethreitz.org',
            'html': grid_html,
            'width': min(maxwidth, 800),
            'height': min(maxheight, 400),
        })

    # Image embed
    match = re.search(r'/images/([0-9a-f-]+)/', url)
    if not match:
        # Assume homepage or non-image URL — return a photo grid
        photos = list(
            Image.objects.filter(visibility='public', is_processing=False)
            .exclude(thumbnail_small='')
            .order_by('?')[:45]
        )
        if not photos:
            return JsonResponse({'error': 'No photos'}, status=404)

        grid_html = '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:4px;max-width:500px;">'
        for img in photos:
            thumb = img.thumbnail_small or img.thumbnail_medium
            if thumb:
                grid_html += f'<a href="https://photos.kennethreitz.org/images/{img.id}/"><img src="{thumb.url}" style="width:100%;aspect-ratio:1;object-fit:cover;border-radius:4px;"></a>'
        grid_html += '</div>'
        grid_html += f'<p style="text-align:center;margin-top:8px;"><a href="https://photos.kennethreitz.org" style="color:#888;">See more at photos.kennethreitz.org</a></p>'

        return JsonResponse({
            'version': '1.0',
            'type': 'rich',
            'title': config.site_title,
            'author_name': config.site_title,
            'author_url': 'https://photos.kennethreitz.org',
            'provider_name': config.site_title,
            'provider_url': 'https://photos.kennethreitz.org',
            'html': grid_html,
            'width': min(maxwidth, 800),
            'height': min(maxheight, 400),
        })

    image = Image.objects.filter(
        id=match.group(1), visibility=Image.Visibility.PUBLIC,
    ).select_related('exif', 'exif__camera', 'exif__lens').first()

    if not image:
        return JsonResponse({'error': 'Not found'}, status=404)

    thumb = image.thumbnail_large or image.thumbnail_medium or image.thumbnail_small
    title = image.ai_title or image.title or 'Photograph'

    # Build EXIF summary
    exif_parts = []
    if image.exif:
        if image.exif.camera:
            exif_parts.append(image.exif.camera.display_name)
        if image.exif.lens:
            exif_parts.append(image.exif.lens.display_name)
        if image.exif.focal_length:
            exif_parts.append(f"{image.exif.focal_length}mm")
        if image.exif.aperture:
            exif_parts.append(f"f/{image.exif.aperture}")
        if image.exif.iso:
            exif_parts.append(f"ISO {image.exif.iso}")
    exif_line = ' · '.join(exif_parts)

    data = {
        'version': '1.0',
        'type': 'photo',
        'title': title,
        'author_name': config.site_title,
        'author_url': 'https://photos.kennethreitz.org',
        'provider_name': config.site_title,
        'provider_url': 'https://photos.kennethreitz.org',
        'url': thumb.url if thumb else '',
        'width': min(maxwidth, 1600),
        'height': min(maxheight, 1200),
    }

    # Add rich HTML for consumers that support it
    description = image.ai_description or ''
    html_parts = [f'<div style="max-width:500px;"><img src="{thumb.url}" alt="{title}" style="max-width:100%;border-radius:4px;">']
    if title:
        html_parts.append(f'<p><strong>{title}</strong></p>')
    if description:
        html_parts.append(f'<p>{description}</p>')
    if exif_line:
        html_parts.append(f'<p style="color:#888;font-size:0.85em;">{exif_line}</p>')
    html_parts.append(f'<p style="text-align:center;margin-top:4px;"><a href="https://photos.kennethreitz.org/images/{image.id}/" style="color:#888;">See more at photos.kennethreitz.org</a></p></div>')

    data['html'] = '\n'.join(html_parts)
    data['type'] = 'rich'

    return JsonResponse(data)


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
