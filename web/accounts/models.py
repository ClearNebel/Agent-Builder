from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    """
    Stores extra, application-specific information for each user.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    provider_settings = models.JSONField(default=dict, blank=True)

    enabled_local_agents = models.JSONField(default=list, blank=True)

    feature_flags = models.JSONField(default=dict, blank=True, help_text='e.g., {"safety_enabled": true}')

    def __str__(self):
        return f"Profile for {self.user.username}"

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile if one doesn't exist for the new User."""
    UserProfile.objects.get_or_create(user=instance)
    instance.profile.save()