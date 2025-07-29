from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, logout
from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from chat.models import Conversation, ChatMessage

def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            try:
                users_group = Group.objects.get(name='Users')
                user.groups.add(users_group)
            except Group.DoesNotExist:
                pass
            login(request, user)
            return redirect('chat_page')
    else:
        form = UserCreationForm()
    return render(request, 'accounts/register.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('accounts:login')

@receiver(user_logged_out)
def on_user_logged_out(sender, request, **kwargs):
    """
    Clears expert settings from the session when a user logs out.
    """
    if 'expert_settings' in request.session:
        del request.session['expert_settings']
        print("[Session] Expert settings cleared on logout.")

@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    """
    Cleans up any empty, untitled conversations for the user upon login.
    """
    try:
        empty_conversations = Conversation.objects.filter(
            user=user,
            title='New Chat',
            messages__isnull=True
        )
        
        count = empty_conversations.count()
        if count > 0:
            empty_conversations.delete()
            print(f"[Cleanup] Deleted {count} empty conversation(s) for user '{user.username}'.")
    except Exception as e:
        print(f"[Cleanup] Error during empty conversation cleanup for user '{user.username}': {e}")