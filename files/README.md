# Инструкция по подготовке к деплою

## Инструкция по созданию FTP
В панели хостинга → FTP-аккаунты → Создать:
- Имя: `pradmin@a1109685`
- Пароль: сгенерировать
- **Домашняя папка: `/domains/slqa.ru/public_html/pr/`**


## Настройка секретов в GitHub
Зайдите в репозиторий → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Создайте 4 секрета:

| Имя секрета | Значение |
|-------------|----------|
| `FTP_HOST` | Адрес FTP-сервера |
| `FTP_USER` | Имя пользователя FTP |
| `FTP_PASSWORD` | Пароль от FTP |
| `FTP_PORT` | Порт FTP (обычно 21) |

---

## Создание `.env` на сервере

Зайдите на сервер по FTP и в папке `/domains/slqa.ru/public_html/pr/` создайте файл `.env`:

```env
# Настройки базы данных
DB_HOST=localhost
DB_NAME=название_базы
DB_USER=пользователь_базы
DB_PASS=пароль_базы
DB_PORT=3306

# Настройки сайта
SITE_URL=https://ваш-домен.ru/папка/
ENVIRONMENT=production
```

---

## Проверка структуры проекта

Убедитесь, что структура папок выглядит так:

```
pr/
├── .env.example
├── .htaccess
├── docs/
│   ├── config/
│   │   └── database.php
│   ├── index.php
│   └── (другие файлы сайта)
└── .github/
    └── workflows/
        └── deploy.yml
```

---

## Что делать при переезде на новый сервер

1. Создать новые секреты в GitHub (новые `FTP_HOST`, `FTP_USER`, `FTP_PASSWORD`)
2. Создать `.env` на новом сервере вручную (по шаблону из `.env.example`)
3. Запушить код — деплой зальёт файлы на новый сервер