#!/bin/bash

# Deployment script для Telegram Parser SaaS
# Запускается на сервере после git pull

set -e  # Остановка при ошибке

echo "🚀 Starting deployment..."

# 1. Активируем виртуальное окружение
source venv/bin/activate

# 2. Обновляем зависимости
echo "📦 Installing dependencies..."
pip install -r requirements.txt
pip install -r requirements.production.txt

# 3. Применяем миграции базы данных
echo "🗄️ Running migrations..."
python manage.py migrate --noinput

# 4. Собираем статические файлы
echo "📁 Collecting static files..."
python manage.py collectstatic --noinput

# 5. Создаем директорию для логов
echo "📝 Creating log directory..."
sudo mkdir -p /var/log/telegram-parser
sudo chown $USER:$USER /var/log/telegram-parser

# 6. Перезапускаем Gunicorn
echo "🔄 Restarting Gunicorn..."
sudo systemctl restart telegram-parser

# 7. Перезапускаем Celery worker
echo "🔄 Restarting Celery..."
sudo systemctl restart telegram-parser-celery

# 8. Перезапускаем Celery beat (если используется)
# sudo systemctl restart telegram-parser-celery-beat

# 9. Перезапускаем Nginx
echo "🔄 Restarting Nginx..."
sudo systemctl restart nginx

echo "✅ Deployment completed successfully!"
echo "🌐 Your site is now live!"
