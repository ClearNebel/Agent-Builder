from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

# It's good practice to set an app_name for namespacing
app_name = 'accounts'

urlpatterns = [
    #path('register/', views.register_view, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path(
        'password_change/', 
        auth_views.PasswordChangeView.as_view(
            template_name='accounts/password_change_form.html',
            success_url='/accounts/password_change/done/'
        ), 
        name='password_change'
    ),
    path(
        'password_change/done/', 
        auth_views.PasswordChangeDoneView.as_view(
            template_name='accounts/password_change_done.html'
        ), 
        name='password_change_done'
    ),
]