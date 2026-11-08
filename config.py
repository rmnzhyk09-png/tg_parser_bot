# tg_parser_bot - конфигурация
# Скопируйте .env.example в .env или задайте переменные окружения.
# Токен в репозиторий не коммитится.

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN", "")   # Получите у @BotFather и положите в .env
ADMIN_IDS = []                      # список ID администраторов (может быть пустым)

# Диапазон подписчиков для фильтрации
SUB_FROM = 300
SUB_TO = 9000

# Минимальный ERR и просмотры на пост
ERR_MIN = 15
VIEWS_MIN = 150

# Категории TGStat (slug -> название)
CATEGORIES = {
    "crypto": "Криптовалюты",
    "economics": "Экономика",
    "business": "Бизнес и стартапы",
    "sales": "Продажи",
    "other": "Другое",
    "telegram": "Telegram",
    "apps": "Софт и приложения",
    "tech": "Технологии",
}

# Алиасы для parser.py (исторические имена)
CATS = CATEGORIES
LANGS = LANGUAGES

# Задержка между запросами к TGStat (сек), чтобы не ловить капчу
DELAY_MIN = 45
DELAY_MAX = 75

# Пути к файлам
DB_PATH = "data/leads.db"
EXPORT_DIR = "exports"
SESSION_DIR = "sessions"

# Языки (код TGStat -> название)
LANGUAGES = {
    "3": "Русский",
    "12": "Английский",
    "18": "Испанский",
    "14": "Португальский",
    "31": "Немецкий",
    "16": "Турецкий",
    "23": "Французский",
    "8": "Итальянский",
    "9": "Арабский",
    "52": "Хинди",
    "55": "Китайский",
    "7": "Индонезийский",
    "53": "Японский",
    "66": "Корейский",
}
