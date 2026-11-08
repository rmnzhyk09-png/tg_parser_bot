# TG Parser Bot

Бот для поиска и проверки Telegram-каналов/чатов (обмен крипты, валюты, заработок) через TGStat.

## Что делает
1. Ищет каналы на TGStat по ключевому слову и категории (фильтр подписчиков 300–9000).
2. Проверяет каждый канал:
   - подписчики, ERR, ERR24
   - охват 1 поста
   - язык и гео аудитории
   - контакт админа в описании
3. Отмечает "живые" каналы (ERR > 15% и просмотры >= 150).
4. Экспортирует в Excel и TXT.

## Быстрый старт

```bash
# 1. Перейдите в папку
cd tg_parser_bot

# 2. Установите зависимости
pip install -r requirements.txt

# 3. Создайте .env на основе .env.example и укажите токен бота (получите у @BotFather)
#    cp .env.example .env
#    BOT_TOKEN=123456:ABC...

# 4. Запустите Edge с отладочным портом (для парсинга TGStat):
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\AppData\Local\Temp\opencode\edge_profile"

# 5. Запустите бота
python bot.py
```

## Команды бота
- `/start` — главное меню
- `/stats` — статистика базы лидов
- `/export` — экспорт в Excel/TXT
- `/check @username` — проверить конкретный канал

## Структура файлов
- `config.py` — настройки (токен, диапазоны, категории)
- `db.py` — SQLite база (`data/leads.db`)
- `parser.py` — парсер TGStat (Playwright + CDP)
- `bot.py` — aiogram-бот
- `requirements.txt` — зависимости
- `data/leads.db` — собранные лиды
- `exports/` — файлы Excel/TXT

## Безопасность
- Токен бота хранится только в `.env` (файл в `.gitignore`) и не попадает в репозиторий.
- Если токен когда-либо попадал в публичный доступ — перевыпустите его у `@BotFather`.

## Важно
- TGStat может показывать капчу при частых запросах — бот делает паузы 45–75 сек между запросами.
- Для парсинга нужен запущенный Edge с `--remote-debugging-port=9222`.
- Бот не отправляет спам — он только собирает публичную статистику каналов.
