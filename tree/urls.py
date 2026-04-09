from django.urls import path

from tree import views

app_name = 'tree'

urlpatterns = [
    path('cameras/', views.camera_list, name='camera-list'),
    path('cameras/all/', views.camera_list_all, name='camera-list-all'),
    path('cameras/<slug:slug>/', views.camera_detail, name='camera-detail'),
    path('lenses/', views.lens_list, name='lens-list'),
    path('lenses/all/', views.lens_list_all, name='lens-list-all'),
    path('lenses/<slug:slug>/', views.lens_detail, name='lens-detail'),
    path('tags/', views.tag_cloud, name='tag-cloud'),
    path('tags/<slug:slug>/', views.tag_detail, name='tag-detail'),
    path('cities/', views.city_list, name='city-list'),
    path('cities/<slug:slug>/', views.city_detail, name='city-detail'),
]
