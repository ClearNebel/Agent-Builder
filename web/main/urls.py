from django.urls import path
from . import views

urlpatterns = [
    path('', views.default_redirect, name='default_redirect'),
]