import json
import os
import sqlite3
from contextlib import contextmanager

from . import seed

DB_PATH = os.environ.get("BRANDLOOM_DB", os.path.join(os.path.dirname(__file__), "..", "data", "brandloom.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT, role TEXT);
CREATE TABLE IF NOT EXISTS rules(id TEXT PRIMARY KEY, category TEXT, title TEXT, text TEXT, severity TEXT,
    kind TEXT, config TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS facts(id TEXT PRIMARY KEY, statement TEXT, keywords TEXT, valid_until TEXT,
    supports TEXT, owner TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS content(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, kind TEXT, channel TEXT,
    author_id TEXT, status TEXT, fg TEXT, bg TEXT, image_path TEXT, alt_text TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY AUTOINCREMENT, content_id INTEGER, n INTEGER, body TEXT,
    note TEXT, author_id TEXT, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS findings(id INTEGER PRIMARY KEY AUTOINCREMENT, content_id INTEGER, revision_id INTEGER,
    rule_id TEXT, category TEXT, severity TEXT, rule_title TEXT, source_quote TEXT, start INTEGER, "end" INTEGER,
    text TEXT, why TEXT, suggestion TEXT, fix TEXT, confidence REAL, needs_human INTEGER, scope TEXT,
    fingerprint TEXT, state TEXT DEFAULT 'open', reason TEXT, resolved_by TEXT, resolved_at TEXT);
CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY AUTOINCREMENT, content_id INTEGER, author_id TEXT,
    body TEXT, created_at TEXT DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, content_id INTEGER, actor TEXT,
    action TEXT, detail TEXT, created_at TEXT DEFAULT (datetime('now')));
"""


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init(reset=False):
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    with conn() as c:
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            for u in seed.USERS:
                c.execute("INSERT INTO users VALUES(?,?,?)", (u["id"], u["name"], u["role"]))
            for r in seed.RULES:
                c.execute("INSERT INTO rules VALUES(?,?,?,?,?,?,?,1)",
                          (r["id"], r["category"], r["title"], r["text"], r["severity"], r["kind"], json.dumps(r["config"])))
            for f in seed.FACTS:
                c.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?)",
                          (f["id"], f["statement"], json.dumps(f["keywords"]), f["valid_until"],
                           json.dumps(f["supports"]), f["owner"], f["source"]))
            c.execute("INSERT INTO settings VALUES('brand',?)", (json.dumps(seed.BRAND),))


def load_library(c):
    rules = []
    for r in c.execute("SELECT * FROM rules ORDER BY id"):
        d = dict(r)
        d["config"] = json.loads(d["config"])
        rules.append(d)
    facts = []
    for f in c.execute("SELECT * FROM facts ORDER BY id"):
        d = dict(f)
        d["keywords"] = json.loads(d["keywords"])
        d["supports"] = json.loads(d["supports"] or "[]")
        facts.append(d)
    brand = json.loads(c.execute("SELECT value FROM settings WHERE key='brand'").fetchone()["value"])
    return {"rules": rules, "facts": facts, "settings": brand}
