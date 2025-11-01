# 🚀 Production Deployment - Quick Guide

## Автоматический деплой (рекомендуется)

### Скопируйте и запустите этот скрипт на сервере:

```bash
#!/bin/bash
# Автоматический деплой Telegram Parser SaaS

set -e

echo "🚀 Starting automatic deployment..."

# Установка всех зависимостей
echo "📦 Installing system dependencies..."
sudo apt update && sudo apt install -y \
    python3.11 python3.11-venv python3-pip python3-dev \
    postgresql postgresql-contrib redis-server nginx git \
    build-essential libpq-dev certbot python3-certbot-nginx

# Настройка PostgreSQL
echo "🗄️ Setting up PostgreSQL..."
sudo -u postgres psql << EOF
CREATE DATABASE telegram_parser_db;
CREATE USER telegram_parser_user WITH PASSWORD 'ChangeThisPassword123!';
GRANT ALL PRIVILEGES ON DATABASE telegram_parser_db TO telegram_parser_user;
\q
EOF

# Клонирование проекта
echo "📥 Cloning project..."
cd /var/www
sudo git clone YOUR_GIT_REPO_URL telegram-parser-saas || echo "Project already exists"
cd telegram-parser-saas
sudo chown -R $USER:www-data .

# Python зависимости
echo "🐍 Installing Python dependencies..."
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements.production.txt

# .env файл
echo "⚙️ Creating .env file..."
cat > .env << 'ENVFILE'
SECRET_KEY=$(python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
DEBUG=False
ALLOWED_HOSTS=YOUR_DOMAIN.com,www.YOUR_DOMAIN.com

DB_NAME=telegram_parser_db
DB_USER=telegram_parser_user
DB_PASSWORD=ChangeThisPassword123!

REDIS_URL=redis://localhost:6379/0

TELEGRAM_API_ID=YOUR_API_ID
TELEGRAM_API_HASH=YOUR_API_HASH

OPENAI_API_KEY=YOUR_OPENAI_KEY

DJANGO_SETTINGS_MODULE=config.settings_production
ENVFILE

echo "⚠️  ВАЖНО: Отредактируйте .env файл и замените YOUR_DOMAIN, YOUR_API_ID и т.д."
read -p "Нажмите Enter после редактирования .env..."
nano .env

# Django setup
echo "🎨 Running Django migrations..."
python manage.py migrate
python manage.py collectstatic --noinput
echo "👤 Create superuser:"
python manage.py createsuperuser

# Создание директорий
sudo mkdir -p /var/log/telegram-parser /var/run/celery
sudo chown $USER:www-data /var/log/telegram-parser /var/run/celery

# Systemd сервисы
echo "⚙️ Setting up systemd services..."
sudo cp systemd/telegram-parser.service /etc/systemd/system/
sudo cp systemd/telegram-parser-celery.service /etc/systemd/system/

sudo sed -i "s|your-username|$USER|g" /etc/systemd/system/telegram-parser*.service
sudo sed -i "s|/path/to/telegram-parser-saas|$(pwd)|g" /etc/systemd/system/telegram-parser*.service

sudo systemctl daemon-reload
sudo systemctl enable telegram-parser telegram-parser-celery
sudo systemctl start telegram-parser telegram-parser-celery

# Nginx
echo "🌐 Configuring Nginx..."
sudo cp nginx/telegram-parser.conf /etc/nginx/sites-available/telegram-parser
sudo sed -i "s|yourdomain.com|YOUR_DOMAIN.com|g" /etc/nginx/sites-available/telegram-parser
sudo sed -i "s|/path/to/telegram-parser-saas|$(pwd)|g" /etc/nginx/sites-available/telegram-parser

read -p "Введите ваш домен (например, example.com): " DOMAIN
sudo sed -i "s|YOUR_DOMAIN.com|$DOMAIN|g" /etc/nginx/sites-available/telegram-parser

sudo ln -s /etc/nginx/sites-available/telegram-parser /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Проверка Nginx
if sudo nginx -t; then
    sudo systemctl restart nginx
    echo "✅ Nginx configured successfully"
else
    echo "❌ Nginx configuration error. Please check manually."
fi

# SSL сертификат
read -p "Хотите установить SSL сертификат сейчас? (y/n): " INSTALL_SSL
if [ "$INSTALL_SSL" == "y" ]; then
    read -p "Введите email для Let's Encrypt: " EMAIL
    sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos -m $EMAIL
fi

echo ""
echo "✅ Deployment completed!"
echo ""
echo "📋 Next steps:"
echo "1. Импортируйте Telegram чаты: python manage.py import_my_chats"
echo "2. Откройте https://$DOMAIN в браузере"
echo "3. Проверьте статус: sudo systemctl status telegram-parser telegram-parser-celery"
echo ""
echo "📝 Логи:"
echo "   tail -f /var/log/telegram-parser/*.log"
echo ""
```

Сохраните этот скрипт как `auto-deploy.sh` и запустите:

```bash
chmod +x auto-deploy.sh
./auto-deploy.sh
```

---

## Ручной деплой (для контроля каждого шага)

См. подробную инструкцию в файле `DEPLOYMENT.md`

---

## После деплоя

### Проверка статуса всех сервисов

```bash
sudo systemctl status telegram-parser telegram-parser-celery nginx postgresql redis-server
```

### Просмотр логов

```bash
# Все логи
tail -f /var/log/telegram-parser/*.log

# Отдельно
tail -f /var/log/telegram-parser/gunicorn-error.log
tail -f /var/log/telegram-parser/celery.log
tail -f /var/log/telegram-parser/django.log
```

### Импорт Telegram чатов

```bash
cd /var/www/telegram-parser-saas
source venv/bin/activate
python manage.py import_my_chats
```

### Перезапуск после изменений

```bash
sudo systemctl restart telegram-parser telegram-parser-celery
```

### Обновление из Git

```bash
cd /var/www/telegram-parser-saas
git pull
source venv/bin/activate
pip install -r requirements.txt -r requirements.production.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart telegram-parser telegram-parser-celery
```

---

## Troubleshooting

### 502 Bad Gateway

```bash
# Проверить Gunicorn
sudo systemctl status telegram-parser
tail -f /var/log/telegram-parser/gunicorn-error.log

# Перезапустить
sudo systemctl restart telegram-parser
```

### Celery не работает

```bash
# Проверить Redis
redis-cli ping

# Проверить Celery
sudo systemctl status telegram-parser-celery
tail -f /var/log/telegram-parser/celery.log
```

### База данных недоступна

```bash
# Проверить PostgreSQL
sudo systemctl status postgresql

# Проверить подключение
psql -U telegram_parser_user -d telegram_parser_db -h localhost
```

---

## Безопасность

### Файрвол

```bash
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw enable
```

### Регулярные обновления

```bash
# Добавить в crontab
0 3 * * * sudo apt update && sudo apt upgrade -y
```

### Backup базы данных

```bash
# Создать backup
pg_dump -U telegram_parser_user telegram_parser_db > backup_$(date +%Y%m%d).sql

# Автоматический backup (добавить в crontab)
0 3 * * * pg_dump -U telegram_parser_user telegram_parser_db > /var/backups/telegram_parser_$(date +\%Y\%m\%d).sql
```

---

## Полезные ссылки

- Полная документация: `DEPLOYMENT.md`
- Конфигурация Nginx: `nginx/telegram-parser.conf`
- Systemd сервисы: `systemd/`
- Пример .env: `.env.production.example`
