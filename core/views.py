from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import ExtractYear
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from core.models import ExifData, Image
from gallery.models import Collection


def home(request):
    year = request.GET.get('year')
    qs = Image.objects.filter(
        visibility=Image.Visibility.PUBLIC, is_processing=False,
    ).select_related('user', 'exif', 'exif__camera', 'exif__lens')

    if year:
        qs = qs.filter(exif__date_taken__year=year)

    import random
    ids = list(qs.values_list('id', flat=True))
    if len(ids) > 48:
        ids = random.sample(ids, 48)
    images = qs.filter(id__in=ids)

    years = (
        ExifData.objects.filter(date_taken__isnull=False)
        .annotate(year=ExtractYear('date_taken'))
        .values_list('year', flat=True)
        .distinct()
        .order_by('-year')
    )

    return render(request, 'home.html', {
        'images': images,
        'years': list(years),
        'selected_year': year,
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


@login_required
def dashboard(request):
    user = request.user
    images = (
        Image.objects.filter(user=user, is_processing=False)
        .select_related('exif', 'exif__camera', 'exif__lens')
        .order_by('-upload_date')
    )
    collections = (
        Collection.objects.filter(user=user)
        .annotate(image_count=Count('collection_images'))
        .order_by('-created_at')
    )
    return render(request, 'dashboard.html', {
        'images': images,
        'collections': collections,
    })


@login_required
@require_POST
def dashboard_create_collection(request):
    title = request.POST.get('title', '').strip()
    if title:
        import uuid
        base_slug = slugify(title) or 'collection'
        slug = base_slug
        while Collection.objects.filter(user=request.user, slug=slug).exists():
            slug = f"{base_slug}-{str(uuid.uuid4())[:8]}"
        Collection.objects.create(
            user=request.user,
            title=title,
            slug=slug,
            description=request.POST.get('description', ''),
        )
    return redirect('dashboard')


@login_required
@require_POST
def dashboard_delete_collection(request, collection_id):
    Collection.objects.filter(id=collection_id, user=request.user).delete()
    return redirect('dashboard')


@login_required
@require_POST
def dashboard_delete_image(request, image_id):
    Image.objects.filter(id=image_id, user=request.user).delete()
    next_url = request.GET.get('next') or request.POST.get('next', '')
    if next_url and next_url.startswith('/'):
        return redirect(next_url)
    return redirect('dashboard')


@login_required
def manage(request):
    from core.models import Camera, Lens

    qs = (
        Image.objects.filter(user=request.user, is_processing=False)
        .select_related('exif', 'exif__camera', 'exif__lens')
        .order_by('-upload_date')
    )

    # Filters
    camera = request.GET.get('camera', '')
    lens = request.GET.get('lens', '')
    year = request.GET.get('year', '')
    visibility = request.GET.get('visibility', '')

    if camera:
        qs = qs.filter(exif__camera_id=camera)
    if lens:
        qs = qs.filter(exif__lens_id=lens)
    if year:
        qs = qs.filter(exif__date_taken__year=int(year))
    if visibility:
        qs = qs.filter(visibility=visibility)

    # Facets: only cameras/lenses/years the user actually has
    user_images = Image.objects.filter(user=request.user, is_processing=False)
    cameras = (
        Camera.objects.filter(images__image__in=user_images)
        .distinct().order_by('manufacturer', 'model')
    )
    lenses = (
        Lens.objects.filter(images__image__in=user_images)
        .distinct().order_by('manufacturer', 'model')
    )
    years = (
        ExifData.objects.filter(image__in=user_images, date_taken__isnull=False)
        .dates('date_taken', 'year', order='DESC')
    )

    collections = (
        Collection.objects.filter(user=request.user)
        .annotate(image_count=Count('collection_images'))
        .order_by('-created_at')
    )

    return render(request, 'manage.html', {
        'images': qs,
        'collections': collections,
        'cameras': cameras,
        'lenses': lenses,
        'years': years,
        'filter_camera': camera,
        'filter_lens': lens,
        'filter_year': year,
        'filter_visibility': visibility,
    })


@login_required
@require_POST
def manage_set_visibility(request):
    image_ids = [x for x in request.POST.getlist('image_ids') if x.strip()]
    visibility = request.POST.get('visibility', 'public')
    if visibility in ('public', 'private', 'unlisted') and image_ids:
        Image.objects.filter(id__in=image_ids, user=request.user).update(visibility=visibility)
    return redirect('manage')


@login_required
@require_POST
def manage_delete_images(request):
    image_ids = [x for x in request.POST.getlist('image_ids') if x.strip()]
    if image_ids:
        Image.objects.filter(id__in=image_ids, user=request.user).delete()
    return redirect('manage')


@login_required
@require_POST
def manage_add_to_collection(request):
    import uuid as _uuid
    from gallery.models import CollectionImage

    image_ids = [x for x in request.POST.getlist('image_ids') if x.strip()]
    collection_id = request.POST.get('collection_id', '').strip()
    new_collection_name = request.POST.get('new_collection', '').strip()

    # Create new collection if requested
    if new_collection_name and not collection_id:
        base_slug = slugify(new_collection_name) or 'collection'
        slug = base_slug
        while Collection.objects.filter(user=request.user, slug=slug).exists():
            slug = f"{base_slug}-{str(_uuid.uuid4())[:8]}"
        col = Collection.objects.create(
            user=request.user, title=new_collection_name, slug=slug,
        )
        collection_id = str(col.id)

    if image_ids and collection_id:
        collection = Collection.objects.filter(id=collection_id, user=request.user).first()
        if collection:
            existing = set(
                CollectionImage.objects.filter(collection=collection, image_id__in=image_ids)
                .values_list('image_id', flat=True)
            )
            count = CollectionImage.objects.filter(collection=collection).count()
            new_entries = []
            for img_id in image_ids:
                parsed = _uuid.UUID(img_id)
                if parsed not in existing:
                    new_entries.append(CollectionImage(
                        collection=collection, image_id=parsed, sort_order=count,
                    ))
                    count += 1
            if new_entries:
                CollectionImage.objects.bulk_create(new_entries)
    return redirect('manage')


@login_required
def flickr_import(request):
    return render(request, 'flickr_import.html')
