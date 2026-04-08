from django.db.models import Count
from django.db.models.functions import ExtractYear
from django.shortcuts import get_object_or_404, render

from core.models import Camera, ExifData, Image, Lens, User
from gallery.models import Collection


def home(request):
    year = request.GET.get('year')
    qs = Image.objects.filter(
        visibility=Image.Visibility.PUBLIC, is_processing=False,
    ).select_related('user', 'exif', 'exif__camera', 'exif__lens')

    if year:
        qs = qs.filter(exif__date_taken__year=year)

    images = qs.order_by('?')[:48]

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
    # Increment view count
    from django.db import models as m
    Image.objects.filter(id=image_id).update(view_count=m.F('view_count') + 1)
    image.view_count += 1

    return render(request, 'image_detail.html', {'image': image})


def dashboard(request):
    return render(request, 'dashboard.html')


def users_list(request):
    q = request.GET.get('q', '')
    users = User.objects.order_by('-created_at')
    if q:
        users = users.filter(username__icontains=q)
    users = users[:50]
    return render(request, 'users.html', {'users': users, 'query': q})


def register_view(request):
    return render(request, 'registration/register.html')


def login_view(request):
    return render(request, 'registration/login.html')
