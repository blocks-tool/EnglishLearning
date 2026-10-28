"""Piper 离线语音合成。

- 优先使用 voices/ 目录下的 *.onnx 模型（神经网络语音，自然度高）
- 没有可用模型时回退到 Windows SAPI5（pyttsx3），保证功能可用
- 合成结果按 (文本, 语速, 模型) 缓存为 WAV，重复朗读零等待
"""
import hashlib
import io
import os
import threading
import wave

import numpy as np

from .paths import TTS_CACHE_DIR, VOICES_DIR

SAMPLE_RATE_FALLBACK = 16000
_lock = threading.RLock()
_voice = None
_voice_model = None
_sapi_engine = None
_failed_reason = ""


def list_voices():
    if not os.path.isdir(VOICES_DIR):
        return []
    return sorted(f for f in os.listdir(VOICES_DIR) if f.endswith(".onnx"))


def _find_model():
    voices = list_voices()
    return os.path.join(VOICES_DIR, voices[0]) if voices else None


def available():
    return bool(list_voices())


def backend_name():
    if available():
        return "Piper TTS"
    return "Windows SAPI5"


def _load_piper():
    """加载 PiperVoice。

    关闭 onnxruntime 的 enable_mem_pattern：复用同一 session 时该缓存会触发
    Reshape 错误（piper 已知兼容问题）。
    """
    global _voice, _voice_model
    model = _find_model()
    if not model:
        raise RuntimeError("voices/ 目录下没有 .onnx 语音模型")
    if _voice is not None and _voice_model == model:
        return _voice
    import json

    import onnxruntime
    from piper import PiperVoice
    from piper.config import PiperConfig

    with open(model + ".json", "r", encoding="utf-8") as f:
        config = PiperConfig.from_dict(json.load(f))
    sess_options = onnxruntime.SessionOptions()
    sess_options.enable_mem_pattern = False
    session = onnxruntime.InferenceSession(
        model, sess_options=sess_options, providers=["CPUExecutionProvider"]
    )
    _voice = PiperVoice(config=config, session=session)
    _voice_model = model
    return _voice


def _cache_path(text, speed):
    model = _find_model() or "sapi"
    key = hashlib.md5(
        f"{os.path.basename(model)}|{speed:.2f}|{text}".encode("utf-8")
    ).hexdigest()
    return os.path.join(TTS_CACHE_DIR, key + ".wav")


def _synth_piper(text, speed):
    from piper.config import SynthesisConfig

    voice = _load_piper()
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(voice.config.sample_rate)
        syn = SynthesisConfig(length_scale=1.0 / max(0.5, min(2.0, speed)))
        voice.synthesize_wav(text, wf, syn_config=syn)
    return out.getvalue()


def _sapi_engine_get():
    global _sapi_engine
    if _sapi_engine is None:
        import pyttsx3

        engine = pyttsx3.init()
        for v in engine.getProperty("voices"):
            if "en" in (v.id or "").lower():
                engine.setProperty("voice", v.id)
                break
        _sapi_engine = engine
    return _sapi_engine


def _synth_sapi(text, speed, path):
    engine = _sapi_engine_get()
    engine.setProperty("rate", int(150 * max(0.5, min(2.0, speed))))
    engine.save_to_file(text, path)
    engine.runAndWait()


def synth_to_file(text, speed=1.0, path=None):
    """合成文本为 WAV 文件，返回路径。同一文本命中缓存时直接返回。"""
    global _failed_reason
    text = (text or "").strip()
    if not text:
        raise ValueError("朗读内容为空")
    speed = round(float(speed or 1.0), 2)
    target = path or _cache_path(text, speed)
    if path is None and os.path.exists(target) and os.path.getsize(target) > 44:
        return target
    with _lock:
        if path is None and os.path.exists(target) and os.path.getsize(target) > 44:
            return target
        try:
            data = _synth_piper(text, speed)
            tmp = target + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, target)
            return target
        except Exception as exc:  # Piper 不可用时回退 SAPI
            _failed_reason = f"Piper 合成失败：{exc}"
        if path is None:
            tmp = target + ".tmp.wav"
            _synth_sapi(text, speed, tmp)
            os.replace(tmp, target)
            return target
        _synth_sapi(text, speed, path)
        return path


def wav_duration(path):
    try:
        with wave.open(path, "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0


def _read_frames(path):
    with wave.open(path, "rb") as wf:
        params = wf.getparams()
        return wf.readframes(wf.getnframes()), params


def synth_sentences(sentences, speed=1.0, progress=None):
    """逐句合成并拼接为一个 WAV，返回 (wav路径, [(start, end)], 总时长)。

    逐句缓存的另一个好处：长文章首次合成后，后续朗读、单句试听都很快。
    """
    sentences = [s.strip() for s in sentences if (s or "").strip()]
    if not sentences:
        raise ValueError("没有可朗读的句子")
    key = hashlib.md5(
        ("|".join(sentences) + f"|{speed:.2f}|{os.path.basename(_find_model() or 'sapi')}").encode("utf-8")
    ).hexdigest()
    merged_path = os.path.join(TTS_CACHE_DIR, "article_" + key + ".wav")
    timings = []
    total = 0.0
    if os.path.exists(merged_path) and os.path.exists(merged_path + ".json"):
        import json

        with open(merged_path + ".json", "r", encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("sentences") == sentences and abs(meta.get("speed", 0) - speed) < 0.01:
            return merged_path, [tuple(t) for t in meta["timings"]], float(meta["duration"])

    with wave.open(merged_path + ".part", "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE_FALLBACK)
        params_set = False
        gap = b"\x00\x00" * int(SAMPLE_RATE_FALLBACK * 0.22)
        for i, sentence in enumerate(sentences):
            if progress:
                progress(int(i * 100 / len(sentences)), sentence)
            wav_path = synth_to_file(sentence, speed)
            frames, params = _read_frames(wav_path)
            if not params_set:
                out.setnchannels(params.nchannels)
                out.setsampwidth(params.sampwidth)
                out.setframerate(params.framerate)
                params_set = True
                rate = params.framerate
                channels = params.nchannels
                width = params.sampwidth
                gap = b"\x00" * int(rate * 0.22 * channels * width)
            dur = params.nframes / float(params.framerate)
            timings.append((round(total, 3), round(total + dur, 3)))
            out.writeframes(frames)
            total += dur
            if i < len(sentences) - 1:
                out.writeframes(gap)
                total += 0.22
        rate = out.getframerate() if params_set else SAMPLE_RATE_FALLBACK
        # 结尾补一点点静音，避免播放器提前结束
        out.writeframes(b"\x00" * int(rate * 0.12) * out.getnchannels() * out.getsampwidth())
        total += 0.12
    os.replace(merged_path + ".part", merged_path)
    import json

    with open(merged_path + ".json", "w", encoding="utf-8") as f:
        json.dump({"sentences": sentences, "speed": speed, "timings": timings,
                   "duration": total}, f, ensure_ascii=False)
    if progress:
        progress(100, "完成")
    return merged_path, timings, total


def speak(text, speed=1.0):
    """合成到缓存文件，供 QMediaPlayer 播放（不阻塞调用线程）。"""
    return synth_to_file(text, speed)
