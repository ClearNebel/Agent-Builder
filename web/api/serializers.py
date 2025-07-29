# web/api/serializers.py
from rest_framework import serializers
from chat.models import Conversation, ChatMessage
from accounts.models import UserProfile
from django.contrib.auth.models import User

class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'agent_name', 'content', 'feedback', 'created_at']

class ConversationSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ['id', 'title', 'created_at', 'messages']

class UserSettingsSerializer(serializers.ModelSerializer):
    provider_settings = serializers.JSONField(source='profile.provider_settings')
    enabled_local_agents = serializers.JSONField(source='profile.enabled_local_agents')
    
    class Meta:
        model = User
        fields = ['id', 'username', 'provider_settings', 'enabled_local_agents']