# tg_parser_bot - база данных (SQLite)
import sqlite3
import os
from datetime import datetime

DB_PATH = "data/leads.db"

def get_conn(db_path: str = DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str = DB_PATH):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            u TEXT PRIMARY KEY,
            kind TEXT,
            subs INTEGER,
            subs_stat INTEGER,
            today_growth INTEGER,
            reach_per_post INTEGER,
            err REAL,
            err24 REAL,
            lang TEXT,
            geo TEXT,
            title TEXT,
            desc TEXT,
            link TEXT,
            cat TEXT,
            sort TEXT,
            kw TEXT,
            source TEXT,
            admin_contact TEXT,
            all_contacts TEXT,
            is_live INTEGER DEFAULT 0,
            is_anomaly INTEGER DEFAULT 0,
            is_dead INTEGER DEFAULT 0,
            skip_captcha INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kw TEXT,
            lang TEXT,
            cat TEXT,
            found INTEGER,
            new INTEGER,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def upsert_lead(rec: dict, db_path: str = DB_PATH):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO leads (
            u, kind, subs, subs_stat, today_growth, reach_per_post, err, err24,
            lang, geo, title, desc, link, cat, sort, kw, source,
            admin_contact, all_contacts, is_live, is_anomaly, is_dead, skip_captcha, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(u) DO UPDATE SET
            kind=excluded.kind,
            subs=excluded.subs,
            subs_stat=excluded.subs_stat,
            today_growth=excluded.today_growth,
            reach_per_post=excluded.reach_per_post,
            err=excluded.err,
            err24=excluded.err24,
            lang=excluded.lang,
            geo=excluded.geo,
            title=excluded.title,
            desc=excluded.desc,
            link=excluded.link,
            cat=excluded.cat,
            sort=excluded.sort,
            kw=excluded.kw,
            source=excluded.source,
            admin_contact=excluded.admin_contact,
            all_contacts=excluded.all_contacts,
            is_live=excluded.is_live,
            is_anomaly=excluded.is_anomaly,
            is_dead=excluded.is_dead,
            skip_captcha=excluded.skip_captcha,
            created_at=excluded.created_at
    """, (
        rec.get("u"), rec.get("kind"), rec.get("subs"), rec.get("subs_stat"),
        rec.get("today_growth"), rec.get("reach_per_post"), rec.get("err"), rec.get("err24"),
        rec.get("lang"), rec.get("geo"), rec.get("title"), rec.get("desc"), rec.get("link"),
        rec.get("cat"), rec.get("sort"), rec.get("kw"), rec.get("source"),
        rec.get("admin_contact"), rec.get("all_contacts"),
        1 if rec.get("is_live") else 0,
        1 if rec.get("is_anomaly") else 0,
        1 if rec.get("is_dead") else 0,
        1 if rec.get("skip_captcha") else 0,
        rec.get("created_at", datetime.utcnow().isoformat()),
    ))
    conn.commit()
    conn.close()

def get_stats(db_path: str = DB_PATH):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as total FROM leads")
    total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) as live FROM leads WHERE is_live=1")
    live = cur.fetchone()["live"]
    cur.execute("SELECT COUNT(*) as anomaly FROM leads WHERE is_anomaly=1")
    anomaly = cur.fetchone()["anomaly"]
    cur.execute("SELECT COUNT(*) as dead FROM leads WHERE is_dead=1")
    dead = cur.fetchone()["dead"]
    cur.execute("SELECT COUNT(*) as captcha FROM leads WHERE skip_captcha=1")
    captcha = cur.fetchone()["captcha"]
    cur.execute("SELECT COUNT(*) as no_err FROM leads WHERE err IS NULL")
    no_err = cur.fetchone()["no_err"]
    conn.close()
    return {
        "total": total, "live": live, "anomaly": anomaly, "dead": dead,
        "captcha": captcha, "no_err": no_err,
    }

def list_leads(db_path: str = DB_PATH, limit: int = 50, offset: int = 0, live_only: bool = False):
    conn = get_conn(db_path)
    cur = conn.cursor()
    q = "SELECT * FROM leads"
    params = []
    if live_only:
        q += " WHERE is_live=1"
    q += " ORDER BY err DESC NULLS LAST LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cur.execute(q, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def search_leads(db_path: str = DB_PATH, kw: str = "", limit: int = 50):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM leads WHERE title LIKE ? OR desc LIKE ? OR u LIKE ? ORDER BY err DESC NULLS LAST LIMIT ?",
        (f"%{kw}%", f"%{kw}%", f"%{kw}%", limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def log_search(kw: str, lang: str, cat: str, found: int, new: int, db_path: str = DB_PATH):
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO search_log (kw, lang, cat, found, new, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (kw, lang, cat, found, new, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
