from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from . import views

app_name = 'api'

urlpatterns = [

    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # POST /api/v1/chat/
    path('chat/', views.ChatInteractionAPIView.as_view(), name='chat_interaction'),
    
    # GET /api/v1/chat/history/<uuid>/
    path('chat/history/<uuid:conversation_id>/', views.ChatHistoryAPIView.as_view(), name='chat_history'),
    
    # GET /api/v1/settings/
    path('settings/', views.UserSettingsAPIView.as_view(), name='user_settings'),
    
    # POST /api/v1/feedback/
    path('feedback/', views.FeedbackAPIView.as_view(), name='feedback'),
]