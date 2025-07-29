from django.db import models
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from django.utils.html import format_html
import uuid
import markdown
import re

class Conversation(models.Model):
    """Stores a single conversation session."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=200, default='New Chat')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"'{self.title}' by {self.user.username}"

class ChatMessage(models.Model):
    """Stores a single message within a conversation."""
    class Role(models.TextChoices):
        USER = 'user', 'User'
        AGENT = 'agent', 'Agent'
        LOG = 'log', 'Log'

    class Feedback(models.IntegerChoices):
        NO_FEEDBACK = 0, 'No Feedback'
        THUMBS_UP = 1, 'Thumbs Up'
        THUMBS_DOWN = -1, 'Thumbs Down'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=Role.choices)
    agent_name = models.CharField(max_length=100, blank=True, null=True)
    content = models.TextField()
    feedback = models.IntegerField(choices=Feedback.choices, default=Feedback.NO_FEEDBACK)
    created_at = models.DateTimeField(auto_now_add=True)
    corrected_content = models.TextField(blank=True, null=True, help_text="Admin-provided ideal response for a rejected message.")
    corrected_route = models.CharField(max_length=100, blank=True, null=True, help_text="Admin-provided correct agent route for this message's prompt.")
    is_reviewed = models.BooleanField(default=False, help_text="True if an admin has reviewed this feedback.")

    def __str__(self):
        return f"{self.get_role_display()} message in '{self.conversation.title}'"

    @property
    def content_as_html(self):
        """Convert Markdown, then wrap <think>…</think> in a <details> tag."""
        html = markdown.markdown(self.content)

        def wrap_thought(match):
            inner_html = match.group(1)
            return format_html(
                '<details class="thought-collapse"><summary>Show Thought</summary>{}</details>',
                mark_safe(inner_html)
            )

        processed = re.sub(r'<think>([\s\S]*?)</think>', wrap_thought, html)
        return mark_safe(processed)

    class Meta:
        ordering = ['created_at']

class AgentPermission(models.Model):
    """
    Stores permissions for which user can access which agent.
    Agents are identified by their string key from the config.yaml file.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='agent_permissions')
    agent_name = models.CharField(max_length=100)
    
    class Meta:
        unique_together = ('user', 'agent_name')

    def __str__(self):
        return f"{self.user.username} has access to {self.agent_name}"
    
class SFTExample(models.Model):
    """
    Stores a single high-quality example for Supervised Fine-Tuning (SFT).
    Each example is a prompt/response pair for a specific agent.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    agent_name = models.CharField(max_length=100, db_index=True)
    
    prompt = models.TextField()
    
    response = models.TextField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"SFT Example for '{self.agent_name}'"