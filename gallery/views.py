from django.db.models import Count
from django.shortcuts import get_object_or_404, render

from core.models import Image, User
from gallery.models import Collection


def profile(request, username):
    user = get_object_or_404(User, username=username)
    images = (
        Image.objects.filter(user=user, visibility=Image.Visibility.PUBLIC, is_processing=False)
        .select_related('exif', 'exif__camera', 'exif__lens')
        .order_by('-upload_date')
    )
    collections = (
        Collection.objects.filter(user=user, visibility=Image.Visibility.PUBLIC)
        .annotate(image_count=Count('collection_images'))
        .order_by('-created_at')
    )
    return render(request, 'gallery/profile.html', {
        'profile_user': user,
        'images': images,
        'collections': collections,
    })


def collection_list(request, username):
    user = get_object_or_404(User, username=username)
    return render(request, 'gallery/collection_list.html', {'profile_user': user})


def collection_detail(request, username, slug):
    user = get_object_or_404(User, username=username)
    collection = get_object_or_404(Collection, user=user, slug=slug)
    images = (
        Image.objects.filter(
            collection_entries__collection=collection, is_processing=False
        )
        .select_related('exif', 'exif__camera', 'exif__lens')
        .order_by('collection_entries__sort_order')
    )
    return render(request, 'gallery/collection_detail.html', {
        'profile_user': user,
        'collection': collection,
        'images': images,
    })
