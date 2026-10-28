"""ECDICT 离线词典查询（约 340 万词条）。"""
import os
import re
import sqlite3

from .paths import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "ecdict.db")
_conn = None


def available():
    return os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 1_000_000


def _get_conn():
    global _conn
    if _conn is None:
        if not available():
            return None
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def lookup(word):
    """查询单词，返回 dict（word/phonetic/translation/definition/pos/tag/collins）。"""
    w = (word or "").strip().lower()
    if not w:
        return None
    conn = _get_conn()
    if conn is None:
        return None
    try:
        row = conn.execute(
            """SELECT word, phonetic, definition, translation, pos, collins, tag
               FROM stardict WHERE word=? LIMIT 1""",
            (w,),
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
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


def phonetic(word):
    info = lookup(word)
    if not info:
        return ""
    p = info["phonetic"].strip()
    return f"/{p.strip('/')}/" if p else ""


def short_translation(word, limit=3):
    """把 ECDICT 的多行释义压缩成一行，最多保留 limit 个义项。"""
    info = lookup(word)
    if not info:
        return ""
    lines = []
    for line in info["translation"].splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[a-z]+\.\s*", "", line, flags=re.I)
        lines.append(line)
        if len(lines) >= limit:
            break
    return "；".join(lines)


def pos_of(word):
    info = lookup(word)
    return (info or {}).get("pos", "") or ""
