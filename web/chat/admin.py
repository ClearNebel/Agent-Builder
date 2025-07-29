from django.contrib import admin
from .models import Conversation, ChatMessage

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = [
        'id', 
        'user', 
        'title', 
    ]
    search_fields = ['id', 'user', 'title' ]
    list_filter = ['user']

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'agent_name', 
        'role', 
        'content', 
    ]
    search_fields = ['id', 'agent_name', 'role' ]
    list_filter = ['agent_name']