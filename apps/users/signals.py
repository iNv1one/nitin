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
            UserChatSettings.objects.get_or_create(
                user=instance,
                global_chat=chat,
                defaults={'is_enabled': True}
            )
        
        print(f"✅ Created {global_chats.count()} chat settings for user {instance.username}")


@receiver(post_save, sender='telegram_parser.GlobalChat')
def enable_global_chat_for_all_users(sender, instance, created, **kwargs):
    """
    Automatically enable new global chat for all existing users
    """
    if created and instance.is_active:
        # Import here to avoid circular imports
        from apps.telegram_parser.models import UserChatSettings
        
        # Get all active users
        users = User.objects.filter(is_active=True)
        
        # Create UserChatSettings for each user
        created_count = 0
        for user in users:
            _, was_created = UserChatSettings.objects.get_or_create(
                user=user,
                global_chat=instance,
                defaults={'is_enabled': True}
            )
            if was_created:
                created_count += 1
        
        print(f"✅ Enabled chat '{instance.name}' for {created_count} users")
