"""字幕生成：
1. 优先用本地 Vosk 英文模型识别音频/视频（离线）
2. 模型不可用时，可用文章文本按媒体时长估算时间轴（兜底）
3. 也支持导入 SRT
"""
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

from .paths import MODELS_DIR

MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_DIR = os.path.join(MODELS_DIR, MODEL_NAME)
MODEL_URL = f"https://alphacephei.com/vosk/models/{MODEL_NAME}.zip"

_model = None


def model_ready():
    return os.path.isdir(os.path.join(MODEL_DIR, "am")) and os.path.isdir(
        os.path.join(MODEL_DIR, "conf")
    )


def vosk_available():
    try:
        import vosk  # noqa: F401
        return True
    except Exception:
        return False


def download_model(progress=None):
    """下载并解压 Vosk 小模型（约 40MB）。"""
    if model_ready():
        return MODEL_DIR
    os.makedirs(MODELS_DIR, exist_ok=True)
    zip_path = os.path.join(MODELS_DIR, MODEL_NAME + ".zip")
    tmp = zip_path + ".part"

    def hook(blocks, block_size, total):
        if progress and total > 0:
            progress(min(99, int(blocks * block_size * 100 / total)), "下载离线模型")
    urllib.request.urlretrieve(MODEL_URL, tmp, reporthook=hook)
    os.replace(tmp, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(MODELS_DIR)
    try:
        os.remove(zip_path)
    except OSError:
        pass
    if progress:
        progress(100, "模型已就绪")
    return MODEL_DIR


def _load_model():
    global _model
    if _model is None:
        from vosk import Model, SetLogLevel

        SetLogLevel(-1)
        _model = Model(MODEL_DIR)
    return _model


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        found = shutil.which("ffmpeg")
        return found


def extract_wav(media_path, out_path):
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("缺少 ffmpeg，无法提取音频（pip install imageio-ffmpeg 即可）")
    cmd = [exe, "-y", "-i", media_path, "-vn", "-ac", "1", "-ar", "16000",
           "-f", "wav", out_path]
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError("音频提取失败，请确认文件未损坏")


def _group_words(words, max_gap=0.65, max_words=12, max_chars=88):
    segments = []
    current = []
    for w in words:
        text = (w.get("word") or "").strip()
        if not text:
            continue
        if current:
            gap = w["start"] - current[-1]["end"]
            chars = sum(len(x["word"]) + 1 for x in current) + len(text)
            if gap > max_gap or len(current) >= max_words or chars > max_chars:
                segments.append(current)
                current = []
        current.append(w)
    if current:
        segments.append(current)
    result = []
    for seg in segments:
        text = " ".join(x["word"] for x in seg).strip()
        if not text:
            continue
        text = text[0].upper() + text[1:]
        result.append({
            "start": round(float(seg[0]["start"]), 2),
            "end": round(float(seg[-1]["end"]), 2),
            "text": text,
        })
    return result


def _recognize_words(media_path, progress=None):
    """离线识别媒体语音，返回 Vosk 的词级结果（含时间）。"""
    if not model_ready():
        if progress:
            progress(2, "准备识别")
        download_model(progress)
    import wave

    from vosk import KaldiRecognizer

    if progress:
        progress(12, "提取音频")
    tmpdir = tempfile.mkdtemp(prefix="asr_")
    wav_path = os.path.join(tmpdir, "audio.wav")
    try:
        extract_wav(media_path, wav_path)
        if progress:
            progress(28, "识别语音")
        model = _load_model()
        with wave.open(wav_path, "rb") as wf:
            rec = KaldiRecognizer(model, wf.getframerate())
            rec.SetWords(True)
            words = []
            total = wf.getnframes() or 1
            read = 0
            while True:
                data = wf.readframes(4000)
                if not data:
                    break
                read += 4000
                if rec.AcceptWaveform(data):
                    part = json.loads(rec.Result())
                    words.extend(part.get("result", []))
                if progress:
                    progress(28 + int(min(60, read * 60 / total)), "识别语音")
            final = json.loads(rec.FinalResult())
            words.extend(final.get("result", []))
        if progress:
            progress(94, "整理文字")
        return words
    finally:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass


def transcribe(media_path, progress=None):
    """离线识别媒体语音，返回 [{start,end,text}]。"""
    return _group_words(_recognize_words(media_path, progress))


def transcribe_text(media_path, progress=None):
    """只识别文字，按停顿切分成行，不返回时间轴；供手动标注时间使用。"""
    segments = _group_words(_recognize_words(media_path, progress))
    return "\n".join(seg["text"] for seg in segments).strip()


def subtitles_from_text(text, duration):
    """没有 ASR 时，用文章文本按字符数估算字幕时间轴。"""
    from .textutil import split_sentences

    sentences = split_sentences(text)
    if not sentences:
        return []
    weights = [max(1, len(s) + 6) for s in sentences]
    total = sum(weights)
    t = 0.0
    result = []
    for sentence, weight in zip(sentences, weights):
        span = max(1.2, duration * weight / total)
        result.append({
            "start": round(t, 2),
            "end": round(min(duration, t + span), 2),
            "text": sentence,
        })
        t += span
    return result


def parse_srt(path):
    import re

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read().replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n", content.strip())
    result = []

    def to_seconds(value):
        h, m, rest = value.split(":")
        s, ms = rest.replace(",", ".").split(".")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0

    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        time_line = next((l for l in lines if "-->" in l), None)
        if not time_line:
            continue
        start_s, end_s = [x.strip() for x in time_line.split("-->")]
        text_lines = lines[lines.index(time_line) + 1:]
        text = " ".join(text_lines).strip()
        if not text:
            continue
        result.append({
            "start": round(to_seconds(start_s), 2),
            "end": round(to_seconds(end_s), 2),
            "text": text,
        })
    return result
