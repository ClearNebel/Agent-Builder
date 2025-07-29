from django.urls import path
from . import views

urlpatterns = [
    path('', views.start_new_chat_view, name='start_new_chat'),
    path('<uuid:conversation_id>/', views.chat_page_view, name='chat_page'),
    path('process/<uuid:conversation_id>/', views.process_chat_view, name='process_chat'),
    path('feedback/', views.feedback_view, name='feedback'),
    path('save_expert_settings/', views.save_expert_settings_view, name='save_expert_settings'),
]