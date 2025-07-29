from django.urls import path
from . import views

app_name = 'admin_panel'

urlpatterns = [
    path('', views.user_list_view, name='user_list'),
    path('user/<int:user_id>/', views.manage_user_permissions_view, name='manage_user_permissions'),
    path('user/create/', views.create_user_view, name='create_user'),
    path('agents/', views.agent_list_view, name='agent_list'),
    path('agents/<str:agent_name>/', views.agent_details_view, name='agent_details'),
    path('analytics/', views.analytics_dashboard_view, name='analytics_dashboard'),
    path('curation/', views.curation_dashboard_view, name='curation_dashboard'),
    path('curation/review/<uuid:message_id>/', views.review_rejected_message_view, name='review_rejected_message'),
    path('datasets/', views.dataset_list_view, name='dataset_list'),
    path('datasets/<str:agent_name>/', views.manage_sft_dataset_view, name='manage_sft_dataset'),
    path('datasets/<str:agent_name>/export/', views.export_sft_dataset_view, name='export_sft_dataset'),
    path('datasets/example/<uuid:example_id>/delete/', views.delete_sft_example_view, name='delete_sft_example'),
]