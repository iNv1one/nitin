# 🚀 Инструкция по деплою Telegram Parser SaaS на сервер

## Требования к серверу

- **ОС**: Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- **RAM**: минимум 2GB, рекомендуется 4GB+
- **CPU**: 2+ ядра
- **Диск**: минимум 20GB свободного места
- **Python**: 3.11+
- **PostgreSQL**: 13+
- **Redis**: 6+
- **Nginx**: 1.18+

## 1. Подготовка сервера

### 1.1 Обновление системы

```bash
sudo apt update && sudo apt upgrade -y
```

### 1.2 Установка необходимых пакетов

```bash
# Python и зависимости
sudo apt install python3.11 python3.11-venv python3-pip python3-dev -y

# PostgreSQL
sudo apt install postgresql postgresql-contrib -y

# Redis
sudo apt install redis-server -y

# Nginx
sudo apt install nginx -y

# Git
sudo apt install git -y

# Дополнительные инструменты
sudo apt install build-essential libpq-dev supervisor -y
```

## 2. Настройка PostgreSQL

```bash
# Войти в PostgreSQL
sudo -u postgres psql

# Создать базу данных и пользователя
CREATE DATABASE telegram_parser_db;
CREATE USER telegram_parser_user WITH PASSWORD 'your-strong-password';
ALTER ROLE telegram_parser_user SET client_encoding TO 'utf8';
ALTER ROLE telegram_parser_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE telegram_parser_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE telegram_parser_db TO telegram_parser_user;
\q
```

## 3. Настройка Redis

```bash
# Запустить и включить автозапуск Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Проверить статус
sudo systemctl status redis-server
```

## 4. Клонирование проекта

```bash
# Создать директорию для проектов
sudo mkdir -p /var/www
cd /var/www

# Клонировать репозиторий (замените URL на ваш)
sudo git clone https://github.com/yourusername/telegram-parser-saas.git
cd telegram-parser-saas

# Установить владельца
sudo chown -R $USER:www-data /var/www/telegram-parser-saas
```

## 5. Настройка виртуального окружения и зависимостей

```bash
# Создать виртуальное окружение
python3.11 -m venv venv

# Активировать
source venv/bin/activate

# Обновить pip
pip install --upgrade pip

# Установить зависимости
pip install -r requirements.txt
pip install -r requirements.production.txt
```

## 6. Настройка переменных окружения

```bash
# Скопировать пример .env файла
cp .env.production.example .env

# Редактировать .env файл
nano .env
```

**Заполните следующие обязательные переменные:**

```env
SECRET_KEY=your-generated-secret-key-here
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

DB_NAME=telegram_parser_db
DB_USER=telegram_parser_user
DB_PASSWORD=your-strong-password
DB_HOST=localhost
DB_PORT=5432

REDIS_URL=redis://localhost:6379/0

TELEGRAM_API_ID=your-api-id
TELEGRAM_API_HASH=your-api-hash

OPENAI_API_KEY=your-openai-key

DJANGO_SETTINGS_MODULE=config.settings_production
```

**Для генерации SECRET_KEY:**

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## 7. Применение миграций и сбор статики

```bash
# Применить миграции
python manage.py migrate

# Собрать статические файлы
python manage.py collectstatic --noinput

# Создать суперпользователя
python manage.py createsuperuser
```

## 8. Создание директорий для логов

```bash
sudo mkdir -p /var/log/telegram-parser
sudo chown $USER:www-data /var/log/telegram-parser
sudo chmod 775 /var/log/telegram-parser
```

## 9. Настройка Gunicorn (systemd service)

```bash
# Скопировать systemd файлы
sudo cp systemd/telegram-parser.service /etc/systemd/system/

# Отредактировать пути в файле
sudo nano /etc/systemd/system/telegram-parser.service
```

**Замените в файле:**
- `your-username` на ваше имя пользователя
- `/path/to/telegram-parser-saas` на `/var/www/telegram-parser-saas`

```bash
# Перезагрузить systemd
sudo systemctl daemon-reload

# Запустить Gunicorn
sudo systemctl start telegram-parser

# Включить автозапуск
sudo systemctl enable telegram-parser

# Проверить статус
sudo systemctl status telegram-parser
```

## 10. Настройка Celery Worker

```bash
# Скопировать systemd файл
sudo cp systemd/telegram-parser-celery.service /etc/systemd/system/

# Отредактировать пути
sudo nano /etc/systemd/system/telegram-parser-celery.service
```

**Замените:**
- `your-username` на ваше имя пользователя
- `/path/to/telegram-parser-saas` на `/var/www/telegram-parser-saas`

```bash
# Создать директорию для PID файлов
sudo mkdir -p /var/run/celery
sudo chown $USER:www-data /var/run/celery

# Перезагрузить systemd
sudo systemctl daemon-reload

# Запустить Celery
sudo systemctl start telegram-parser-celery

# Включить автозапуск
sudo systemctl enable telegram-parser-celery

# Проверить статус
sudo systemctl status telegram-parser-celery
```

## 11. Настройка Nginx

```bash
# Скопировать конфигурацию Nginx
sudo cp nginx/telegram-parser.conf /etc/nginx/sites-available/telegram-parser

# Отредактировать конфигурацию
sudo nano /etc/nginx/sites-available/telegram-parser
```

**Замените:**
- `yourdomain.com` на ваш домен
- `/path/to/telegram-parser-saas` на `/var/www/telegram-parser-saas`

```bash
# Создать символическую ссылку
sudo ln -s /etc/nginx/sites-available/telegram-parser /etc/nginx/sites-enabled/

# Удалить дефолтную конфигурацию (опционально)
sudo rm /etc/nginx/sites-enabled/default

# Проверить конфигурацию Nginx
sudo nginx -t

# Перезапустить Nginx
sudo systemctl restart nginx

# Включить автозапуск
sudo systemctl enable nginx
```

## 12. Настройка SSL с Let's Encrypt

```bash
# Установить Certbot
sudo apt install certbot python3-certbot-nginx -y

# Получить SSL сертификат
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Certbot автоматически настроит Nginx и создаст auto-renewal
```

## 13. Импорт Telegram чатов

```bash
# Активировать виртуальное окружение
source /var/www/telegram-parser-saas/venv/bin/activate

# Перейти в директорию проекта
cd /var/www/telegram-parser-saas

# Запустить импорт чатов
python manage.py import_my_chats
```

**Важно:** При первом запуске Telethon попросит авторизоваться. Введите номер телефона и код из SMS.

## 14. Проверка работоспособности

### 14.1 Проверка статуса сервисов

```bash
# Gunicorn
sudo systemctl status telegram-parser

# Celery
sudo systemctl status telegram-parser-celery

# Nginx
sudo systemctl status nginx

# PostgreSQL
sudo systemctl status postgresql

# Redis
sudo systemctl status redis-server
```

### 14.2 Проверка логов

```bash
# Gunicorn логи
tail -f /var/log/telegram-parser/gunicorn-error.log

# Celery логи
tail -f /var/log/telegram-parser/celery.log

# Django логи
tail -f /var/log/telegram-parser/django.log

# Nginx логи
tail -f /var/log/nginx/telegram-parser-error.log
```

### 14.3 Открыть сайт

Откройте в браузере: `https://yourdomain.com`

## 15. Автоматический деплой (опционально)

### 15.1 Сделать deploy.sh исполняемым

```bash
chmod +x /var/www/telegram-parser-saas/deploy.sh
```

### 15.2 Запуск деплоя после git pull

```bash
cd /var/www/telegram-parser-saas
git pull origin main
./deploy.sh
```

## 16. Настройка мониторинга (опционально)

### 16.1 Установка supervisor для мониторинга процессов

```bash
sudo apt install supervisor -y
```

### 16.2 Настройка firewall

```bash
# Разрешить SSH, HTTP, HTTPS
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

## 17. Резервное копирование

### 17.1 Backup базы данных

```bash
# Создать backup
pg_dump -U telegram_parser_user telegram_parser_db > backup_$(date +%Y%m%d).sql

# Восстановить backup
psql -U telegram_parser_user telegram_parser_db < backup_20240101.sql
```

### 17.2 Автоматический backup (cron)

```bash
# Добавить в crontab
crontab -e

# Backup каждый день в 3:00
0 3 * * * pg_dump -U telegram_parser_user telegram_parser_db > /var/backups/telegram_parser_$(date +\%Y\%m\%d).sql
```

## Troubleshooting

### Проблема: Gunicorn не запускается

```bash
# Проверить логи
sudo journalctl -u telegram-parser.service -n 50

# Проверить права на socket
ls -la /var/www/telegram-parser-saas/gunicorn.sock
```

### Проблема: Celery не работает

```bash
# Проверить логи
sudo journalctl -u telegram-parser-celery.service -n 50

# Проверить подключение к Redis
redis-cli ping
```

### Проблема: 502 Bad Gateway

```bash
# Проверить, что Gunicorn запущен
sudo systemctl status telegram-parser

# Проверить путь к socket в Nginx конфигурации
sudo nano /etc/nginx/sites-available/telegram-parser
```

### Проблема: Статика не загружается

```bash
# Пересобрать статику
cd /var/www/telegram-parser-saas
source venv/bin/activate
python manage.py collectstatic --noinput

# Проверить права
sudo chown -R $USER:www-data /var/www/telegram-parser-saas/staticfiles
sudo chmod -R 755 /var/www/telegram-parser-saas/staticfiles
```

## Полезные команды

```bash
# Перезапуск всех сервисов
sudo systemctl restart telegram-parser telegram-parser-celery nginx

# Просмотр всех логов одновременно
tail -f /var/log/telegram-parser/*.log

# Проверка использования ресурсов
htop

# Проверка дискового пространства
df -h

# Проверка использования памяти
free -h
```

## Контакты и поддержка

При возникновении проблем:
1. Проверьте логи всех сервисов
2. Убедитесь, что все переменные окружения правильно настроены
3. Проверьте файрвол и сетевые настройки
4. Проверьте права доступа к файлам

---

**Готово! 🎉 Ваш Telegram Parser SaaS теперь работает на production сервере!**
