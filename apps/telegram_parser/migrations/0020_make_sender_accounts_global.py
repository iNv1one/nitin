# Generated manually

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('telegram_parser', '0019_senderaccount_sending_control'),
    ]

    operations = [
        # 1. Удаляем unique_together constraint
        migrations.AlterUniqueTogether(
            name='senderaccount',
            unique_together=set(),
        ),
        
        # 2. Делаем user nullable
        migrations.AlterField(
            model_name='senderaccount',
            name='user',
            field=models.ForeignKey(
                blank=True,
                help_text='Поле deprecated - аккаунты теперь общие',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sender_accounts',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Пользователь (устарело)'
            ),
        ),
        
        # 3. Удаляем старый индекс с user
        migrations.RemoveIndex(
            model_name='senderaccount',
            name='telegram_pa_user_id_c73870_idx',
        ),
        
        # 4. Добавляем новые индексы без user
        migrations.AddIndex(
            model_name='senderaccount',
            index=models.Index(fields=['is_active'], name='sender_is_active_idx'),
        ),
        migrations.AddIndex(
            model_name='senderaccount',
            index=models.Index(fields=['phone'], name='sender_phone_idx'),
        ),
    ]
