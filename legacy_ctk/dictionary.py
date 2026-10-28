"""ECDICT 离线词典查询。
数据库结构（ecdict.db，表 stardict）：
  word, sw, phonetic, definition(英文释义), translation(中文释义),
  pos, collins(1-5星), oxford, tag(cet4/cet6/...), bnc, frq, exchange
"""
import os
import sqlite3
import gzip
import shutil
import zipfile
import urllib.request

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
ECDICT_PATH = os.path.join(DATA_DIR, "ecdict.db")
ECDICT_ZIP_URL = "https://github.com/skywind3000/ECDICT/releases/download/1.0.28/ecdict-sqlite-28.zip"

_conn = None


def ensure_dictionary(progress_cb=None):
    """确保 ecdict.db 存在。若不存在则提示/下载。返回 True 可用。"""
    if os.path.exists(ECDICT_PATH) and os.path.getsize(ECDICT_PATH) > 1_000_000:
        return True
    return False


def get_conn():
    global _conn
    if _conn is None:
        if not os.path.exists(ECDICT_PATH) or os.path.getsize(ECDICT_PATH) < 1_000_000:
            return None
        _conn = sqlite3.connect(ECDICT_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def lookup(word):
    """查询单个单词。返回 dict 或 None（词典未加载时也返回 None）。"""
    w = word.strip().lower()
    if not w:
        return None
    try:
        c = get_conn()
        if c is None:
            return None
    except Exception:
        return None
    row = c.execute("""
        SELECT word, phonetic, definition, translation, pos, collins, tag
        FROM stardict WHERE word=? LIMIT 1
    """, (w,)).fetchone()
    if row is None:
        # 尝试去复数/ing等简单变形：直接查不到就返回None
        return None
    return {
        "word": row["word"],
        "phonetic": row["phonetic"] or "",
        "translation": row["translation"] or "",
        "definition": row["definition"] or "",
        "pos": row["pos"] or "",
        "collins": row["collins"] or 0,
        "tag": row["tag"] or "",
    }


def is_cet6(tag):
    return "cet6" in (tag or "").lower()
