"""离线发音：优先 Piper TTS（voices/*.onnx），无模型回退 SAPI5（pyttsx3）。
支持 stop() 立即停止和播放结束回调。"""
import ctypes
import io
import os
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor

_VOICES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")
_piper_available = None
_piper_voice = None
_piper_voice_lock = threading.Lock()
_model_path_cache = None
_sapi_engine = None
_sapi_lock = threading.Lock()
_piper_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="piper-tts")
_waveout_play_lock = threading.Lock()
_waveout_handle_lock = threading.Lock()
_active_waveout = None
_playing = threading.Event()
_playback_lock = threading.Lock()
_playback_id = 0
_finished_cb = None

_WHDR_DONE = 0x00000001
_WAVE_MAPPER = 0xFFFFFFFF


class _WaveFormatEx(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", ctypes.c_ushort),
        ("nChannels", ctypes.c_ushort),
        ("nSamplesPerSec", ctypes.c_uint),
        ("nAvgBytesPerSec", ctypes.c_uint),
        ("nBlockAlign", ctypes.c_ushort),
        ("wBitsPerSample", ctypes.c_ushort),
        ("cbSize", ctypes.c_ushort),
    ]


class _WaveHeader(ctypes.Structure):
    pass


_WaveHeader._fields_ = [
    ("lpData", ctypes.c_void_p),
    ("dwBufferLength", ctypes.c_uint),
    ("dwBytesRecorded", ctypes.c_uint),
    ("dwUser", ctypes.c_size_t),
    ("dwFlags", ctypes.c_uint),
    ("dwLoops", ctypes.c_uint),
    ("lpNext", ctypes.POINTER(_WaveHeader)),
    ("reserved", ctypes.c_size_t),
]

_winmm = ctypes.WinDLL("winmm", use_last_error=True)
_winmm.waveOutOpen.argtypes = [
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.c_uint,
    ctypes.POINTER(_WaveFormatEx),
    ctypes.c_size_t,
    ctypes.c_size_t,
    ctypes.c_uint,
]
_winmm.waveOutOpen.restype = ctypes.c_uint
_winmm.waveOutPrepareHeader.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_WaveHeader),
    ctypes.c_uint,
]
_winmm.waveOutPrepareHeader.restype = ctypes.c_uint
_winmm.waveOutWrite.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_WaveHeader),
    ctypes.c_uint,
]
_winmm.waveOutWrite.restype = ctypes.c_uint
_winmm.waveOutReset.argtypes = [ctypes.c_void_p]
_winmm.waveOutReset.restype = ctypes.c_uint
_winmm.waveOutUnprepareHeader.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(_WaveHeader),
    ctypes.c_uint,
]
_winmm.waveOutUnprepareHeader.restype = ctypes.c_uint
_winmm.waveOutClose.argtypes = [ctypes.c_void_p]
_winmm.waveOutClose.restype = ctypes.c_uint

def _is_current_playback(playback_id):
    with _playback_lock:
        return playback_id == _playback_id


def _stop_backend():
    with _waveout_handle_lock:
        handle = _active_waveout
        if handle is not None:
            result = _winmm.waveOutReset(handle)
            if result:
                print(f"[TTS] waveOutReset failed: {result}")
    eng = _sapi_engine
    if eng is not None:
        try:
            eng.stop()
        except Exception:
            pass


def _find_piper_model():
    """缓存模型路径，避免每次合成重复扫描目录。"""
    global _model_path_cache
    if _model_path_cache is not None:
        return _model_path_cache
    if not os.path.isdir(_VOICES_DIR):
        return None
    for f in sorted(os.listdir(_VOICES_DIR)):
        if f.endswith(".onnx"):
            _model_path_cache = os.path.join(_VOICES_DIR, f)
            return _model_path_cache
    return None


def _load_piper():
    global _piper_available
    if _piper_available is not None:
        return _piper_available
    model = _find_piper_model()
    if not model:
        _piper_available = False
        return False
    try:
        from piper import PiperVoice
        _piper_available = True
        return True
    except Exception as e:
        print(f"[TTS] Piper unavailable: {e}")
        _piper_available = False
        return False


def _get_piper_voice():
    """全局缓存 PiperVoice，避免每次朗读重载几十 MB 的 ONNX 模型。"""
    global _piper_voice
    if _piper_voice is None:
        with _piper_voice_lock:
            if _piper_voice is None:
                _piper_voice = _load_voice()
                print(f"[TTS] Piper voice loaded: {os.path.basename(_find_piper_model())}")
    return _piper_voice


def _load_voice():
    """手动加载模型。

    必须关闭 onnxruntime 的 enable_mem_pattern：缓存复用同一 session 时，
    默认开启的内存模式缓存会导致第二次合成报 Reshape 错（piper 已知兼容问题）。
    等价于 PiperVoice.load(model)，只是自定义了 SessionOptions。"""
    import json
    import onnxruntime
    from piper import PiperVoice
    from piper.config import PiperConfig

    model = _find_piper_model()
    if not model:
        raise FileNotFoundError("No Piper voice model found")
    with open(model + ".json", "r", encoding="utf-8") as f:
        config = PiperConfig.from_dict(json.load(f))
    sess_options = onnxruntime.SessionOptions()
    sess_options.enable_mem_pattern = False
    session = onnxruntime.InferenceSession(
        model, sess_options=sess_options, providers=["CPUExecutionProvider"])
    return PiperVoice(config=config, session=session)


def _load_piper_on_worker():
    return _piper_executor.submit(_load_piper).result()


def list_voices():
    if not os.path.isdir(_VOICES_DIR):
        return []
    return sorted(f for f in os.listdir(_VOICES_DIR) if f.endswith(".onnx"))


def is_playing():
    return _playing.is_set()


def stop():
    """立即停止朗读，触发 finished 回调。"""
    global _finished_cb, _playback_id
    with _playback_lock:
        _playback_id += 1
        _playing.clear()
        cb = _finished_cb
        _finished_cb = None
    _stop_backend()
    if cb:
        try:
            cb()
        except Exception:
            pass


def _play_piper(text, playback_id):
    audio = _synthesize_piper(text, playback_id)
    if audio is None:
        return
    _play_wave_bytes(audio, playback_id)


def _play_wave_bytes(audio_data, playback_id):
    global _active_waveout
    with _waveout_play_lock:
        if not _is_current_playback(playback_id):
            return
        with wave.open(io.BytesIO(audio_data), "rb") as wav_file:
            if wav_file.getcomptype() != "NONE":
                raise ValueError(f"Unsupported WAV compression: {wav_file.getcomptype()}")
            channels = wav_file.getnchannels()
            sample_rate = wav_file.getframerate()
            bits_per_sample = wav_file.getsampwidth() * 8
            audio_data = wav_file.readframes(wav_file.getnframes())

        block_align = channels * bits_per_sample // 8
        wave_format = _WaveFormatEx(
            1,
            channels,
            sample_rate,
            sample_rate * block_align,
            block_align,
            bits_per_sample,
            0,
        )
        audio_buffer = ctypes.create_string_buffer(audio_data)
        header = _WaveHeader(
            ctypes.cast(audio_buffer, ctypes.c_void_p),
            len(audio_data),
            0,
            0,
            0,
            0,
            None,
            0,
        )
        handle = ctypes.c_void_p()
        result = _winmm.waveOutOpen(
            ctypes.byref(handle),
            _WAVE_MAPPER,
            ctypes.byref(wave_format),
            0,
            0,
            0,
        )
        if result:
            raise OSError(f"waveOutOpen failed: {result}")

        prepared = False
        try:
            with _waveout_handle_lock:
                _active_waveout = handle
                if not _is_current_playback(playback_id):
                    _winmm.waveOutReset(handle)
                    return
            result = _winmm.waveOutPrepareHeader(
                handle, ctypes.byref(header), ctypes.sizeof(header)
            )
            if result:
                raise OSError(f"waveOutPrepareHeader failed: {result}")
            prepared = True
            if not _is_current_playback(playback_id):
                return
            result = _winmm.waveOutWrite(handle, ctypes.byref(header), ctypes.sizeof(header))
            if result:
                raise OSError(f"waveOutWrite failed: {result}")
            while not header.dwFlags & _WHDR_DONE:
                if not _is_current_playback(playback_id):
                    _winmm.waveOutReset(handle)
                time.sleep(0.05)
        finally:
            if prepared:
                result = _winmm.waveOutUnprepareHeader(
                    handle, ctypes.byref(header), ctypes.sizeof(header)
                )
                if result:
                    print(f"[TTS] waveOutUnprepareHeader failed: {result}")
            with _waveout_handle_lock:
                if _active_waveout == handle:
                    _active_waveout = None
                result = _winmm.waveOutClose(handle)
                if result:
                    print(f"[TTS] waveOutClose failed: {result}")


def _create_sapi_engine():
    import pyttsx3
    engine = pyttsx3.Engine()
    voices = engine.getProperty("voices")
    for v in voices:
        if "en" in (v.id or "").lower():
            engine.setProperty("voice", v.id)
            break
    engine.setProperty("rate", 150)
    return engine


def _get_sapi_engine():
    """SAPI 引擎单例：pyttsx3 初始化很慢，复用同一实例。"""
    global _sapi_engine
    if _sapi_engine is None:
        _sapi_engine = _create_sapi_engine()
    return _sapi_engine


def _play_sapi(text, playback_id):
    with _sapi_lock:
        if not _is_current_playback(playback_id):
            return
        engine = _get_sapi_engine()
        if not _is_current_playback(playback_id):
            return
        engine.say(text)
        engine.runAndWait()


def _synthesize_piper(text, playback_id):
    """在工作线程合成到内存缓冲，返回 WAV 字节；被打断则返回 None。"""
    def _synthesize():
        if not _is_current_playback(playback_id):
            return None
        voice = _get_piper_voice()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            # 预先写好 WAV 参数：若合成中途抛错，with 退出时 close() 不会再
            # 抛出 "# channels not specified" 掩盖真正的异常
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(voice.config.sample_rate)
            voice.synthesize_wav(text, wf)
        if not _is_current_playback(playback_id):
            return None
        return buffer.getvalue()

    return _piper_executor.submit(_synthesize).result()


def speak(text, on_finished=None, on_error=None):
    """后台线程朗读；播放结束或被替换/停止时调用 on_finished。"""
    global _finished_cb, _playback_id
    text = (text or "").strip()
    if not text:
        return
    with _playback_lock:
        old_cb = _finished_cb
        _playback_id += 1
        playback_id = _playback_id
        _finished_cb = on_finished
        _playing.set()
    _stop_backend()
    if old_cb:
        try:
            old_cb()
        except Exception:
            pass

    def _run():
        global _finished_cb
        try:
            if not _is_current_playback(playback_id):
                return
            if _load_piper_on_worker():
                _play_piper(text, playback_id)
            else:
                _play_sapi(text, playback_id)
        except Exception as e:
            print(f"[TTS] speak error: {e}")
            if on_error:
                try:
                    on_error(e)
                except Exception as callback_error:
                    print(f"[TTS] error callback failed: {callback_error}")
        finally:
            with _playback_lock:
                if playback_id == _playback_id:
                    _playing.clear()
                    cb = _finished_cb
                    _finished_cb = None
                else:
                    cb = None
            if cb:
                try:
                    cb()
                except Exception:
                    pass

    threading.Thread(target=_run, daemon=True).start()
