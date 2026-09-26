"""SQLite-Datenhaltung. Bewusst ohne ORM, damit das Projekt klein bleibt."""
import sqlite3
import threading
from contextlib import contextmanager

from . import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT DEFAULT '',
    total_area_m2 REAL,          -- Gesamtwohnfläche der WEG
    unit_area_m2 REAL,           -- Wohnfläche der eigenen Einheit
    mea_share REAL,              -- Miteigentumsanteil als Bruch, z. B. 85/10000 -> 0.0085
    price_eur REAL,
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    doc_type TEXT NOT NULL DEFAULT 'sonstiges',
    doc_year INTEGER,
    path TEXT NOT NULL,
    pages INTEGER DEFAULT 0,
    ocr_pages INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'wartet',
    progress TEXT DEFAULT '',
    error TEXT DEFAULT '',
    ai_status TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS pages (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER NOT NULL,
    text TEXT NOT NULL,
    ocr INTEGER DEFAULT 0,
    PRIMARY KEY (document_id, page_no)
);
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER,
    source TEXT NOT NULL,        -- 'regel' oder 'ki'
    category TEXT NOT NULL,
    severity TEXT NOT NULL,      -- 'hoch', 'mittel', 'info'
    title TEXT NOT NULL,
    detail TEXT DEFAULT '',
    snippet TEXT DEFAULT '',
    amount_eur REAL,
    verified INTEGER DEFAULT 1,  -- KI: Zitat im Dokument gefunden?
    hits INTEGER DEFAULT 1,
    dismissed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS figures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id INTEGER NOT NULL REFERENCES objects(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no INTEGER,
    kind TEXT NOT NULL,          -- 'ruecklage_stand', 'ruecklage_zufuehrung', 'hausgeld_gesamt', 'sonderumlage'
    value_eur REAL NOT NULL,
    context TEXT DEFAULT '',
    year INTEGER,
    chosen INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS summaries (
    object_id INTEGER PRIMARY KEY REFERENCES objects(id) ON DELETE CASCADE,
    status TEXT DEFAULT '',
    text TEXT DEFAULT '',
    model TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findings_obj ON findings(object_id);
CREATE INDEX IF NOT EXISTS idx_docs_obj ON documents(object_id);
"""


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA foreign_keys = ON")
            _conn.execute("PRAGMA journal_mode = WAL")
            _conn.executescript(SCHEMA)
            _conn.commit()
        return _conn


@contextmanager
def tx():
    with _lock:
        c = conn()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


def q(sql: str, params=()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, params).fetchall()]


def q1(sql: str, params=()) -> dict | None:
    rows = q(sql, params)
    return rows[0] if rows else None


def ex(sql: str, params=()) -> int:
    with tx() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid
