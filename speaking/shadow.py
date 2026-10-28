"""跟读练习：文章逐句跟读 + 音视频字幕跟读。"""
import os
import time

from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QSizePolicy, QVBoxLayout, QWidget,
)

from core import audio, media, tts
from core.audio import Recorder, waveform_peaks
from core.tasks import run_task
from core.ui import (
    COLORS, Card, MicLevelBar, ScoreRing, WaveformWidget, busy_progress, button, hline, label,
)

from . import dialogs


class ShadowPractice(QWidget):
    """右侧跟读面板：原音、录音、评分、发音建议。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_text = ""
        self.ref_path = None
        self.user_path = None
        self.recording = False
        self._ref_seq = 0
        self.external_play = None
        self.external_pause = None
        self.recorder = Recorder()
        self.ref_player = QMediaPlayer(self)
        self.ref_player.setVolume(95)
        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self._tick)
        self._start_ts = 0
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        header = QHBoxLayout()
        header.addWidget(label("跟读练习", 13, COLORS["text"], bold=True))
        header.addStretch(1)
        self.status = label("", 9, COLORS["sub"])
        header.addWidget(self.status)
        lay.addLayout(header)

        self.sentence_label = label("请选择一句话开始跟读", 13, COLORS["text"], wrap=True)
        self.sentence_label.setMinimumHeight(46)
        self.sentence_label.setStyleSheet(
            f"background:#f8faff;border:1px solid {COLORS['border']};"
            "border-radius:10px;padding:9px 11px;")
        lay.addWidget(self.sentence_label)

        ref_row = QHBoxLayout()
        ref_row.setSpacing(8)
        ref_row.addWidget(label("原音", 9, COLORS["sub"]), 0, Qt.AlignTop)
        self.ref_wave = WaveformWidget(color=COLORS["primary"], height=44)
        ref_row.addWidget(self.ref_wave, 1)
        lay.addLayout(ref_row)

        user_row = QHBoxLayout()
        user_row.setSpacing(8)
        user_row.addWidget(label("我的录音", 9, COLORS["sub"]), 0, Qt.AlignTop)
        self.user_wave = WaveformWidget(color=COLORS["red"], height=44)
        user_row.addWidget(self.user_wave, 1)
        self.user_time = label("", 9, COLORS["muted"])
        self.user_time.setFixedWidth(40)
        self.user_time.setAlignment(Qt.AlignRight | Qt.AlignTop)
        user_row.addWidget(self.user_time)
        lay.addLayout(user_row)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.play_btn = button("播放原音", "Soft")
        self.play_btn.clicked.connect(self.play_reference)
        controls.addWidget(self.play_btn)
        self.record_btn = button("● 开始录音", "RecordButton")
        self.record_btn.clicked.connect(self.toggle_record)
        controls.addWidget(self.record_btn)
        self.retry_btn = button("重新录音", "Ghost")
        self.retry_btn.clicked.connect(self.reset_recording)
        controls.addWidget(self.retry_btn)
        controls.addStretch(1)
        lay.addLayout(controls)

        meter_row = QHBoxLayout()
        self.meter = MicLevelBar()
        meter_row.addWidget(self.meter, 1)
        self.record_time = label("", 9, COLORS["muted"])
        self.record_time.setFixedWidth(52)
        meter_row.addWidget(self.record_time)
        lay.addLayout(meter_row)

        self.result = QFrame()
        self.result.setStyleSheet(
            f"QFrame{{background:#f8faff;border:1px solid {COLORS['border']};border-radius:10px;}}")
        res_lay = QHBoxLayout(self.result)
        res_lay.setContentsMargins(12, 10, 12, 10)
        res_lay.setSpacing(14)
        self.ring = ScoreRing(size=88)
        res_lay.addWidget(self.ring, 0, Qt.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(4)
        self.summary = label("", 11, COLORS["text"], bold=True, wrap=True)
        info.addWidget(self.summary)
        self.advice = QLabel()
        self.advice.setWordWrap(True)
        self.advice.setTextFormat(Qt.RichText)
        self.advice.setStyleSheet("font-size:10px; color:#4b5563;")
        info.addWidget(self.advice)
        info.addStretch(1)
        res_lay.addLayout(info, 1)
        self.result.setVisible(False)
        lay.addWidget(self.result)
        lay.addStretch(1)

    # ---------- 句子 / 原音 ----------
    def set_sentence(self, text):
        self.stop_all()
        self.current_text = (text or "").strip()
        self.sentence_label.setText(self.current_text or "请选择一句话开始跟读")
        self.ref_path = None
        self.user_path = None
        self.ref_wave.set_samples(None)
        self.user_wave.set_samples(None)
        self.user_time.setText("")
        self.result.setVisible(False)
        self.ring.set_score(0)
        self.record_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.retry_btn.setEnabled(False)
        if not self.current_text:
            return
        self.status.setText("正在生成标准发音…")
        self._ref_seq += 1
        seq = self._ref_seq

        def done(path):
            if seq != self._ref_seq:
                return
            self.ref_path = path
            data, rate = audio.read_wav(path)
            self.ref_wave.set_samples(waveform_peaks(data))
            self.status.setText("可以开始录音")
            self.record_btn.setEnabled(True)
            self.play_btn.setEnabled(True)
            self.retry_btn.setEnabled(True)

        def failed(message):
            if seq == self._ref_seq:
                self.status.setText(f"标准发音生成失败：{message}")

        run_task(tts.speak, done, failed, None, text=self.current_text, speed=1.0)

    def play_reference(self):
        if self.external_play:
            self.external_play()
            return
        if self.ref_path:
            self.ref_player.setMedia(QMediaContent(QUrl.fromLocalFile(self.ref_path)))
            self.ref_player.play()

    def stop_all(self):
        self._ref_seq += 1
        self.ref_player.stop()
        if self.recording:
            try:
                self.recorder.stop()
            except Exception:
                pass
            self.recording = False
            self.timer.stop()
        self.record_btn.setText("● 开始录音")
        self.meter.set_level(0)

    # ---------- 录音 ----------
    def toggle_record(self):
        if self.recording:
            self.stop_record()
            return
        if not self.ref_path:
            self.status.setText("标准发音还没准备好，请稍候")
            return
        if not Recorder.available():
            QMessageBox.warning(self, "无法录音", "未检测到可用的录音组件（sounddevice）。")
            return
        if self.external_pause:
            self.external_pause()
        self.ref_player.stop()
        try:
            self.recorder.start()
        except Exception as exc:
            QMessageBox.warning(self, "无法录音", f"麦克风打开失败：{exc}")
            return
        self.recording = True
        self._start_ts = time.time()
        self.timer.start()
        self.record_btn.setText("■ 停止录音")
        self.record_btn.setStyleSheet(
            "background:#ef4444;border:1px solid #ef4444;color:white;"
            "border-radius:9px;font-weight:600;padding:8px 18px;")
        self.result.setVisible(False)
        self.user_wave.set_samples(None)
        self.status.setText("正在录音…")

    def stop_record(self):
        self.recording = False
        self.timer.stop()
        self.record_btn.setText("● 开始录音")
        self.record_btn.setStyleSheet("")
        data = self.recorder.stop()
        self.meter.set_level(0)
        if len(data) < self.recorder.samplerate * 0.2:
            self.status.setText("录音太短，请重新录音")
            return
        os.makedirs(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache", "record"),
                    exist_ok=True)
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache", "record",
                            f"user_{int(time.time() * 1000)}.wav")
        audio.write_wav(path, data, self.recorder.samplerate)
        self.user_path = path
        self.user_wave.set_samples(waveform_peaks(audio.resample(data, self.recorder.samplerate)))
        self.user_time.setText(f"{len(data) / self.recorder.samplerate:.1f}s")
        self.status.setText("正在评测…")
        self._evaluate()

    def _evaluate(self):
        if not self.ref_path or not self.user_path:
            return
        self.ring.set_score(0)
        self.summary.setText("正在评测…")
        self.advice.setText("")
        self.result.setVisible(True)
        run_task(audio.evaluate_pronunciation, self._show_result, self._show_error,
                 None, self.ref_path, self.user_path, self.current_text)

    def _show_error(self, message):
        self.status.setText("评测失败")
        self.summary.setText("评测失败")
        self.advice.setText(message)

    def _show_result(self, result):
        self.status.setText("评测完成，可以重新录音再试")
        self.ring.set_score(result["score"])
        score = result["score"]
        if score >= 85:
            summary = "发音清晰，继续保持"
        elif score >= 70:
            summary = "整体不错，注意个别单词"
        elif score >= 55:
            summary = "基本能听懂，需要多练几遍"
        else:
            summary = "与原音差距较大，建议放慢速度跟读"
        self.summary.setText(f"{summary} · {score} 分")
        self.ref_wave.set_samples(result["ref_wave"])
        self.user_wave.set_samples(result["user_wave"])
        lines = ["<b>发音建议</b>"]
        for note in result.get("notes", []):
            lines.append(f"<div>· {note}</div>")
        words = result.get("words", [])
        if words:
            lines.append("<div style='margin-top:4px'><b>需要留意的单词</b></div>")
            for w in words:
                ipa = f" {w['ipa']}" if w.get("ipa") else ""
                color = COLORS["red"] if w["score"] < 55 else COLORS["orange"]
                lines.append(
                    f"<div>· <b>{w['word']}</b>{ipa} "
                    f"<span style='color:{color}'>{w['score']} 分</span></div>")
        self.advice.setText("".join(lines))
        self.result.setVisible(True)

    def reset_recording(self):
        self.user_path = None
        self.user_wave.set_samples(None)
        self.user_time.setText("")
        self.result.setVisible(False)
        self.status.setText("可以开始录音")

    def _tick(self):
        if not self.recording:
            return
        elapsed = time.time() - self._start_ts
        self.record_time.setText(f"{elapsed:.1f}s")
        self.meter.set_level(self.recorder.level)


class ShadowDialog(QDialog):
    """文章 / 音视频 跟读窗口。"""

    def __init__(self, title, sentences, parent=None, media_path=None, is_video=False,
                 items=None, start_index=0):
        super().__init__(parent)
        self.setWindowTitle(f"跟读 - {title}")
        self.resize(1200, 820)
        self.setMinimumSize(1000, 700)
        self.title = title
        self.sentences = [s for s in sentences if s and s.strip()]
        self.media_path = media_path
        self.is_video = is_video
        self.items = items or [{"text": s, "start": None} for s in self.sentences]
        self.current_index = -1
        self._play_end = None
        self._fallback_tried = False
        self._busy = None
        self.player = QMediaPlayer(self)
        self.tts_player = QMediaPlayer(self)
        self.player.setVolume(95)
        self.tts_player.setVolume(95)
        self.practice = ShadowPractice()
        self._build()
        if self.media_path:
            self._load_media()
        if self.items:
            self._select_index(max(0, min(int(start_index or 0), len(self.items) - 1)))

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(label(f"跟读 · {self.title}", 18, COLORS["text"], bold=True))
        head.addStretch(1)
        head.addWidget(label("播放原音 → 录音 → 查看评分与发音建议",
                             10, COLORS["sub"]))
        close = button("关闭", "Ghost")
        close.clicked.connect(self.accept)
        head.addWidget(close)
        lay.addLayout(head)

        if self.media_path:
            self._build_media_body(lay)
        else:
            self._build_article_body(lay)

        self.practice.external_play = self._play_current
        self.practice.external_pause = self._pause_media
        # 句子单独显示在上方，练习面板内不再重复
        self.practice.sentence_label.setVisible(False)
        if self.media_path:
            self.player.positionChanged.connect(self._on_position)

    def _build_article_body(self, lay):
        """上方显示当前句，下方显示跟读练习与评分。"""
        self.resize(1080, 900)
        self._build_sentence_card(lay, "当前句子")
        self._build_practice_area(lay)

    def _build_media_body(self, lay):
        """音视频跟读：上方显示当前字幕，下方跟读与评分；播放使用媒体原声。"""
        self.resize(1080, 900)
        self._build_sentence_card(lay, "当前字幕", with_zh=True)
        self._build_practice_area(lay)

    def _build_sentence_card(self, lay, header_text, with_zh=False):
        card = Card(padding=18)
        head_row = QHBoxLayout()
        head_row.addWidget(label(header_text, 10, COLORS["sub"], bold=True))
        head_row.addSpacing(10)
        self.sent_index = label("", 10, COLORS["sub"])
        head_row.addWidget(self.sent_index)
        head_row.addStretch(1)
        self.prev_sent = button("「 上一句")
        self.prev_sent.clicked.connect(lambda: self._step_sentence(-1))
        self.next_sent = button("下一句 」")
        self.next_sent.clicked.connect(lambda: self._step_sentence(1))
        head_row.addWidget(self.prev_sent)
        head_row.addSpacing(6)
        head_row.addWidget(self.next_sent)
        head_row.addSpacing(12)
        self.hide_sentence = QCheckBox("关闭原句")
        self.hide_sentence.setToolTip("勾选后跟读时不显示原句文字，仅凭听音跟读")
        self.hide_sentence.setCursor(Qt.PointingHandCursor)
        self.hide_sentence.toggled.connect(self._toggle_sentence)
        head_row.addWidget(self.hide_sentence)
        card.layout.addLayout(head_row)

        self.big_sentence = label("", 24, COLORS["text"], wrap=True)
        self.big_sentence.setMinimumHeight(90)
        self.big_sentence.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.big_sentence.setStyleSheet(
            f"background:#f8faff;border:1px solid {COLORS['border']};"
            "border-radius:12px;padding:16px 18px;")
        card.layout.addWidget(self.big_sentence)

        if with_zh:
            self.zh_label = label("", 15, COLORS["sub"], wrap=True)
            self.zh_label.setStyleSheet("padding:0px 18px 10px 18px;")
            self.zh_label.setVisible(False)
            card.layout.addWidget(self.zh_label)

        self.hidden_hint = label("原句已关闭 · 点击「播放原音」听音后开始跟读",
                                 11, COLORS["sub"], wrap=True)
        self.hidden_hint.setAlignment(Qt.AlignCenter)
        self.hidden_hint.setMinimumHeight(90)
        self.hidden_hint.setStyleSheet(
            f"background:#f8faff;border:1px dashed {COLORS['border']};"
            "border-radius:12px;padding:16px 18px;")
        self.hidden_hint.setVisible(False)
        card.layout.addWidget(self.hidden_hint)
        lay.addWidget(card, 0)

    def _build_practice_area(self, lay):
        practice_card = Card(padding=16)
        practice_card.layout.addWidget(self.practice, 1)
        lay.addWidget(practice_card, 1)

        tips = Card(padding=14)
        tips.layout.addWidget(label("评分说明", 10, COLORS["text"], bold=True))
        tips.layout.addWidget(label(
            "评分基于与原音的节奏、频谱特征对齐，并给出逐词发音建议。"
            "60 分以下建议放慢速度、逐词跟读；录音只保存在本地 data/cache/record。",
            9, COLORS["sub"], wrap=True))
        lay.addWidget(tips, 0)

    def _load_media(self):
        if not self.media_path or not os.path.exists(self.media_path):
            return
        # 不设置视频输出，只播原声
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(self.media_path)))
        self.player.mediaStatusChanged.connect(self._on_status)


    def _on_status(self, status):
        if status == QMediaPlayer.InvalidMedia:
            self._try_fallback()

    def _try_fallback(self):
        """系统缺少解码器时（典型是 MP4），用 ffmpeg 转换一次再播放。"""
        if self._fallback_tried or not self.media_path or not os.path.exists(self.media_path):
            return
        self._fallback_tried = True
        self._busy = busy_progress(self, "当前系统缺少该格式解码器，正在转换…")

        def progress(percent, text=""):
            if self._busy:
                self._busy.setValue(int(percent))

        run_task(media.ensure_playable, self._on_fallback, self._on_fallback_failed,
                 progress, self.media_path, self.is_video)

    def _on_fallback(self, path):
        self._close_busy()
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))

    def _on_fallback_failed(self, message):
        self._close_busy()
        QMessageBox.warning(self, "无法播放该媒体", message)

    def _close_busy(self):
        if self._busy:
            self._busy.close()
            self._busy = None

    # ---------- 句子交互 ----------
    def _select_index(self, index):
        if index < 0 or index >= len(self.items):
            return
        self.current_index = index
        text = self.items[index].get("text", "")
        self.big_sentence.setText(text or "（空句子）")
        self.sent_index.setText(f"第 {index + 1} / {len(self.items)} 句")
        self.prev_sent.setEnabled(index > 0)
        self.next_sent.setEnabled(index < len(self.items) - 1)
        if hasattr(self, "zh_label"):
            zh = self.items[index].get("zh") or self.items[index].get("text_zh") or ""
            self.zh_label.setText(zh)
            self.zh_label.setVisible(bool(zh) and not self.hide_sentence.isChecked())
        self.practice.set_sentence(text)

    def _toggle_sentence(self, hidden):
        """关闭原句：隐藏原句文字，仅凭听音跟读（默认不关闭）。"""
        self.big_sentence.setVisible(not hidden)
        self.hidden_hint.setVisible(hidden)
        if hasattr(self, "zh_label"):
            zh = self.zh_label.text().strip()
            self.zh_label.setVisible(bool(zh) and not hidden)

    def _step_sentence(self, delta):
        if not self.items:
            return
        base = self.current_index if self.current_index >= 0 else 0
        target = max(0, min(len(self.items) - 1, base + delta))
        if target != self.current_index:
            self._select_index(target)

    def _play_at(self, index):
        """播放当前句的原声，只播到该句结束。"""
        if not (0 <= index < len(self.items)):
            return
        item = self.items[index]
        start = item.get("start")
        end = item.get("end")
        if start is not None:
            self.player.setPosition(int(float(start) * 1000))
        self._play_end = int(float(end) * 1000) if end is not None else None
        self.player.play()



    def _play_current(self):
        if self.media_path and self.current_index >= 0:
            self._play_at(self.current_index)
        else:
            self.practice.ref_player.setMedia(
                QMediaContent(QUrl.fromLocalFile(self.practice.ref_path)))
            self.practice.ref_player.play()

    def _pause_media(self):
        if self.media_path:
            self.player.pause()

    def _on_position(self, pos):
        if self._play_end is not None and pos >= self._play_end:
            self.player.pause()
            self._play_end = None

    def closeEvent(self, event):  # noqa: N802
        self.player.stop()
        self.tts_player.stop()
        self.practice.stop_all()
        super().closeEvent(event)
