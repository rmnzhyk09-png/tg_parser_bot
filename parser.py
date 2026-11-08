# tg_parser_bot - парсер TGStat через Playwright (CDP к Edge)
import asyncio
import json
import os
import re
import random
import sys
import io
from datetime import datetime
from playwright.async_api import async_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from config import (
    CATS as CATS_MAP, LANGS as LANG_MAP, SUB_FROM, SUB_TO,
    ERR_MIN, VIEWS_MIN, DELAY_MIN, DELAY_MAX, DB_PATH,
)

JS_ITEMS = """() => {
  const out = [];
  document.querySelectorAll("a[href*='/channel/'], a[href*='/chat/']").forEach(a => {
    const href = a.getAttribute("href") || "";
    if (!/\\/(channel|chat)\\/(@[^/]+)/.test(href)) return;
    const card = a.closest(".col") || a.parentElement;
    out.push({
      href, kind: href.includes("/chat/") ? "chat" : "channel",
      title: (card.innerText||"").split("\\n")[0].trim(),
      txt: (card.innerText||"").replace(/\\s+/g," ").slice(0,200),
    });
  });
  return out;
}"""

SERVICE_HANDLES = {
    "tgstat","tgstat_chat","telepulse","tgstatapi","tgstat_bot","searcheebot",
    "tgalertsbot","tg_analytics_bot","tgstatchatbot","t.me","joinchat",
}
ADMIN_WORDS = re.compile(
    r"admin|админ|contact|контакт|support|поддержк|help|менеджер|вопрос|пишите|write|"
    r"связь|телеграм|telegram|dm|лс|владелец|создатель|брать|заказать|куп|продаж|обмен|"
    r"менеджер|администратор",
    re.I,
)


class Runner:
    def __init__(self):
        self.pw = None
        self.browser = None
        self.ctx = None
        self.page = None

    async def ensure(self):
        try:
            if self.page and not self.page.is_closed():
                await self.page.evaluate("1")
                return
        except Exception:
            pass
        if self.pw is None:
            self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        self.ctx = self.browser.contexts[0]
        self.page = self.ctx.pages[0] if self.ctx.pages else await self.ctx.new_page()


async def search_page(runner, q: str, langval: str, cats: list):
    await runner.page.goto("https://tgstat.ru/channels/search", timeout=90000)
    await runner.page.wait_for_timeout(3500)
    await runner.page.wait_for_selector("select[name='categories[]']", timeout=15000)
    await runner.page.select_option("select[name='categories[]']", cats)
    try:
        await runner.page.select_option("select[name='countries[]']", [])
    except Exception:
        pass
    await runner.page.select_option("select[name='languages[]']", [str(langval)])
    await runner.page.fill("input[name='participantsCountFrom']", str(SUB_FROM))
    await runner.page.fill("input[name='participantsCountTo']", str(SUB_TO))
    try:
        await runner.page.check("input[name='inAbout']", timeout=2000)
    except Exception:
        pass
    await runner.page.fill("input[name='q']", q)
    await runner.page.locator("input[name='q']").press("Enter")
    await runner.page.wait_for_timeout(7000)
    txt = await runner.page.evaluate("document.body.innerText")
    if "Подозрение на робота" in txt or "проверки безопасности" in txt:
        return "CAPTCHA", []
    return "OK", await runner.page.evaluate(JS_ITEMS)


def find_number_near(lines, idx, direction=1, maxdist=4):
    rng = range(idx + 1, min(len(lines), idx + 1 + maxdist)) if direction == 1 else range(idx - 1, max(-1, idx - 1 - maxdist), -1)
    for j in rng:
        s = lines[j].replace("\u00a0", " ").strip()
        if re.fullmatch(r"-?[\d\s]+", s) and re.search(r"\d", s):
            return int(re.sub(r"\D", "", s))
    return None


def parse_stat(txt):
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    subs = None
    today = None
    reach = None
    for i, l in enumerate(lines):
        if "подписчиков" in l:
            subs = find_number_near(lines, i, 1)
            break
    for i, l in enumerate(lines):
        if l == "за сегодня":
            s = lines[i - 1].replace("\u00a0", " ").strip() if i > 0 else ""
            if re.fullmatch(r"-?[\d\s]+", s) and re.search(r"\d", s):
                today = int(re.sub(r"\D", "", s))
            break
    for i, l in enumerate(lines):
        if "охват 1 поста" in l:
            s = l.split("охват")[0].replace("\u00a0", " ").strip()
            if re.fullmatch(r"-?[\d\s]+", s) and re.search(r"\d", s):
                reach = int(re.sub(r"\D", "", s))
            else:
                reach = find_number_near(lines, i, -1)
            break
    return subs, today, reach


async def parse_channel_page(runner, kind: str, uname: str):
    await runner.page.goto(f"https://tgstat.ru/{kind}/@{uname}", timeout=60000)
    await runner.page.wait_for_timeout(2000)
    txt = await runner.page.evaluate("document.body.innerText")
    if "Подозрение на робота" in txt or "проверки безопасности" in txt:
        return None, "CAPTCHA"
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    rec = {}
    try:
        si = next(i for i, l in enumerate(lines) if l.startswith("@"))
        ei = next(i for i, l in enumerate(lines[si:], si) if l == "Связанные каналы")
        rec["desc"] = " ".join(lines[si + 1:ei])[:800]
    except Exception:
        rec["desc"] = ""
    rec["title"] = lines[1] if len(lines) > 1 else ""
    geo = lang = ""
    try:
        gi = next(i for i, l in enumerate(lines) if re.fullmatch(r"Гео и язык (канала|чата)", l))
        gll = lines[gi + 1] if gi + 1 < len(lines) else ""
        parts = [x.strip() for x in gll.split(",")]
        geo = parts[0] if parts else ""
        lang = parts[1] if len(parts) > 1 else ""
    except Exception:
        pass
    rec["geo"] = geo
    rec["lang"] = lang
    contacts = []
    for m in re.finditer(r"@([A-Za-z0-9_]{4,32})", rec["desc"]):
        u = m.group(1)
        if u.lower() in SERVICE_HANDLES:
            continue
        ctx2 = rec["desc"][max(0, m.start() - 100): m.end() + 40]
        contacts.append({"handle": u, "in_admin_context": bool(ADMIN_WORDS.search(ctx2))})
    seenh = set()
    out = []
    for c in contacts:
        if c["handle"].lower() in seenh:
            continue
        seenh.add(c["handle"].lower())
        out.append(c)
    rec["contacts"] = out
    return rec, "OK"


async def get_stat(runner, kind: str, uname: str):
    if kind == "chat":
        return None, "CHAT_NO_ERR"
    await runner.page.goto(f"https://tgstat.ru/{kind}/@{uname}/stat", timeout=60000)
    await runner.page.wait_for_timeout(2000)
    txt = await runner.page.evaluate("document.body.innerText")
    if "Подозрение на робота" in txt or "проверки безопасности" in txt:
        return None, "CAPTCHA"
    d = {}
    m = re.search(r"([\d.,]+)%\s*ERR\b", txt) or re.search(r"\(ERR\)\s*([\d.,]+)%", txt)
    if m:
        try:
            d["err"] = float(m.group(1).replace(",", "."))
        except Exception:
            pass
    m = re.search(r"([\d.,]+)%\s*ERR24\b", txt)
    if m:
        try:
            d["err24"] = float(m.group(1).replace(",", "."))
        except Exception:
            pass
    return d, "OK"


async def run_search(keyword: str, lang: str, cat: str, cats: list, limit: int = 30):
    """Один поисковый запрос к TGStat. Возвращает список кандидатов."""
    runner = Runner()
    await runner.ensure()
    status, items = await search_page(runner, keyword, lang, cats)
    if status == "CAPTCHA":
        await runner.browser.close()
        runner.browser = None
        return "CAPTCHA", []
    new = []
    for it in items:
        m = re.search(r"/(channel|chat)/(@[^/]+)/", it["href"] + "/")
        if not m:
            continue
        u = m.group(2)
        if u in seen_global:
            continue
        seen_global.add(u)
        ms = re.search(r"([\d\s\u00a0]{1,15})\s*(?:подписчик|участник)", it["txt"])
        subs = int(re.sub(r"\D", "", ms.group(1))) if ms else None
        new.append({
            "u": u, "kind": it.get("kind", "channel"), "title": it.get("title", ""),
            "subs": subs, "kw": keyword, "lang": lang, "txt": it["txt"],
            "cat": cat, "sort": "search",
        })
    await runner.browser.close()
    runner.browser = None
    return "OK", new


seen_global = set()

async def enrich_candidate(runner, rec: dict):
    uname = rec["u"].lstrip("@")
    kind = rec.get("kind", "channel")
    full = dict(rec)
    try:
        cd, st = await parse_channel_page(runner, kind, uname)
        if st == "CAPTCHA":
            rec["skip_captcha"] = True
            return rec
        rec.update(cd or {})
    except Exception as e:
        rec["page_err"] = str(e)[:60]
        try:
            await runner.ensure()
        except Exception:
            pass
    try:
        sd, st = await get_stat(runner, kind, uname)
        if st == "CAPTCHA":
            rec["skip_captcha"] = True
            return rec
        if sd:
            rec.update(sd)
    except Exception as e:
        rec["stat_err"] = str(e)[:60]
    #ライブ判定
    subs = rec.get("subs_stat") or rec.get("subs")
    err = rec.get("err")
    reach = rec.get("reach_per_post")
    rec["is_live"] = bool(subs and err is not None and err > ERR_MIN and reach is not None and reach >= VIEWS_MIN)
    rec["is_anomaly"] = bool(subs and rec.get("today_growth") is not None and rec["today_growth"] > subs * 0.5)
    rec["is_dead"] = bool(reach is not None and reach < VIEWS_MIN)
    contacts = rec.get("contacts") or []
    admin = next((c["handle"] for c in contacts if c.get("in_admin_context")), contacts[0]["handle"] if contacts else "")
    rec["admin_contact"] = admin
    rec["all_contacts"] = ", ".join(c["handle"] for c in contacts)
    rec["created_at"] = datetime.utcnow().isoformat()
    return rec


async def batch_enrich(cands: list):
    runner = Runner()
    await runner.ensure()
    enriched = []
    skipped = 0
    for i, rec in enumerate(cands, 1):
        try:
            if not (runner.page and not runner.page.is_closed()):
                await runner.ensure()
            rec = await enrich_candidate(runner, rec)
            enriched.append(rec)
            if rec.get("skip_captcha"):
                skipped += 1
                print(f"[{i}/{len(cands)}] {rec['u']} CAPTCHA -> skip", flush=True)
            else:
                print(f"[{i}/{len(cands)}] {rec['u']} subs={rec.get('subs_stat')} err={rec.get('err')} reach={rec.get('reach_per_post')} live={rec.get('is_live')}", flush=True)
        except Exception as e:
            rec["err"] = str(e)[:60]
            enriched.append(rec)
            try:
                await runner.ensure()
            except Exception:
                pass
        if i % 10 == 0:
            await runner.page.wait_for_timeout(2000)
        else:
            await runner.page.wait_for_timeout(1000)
    await runner.browser.close()
    runner.browser = None
    return enriched, skipped
