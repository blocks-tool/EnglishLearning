"""口语学习助手数据库：分组 + 素材（文章/音频/视频）。"""
import json
import os
import sqlite3
from datetime import datetime

from .paths import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "speaking.db")

DEMO_ARTICLE = (
    "Japan is a beautiful country with a rich culture and long history. "
    "I traveled to Japan last spring. I visited Tokyo, Kyoto, and Osaka. "
    "The people were friendly, and the food was amazing. "
    "I enjoyed the cherry blossoms and learned a lot about Japanese culture. "
    "It was an unforgettable experience."
)

_conn = None


def _conn_get():
    global _conn
    if _conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def init_db():
    c = _conn_get()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT DEFAULT '',
            path TEXT DEFAULT '',
            subtitles TEXT DEFAULT '[]',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
        );
    """)
    c.commit()
    if not c.execute("SELECT COUNT(*) FROM groups").fetchone()[0]:
        _seed()


def _seed():
    c = _conn_get()
    now = datetime.now().isoformat(timespec="seconds")
    groups = ["日常英语", "影视素材", "新闻听力", "其他"]
    ids = []
    for i, name in enumerate(groups):
        cur = c.execute("INSERT INTO groups(name, sort_order, created_at) VALUES(?,?,?)",
                        (name, i, now))
        ids.append(cur.lastrowid)
    c.execute("""INSERT INTO materials(group_id, kind, title, content, sort_order, created_at)
                 VALUES(?,?,?,?,?,?)""", (ids[0], "article", "Travel to Japan", DEMO_ARTICLE, 0, now))
    c.execute("""INSERT INTO materials(group_id, kind, title, content, sort_order, created_at)
                 VALUES(?,?,?,?,?,?)""",
              (ids[0], "article", "自我介绍",
               "Good morning. My name is Li Hua, and I am a junior student majoring in computer science. "
               "I enjoy reading and playing badminton in my spare time. "
               "I hope to improve my spoken English and make new friends here.", 1, now))
    c.execute("""INSERT INTO materials(group_id, kind, title, content, sort_order, created_at)
                 VALUES(?,?,?,?,?,?)""",
              (ids[1], "article", "The Pursuit of Happyness",
               "Don't ever let somebody tell you that you can't do something. "
               "You got a dream, you gotta protect it. "
               "If you want something, go get it. Period.", 0, now))
    c.commit()


def list_groups():
    return [dict(r) for r in _conn_get().execute(
        "SELECT * FROM groups ORDER BY sort_order, id").fetchall()]


def create_group(name):
    name = (name or "").strip()
    if not name:
        raise ValueError("分组名称不能为空")
    c = _conn_get()
    order = c.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM groups").fetchone()[0]
    cur = c.execute("INSERT INTO groups(name, sort_order, created_at) VALUES(?,?,?)",
                    (name, order, datetime.now().isoformat(timespec="seconds")))
    c.commit()
    return cur.lastrowid


def rename_group(gid, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("分组名称不能为空")
    c = _conn_get()
    c.execute("UPDATE groups SET name=? WHERE id=?", (name, gid))
    c.commit()


def delete_group(gid):
    c = _conn_get()
    for row in c.execute("SELECT path FROM materials WHERE group_id=?", (gid,)).fetchall():
        path = row["path"]
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    c.execute("DELETE FROM materials WHERE group_id=?", (gid,))
    c.execute("DELETE FROM groups WHERE id=?", (gid,))
    c.commit()


def add_material(gid, kind, title, content="", path="", subtitles=None):
    c = _conn_get()
    order = c.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM materials WHERE group_id=?",
                      (gid,)).fetchone()[0]
    cur = c.execute("""INSERT INTO materials
        (group_id, kind, title, content, path, subtitles, sort_order, created_at)
        VALUES(?,?,?,?,?,?,?,?)""",
        (gid, kind, title, content, path, json.dumps(subtitles or [], ensure_ascii=False),
         order, datetime.now().isoformat(timespec="seconds")))
    c.commit()
    return cur.lastrowid


def update_material(mid, title=None, content=None, subtitles=None):
    c = _conn_get()
    if title is not None:
        c.execute("UPDATE materials SET title=? WHERE id=?", (title, mid))
    if content is not None:
        c.execute("UPDATE materials SET content=? WHERE id=?", (content, mid))
    if subtitles is not None:
        c.execute("UPDATE materials SET subtitles=? WHERE id=?",
                  (json.dumps(subtitles, ensure_ascii=False), mid))
    c.commit()


def delete_material(mid):
    c = _conn_get()
    row = c.execute("SELECT path FROM materials WHERE id=?", (mid,)).fetchone()
    if row and row["path"] and os.path.isfile(row["path"]):
        try:
            os.remove(row["path"])
        except OSError:
            pass
    c.execute("DELETE FROM materials WHERE id=?", (mid,))
    c.commit()


def get_material(mid):
    row = _conn_get().execute("SELECT * FROM materials WHERE id=?", (mid,)).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["subtitle_list"] = json.loads(data.get("subtitles") or "[]")
    except Exception:
        data["subtitle_list"] = []
    return data


def list_materials(gid):
    return [dict(r) for r in _conn_get().execute(
        "SELECT * FROM materials WHERE group_id=? ORDER BY sort_order, id", (gid,)).fetchall()]


def material_counts(gid):
    row = _conn_get().execute(
        "SELECT COUNT(*) AS c FROM materials WHERE group_id=?", (gid,)).fetchone()
    return row["c"] if row else 0
