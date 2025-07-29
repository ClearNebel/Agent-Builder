import json
import uuid
import asyncio
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.shortcuts import get_object_or_404
from asgiref.sync import sync_to_async, async_to_sync
from datetime import datetime

from .serializers import ConversationSerializer, UserSettingsSerializer
from chat.models import Conversation, ChatMessage
from chat.views import REDIS_CLIENT, MAX_QUEUE_LENGTH, format_chat_history_for_llm, ALL_SYSTEM_AGENTS, CONFIG
from accounts.models import UserProfile 

async def get_agent_response(query, conversation, conversation_id, request):
    job_id = str(uuid.uuid4())
    current_user = request.user
    
    profile = await sync_to_async(UserProfile.objects.get)(user=current_user)
    expert_settings = request.session.get('expert_settings', {})
    model_selection = expert_settings.get('model_selection', 'local_system')
    
    target_system_key = 'local_system' if model_selection == 'local_system' else model_selection.split(':')[0]
    
    is_admin = await sync_to_async(
        lambda: current_user.is_superuser or current_user.groups.filter(name='Admins').exists()
    )()

    if not is_admin:
        user_provider_settings = profile.provider_settings.get(target_system_key, {})
        if not user_provider_settings.get('enabled', False):
            return Response(f"You do not have permission to use the {target_system_key.replace('_', ' ').title()}.")

        rate_limit = user_provider_settings.get('rate_limit')
        if rate_limit is None:
            system_defaults = CONFIG.get(target_system_key) or CONFIG.get('providers', {}).get(target_system_key, {})
            rate_limit = system_defaults.get('default_rate_limit')

        if rate_limit is not None and rate_limit > 0:
            today_str = datetime.utcnow().strftime('%Y-%m-%d')
            redis_key = f"rate_limit:{current_user.id}:{target_system_key}:{today_str}"
            current_usage = await sync_to_async(REDIS_CLIENT.get)(redis_key)
            current_usage = int(current_usage) if current_usage else 0
            if current_usage >= rate_limit:
                return Response(f"You have reached your daily limit for the {target_system_key.replace('_', ' ').title()}.")
        
            pipe = await sync_to_async(REDIS_CLIENT.pipeline)()
            await sync_to_async(pipe.incr)(redis_key)
            await sync_to_async(pipe.expire)(redis_key, 86400)
            await sync_to_async(pipe.execute)()

    user_available_agents = []
    if model_selection == 'local_system':
        if is_admin:
            permitted_agents = ALL_SYSTEM_AGENTS
        else:
            permitted_agents = profile.enabled_local_agents

        session_enabled_agents = expert_settings.get('enabled_agents')
        if session_enabled_agents is not None:
            user_available_agents = [agent for agent in permitted_agents if agent in session_enabled_agents]
        else:
            user_available_agents = permitted_agents
    recent_messages_qs = conversation.messages.exclude(role=ChatMessage.Role.LOG).order_by('-created_at')[:11]
    recent_messages = await sync_to_async(list)(recent_messages_qs)
    recent_messages.reverse()
    chat_history_for_local = format_chat_history_for_llm(recent_messages) if recent_messages else ""
    chat_history_for_providers = [
        {"role": "user" if msg.role == "user" else "assistant", "content": msg.content}
        for msg in recent_messages
    ]

    job_payload = {
        'job_id': job_id, 
        'user_query': query,
        'expert_settings': expert_settings,
        'user_profile_settings': profile.provider_settings,
        'enabled_local_agents': profile.enabled_local_agents,
        'chat_history_for_local': chat_history_for_local,
        'chat_history_for_providers': chat_history_for_providers,
        'user_available_agents': user_available_agents,
        'user_feature_flags': profile.feature_flags, 
        'conversation_id': str(conversation_id),
    }
    
    current_queue_length = await sync_to_async(REDIS_CLIENT.llen)("job_queue")
    if current_queue_length >= MAX_QUEUE_LENGTH:
        raise Exception("The agent service is currently overloaded. Please try again shortly.")
    
    await sync_to_async(REDIS_CLIENT.rpush)("job_queue", json.dumps([job_id, json.dumps(job_payload)]))
    
    polling_timeout = 60
    start_time = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start_time) < polling_timeout:
        result_str = await sync_to_async(REDIS_CLIENT.get)(f"result:{job_id}")
        if result_str:
            await sync_to_async(REDIS_CLIENT.delete)(f"result:{job_id}")
            return json.loads(result_str)
        await asyncio.sleep(1)
    
    raise asyncio.TimeoutError("Request timed out waiting for agent.")


class ChatInteractionAPIView(APIView):
    """
    API endpoint to send a message to a conversation and get a response.
    """
    print("Enter Chat view")
    permission_classes = [permissions.IsAuthenticated]
    print("Enter Chat view")
    def post(self, request, *args, **kwargs):
        query = request.data.get('query')
        conversation_id = request.data.get('conversation_id')
        expert_settings = request.data.get('expert_settings', {})

        if not query:
            return Response({"error": "Query is required."}, status=status.HTTP_400_BAD_REQUEST)

        if conversation_id:
            conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
        else:
            conversation = Conversation.objects.create(user=request.user, title=query[:100])
        
        ChatMessage.objects.create(
            conversation=conversation, role=ChatMessage.Role.USER, content=query
        )

        try:
            result_data = async_to_sync(get_agent_response)(query, conversation, conversation_id, request)
            
            if result_data.get('status') == 'complete':
                agent_message = ChatMessage.objects.create(
                    conversation=conversation, role=ChatMessage.Role.AGENT,
                    content=result_data['response'], agent_name=result_data['agent_name']
                )
                return Response({
                    "conversation_id": str(conversation.id),
                    "response": result_data['response'],
                    "agent_name": result_data['agent_name'],
                    "message_id": str(agent_message.id)
                }, status=status.HTTP_200_OK)
            else:
                return Response({"error": result_data.get('response', 'Unknown worker error')}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except asyncio.TimeoutError:
            return Response({"error": "Request timed out waiting for agent."}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except PermissionError as e: 
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UserSettingsAPIView(APIView):
    """
    API endpoint to get the current user's settings.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        serializer = UserSettingsSerializer(request.user)
        return Response(serializer.data)


class ChatHistoryAPIView(APIView):
    """
    API endpoint to get the chat history for a specific conversation.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, conversation_id, *args, **kwargs):
        print(conversation_id, request.user)
        conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
        serializer = ConversationSerializer(conversation)
        return Response(serializer.data)

class FeedbackAPIView(APIView):
    """
    API endpoint to submit feedback for a message.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        message_id = request.data.get('message_id')
        feedback_str = request.data.get('feedback') # 'up', 'down', or 'none'

        if not message_id or feedback_str not in ['up', 'down', 'none']:
            return Response({"error": "message_id and a valid feedback type are required."}, status=status.HTTP_400_BAD_REQUEST)

        message = get_object_or_404(ChatMessage, id=message_id)

        if message.conversation.user != request.user:
            return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

        if feedback_str == 'up':
            message.feedback = ChatMessage.Feedback.THUMBS_UP
        elif feedback_str == 'down':
            message.feedback = ChatMessage.Feedback.THUMBS_DOWN
        else:
            message.feedback = ChatMessage.Feedback.NO_FEEDBACK
        
        message.save()
        return Response({"status": "ok"}, status=status.HTTP_200_OK)