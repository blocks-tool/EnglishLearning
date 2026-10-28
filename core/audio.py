"""音频工具：录音、WAV 读写、波形数据、离线发音评测。

发音评测完全离线：
1. 参考音频使用 Piper 合成的标准发音
2. 提取 MFCC 特征，做 DTW 对齐
3. 得到整体相似度分数 + 逐词得分，指出明显偏差的单词
"""
import math
import os
import time
import wave

import numpy as np

SR_EVAL = 16000


# ---------------- WAV ----------------
def read_wav(path):
    """返回 (float32 单声道 [-1,1], 采样率)。"""
    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if width == 1:
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0
        data /= 128.0
    elif width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        return np.zeros(0, dtype=np.float32), rate
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


def write_wav(path, data, rate):
    data = np.asarray(data, dtype=np.float32)
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(rate))
        wf.writeframes(pcm.tobytes())
    return path


def resample(data, src_rate, dst_rate=SR_EVAL):
    if src_rate == dst_rate or len(data) == 0:
        return data
    from scipy.signal import resample_poly

    g = math.gcd(int(src_rate), int(dst_rate))
    return resample_poly(data, dst_rate // g, src_rate // g).astype(np.float32)


def trim_silence(data, rate=SR_EVAL, thresh_ratio=0.06, pad_ms=80):
    if len(data) == 0:
        return data
    frame = max(1, int(rate * 0.02))
    n = len(data) // frame
    if n == 0:
        return data
    energy = np.sqrt(np.mean(data[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-9)
    peak = float(energy.max())
    if peak < 1e-5:
        return data
    mask = energy > peak * thresh_ratio
    if not mask.any():
        return data
    start = int(np.argmax(mask)) * frame
    end = (len(mask) - int(np.argmax(mask[::-1]))) * frame
    pad = int(rate * pad_ms / 1000)
    return data[max(0, start - pad): min(len(data), end + pad)]


def waveform_peaks(data, buckets=420):
    """把波形压缩成绘制用的峰值数组（-1~1）。"""
    data = np.asarray(data, dtype=np.float32)
    if len(data) == 0:
        return np.zeros(buckets, dtype=np.float32)
    n = len(data)
    step = max(1, n // buckets)
    usable = n // step * step
    chunks = data[:usable].reshape(-1, step)
    peaks = np.abs(chunks).max(axis=1)
    if len(peaks) < buckets:
        peaks = np.pad(peaks, (0, buckets - len(peaks)), mode="constant")
    else:
        peaks = peaks[:buckets]
    m = float(peaks.max()) or 1.0
    return np.clip(peaks / m, 0.02, 1.0)


# ---------------- 录音 ----------------
class Recorder:
    """基于 sounddevice 的麦克风录音，支持实时电平。"""

    def __init__(self, samplerate=None):
        self.samplerate = samplerate or self._default_rate()
        self._stream = None
        self._chunks = []
        self._level = 0.0
        self._recording = False

    @staticmethod
    def available():
        try:
            import sounddevice  # noqa: F401
            return True
        except Exception:
            return False

    @staticmethod
    def _default_rate():
        try:
            import sounddevice as sd
            info = sd.query_devices(kind="input")
            rate = int(info.get("default_samplerate") or 44100)
            return rate if rate > 0 else 44100
        except Exception:
            return 44100

    @property
    def level(self):
        return self._level

    @property
    def recording(self):
        return self._recording

    def start(self):
        import sounddevice as sd

        self._chunks = []
        self._level = 0.0
        self._recording = True

        def callback(indata, frames, time_info, status):  # noqa: ARG001
            mono = indata[:, 0].copy()
            self._chunks.append(mono)
            self._level = float(np.sqrt(np.mean(mono ** 2) + 1e-12))

        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            callback=callback,
            blocksize=1024,
        )
        self._stream.start()

    def stop(self):
        self._recording = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        data = np.concatenate(self._chunks).astype(np.float32)
        self._chunks = []
        self._level = 0.0
        return data

    def save(self, path):
        data = self.stop()
        write_wav(path, data, self.samplerate)
        return path, data


# ---------------- MFCC / DTW ----------------
def _mel_filterbank(n_mels, n_fft, sr):
    def hz_to_mel(hz):
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    def mel_to_hz(mel):
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    low = hz_to_mel(80)
    high = hz_to_mel(sr / 2.0)
    mels = np.linspace(low, high, n_mels + 2)
    hzs = mel_to_hz(mels)
    bins = np.floor((n_fft + 1) * hzs / sr).astype(int)
    fbank = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        l, c, r = bins[i], bins[i + 1], bins[i + 2]
        for j in range(l, c):
            if c > l:
                fbank[i, j] = (j - l) / (c - l)
        for j in range(c, r):
            if r > c:
                fbank[i, j] = (r - j) / (r - c)
    return fbank


def mfcc_feature(data, sr=SR_EVAL, n_mfcc=20, n_mels=40, win=0.025, hop=0.01):
    if len(data) < int(sr * win):
        return np.zeros((0, n_mfcc), dtype=np.float32)
    data = np.asarray(data, dtype=np.float32)
    data = np.append(data[0], data[1:] - 0.97 * data[:-1])
    win_len = int(sr * win)
    hop_len = int(sr * hop)
    if len(data) < win_len:
        return np.zeros((0, n_mfcc), dtype=np.float32)
    n_frames = 1 + (len(data) - win_len) // hop_len
    idx = np.arange(win_len)[None, :] + hop_len * np.arange(n_frames)[:, None]
    frames = data[idx] * np.hamming(win_len)[None, :]
    n_fft = 512
    spec = np.abs(np.fft.rfft(frames, n=n_fft)) ** 2
    fbank = _mel_filterbank(n_mels, n_fft, sr)
    mel = np.log(spec @ fbank.T + 1e-10)
    n = np.arange(n_mels)
    dct = np.cos(np.pi * n[None, :] * (np.arange(n_mels)[:, None] + 0.5) / n_mels)
    coeffs = mel @ dct
    feats = coeffs[:, 1: n_mfcc + 1]
    feats = (feats - feats.mean(axis=0, keepdims=True)) / (feats.std(axis=0, keepdims=True) + 1e-6)
    return feats.astype(np.float32)


def _cosine_cost(a, b):
    a = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-6)
    b = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-6)
    return np.clip(1.0 - a @ b.T, 0.0, 2.0)


def dtw(cost):
    n, m = cost.shape
    acc = np.full((n + 1, m + 1), np.inf, dtype=np.float32)
    acc[0, 0] = 0.0
    for i in range(1, n + 1):
        row = acc[i]
        prev = acc[i - 1]
        c = cost[i - 1]
        for j in range(1, m + 1):
            row[j] = c[j - 1] + min(prev[j - 1], prev[j], row[j - 1])
    path = []
    i, j = n, m
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        options = (acc[i - 1, j - 1], acc[i - 1, j], acc[i, j - 1])
        choice = int(np.argmin(options))
        if choice == 0:
            i, j = i - 1, j - 1
        elif choice == 1:
            i -= 1
        else:
            j -= 1
    path.reverse()
    return acc[n, m] / max(1, len(path)), path


def _word_spans(text):
    import re

    words = [w for w in re.split(r"\s+", text.strip()) if w]
    cleaned = [re.sub(r"[^A-Za-z0-9']", "", w) for w in words]
    weights = [max(1, len(re.sub(r"[^A-Za-z0-9]", "", w))) for w in words]
    return words, cleaned, weights


def evaluate_pronunciation(ref_path, user_path, text, ui_lang=True):
    """离线评测。返回 score / words / notes / 波形。"""
    ref, ref_sr = read_wav(ref_path)
    user, user_sr = read_wav(user_path)
    ref = trim_silence(resample(ref, ref_sr), SR_EVAL)
    user = trim_silence(resample(user, user_sr), SR_EVAL)
    ref_peaks = waveform_peaks(ref)
    user_peaks = waveform_peaks(user)

    if len(user) < SR_EVAL * 0.25:
        return {
            "score": 0,
            "words": [],
            "notes": ["没有录到有效语音，请靠近麦克风重新录音"],
            "ref_wave": ref_peaks,
            "user_wave": user_peaks,
            "ref_duration": len(ref) / SR_EVAL,
            "user_duration": len(user) / SR_EVAL,
        }

    f_ref = mfcc_feature(ref)
    f_user = mfcc_feature(user)
    notes = []
    if len(f_ref) < 3 or len(f_user) < 3:
        return {
            "score": 10,
            "words": [],
            "notes": ["语音太短，无法评测"],
            "ref_wave": ref_peaks,
            "user_wave": user_peaks,
            "ref_duration": len(ref) / SR_EVAL,
            "user_duration": len(user) / SR_EVAL,
        }

    cost = _cosine_cost(f_user, f_ref)  # 行=用户, 列=参考
    avg_dist, path = dtw(cost)

    spectral = max(0.0, 1.0 - avg_dist / 0.95)
    dur_ref = len(ref) / SR_EVAL
    dur_user = len(user) / SR_EVAL
    ratio = min(dur_ref, dur_user) / max(dur_ref, dur_user, 1e-6)
    duration_score = max(0.0, 1.0 - abs(1.0 - ratio) / 0.7)
    user_rms = float(np.sqrt(np.mean(user ** 2)))
    activity = min(1.0, user_rms / 0.045)
    score = 100.0 * (0.72 * spectral + 0.18 * duration_score + 0.10 * activity)
    score = int(max(5, min(96, round(score))))

    if ratio < 0.72:
        notes.append("朗读明显偏快，注意把单词读完整")
    elif ratio > 1.45:
        notes.append("朗读明显偏慢，注意句子连贯")
    if user_rms < 0.012:
        notes.append("录音音量偏小，请靠近麦克风")

    # 逐词对齐：把参考帧按单词字符长度切分，再通过 DTW 映射到用户帧
    words, cleaned, weights = _word_spans(text)
    total_w = sum(weights) or 1
    ref_len = len(f_ref)
    word_results = []
    if words:
        ref_to_user = {}
        for ui, rj in path:
            if rj not in ref_to_user:
                ref_to_user[rj] = ui
        cursor = 0
        from . import dictionary

        for word, clean, weight in zip(words, cleaned, weights):
            span = max(1, round(weight * ref_len / total_w))
            start = cursor
            end = min(ref_len, cursor + span)
            cursor = end
            if start >= end:
                continue
            ref_idx = list(range(start, end))
            distances = []
            for ri in ref_idx:
                uj = ref_to_user.get(ri)
                if uj is not None:
                    distances.append(float(cost[min(uj, len(f_user) - 1), ri]))
            d = float(np.mean(distances)) if distances else avg_dist
            wscore = int(max(0, min(100, round(100 * (1.0 - d / 0.95)))))
            if clean and wscore < 62:
                ipa = dictionary.phonetic(clean)
                word_results.append({
                    "word": clean,
                    "ipa": ipa,
                    "score": wscore,
                })
        word_results.sort(key=lambda x: x["score"])
        word_results = word_results[:6]

    if not notes:
        if score >= 85:
            notes.append("发音清晰自然，重音和节奏都很好")
        elif score >= 70:
            notes.append("整体不错，个别单词可以再清晰一些")
        else:
            notes.append("注意单词尾音和连读，跟着原音多练两遍")

    return {
        "score": score,
        "words": word_results,
        "notes": notes,
        "ref_wave": ref_peaks,
        "user_wave": user_peaks,
        "ref_duration": dur_ref,
        "user_duration": dur_user,
    }
