"""
Signals for user model
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_chat_settings(sender, instance, created, **kwargs):
    """
    Automatically enable all global chats for new users
    """
    if created:
        # Import here to avoid circular imports
        from apps.telegram_parser.models import GlobalChat, UserChatSettings
        
        # Get all active global chats
        global_chats = GlobalChat.objects.filter(is_active=True)
        
        # Create UserChatSettings for each global chat
        for chat in global_chats:
            UserChatSettings.objects.create(
                user=instance,
                global_chat=chat,
                is_enabled=True
            )
        
        print(f"✅ Created {global_chats.count()} chat settings for user {instance.username}")
