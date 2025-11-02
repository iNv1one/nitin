"""
Management command to enable all global chats for a specific user
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.telegram_parser.models import GlobalChat, UserChatSettings

User = get_user_model()


class Command(BaseCommand):
    help = 'Enable all global chats for a specific user'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='User ID to enable chats for (default: 1 - first user)',
            default=1
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Username to enable chats for (alternative to user-id)',
        )

    def handle(self, *args, **options):
        user_id = options['user_id']
        username = options.get('username')
        
        # Get user
        try:
            if username:
                user = User.objects.get(username=username)
            else:
                user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ User not found'))
            return
        
        self.stdout.write(self.style.SUCCESS(f'👤 Found user: {user.username} (ID: {user.id})'))
        
        # Get all global chats
        global_chats = GlobalChat.objects.filter(is_active=True)
        total_chats = global_chats.count()
        
        if total_chats == 0:
            self.stdout.write(self.style.WARNING('⚠️  No active global chats found'))
            return
        
        self.stdout.write(f'📺 Found {total_chats} active global chats')
        
        # Create UserChatSettings for each chat
        created_count = 0
        updated_count = 0
        
        for chat in global_chats:
            setting, created = UserChatSettings.objects.get_or_create(
                user=user,
                global_chat=chat,
                defaults={'is_enabled': True}
            )
            
            if created:
                created_count += 1
            else:
                if not setting.is_enabled:
                    setting.is_enabled = True
                    setting.save()
                    updated_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Done!'))
        self.stdout.write(f'  ✨ Created: {created_count} new settings')
        self.stdout.write(f'  🔄 Updated: {updated_count} existing settings')
        self.stdout.write(f'  📊 Total enabled chats: {total_chats}')
        
        # Show summary
        self.stdout.write(f'\n📈 Summary:')
        self.stdout.write(f'  User: {user.username}')
        self.stdout.write(f'  Enabled chats: {UserChatSettings.objects.filter(user=user, is_enabled=True).count()}')
        self.stdout.write(f'  Disabled chats: {UserChatSettings.objects.filter(user=user, is_enabled=False).count()}')
