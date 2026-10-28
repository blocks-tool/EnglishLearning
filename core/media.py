"""媒体兼容处理。

Qt 的 DirectShow 后端依赖系统解码器：很多 Windows 环境缺少 MP4（H.264/AAC）
解码器，播放会直接报 InvalidMedia。这里用 ffmpeg 把不支持的媒体转换成
系统能播放的格式（视频 → WMV，音频 → WAV），转换结果按源文件缓存复用。
时间轴保持不变，因此已有字幕无需重新制作。
"""
import hashlib
import os
import subprocess

from . import asr
from .paths import CACHE_DIR

MEDIA_CACHE = os.path.join(CACHE_DIR, "media")


def _cache_path(src, ext):
    st = os.stat(src)
    key = hashlib.md5(
        f"{os.path.abspath(src)}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8")
    ).hexdigest()[:16]
    os.makedirs(MEDIA_CACHE, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(MEDIA_CACHE, f"{stem}-{key}.{ext}")


def ensure_playable(src, is_video, progress=None):
    """返回系统播放器可播放的本地文件路径（结果缓存）。"""
    ext = "wmv" if is_video else "wav"
    out = _cache_path(src, ext)
    if os.path.exists(out) and os.path.getsize(out) > 1024:
        if progress:
            progress(100, "完成")
        return out

    exe = asr.ffmpeg_exe()
    if not exe:
        raise RuntimeError("缺少 ffmpeg，无法转换媒体")
    if is_video:
        args = ["-c:v", "wmv2", "-b:v", "1500k", "-c:a", "wmav2", "-b:a", "128k"]
    else:
        args = ["-vn", "-ar", "44100", "-ac", "2"]

    if progress:
        progress(5, "开始转换")
    result = subprocess.run(
        [exe, "-y", "-i", src, *args, out],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
        raise RuntimeError("媒体格式转换失败")
    if progress:
        progress(100, "完成")
    return out
