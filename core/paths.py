"""统一管理应用目录。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
VOICES_DIR = os.path.join(BASE_DIR, "voices")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
TTS_CACHE_DIR = os.path.join(CACHE_DIR, "tts")
RECORD_DIR = os.path.join(CACHE_DIR, "record")
MODELS_DIR = os.path.join(DATA_DIR, "models")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")


def ensure_dirs():
    for d in (DATA_DIR, CACHE_DIR, TTS_CACHE_DIR, RECORD_DIR, MODELS_DIR):
        os.makedirs(d, exist_ok=True)


ensure_dirs()
