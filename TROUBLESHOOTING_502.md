# Исправление ошибки 502 Bad Gateway

## Что означает ошибка 502?
502 Bad Gateway означает, что Nginx (веб-сервер) не может связаться с Django приложением (Gunicorn).

## Быстрая диагностика

### 1. Проверьте статус всех сервисов

```bash
# Проверить статус Django
sudo systemctl status telegram-parser

# Проверить статус Celery
sudo systemctl status telegram-parser-celery

# Проверить статус Nginx
sudo systemctl status nginx
```

Ищите строки с ошибками или "failed" / "inactive (dead)".

### 2. Проверьте, запущен ли Gunicorn

```bash
# Проверить процессы Gunicorn
ps aux | grep gunicorn

# Если ничего не найдено - Gunicorn не запущен
```

## Решения

### Решение 1: Перезапустить Django/Gunicorn

```bash
# Перезапустить основной сервис
sudo systemctl restart telegram-parser

# Проверить статус
sudo systemctl status telegram-parser

# Посмотреть логи
sudo journalctl -u telegram-parser -n 50
```

### Решение 2: Проверить логи на ошибки

```bash
# Логи Django/Gunicorn
sudo journalctl -u telegram-parser -f

# Логи Nginx
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log

# Логи приложения (если настроены)
tail -f /path/to/django/logs/django.log
```

### Решение 3: Проверить настройки Gunicorn

Проверьте файл сервиса:
```bash
sudo systemctl cat telegram-parser
```

Убедитесь что:
- `WorkingDirectory` указывает на правильную директорию проекта
- `ExecStart` содержит правильный путь к gunicorn
- Пользователь имеет права на файлы

### Решение 4: Проверить порт и сокет

```bash
# Проверить, слушает ли Gunicorn на порту/сокете
sudo netstat -tlnp | grep gunicorn

# Или
sudo lsof -i :8000  # если используется порт 8000
```

### Решение 5: Проверить права на файлы

```bash
# Перейти в директорию проекта
cd /path/to/telegram-parser-saas

# Проверить владельца
ls -la

# Если нужно, изменить владельца
sudo chown -R www-data:www-data /path/to/telegram-parser-saas

# Или для пользователя, от которого запущен Gunicorn
sudo chown -R your-user:your-user /path/to/telegram-parser-saas
```

### Решение 6: Проверить конфигурацию Nginx

```bash
# Проверить конфигурацию на ошибки
sudo nginx -t

# Посмотреть конфигурацию вашего сайта
sudo cat /etc/nginx/sites-enabled/telegram-parser

# Проверить что upstream указывает на правильный сокет/порт
```

Пример правильной конфигурации:
```nginx
upstream django {
    server unix:/path/to/telegram-parser.sock;
    # или
    # server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://django;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Решение 7: Проверить миграции базы данных

Иногда 502 возникает из-за ошибок в БД:

```bash
cd /path/to/telegram-parser-saas

# Активировать виртуальное окружение
source venv/bin/activate

# Выполнить миграции
python manage.py migrate

# Проверить подключение к БД
python manage.py dbshell
```

### Решение 8: Проверить зависимости Python

```bash
cd /path/to/telegram-parser-saas
source venv/bin/activate

# Установить/обновить зависимости
pip install -r requirements.txt

# Проверить что все импорты работают
python manage.py check
```

## Типичные причины и решения

### Причина: Django не запущен
**Решение:**
```bash
sudo systemctl start telegram-parser
sudo systemctl enable telegram-parser
```

### Причина: Изменения в коде не применены
**Решение:**
```bash
cd /path/to/telegram-parser-saas
git pull
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart telegram-parser
```

### Причина: Неправильный путь к сокету
**Решение:** Проверьте, что путь к сокету в Nginx и Gunicorn одинаковый

### Причина: Нехватка памяти
**Решение:**
```bash
# Проверить память
free -h

# Проверить использование
top

# Если мало памяти - добавить swap или увеличить RAM
```

### Причина: Ошибка в Python коде
**Решение:** Проверьте логи:
```bash
sudo journalctl -u telegram-parser -n 100
```

## Автоматический скрипт проверки

Создайте файл `check_services.sh`:

```bash
#!/bin/bash

echo "=== Проверка сервисов ==="

echo -e "\n1. Django (telegram-parser):"
sudo systemctl status telegram-parser --no-pager | grep Active

echo -e "\n2. Celery (telegram-parser-celery):"
sudo systemctl status telegram-parser-celery --no-pager | grep Active

echo -e "\n3. Nginx:"
sudo systemctl status nginx --no-pager | grep Active

echo -e "\n4. Процессы Gunicorn:"
ps aux | grep gunicorn | grep -v grep | wc -l

echo -e "\n5. Последние ошибки Django:"
sudo journalctl -u telegram-parser -n 5 --no-pager | grep -i error

echo -e "\n6. Последние ошибки Nginx:"
sudo tail -n 5 /var/log/nginx/error.log

echo -e "\n=== Конец проверки ==="
```

Сделайте исполняемым и запустите:
```bash
chmod +x check_services.sh
./check_services.sh
```

## После исправления

1. Перезапустите все сервисы:
```bash
sudo systemctl restart telegram-parser
sudo systemctl restart telegram-parser-celery
sudo systemctl restart nginx
```

2. Проверьте статус:
```bash
sudo systemctl status telegram-parser
sudo systemctl status nginx
```

3. Откройте сайт в браузере и проверьте работу

## Если ничего не помогло

Соберите диагностическую информацию:

```bash
# Создать файл с диагностикой
{
    echo "=== System Info ==="
    uname -a
    echo -e "\n=== Django Service ==="
    sudo systemctl status telegram-parser --no-pager
    echo -e "\n=== Django Logs ==="
    sudo journalctl -u telegram-parser -n 50 --no-pager
    echo -e "\n=== Nginx Config Test ==="
    sudo nginx -t
    echo -e "\n=== Nginx Error Log ==="
    sudo tail -n 20 /var/log/nginx/error.log
    echo -e "\n=== Processes ==="
    ps aux | grep -E 'gunicorn|nginx'
    echo -e "\n=== Ports ==="
    sudo netstat -tlnp | grep -E '80|8000|3000'
} > diagnostic.txt

cat diagnostic.txt
```

Отправьте содержимое `diagnostic.txt` для анализа.
