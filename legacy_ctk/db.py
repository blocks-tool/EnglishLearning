"""应用数据库：单词本、单词、学习状态标记。
桌面单用户场景，使用模块级共享连接，省去每次建连/关连开销。"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "app.db")

# 学习状态
STATUS_UNKNOWN = 0   # 陌生
STATUS_FUZZY = 1     # 模糊
STATUS_FAMILIAR = 2  # 熟悉
STATUS_LABELS = {0: "陌生", 1: "模糊", 2: "熟悉"}

_app_conn = None


def _conn():
    global _app_conn
    if _app_conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _app_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _app_conn.row_factory = sqlite3.Row
    return _app_conn


def init_db():
    c = _conn()
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notebooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
    """)
    notebook_columns = {row["name"] for row in cur.execute("PRAGMA table_info(notebooks)")}
    if "sort_order" not in notebook_columns:
        cur.execute("ALTER TABLE notebooks ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        notebook_ids = cur.execute("SELECT id FROM notebooks ORDER BY id DESC").fetchall()
        cur.executemany(
            "UPDATE notebooks SET sort_order=? WHERE id=?",
            ((index, row["id"]) for index, row in enumerate(notebook_ids)),
        )
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
    c.commit()


# ---------- 单词本 ----------
def list_notebooks():
    rows = _conn().execute("SELECT * FROM notebooks ORDER BY sort_order, id DESC").fetchall()
    return [dict(r) for r in rows]


def create_notebook(name):
    """返回新建单词本 id。"""
    name = name.strip()
    if not name:
        raise ValueError("单词本名称不能为空")
    c = _conn()
    try:
        next_order = c.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM notebooks"
        ).fetchone()[0]
        cur = c.execute("INSERT INTO notebooks(name, created_at, sort_order) VALUES(?,?,?)",
                        (name, datetime.now().isoformat(timespec="seconds"), next_order))
        c.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError(f"单词本「{name}」已存在")


def rename_notebook(nid, name):
    name = name.strip()
    if not name:
        raise ValueError("单词本名称不能为空")
    c = _conn()
    try:
        c.execute("UPDATE notebooks SET name=? WHERE id=?", (name, nid))
        c.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f"单词本「{name}」已存在")


def delete_notebook(nid):
    c = _conn()
    c.execute("DELETE FROM words WHERE notebook_id=?", (nid,))
    c.execute("DELETE FROM notebooks WHERE id=?", (nid,))
    c.commit()


def reorder_notebooks(notebook_ids):
    """按传入顺序保存所有单词本的排序。"""
    c = _conn()
    rows = c.execute("SELECT id FROM notebooks").fetchall()
    existing_ids = {row["id"] for row in rows}
    ordered_ids = list(notebook_ids)
    if len(ordered_ids) != len(existing_ids) or set(ordered_ids) != existing_ids:
        raise ValueError("单词本排序列表与数据库内容不一致")
    c.executemany(
        "UPDATE notebooks SET sort_order=? WHERE id=?",
        ((index, notebook_id) for index, notebook_id in enumerate(ordered_ids)),
    )
    c.commit()


# ---------- 单词 ----------
def add_words(nid, word_rows):
    """word_rows: list of dict(word, phonetic, translation, definition, tag, collins)。
    批量 INSERT OR IGNORE，一次事务。返回 (新增数, 跳过重复数)。"""
    if not word_rows:
        return 0, 0
    c = _conn()
    now = datetime.now().isoformat(timespec="seconds")
    params = [
        (nid, w["word"].strip().lower(), w.get("phonetic") or "",
         w.get("translation") or "", w.get("definition") or "",
         w.get("tag") or "", w.get("collins") or 0, STATUS_UNKNOWN, now)
        for w in word_rows
    ]
    before = c.total_changes
    c.executemany("""INSERT OR IGNORE INTO words(notebook_id, word, phonetic, translation,
                      definition, tag, collins, status, created_at)
                      VALUES(?,?,?,?,?,?,?,?,?)""", params)
    c.commit()
    added = c.total_changes - before
    return added, len(params) - added


def list_words(nid, status=None):
    c = _conn()
    if status is None:
        rows = c.execute("SELECT * FROM words WHERE notebook_id=? ORDER BY id", (nid,)).fetchall()
    else:
        rows = c.execute("SELECT * FROM words WHERE notebook_id=? AND status=? ORDER BY id",
                         (nid, status)).fetchall()
    return [dict(r) for r in rows]


def list_word_statuses(nid):
    """仅读取单词 ID 和学习状态，供轻量刷新使用。"""
    rows = _conn().execute(
        "SELECT id, status FROM words WHERE notebook_id=?",
        (nid,),
    ).fetchall()
    return [dict(row) for row in rows]


def delete_word(wid):
    c = _conn()
    c.execute("DELETE FROM words WHERE id=?", (wid,))
    c.commit()


def set_status(wid, status):
    c = _conn()
    c.execute("UPDATE words SET status=? WHERE id=?", (status, wid))
    c.commit()


def update_word(wid, translation, definition, phonetic):
    """修改单词的释义/音标（空串表示清空）。"""
    c = _conn()
    c.execute("UPDATE words SET translation=?, definition=?, phonetic=? WHERE id=?",
              (translation or "", definition or "", phonetic or "", wid))
    c.commit()


def stats(nid):
    """返回 {total, unknown, fuzzy, familiar}。"""
    row = _conn().execute("""
        SELECT
          COUNT(*) AS total,
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
