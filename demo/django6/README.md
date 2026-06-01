# Django 6 Demo Stand

## Bootstrap

```powershell
cd demo\django6
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py ensure_demo_admin
python manage.py runserver
```

## Admin Login

- URL: `http://127.0.0.1:8000/admin/`
- Login: `admin`
- Password: `admin`

## ⚠️ Только для локальной демонстрации — не для продакшена

Стенд намеренно использует небезопасные демо-дефолты и **не должен** разворачиваться в публичной сети как есть:

- `SECRET_KEY` захардкожен в `demo_site/settings.py`;
- `DEBUG = True`;
- `ALLOWED_HOSTS = ["*"]`;
- суперпользователь `admin/admin`.

Целевой рантайм стенда — Python 3.13 / Django 6.x. Для реального использования задайте секрет из окружения, выключите `DEBUG`, ограничьте `ALLOWED_HOSTS` и смените учётные данные.
