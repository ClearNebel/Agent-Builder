import json
import os
import yaml
import asyncio
import redis
import uuid
import markdown
from django.shortcuts import render, redirect, get_object_or_404
from django.http import StreamingHttpResponse, JsonResponse, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.exceptions import PermissionDenied
from django.utils.safestring import mark_safe
from asgiref.sync import sync_to_async
from django.conf import settings
from datetime import datetime

from .models import Conversation, ChatMessage, AgentPermission
from accounts.models import UserProfile 

try:
    REDIS_CLIENT = settings.REDIS_CLIENT
    REDIS_CLIENT.ping()
    print("[Django] Successfully connected to Redis.")
except redis.exceptions.ConnectionError:
    print("[Django] FATAL: Could not connect to Redis. Is the Redis server running?")
    REDIS_CLIENT = None
MAX_QUEUE_LENGTH = 10

PROJECT_ROOT = os.path.abspath(os.path.join(settings.BASE_DIR, '../agent'))
print(PROJECT_ROOT)
CONFIG_PATH = PROJECT_ROOT + '/configs/config.yaml'
with open(CONFIG_PATH, 'r') as f:
    CONFIG = yaml.safe_load(f)
AGENTS_CONFIG = CONFIG.get('agents', {})

ALL_SYSTEM_AGENTS = list(AGENTS_CONFIG.keys())
ALL_PROVIDER_CONFIGS = CONFIG.get('providers', {})
ENABLED_PROVIDER_CONFIGS = {}
for provider_key, provider_details in ALL_PROVIDER_CONFIGS.items():
    if provider_details.get('enabled', False):
        ENABLED_PROVIDER_CONFIGS[provider_key] = {
            'display_name': provider_details.get('display_name', provider_key.capitalize()),
            'models': provider_details.get('models', [])
        }
print(f"[Django] Enabled external providers: {list(ENABLED_PROVIDER_CONFIGS.keys())}")

def format_chat_history_for_llm(messages):
    """
    Formats a queryset of ChatMessage objects into a list of dictionaries
    suitable for LLM API contexts (e.g., OpenAI Chat Completion API).

    Args:
        messages: A queryset or list of ChatMessage objects, ordered chronologically.

    Returns:
        A list of dictionaries, where each dictionary has 'role' and 'content' keys.
        Example:
        [
            {"role": "system", "content": "This is the previous conversation history. Based on this, please respond to the user."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
            # ...
        ]
    """
    formatted_history = []

    system_intro_content = "This is the previous conversation history. Based on this, please respond to the user concisely and helpfully."
    formatted_history.append({"role": "system", "content": system_intro_content})

    for msg in messages:
        if msg.role == ChatMessage.Role.USER:
            formatted_history.append({
                "role": "user",
                "content": msg.content
            })
        elif msg.role == ChatMessage.Role.AGENT:
            formatted_history.append({
                "role": "assistant",
                "content": msg.content
            })

    return formatted_history

@login_required
def start_new_chat_view(request):
    """Creates a new conversation object and redirects to its page."""
    if 'expert_settings' in request.session:
        del request.session['expert_settings']

    try:
        empty_conversations = Conversation.objects.filter(
            user=request.user,
            title='New Chat',
            messages__isnull=True 
        )
        
        count = empty_conversations.count()
        if count > 0:
            empty_conversations.delete()
            print(f"[Cleanup] Deleted {count} empty conversation(s) for user '{request.user.username}'.")
    except Exception as e:
        print(f"[Cleanup] Error during empty conversation cleanup for user '{request.user.username}': {e}")
    conversation = Conversation.objects.create(user=request.user)
    return redirect('chat_page', conversation_id=conversation.id)

@login_required
def chat_page_view(request, conversation_id):
    """Renders the chat page, passing conversation history and user permissions."""
    conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
    user_conversations = Conversation.objects.filter(user=request.user).order_by('-created_at')

    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    user_enabled_providers = profile.provider_settings.get('enabled_providers_list', []) # Using a helper key
    user_enabled_providers = [k for k,v in profile.provider_settings.items() if v.get('enabled')]

    final_providers_for_user = {
        key: details for key, details in ENABLED_PROVIDER_CONFIGS.items() if key in user_enabled_providers
    }
    
    is_admin = request.user.is_superuser or request.user.groups.filter(name='Admins').exists()
    if is_admin:
        permitted_agents = ALL_SYSTEM_AGENTS
        final_providers_for_user = ENABLED_PROVIDER_CONFIGS
    else:
        user_permitted_local_agents = profile.enabled_local_agents
        permitted_agents = [agent for agent in ALL_SYSTEM_AGENTS if agent in user_permitted_local_agents]

    context = {
        'conversation': conversation,
        'past_conversations': user_conversations,
        'user_permitted_agents_json': json.dumps(permitted_agents),
        'provider_configs': final_providers_for_user,
        'provider_configs_json': json.dumps(final_providers_for_user)
    }
    return render(request, 'chat/chat_page.html', context)


@login_required
@require_POST
def feedback_view(request):
    """Receives feedback via AJAX and updates the message."""
    try:
        data = json.loads(request.body)
        message_id = data.get('message_id')
        feedback_type = data.get('feedback')
        message = get_object_or_404(ChatMessage, id=message_id)
        if message.conversation.user != request.user:
            return HttpResponseForbidden("Forbidden")
        
        if feedback_type == 'up': message.feedback = ChatMessage.Feedback.THUMBS_UP
        elif feedback_type == 'down': message.feedback = ChatMessage.Feedback.THUMBS_DOWN
        else: message.feedback = ChatMessage.Feedback.NO_FEEDBACK
        
        message.save()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
@require_POST
def save_expert_settings_view(request):
    """Saves expert settings from the panel to the user's session."""
    try:
        data = json.loads(request.body)
        request.session['expert_settings'] = {
            'temperature': float(data.get('temperature', 0.7)),
            'top_p': float(data.get('top_p', 0.9)),
            'enabled_agents': data.get('enabled_agents', []),
            'model_selection': data.get('model_selection', [])
        }
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
async def process_chat_view(request, conversation_id):
    """
    Handles an incoming chat query by placing it on the Redis queue
    and then streaming back the results by polling Redis.
    """
    if not REDIS_CLIENT:
        async def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'content': 'The backend service is not connected to Redis.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingHttpResponse(error_stream(), content_type="text/event-stream")

    query = request.GET.get('query', '')
    conversation = await sync_to_async(get_object_or_404)(Conversation, id=conversation_id, user=request.user)

    await sync_to_async(ChatMessage.objects.create)(
        conversation=conversation, role=ChatMessage.Role.USER, content=query
    )
    if await sync_to_async(lambda: conversation.title == 'New Chat')():
        conversation.title = query[:100]
        await sync_to_async(conversation.save)()

    async def event_stream():
        job_id = str(uuid.uuid4())
        current_user = request.user
        
        try:
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
                    raise PermissionDenied(f"You do not have permission to use the {target_system_key.replace('_', ' ').title()}.")

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
                        raise PermissionDenied(f"You have reached your daily limit for the {target_system_key.replace('_', ' ').title()}.")
                
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
            yield f"data: {json.dumps({'type': 'log', 'content': f'Request queued (Position: {current_queue_length + 1})'})}\n\n"
            
            polling_timeout = 600
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < polling_timeout:
                result_str = await sync_to_async(REDIS_CLIENT.get)(f"result:{job_id}")
                if result_str:
                    result_data = json.loads(result_str)
                    if result_data['status'] == 'complete':
                        final_msg = await sync_to_async(ChatMessage.objects.create)(
                            conversation=conversation, role=ChatMessage.Role.AGENT,
                            content=result_data['response'], agent_name=result_data['agent_name']
                        )
                        final_msg.content = mark_safe(markdown.markdown(final_msg.content))
                        yield f"data: {json.dumps({'type': 'final_answer', 'content': mark_safe(markdown.markdown(result_data['response'])), 'agent_name': result_data['agent_name'], 'id': str(final_msg.id)})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'error', 'content': mark_safe(markdown.markdown(result_data['response']))})}\n\n"

                    await sync_to_async(REDIS_CLIENT.delete)(f"result:{job_id}")
                    break
                
                await asyncio.sleep(1)
            else: 
                yield f"data: {json.dumps({'type': 'error', 'content': 'The request timed out while waiting for an agent to become available.'})}\n\n"

        except (PermissionDenied, Exception) as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")