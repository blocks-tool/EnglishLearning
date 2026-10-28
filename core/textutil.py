"""英文文本处理：按句切分、字数统计、时间格式化。"""
import re


def split_sentences(text):
    """按英文句号/问号/感叹号切句，兼容常见缩写与换行。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in text.split("\n") if b.strip()]
    sentences = []
    for block in blocks:
        # 保护常见缩写中的句点
        protected = block
        for abbr in ("Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "St.", "Jr.", "Sr.",
                     "e.g.", "i.e.", "etc.", "vs.", "U.S.", "U.K.", "a.m.", "p.m."):
            protected = protected.replace(abbr, abbr.replace(".", "\u0000"))
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“(])", protected)
        for part in parts:
            part = part.replace("\u0000", ".").strip()
            if part:
                sentences.append(part)
    return sentences


def split_paragraphs(text):
    return [p.strip() for p in (text or "").replace("\r", "").split("\n") if p.strip()]


def word_count(text):
    return len(re.findall(r"[A-Za-z0-9']+", text or ""))


def fmt_time(ms):
    try:
        ms = max(0, int(ms))
    except Exception:
        return "00:00"
    seconds = ms // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
