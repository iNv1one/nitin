# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('telegram_parser', '0020_make_sender_accounts_global'),
    ]

    operations = [
        # Создаем модель ChatTag
        migrations.CreateModel(
            name='ChatTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Например: Недвижимость, Активный, Удалить', max_length=100, unique=True, verbose_name='Название тега')),
                ('color', models.CharField(choices=[('primary', 'Синий'), ('secondary', 'Серый'), ('success', 'Зеленый'), ('danger', 'Красный'), ('warning', 'Желтый'), ('info', 'Голубой'), ('dark', 'Темный')], default='primary', help_text='Цвет отображения в интерфейсе', max_length=20, verbose_name='Цвет тега')),
                ('description', models.TextField(blank=True, help_text='Для чего используется этот тег', verbose_name='Описание')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создан')),
            ],
            options={
                'verbose_name': 'Тег чата',
                'verbose_name_plural': 'Теги чатов',
                'ordering': ['name'],
            },
        ),
        
        # Добавляем поле tags в GlobalChat
        migrations.AddField(
            model_name='globalchat',
            name='tags',
            field=models.ManyToManyField(
                blank=True,
                help_text='Группы/категории чата',
                related_name='chats',
                to='telegram_parser.ChatTag',
                verbose_name='Теги'
            ),
        ),
    ]
