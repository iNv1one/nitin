from django.core.management.base import BaseCommand
from apps.users.models import User
from apps.telegram_parser.models import KeywordGroup, MonitoredChat


class Command(BaseCommand):
    help = 'Инициализация проекта: создание тестового пользователя и данных'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('=== Инициализация проекта ===\n'))
        
        # Создаем тестового пользователя
        if not User.objects.filter(username='test').exists():
            test_user = User.objects.create_user(
                username='test',
                email='test@example.com',
                password='test123',
                first_name='Тест',
                last_name='Пользователь',
                subscription_plan='pro'
            )
            self.stdout.write(self.style.SUCCESS(f'✓ Создан тестовый пользователь: test / test123'))
        else:
            test_user = User.objects.get(username='test')
            self.stdout.write(self.style.WARNING('⚠ Тестовый пользователь уже существует'))
        
        # Создаем тестовые группы ключевых слов
        if not KeywordGroup.objects.filter(user=test_user).exists():
            group1 = KeywordGroup.objects.create(
                user=test_user,
                name='Недвижимость',
                keywords=['купить квартиру', 'продажа квартир', 'недвижимость'],
                is_active=True
            )
            
            group2 = KeywordGroup.objects.create(
                user=test_user,
                name='Авто',
                keywords=['продам авто', 'купить машину', 'автомобиль'],
                use_ai_filter=True,
                ai_prompt='Пропускай только сообщения о продаже легковых автомобилей',
                is_active=True
            )
            
            self.stdout.write(self.style.SUCCESS(f'✓ Создано 2 тестовые группы ключевых слов'))
        else:
            self.stdout.write(self.style.WARNING('⚠ Тестовые группы уже существуют'))
        
        # Создаем суперпользователя если его нет
        if not User.objects.filter(is_superuser=True).exists():
            admin = User.objects.create_superuser(
                username='admin',
                email='admin@example.com',
                password='admin123'
            )
            self.stdout.write(self.style.SUCCESS(f'✓ Создан суперпользователь: admin / admin123'))
        else:
            self.stdout.write(self.style.WARNING('⚠ Суперпользователь уже существует'))
        
        self.stdout.write(self.style.SUCCESS('\n=== Инициализация завершена ==='))
        self.stdout.write(self.style.SUCCESS('\nТеперь вы можете:'))
        self.stdout.write('1. Запустить сервер: python manage.py runserver')
        self.stdout.write('2. Войти как тестовый пользователь: test / test123')
        self.stdout.write('3. Или войти как админ: admin / admin123')
        self.stdout.write('4. Перейти на: http://localhost:8000/dashboard/')
