from django.urls import path

from client import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('favourite/', views.favourite, name='favourite'),
    path('favourite2/', views.favourite2, name='favourite2'),
    path('match/', views.matches_view, name='matches'),
    path('api/toggle-favorite/', views.toggle_favorite, name='toggle-favorite'),
    path('feed/', views.feed_view, name='feed'),
    path('favorites/', views.favorites_view, name='favorites'),
    path('news/', views.news_view, name='news'),
    path('get_started/', views.getStarted, name='getStarted'),
]
