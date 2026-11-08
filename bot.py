# tg_parser_bot - Telegram-бот на aiogram 3.x
import asyncio
import json
import os
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import (
    BOT_TOKEN, ADMIN_IDS, SUB_FROM, SUB_TO, ERR_MIN, VIEWS_MIN,
    DELAY_MIN, DELAY_MAX, CATEGORIES, LANGUAGES, DB_PATH, EXPORT_DIR,
)
from db import (
    init_db, upsert_lead, get_stats, list_leads, search_leads, log_search,
)
from parser import run_search, batch_enrich, seen_global

os.makedirs(EXPORT_DIR, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class SearchStates(StatesGroup):
    waiting_kw = State()


def main_kb() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="🔍 Поиск по ключу", callback_data="search_kw")],
        [InlineKeyboardButton(text="📂 Поиск по категории", callback_data="search_cat")],
        [InlineKeyboardButton(text="📊 Статистика базы", callback_data="stats")],
        [InlineKeyboardButton(text="📤 Экспорт в Excel", callback_data="export_xlsx")],
        [InlineKeyboardButton(text="📤 Экспорт в TXT", callback_data="export_txt")],
        [InlineKeyboardButton(text="✅ Только живые (ERR>15%, охват>=150)", callback_data="list_live")],
        [InlineKeyboardButton(text="❌ Стоп парсинга", callback_data="stop")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


@dp.message(Command("start"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(
        "Бот-парсер каналов Telegram для поиска аудитории обмена крипты/валюты.\n"
        "Ищет на TGStat по ключевым словам и категориям, проверяет:\n"
        f"• подписчики {SUB_FROM}–{SUB_TO}\n"
        f"• ERR > {ERR_MIN}%\n"
        f"• просмотры на пост >= {VIEWS_MIN}\n"
        "• наличие контакта админа в описании\n\n"
        "Выберите действие:", reply_markup=main_kb()
    )


@dp.message(Command("stats"))
async def cmd_stats(m: Message):
    st = get_stats()
    txt = (
        f"📊 Статистика базы:\n"
        f"Всего каналов: {st['total']}\n"
        f"Живые (ERR>{ERR_MIN}%, охват>={VIEWS_MIN}): {st['live']}\n"
        f"Аномалия роста: {st['anomaly']}\n"
        f"Мёртвые (охват<{VIEWS_MIN}): {st['dead']}\n"
        f"Без данных ERR: {st['no_err']}\n"
        f"Капча (пропущены): {st['captcha']}\n"
    )
    await m.answer(txt, reply_markup=main_kb())


@dp.message(Command("export"))
async def cmd_export(m: Message):
    await m.answer("Выберите формат:", reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Excel (.xlsx)", callback_data="export_xlsx")],
            [InlineKeyboardButton(text="Текст (.txt)", callback_data="export_txt")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
        ]
    ))


@dp.message(Command("check"))
async def cmd_check(m: Message, state: FSMContext):
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        await m.answer("Укажите username канала: /check @username")
        return
    uname = args[1].lstrip("@")
    await state.set_state(SearchStates.waiting_kw)
    await state.update_data(check_uname=uname)
    await m.answer(f"Проверяю канал @{uname}... подождите.")
    await process_check(m, uname)


@dp.callback_query(F.data == "search_kw")
async def cb_search_kw(cq: CallbackQuery, state: FSMContext):
    await state.set_state(SearchStates.waiting_kw)
    await cq.message.answer("Введите ключевое слово для поиска (например: обмен валюты дубай):")
    await cq.answer()


@dp.callback_query(F.data == "search_cat")
async def cb_search_cat(cq: CallbackQuery):
    rows = []
    for slug, name in CATEGORIES.items():
        rows.append([InlineKeyboardButton(text=name, callback_data=f"cat_{slug}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")])
    await cq.message.edit_text("Выберите категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cq.answer()


@dp.callback_query(F.data.startswith("cat_"))
async def cb_cat(cq: CallbackQuery, state: FSMContext):
    slug = cq.data.split("_", 1)[1]
    await state.update_data(cat=slug)
    await state.set_state(SearchStates.waiting_kw)
    await cq.message.answer(f"Категория: {CATEGORIES.get(slug, slug)}. Введите ключевое слово (или отправьте '-' для поиска без ключа):")
    await cq.answer()


@dp.callback_query(F.data == "stats")
async def cb_stats(cq: CallbackQuery):
    st = get_stats()
    txt = (
        f"📊 Статистика базы:\n"
        f"Всего каналов: {st['total']}\n"
        f"Живые (ERR>{ERR_MIN}%, охват>={VIEWS_MIN}): {st['live']}\n"
        f"Аномалия роста: {st['anomaly']}\n"
        f"Мёртвые (охват<{VIEWS_MIN}): {st['dead']}\n"
        f"Без данных ERR: {st['no_err']}\n"
        f"Капча (пропущены): {st['captcha']}\n"
    )
    await cq.message.edit_text(txt, reply_markup=main_kb())
    await cq.answer()


@dp.callback_query(F.data == "export_xlsx")
async def cb_export_xlsx(cq: CallbackQuery):
    path = os.path.join(EXPORT_DIR, "leads.xlsx")
    if not os.path.exists(path):
        await cq.message.answer("Файл ещё не создан. Сначала выполните поиск.")
        await cq.answer()
        return
    await cq.message.answer_document(FSInputFile(path), caption="Экспорт лидов (Excel)")
    await cq.answer()


@dp.callback_query(F.data == "export_txt")
async def cb_export_txt(cq: CallbackQuery):
    path = os.path.join(EXPORT_DIR, "leads.txt")
    if not os.path.exists(path):
        await cq.message.answer("Файл ещё не создан. Сначала выполните поиск.")
        await cq.answer()
        return
    await cq.message.answer_document(FSInputFile(path), caption="Экспорт лидов (TXT)")
    await cq.answer()


@dp.callback_query(F.data == "list_live")
async def cb_list_live(cq: CallbackQuery):
    rows = list_leads(limit=20, live_only=True)
    if not rows:
        await cq.message.answer("Живых каналов пока нет. Выполните поиск.")
        await cq.answer()
        return
    txt = "✅ Живые каналы (первые 20):\n\n"
    for r in rows:
        txt += f"• {r['link']} | subs={r['subs_stat'] or r['subs']} | ERR={r['err']} | охват={r['reach_per_post']} | {r['admin_contact'] or 'без контакта'}\n"
    await cq.message.edit_text(txt[:4000], reply_markup=main_kb())
    await cq.answer()


@dp.callback_query(F.data == "stop")
async def cb_stop(cq: CallbackQuery):
    await cq.message.edit_text("Остановка запрошена. Завершу текущую операцию...", reply_markup=main_kb())
    await cq.answer()


@dp.callback_query(F.data == "back_main")
async def cb_back(cq: CallbackQuery):
    await cq.message.edit_text("Главное меню:", reply_markup=main_kb())
    await cq.answer()


@dp.callback_query(F.data == "cancel")
async def cb_cancel(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await cq.message.edit_text("Отменено.", reply_markup=main_kb())
    await cq.answer()


@dp.message(SearchStates.waiting_kw)
async def handle_kw(m: Message, state: FSMContext):
    data = await state.get_data()
    check_uname = data.get("check_uname")
    if check_uname:
        await state.clear()
        await process_check(m, check_uname)
        return
    kw = m.text.strip()
    if kw == "-":
        kw = ""
    cat = data.get("cat", "crypto")
    lang = data.get("lang", "3")
    await state.clear()
    await m.answer(f"Начинаю поиск: '{kw}' в категории {CATEGORIES.get(cat, cat)}...\nЭто может занять некоторое время.")
    await run_search_flow(m, kw, lang, cat)


async def process_check(m: Message, uname: str):
    from parser import Runner, parse_channel_page, get_stat, enrich_candidate
    runner = Runner()
    await runner.ensure()
    try:
        if not (runner.page and not runner.page.is_closed()):
            await runner.ensure()
        rec = {"u": uname, "kind": "channel", "title": "", "subs": None, "kw": "manual", "lang": "", "txt": "", "cat": "", "sort": "manual"}
        rec = await enrich_candidate(runner, rec)
    finally:
        try:
            await runner.browser.close()
        except Exception:
            pass
    upsert_lead(rec)
    st = get_stats()
    txt = (
        f"✅ Проверено: @{uname}\n"
        f"Подписчики: {rec.get('subs_stat') or rec.get('subs')}\n"
        f"ERR: {rec.get('err')}\n"
        f"Охват/пост: {rec.get('reach_per_post')}\n"
        f"Язык: {rec.get('lang')} | Гео: {rec.get('geo')}\n"
        f"Контакт: {rec.get('admin_contact') or 'не найден'}\n"
        f"Живой: {'да' if rec.get('is_live') else 'нет'}\n"
        f"Всего в базе: {st['total']} (живых {st['live']})"
    )
    await m.answer(txt, reply_markup=main_kb())


async def run_search_flow(m: Message, kw: str, lang: str, cat: str):
    cats = [cat]
    status, items = await run_search(kw, lang, cat, cats)
    if status == "CAPTCHA":
        await m.answer("⚠️ TGStat показал капчу. Поиск остановлен. Попробуйте позже.", reply_markup=main_kb())
        return
    if not items:
        await m.answer("Ничего не найдено по этому запросу.", reply_markup=main_kb())
        return
    await m.answer(f"Найдено {len(items)} каналов. Начинаю проверку каждого (ERR, охват, контакты)...")
    enriched, skipped = await batch_enrich(items)
    for rec in enriched:
        upsert_lead(rec)
    log_search(kw, lang, cat, len(items), len(enriched))
    st = get_stats()
    live = sum(1 for r in enriched if r.get("is_live"))
    txt = (
        f"✅ Поиск завершён.\n"
        f"Найдено: {len(items)}\n"
        f"Проверено: {len(enriched)}\n"
        f"Живых (ERR>{ERR_MIN}%, охват>={VIEWS_MIN}): {live}\n"
        f"Пропущено капчей: {skipped}\n"
        f"Всего в базе: {st['total']}\n"
    )
    await m.answer(txt, reply_markup=main_kb())


@dp.message()
async def fallback(m: Message):
    await m.answer("Используйте кнопки меню или команды /start, /stats, /export, /check @username", reply_markup=main_kb())


async def export_to_files():
    rows = list_leads(limit=10000)
    # Excel
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        wb = Workbook()
        ws = wb.active
        ws.title = "leads"
        ws.append(["Ссылка", "Тип", "Подписчики", "ERR%", "ERR24%", "Охват/пост", "Язык", "Гео", "Контакт админа", "Все контакты", "Название", "Описание"])
        for c in ws[1]:
            c.font = Font(bold=True)
        for r in rows:
            ws.append([
                r["link"], r["kind"], r["subs_stat"] or r["subs"], r["err"], r["err24"],
                r["reach_per_post"], r["lang"], r["geo"], r["admin_contact"] or "",
                r["all_contacts"] or "", r["title"] or "", r["desc"] or "",
            ])
        for col, w in zip("ABCDEFGHIJKL", [34, 10, 12, 10, 10, 12, 10, 20, 22, 40, 50, 80]):
            ws.column_dimensions[col].width = w
        xlsx_path = os.path.join(EXPORT_DIR, "leads.xlsx")
        wb.save(xlsx_path)
    except Exception as e:
        xlsx_path = None
        print("Excel export error:", e)
    # TXT
    txt_path = os.path.join(EXPORT_DIR, "leads.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(r["link"] + "\n")
    return xlsx_path, txt_path


async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
