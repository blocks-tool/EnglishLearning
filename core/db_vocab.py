"""单词本数据库（复用 data/app.db，兼容旧版数据结构）。"""
import os
import sqlite3
from datetime import datetime

from .paths import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "app.db")

STATUS_UNKNOWN = 0
STATUS_FUZZY = 1
STATUS_FAMILIAR = 2
STATUS_LABELS = {0: "陌生", 1: "模糊", 2: "熟悉"}

_conn = None


def _conn_get():
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def init_db():
    c = _conn_get()
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notebooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notebook_id INTEGER NOT NULL,
            word TEXT NOT NULL,
            phonetic TEXT,
            translation TEXT,
            definition TEXT,
            tag TEXT,
            collins INTEGER DEFAULT 0,
            status INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE,
            UNIQUE(notebook_id, word)
        )
    """)
    cols = {row["name"] for row in cur.execute("PRAGMA table_info(words)")}
    for name, decl in (("example_en", "TEXT DEFAULT ''"),
                       ("example_zh", "TEXT DEFAULT ''"),
                       ("example_source", "TEXT DEFAULT ''")):
        if name not in cols:
            cur.execute(f"ALTER TABLE words ADD COLUMN {name} {decl}")
    cols_nb = {row["name"] for row in cur.execute("PRAGMA table_info(notebooks)")}
    if "sort_order" not in cols_nb:
        cur.execute("ALTER TABLE notebooks ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
    c.commit()


def list_notebooks():
    rows = _conn_get().execute(
        "SELECT n.*, (SELECT COUNT(*) FROM words w WHERE w.notebook_id=n.id) AS count "
        "FROM notebooks n ORDER BY sort_order, id DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def create_notebook(name):
    name = (name or "").strip()
    if not name:
        raise ValueError("单词本名称不能为空")
    c = _conn_get()
    try:
        order = c.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM notebooks").fetchone()[0]
        cur = c.execute(
            "INSERT INTO notebooks(name, created_at, sort_order) VALUES(?,?,?)",
            (name, datetime.now().isoformat(timespec="seconds"), order),
        )
        c.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError(f"单词本「{name}」已存在")


def rename_notebook(nid, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("单词本名称不能为空")
    try:
        _conn_get().execute("UPDATE notebooks SET name=? WHERE id=?", (name, nid))
        _conn_get().commit()
    except sqlite3.IntegrityError:
        raise ValueError(f"单词本「{name}」已存在")


def delete_notebook(nid):
    c = _conn_get()
    c.execute("DELETE FROM words WHERE notebook_id=?", (nid,))
    c.execute("DELETE FROM notebooks WHERE id=?", (nid,))
    c.commit()


def add_words(nid, rows):
    """rows: dict(word, phonetic, translation, definition, tag, collins,
    example_en, example_zh, example_source)。返回 (新增, 重复跳过)。"""
    if not rows:
        return 0, 0
    c = _conn_get()
    now = datetime.now().isoformat(timespec="seconds")
    params = [
        (nid, r["word"].strip().lower(), r.get("phonetic") or "",
         r.get("translation") or "", r.get("definition") or "",
         r.get("tag") or "", r.get("collins") or 0, STATUS_UNKNOWN, now,
         r.get("example_en") or "", r.get("example_zh") or "",
         r.get("example_source") or "")
        for r in rows
    ]
    before = c.total_changes
    c.executemany("""INSERT OR IGNORE INTO words
        (notebook_id, word, phonetic, translation, definition, tag, collins, status,
         created_at, example_en, example_zh, example_source)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", params)
    c.commit()
    added = c.total_changes - before
    return added, len(params) - added


def list_words(nid, statuses=None, keyword=""):
    query = "SELECT * FROM words WHERE notebook_id=?"
    params = [nid]
    if statuses:
        marks = ",".join("?" * len(statuses))
        query += f" AND status IN ({marks})"
        params.extend(statuses)
    if keyword:
        query += " AND (word LIKE ? OR translation LIKE ?)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    query += " ORDER BY id"
    return [dict(r) for r in _conn_get().execute(query, params).fetchall()]


def get_word(wid):
    row = _conn_get().execute("SELECT * FROM words WHERE id=?", (wid,)).fetchone()
    return dict(row) if row else None


def set_status(wid, status):
    c = _conn_get()
    c.execute("UPDATE words SET status=? WHERE id=?", (status, wid))
    c.commit()


def delete_word(wid):
    c = _conn_get()
    c.execute("DELETE FROM words WHERE id=?", (wid,))
    c.commit()


def update_word(wid, translation=None, example_en=None, example_zh=None):
    c = _conn_get()
    fields, params = [], []
    for field, value in (("translation", translation), ("example_en", example_en),
                         ("example_zh", example_zh)):
        if value is not None:
            fields.append(f"{field}=?")
            params.append(value)
    if not fields:
        return
    params.append(wid)
    c.execute(f"UPDATE words SET {', '.join(fields)} WHERE id=?", params)
    c.commit()


def stats(nid):
    row = _conn_get().execute("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status=0 THEN 1 ELSE 0 END) AS unknown,
               SUM(CASE WHEN status=1 THEN 1 ELSE 0 END) AS fuzzy,
               SUM(CASE WHEN status=2 THEN 1 ELSE 0 END) AS familiar
        FROM words WHERE notebook_id=?
    """, (nid,)).fetchone()
    return {
        "total": row["total"] or 0,
        "unknown": row["unknown"] or 0,
        "fuzzy": row["fuzzy"] or 0,
        "familiar": row["familiar"] or 0,
    }


def count_words(nid):
    row = _conn_get().execute(
        "SELECT COUNT(*) AS c FROM words WHERE notebook_id=?", (nid,)
    ).fetchone()
    return row["c"] if row else 0
