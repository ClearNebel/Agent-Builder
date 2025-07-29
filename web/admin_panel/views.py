import yaml
import os
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncDay
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from django.db import transaction 
from datetime import datetime, timedelta

from accounts.decorators import admin_required
from chat.models import AgentPermission, ChatMessage, SFTExample
from accounts.models import UserProfile 

CONFIG_PATH = os.path.join(settings.BASE_DIR.parent, 'agent/configs/config.yaml')
with open(CONFIG_PATH, 'r') as f:
    CONFIG = yaml.safe_load(f)
AVAILABLE_AGENTS = list(CONFIG.get('agents', {}).keys())
AGENTS_CONFIG = CONFIG.get('agents', {})
ALL_SYSTEM_AGENTS = list(AGENTS_CONFIG.keys())
ALL_PROVIDER_CONFIGS = CONFIG.get('providers', {})


@login_required
@admin_required
def user_list_view(request):
    """Displays a list of all non-admin, non-superuser users."""
    users = User.objects.filter(is_superuser=False, groups__name='Users').distinct()
    context = {
        'users': users
    }
    return render(request, 'admin_panel/user_list.html', context)

@login_required
@admin_required
def manage_user_permissions_view(request, user_id):
    """Displays a form to manage a specific user's agent permissions."""
    target_user = get_object_or_404(User, id=user_id)
    profile, created = UserProfile.objects.get_or_create(user=target_user)

    all_configurable_providers = {'local_system': CONFIG['local_system']}
    all_configurable_providers.update(CONFIG['providers'])

    if request.method == 'POST':
        new_provider_settings = {}
        for key, details in all_configurable_providers.items():
            is_enabled = request.POST.get(f'enabled_{key}') == 'on'
            rate_limit_str = request.POST.get(f'rate_limit_{key}', '')
            rate_limit = None
            if rate_limit_str.isdigit() and int(rate_limit_str) >= 0:
                rate_limit = int(rate_limit_str)
            
            new_provider_settings[key] = {
                'enabled': is_enabled,
                'rate_limit': rate_limit
            }
        profile.provider_settings = new_provider_settings
        
        selected_local_agents = request.POST.getlist('local_agents')
        profile.enabled_local_agents = [agent for agent in selected_local_agents if agent in AVAILABLE_AGENTS]

        profile.feature_flags = {
            'pii_force_local': request.POST.get('flag_pii_force_local') == 'on',
            'block_dangerous_content': request.POST.get('flag_block_dangerous_content') == 'on',
        }

        profile.save()
        return redirect('admin_panel:user_list')

    display_settings = {}
    for key, details in all_configurable_providers.items():
        user_specific_settings_for_provider = profile.provider_settings.get(key, {})
        
        default_rate_limit = details.get('default_rate_limit')
        display_settings[key] = {
            'display_name': details['display_name'],
            'enabled': user_specific_settings_for_provider.get('enabled', False),
            'rate_limit': user_specific_settings_for_provider.get('rate_limit', default_rate_limit),

        }

    context = {
        'target_user': target_user,
        'display_settings': display_settings,
        'available_local_agents': AVAILABLE_AGENTS, 
        'user_enabled_local_agents': profile.enabled_local_agents, 
        'user_feature_flags': profile.feature_flags or {},
    }
    return render(request, 'admin_panel/manage_user_permissions.html', context)

@login_required
@admin_required
def agent_list_view(request):
    """Displays a list of all agents defined in the config file."""
    agents_with_details = []
    all_agent_configs = CONFIG.get('agents', {})
    
    for agent_name, agent_config in all_agent_configs.items():
        agents_with_details.append({
            'name': agent_name,
            'description': agent_config.get('description', 'No description provided.') # Provide a default
        })
        
    context = {
        'agents': agents_with_details,
    }
    return render(request, 'admin_panel/agent_list.html', context)

@login_required
@admin_required
def agent_details_view(request, agent_name):
    """Displays the configuration details for a specific agent."""
    if agent_name not in AVAILABLE_AGENTS:
        return redirect('admin_panel:agent_list')

    agent_config = CONFIG.get('agents', {}).get(agent_name, {})
    
    prompt_content = "File not found or could not be read."
    prompt_file_path_relative = agent_config.get('prompt_file')
    if prompt_file_path_relative:
        prompt_file_path_absolute = str(settings.BASE_DIR.parent) + '/agent' + prompt_file_path_relative
        try:
            with open(prompt_file_path_absolute, 'r', encoding='utf-8') as f:
                prompt_content = f.read()
        except FileNotFoundError:
            prompt_content = f"Error: Prompt file not found at '{prompt_file_path_absolute}'"
        except Exception as e:
            prompt_content = f"An error occurred while reading the file: {e}"

    context = {
        'agent_name': agent_name,
        'base_model': CONFIG.get('base_model', 'Not specified'),
        'prompt_file': prompt_file_path_relative or "Not specified",
        'prompt_content': prompt_content,
        'available_tools': agent_config.get('tools_whitelist', []) or ["None"], # Provide a default if the list is empty
    }
    
    return render(request, 'admin_panel/agent_details.html', context)

@login_required
@admin_required
def curation_dashboard_view(request):
    """
    Displays a dashboard for data curation, showing rejected messages that need review.
    """
    rejected_messages = ChatMessage.objects.filter(
        feedback=ChatMessage.Feedback.THUMBS_DOWN,
        is_reviewed=False
    ).select_related('conversation', 'conversation__user').order_by('created_at')
    
    context = {
        'rejected_messages': rejected_messages
    }
    return render(request, 'admin_panel/curation_dashboard.html', context)


@login_required
@admin_required
def review_rejected_message_view(request, message_id):
    """
    Allows an admin to view a rejected message in context and provide a corrected response.
    """
    rejected_message = get_object_or_404(ChatMessage, id=message_id)

    if rejected_message.feedback != ChatMessage.Feedback.THUMBS_DOWN:
        return redirect('admin_panel:curation_dashboard')

    if request.method == 'POST':
        corrected_text = request.POST.get('corrected_content', '')
        corrected_agent_route = request.POST.get('corrected_route', '')
        action = request.POST.get('action')

        if action == 'save':
            rejected_message.corrected_content = corrected_text
            
            if corrected_agent_route and corrected_agent_route in AVAILABLE_AGENTS:
                rejected_message.corrected_route = corrected_agent_route
            
            rejected_message.is_reviewed = True
            rejected_message.save()
        elif action == 'ignore':
            rejected_message.is_reviewed = True
            rejected_message.save()
            
        return redirect('admin_panel:curation_dashboard')

    conversation_context = rejected_message.conversation.messages.filter(
        created_at__lte=rejected_message.created_at
    ).order_by('created_at')

    context = {
        'rejected_message': rejected_message,
        'conversation_context': conversation_context,
        'available_agents': AVAILABLE_AGENTS,
    }
    return render(request, 'admin_panel/review_rejected_message.html', context)

@login_required
@admin_required
def analytics_dashboard_view(request):
    """
    Provides analytics on model usage with powerful filtering.
    """
    queryset = ChatMessage.objects.filter(role=ChatMessage.Role.AGENT)

    selected_users = request.GET.getlist('users')
    selected_agents = request.GET.getlist('agents')
    date_from_str = request.GET.get('date_from')
    date_to_str = request.GET.get('date_to')

    if selected_users:
        queryset = queryset.filter(conversation__user__id__in=selected_users)
    
    if selected_agents:
        queryset = queryset.filter(agent_name__in=selected_agents)
        
    if date_from_str:
        queryset = queryset.filter(created_at__gte=datetime.strptime(date_from_str, '%Y-%m-%d'))
    
    if date_to_str:
        date_to = datetime.strptime(date_to_str, '%Y-%m-%d') + timedelta(days=1)
        queryset = queryset.filter(created_at__lt=date_to)

    total_calls = queryset.count()

    usage_by_agent = queryset.values('agent_name').annotate(
        call_count=Count('id')
    ).order_by('-call_count')
    
    usage_by_user = queryset.values(
        'conversation__user__username'
    ).annotate(
        call_count=Count('id')
    ).order_by('-call_count')

    daily_usage = queryset.annotate(
        day=TruncDay('created_at')
    ).values('day').annotate(
        call_count=Count('id')
    ).order_by('day')
    
    chart_labels = [d['day'].strftime('%Y-%m-%d') for d in daily_usage]
    chart_data = [d['call_count'] for d in daily_usage]
    
    all_users = User.objects.filter(is_staff=False).order_by('username')
    
    all_used_agents = ChatMessage.objects.filter(role=ChatMessage.Role.AGENT).values_list(
        'agent_name', flat=True
    ).distinct().order_by('agent_name')

    context = {
        'total_calls': total_calls,
        'usage_by_agent': usage_by_agent,
        'usage_by_user': usage_by_user,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
        
        'all_users': all_users,
        'all_agents': all_used_agents,
        
        'current_filters': {
            'users': [int(u) for u in selected_users],
            'agents': selected_agents,
            'date_from': date_from_str,
            'date_to': date_to_str,
        }
    }
    
    return render(request, 'admin_panel/analytics_dashboard.html', context)

@login_required
@admin_required
def create_user_view(request):
    """
    Allows an admin to create a new user and set all their permissions
    and settings in a single form.
    """
    user_form = UserCreationForm(request.POST or None)

    if request.method == 'POST':
        if user_form.is_valid():
            try:
                with transaction.atomic():
                    new_user = user_form.save()
                    try:
                        users_group = Group.objects.get(name='Users')
                        new_user.groups.add(users_group)
                    except Group.DoesNotExist:
                        pass

                    profile = new_user.profile 
                    
                    all_configurable_providers = {'local_system': CONFIG['local_system']}
                    all_configurable_providers.update(CONFIG['providers'])
                    
                    new_provider_settings = {}
                    for key in all_configurable_providers.keys():
                        is_enabled = request.POST.get(f'enabled_{key}') == 'on'
                        rate_limit_str = request.POST.get(f'rate_limit_{key}', '')
                        rate_limit = None
                        if rate_limit_str.isdigit() and int(rate_limit_str) >= 0:
                            rate_limit = int(rate_limit_str)
                        
                        new_provider_settings[key] = {'enabled': is_enabled, 'rate_limit': rate_limit}
                    
                    profile.provider_settings = new_provider_settings
                    
                    selected_local_agents = request.POST.getlist('local_agents')
                    profile.enabled_local_agents = [agent for agent in selected_local_agents if agent in ALL_SYSTEM_AGENTS]
                    
                    profile.save()

                return redirect('admin_panel:user_list')
            except Exception as e:
                user_form.add_error(None, f"An unexpected error occurred: {e}")

    all_configurable_providers = {'local_system': CONFIG['local_system']}
    all_configurable_providers.update(CONFIG['providers'])
    
    default_settings = {}
    for key, details in all_configurable_providers.items():
        default_settings[key] = {
            'display_name': details['display_name'],
            'enabled': False, 
            'rate_limit': details['default_rate_limit']
        }

    context = {
        'user_form': user_form,
        'display_settings': default_settings,
        'available_local_agents': ALL_SYSTEM_AGENTS,
    }
    return render(request, 'admin_panel/create_user.html', context)

@login_required
@admin_required
def dataset_list_view(request):
    """Shows a list of agents for which SFT datasets can be managed."""
    agent_counts = SFTExample.objects.values('agent_name').annotate(example_count=Count('id'))
    agent_count_map = {item['agent_name']: item['example_count'] for item in agent_counts}

    agents_with_counts = []
    for agent_name, agent_details in CONFIG.get('agents', {}).items():
        agents_with_counts.append({
            'name': agent_name,
            'description': agent_details.get('description', ''),
            'count': agent_count_map.get(agent_name, 0)
        })

    context = {
        'agents': agents_with_counts
    }
    return render(request, 'admin_panel/dataset_list.html', context)


@login_required
@admin_required
def manage_sft_dataset_view(request, agent_name):
    """Allows an admin to view, add, and manage SFT examples for a specific agent."""
    if agent_name not in ALL_SYSTEM_AGENTS:
        return redirect('admin_panel:dataset_list')

    if request.method == 'POST':
        prompt = request.POST.get('prompt')
        response = request.POST.get('response')
        if prompt and response:
            SFTExample.objects.create(agent_name=agent_name, prompt=prompt, response=response)
        return redirect('admin_panel:manage_sft_dataset', agent_name=agent_name)

    examples = SFTExample.objects.filter(agent_name=agent_name).order_by('-created_at')
    
    agent_config = CONFIG.get('agents', {}).get(agent_name, {})
    prompt_file_path_relative = agent_config.get('prompt_file')
    system_prompt = "System prompt file not found."
    if prompt_file_path_relative:
        prompt_file_path_absolute = os.path.join(settings.BASE_DIR.parent, 'agent', prompt_file_path_relative)
        try:
            with open(prompt_file_path_absolute, 'r') as f:
                system_prompt = f.read()
        except FileNotFoundError:
            pass
            
    context = {
        'agent_name': agent_name,
        'examples': examples,
        'system_prompt': system_prompt
    }
    return render(request, 'admin_panel/manage_sft_dataset.html', context)


@login_required
@admin_required
def delete_sft_example_view(request, example_id):
    """Deletes a single SFT example."""
    if request.method == 'POST':
        example = get_object_or_404(SFTExample, id=example_id)
        agent_name = example.agent_name
        example.delete()
        return redirect('admin_panel:manage_sft_dataset', agent_name=agent_name)


@login_required
@admin_required
def export_sft_dataset_view(request, agent_name):
    """Exports the SFT dataset for an agent to its .jsonl file."""
    if agent_name not in ALL_SYSTEM_AGENTS:
        return redirect('admin_panel:dataset_list')
        
    examples = SFTExample.objects.filter(agent_name=agent_name)
    output_path = os.path.join(settings.BASE_DIR.parent, 'agent/data/agents', f'{agent_name}_sft_data.jsonl')
    
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            for example in examples:
                data = {"prompt": f"{example.prompt}", "completion": f"{example.response}"}
                f.write(json.dumps(data) + '\n')
    except Exception as e:
        print(f"Error exporting dataset: {e}")

    return redirect('admin_panel:manage_sft_dataset', agent_name=agent_name)