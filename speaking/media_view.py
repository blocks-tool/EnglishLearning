"""音频 / 视频视图：播放、倍速、±n 秒、字幕生成与跟读。"""
import os
import tempfile

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QSpinBox,
    QVBoxLayout, QWidget,
)

from core import asr, audio, db_speaking, media
from core.tasks import run_task
from core.textutil import fmt_time, split_sentences
from core.ui import (
    COLORS, Card, SubtitleList, VideoStage, WaveformWidget,
    busy_progress, button, hline, label,
)

from .dialogs import SentenceTimingDialog, SubtitleEditDialog
from .shadow import ShadowDialog


class MediaView(QWidget):
    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.material = None
        self.kind = "audio"
        self.subtitles = []
        self.current_cue = -1
        self.player = player   # 由主窗口提供，全窗口共用一个播放器
        self._busy = None
        self._src_path = ""
        self._play_path = ""
        self._fallback_tried = False
        self._build()
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.mediaStatusChanged.connect(self._on_status)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        head = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.title_label = label("", 21, COLORS["text"], bold=True)
        self.meta_label = label("", 10, COLORS["sub"])
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.meta_label)
        head.addLayout(title_box)
        head.addStretch(1)
        self.gen_btn = button("生成字幕", "Soft")
        self.gen_btn.clicked.connect(self.generate_subtitles)
        head.addWidget(self.gen_btn)
        self.import_btn = button("导入字幕")
        self.import_btn.clicked.connect(self.import_srt)
        head.addWidget(self.import_btn)
        self.shadow_btn = button("跟读", "Primary")
        self.shadow_btn.clicked.connect(self.open_shadow)
        head.addWidget(self.shadow_btn)
        lay.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(10)

        self.audio_card = Card(padding=18)
        audio_head = QHBoxLayout()
        icon = QLabel("♪")
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            f"background:{COLORS['blue_soft']};color:{COLORS['primary']};"
            "border-radius:11px;font-size:22px;")
        audio_head.addWidget(icon)
        meta_box = QVBoxLayout()
        meta_box.setSpacing(1)
        self.audio_title = label("", 13, COLORS["text"], bold=True)
        self.audio_meta = label("", 9, COLORS["sub"])
        meta_box.addWidget(self.audio_title)
        meta_box.addWidget(self.audio_meta)
        audio_head.addLayout(meta_box, 1)
        self.audio_card.layout.addLayout(audio_head, 0)
        self.wave = WaveformWidget(color=COLORS["primary"], height=150)
        self.audio_card.layout.addWidget(self.wave, 1)
        self.audio_status = label("", 9, COLORS["muted"])
        self.audio_card.layout.addWidget(self.audio_status)
        left.addWidget(self.audio_card, 0)
        left.addStretch(1)

        self.video_card = Card(padding=14)
        self.stage = VideoStage(min_height=360)
        self.video_card.layout.addWidget(self.stage, 1)
        left.addWidget(self.video_card, 1)
        body.addLayout(left, 1)
        self._left = left

        self.sub_card = Card(padding=12)
        sub_head = QHBoxLayout()
        sub_head.addWidget(label("字幕列表", 12, COLORS["text"], bold=True))
        sub_head.addStretch(1)
        self.sub_count = label("", 9, COLORS["muted"])
        sub_head.addWidget(self.sub_count)
        self.sub_card.layout.addLayout(sub_head)
        self.sub_card.layout.addWidget(hline())

        settings = QHBoxLayout()
        settings.setSpacing(5)
        settings.addWidget(label("字号", 9, COLORS["sub"]))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(12, 40)
        self.font_spin.setValue(24)
        self.font_spin.setFixedWidth(58)
        settings.addWidget(self.font_spin)
        settings.addWidget(label("显示", 9, COLORS["sub"]))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["双语字幕", "英文字幕", "中文字幕"])
        self.mode_combo.setFixedWidth(92)
        settings.addWidget(self.mode_combo)
        self.apply_sub_btn = button("应用", "Soft")
        self.apply_sub_btn.clicked.connect(self._apply_subtitle_settings)
        settings.addWidget(self.apply_sub_btn)
        settings.addStretch(1)
        self.edit_btn = button("编辑字幕", "Soft")
        self.edit_btn.clicked.connect(self.open_edit_dialog)
        settings.addWidget(self.edit_btn)
        self.sub_card.layout.addLayout(settings)

        self.sub_list = SubtitleList()
        self.sub_list.sentenceSelected.connect(self._on_cue_selected)
        self.sub_list.sentencePlay.connect(self._on_cue_play)
        self.sub_card.layout.addWidget(self.sub_list, 1)
        self.sub_hint = label("还没有字幕。点击「生成字幕」识别文字并标注时间轴，或导入 SRT。",
                              9, COLORS["muted"], wrap=True)
        self.sub_card.layout.addWidget(self.sub_hint)
        self.sub_card.setMinimumWidth(420)
        self.sub_card.setMaximumWidth(520)
        body.addWidget(self.sub_card, 0)
        lay.addLayout(body, 1)
        self.video_card.setVisible(False)

    # ---------- 数据 ----------
    def set_material(self, material):
        self.player.stop()
        self.material = material
        self.kind = material.get("kind", "audio")
        self.subtitles = list(material.get("subtitle_list") or [])
        self.current_cue = -1
        title = material.get("title", "媒体")
        self.title_label.setText(title)
        self.audio_title.setText(title)
        self.meta_label.setText("音频" if self.kind == "audio" else "视频")
        path = material.get("path", "")
        self._src_path = path
        self._play_path = path
        self._fallback_tried = False
        is_video = self.kind == "video"
        self._left.setStretch(1, 0 if is_video else 1)
        self.audio_card.setVisible(not is_video)
        self.video_card.setVisible(is_video)

        if is_video:
            self.player.setVideoOutput(self.stage.video)
        else:
            self.player.setVideoOutput(None)
            self.audio_status.setText("正在分析波形…")
            self.wave.set_samples(None)
            if path and os.path.exists(path):
                run_task(self._extract_peaks, self._on_peaks,
                         lambda m: self.audio_status.setText(m), None, path)

        self._refresh_subtitles()
        self._update_meta()
        if not path or not os.path.exists(path):
            self.meta_label.setText("媒体文件不存在，请重新导入")
            self.audio_status.setText("文件缺失")
            return
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        self.audio_status.setText("已加载，点击播放开始")

    def _update_meta(self):
        if not self.material:
            return
        path = self.material.get("path", "")
        size = ""
        if path and os.path.exists(path):
            b = os.path.getsize(path)
            size = f"{b / 1024 / 1024:.1f} MB" if b > 1024 * 1024 else f"{b / 1024:.0f} KB"
        duration = self.player.duration()
        parts = ["视频" if self.kind == "video" else "音频"]
        if duration > 0:
            parts.append(f"时长 {fmt_time(duration)}")
        if size:
            parts.append(size)
        self.meta_label.setText(" · ".join(parts))
        self.audio_meta.setText(" · ".join(parts))

    def _extract_peaks(self, path):
        tmpdir = tempfile.mkdtemp(prefix="wave_")
        wav = os.path.join(tmpdir, "a.wav")
        asr.extract_wav(path, wav)
        data, rate = audio.read_wav(wav)
        return audio.waveform_peaks(data), len(data) / rate

    def _on_peaks(self, result):
        peaks, duration = result
        self.wave.set_samples(peaks)
        self.audio_status.setText("波形已就绪")

    def _on_duration(self, duration):
        self._update_meta()

    def _on_status(self, status):
        if status == QMediaPlayer.InvalidMedia:
            self._try_fallback()
        elif status == QMediaPlayer.LoadedMedia:
            self._update_meta()

    def _try_fallback(self):
        """系统缺少解码器时（典型是 MP4），用 ffmpeg 转换一次后播放。"""
        if self._fallback_tried or not self._src_path or not os.path.exists(self._src_path):
            return
        self._fallback_tried = True
        self.meta_label.setText("当前系统缺少该格式解码器，正在转换…")
        self.audio_status.setText("正在转换媒体格式…")
        self._busy = busy_progress(self, "正在转换为可播放格式，请稍候…")

        def progress(percent, text=""):
            if self._busy:
                self._busy.setValue(int(percent))

        run_task(media.ensure_playable, self._on_fallback, self._on_fallback_failed,
                 progress, self._src_path, self.kind == "video")

    def _on_fallback(self, path):
        self._close_busy()
        self._play_path = path
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        self.audio_status.setText("已转换为兼容格式")

    def _on_fallback_failed(self, message):
        self._close_busy()
        self.meta_label.setText("无法播放该媒体（编码不受支持）")
        self.audio_status.setText(message)

    # ---------- 字幕 ----------
    def _display_items(self):
        mode = self.mode_combo.currentText()
        result = []
        for item in self.subtitles:
            text = item.get("text", "")
            zh = item.get("zh") or item.get("text_zh") or ""
            if mode == "英文字幕":
                zh = ""
            elif mode == "中文字幕":
                text = zh or text
                zh = ""
            result.append({"text": text, "zh": zh, "start": item.get("start")})
        return result

    def _refresh_subtitles(self):
        items = self._display_items()
        self.sub_list.set_items(items, bilingual=True,
                                font_size=max(10, self.font_spin.value()))
        self.sub_count.setText(f"{len(self.subtitles)} 条")
        self.sub_hint.setVisible(not self.subtitles)
        self.sub_list.setVisible(bool(self.subtitles))

    def _apply_subtitle_settings(self):
        self._refresh_subtitles()
        if self.kind == "video" and 0 <= self.current_cue < len(self.subtitles):
            self._show_caption(self.current_cue)

    def _show_caption(self, index):
        if not (0 <= index < len(self.subtitles)):
            return
        item = self.subtitles[index]
        text = item.get("text", "")
        zh = item.get("zh") or item.get("text_zh") or ""
        mode = self.mode_combo.currentText()
        if mode == "英文字幕":
            caption = text
        elif mode == "中文字幕":
            caption = zh or text
        else:
            caption = (text + "\n" + zh).strip()
        self.stage.set_caption(caption, self.font_spin.value())

    def generate_subtitles(self):
        """识别出纯文字并按句切分，再在弹框里边听原声边标注时间轴。"""
        if not self.material or not self.material.get("path"):
            return
        path = self.material["path"]
        if not os.path.exists(path):
            QMessageBox.warning(self, "文件不存在", "媒体文件已不存在，请重新导入。")
            return
        self.gen_btn.setEnabled(False)
        self._busy = busy_progress(self, "正在识别语音（首次会自动下载离线模型）…")

        def progress(percent, text=""):
            if self._busy:
                self._busy.setValue(percent)

        def done(text):
            self._close_busy()
            self.gen_btn.setEnabled(True)
            sentences = split_sentences(text)
            if not sentences:
                QMessageBox.information(self, "未识别人声", "没有识别到有效语音，"
                                                            "可以尝试导入 SRT 字幕。")
                return
            self.player.pause()
            dlg = SentenceTimingDialog(sentences,
                                       self._play_path or path,
                                       self.kind == "video", self)
            if dlg.exec_() != QDialog.Accepted:
                return
            items = dlg.result_items()
            if not items:
                return
            self.subtitles = items
            db_speaking.update_material(self.material["id"], subtitles=items)
            self.material["subtitle_list"] = items
            self._refresh_subtitles()
            self.audio_status.setText(f"字幕已生成：{len(items)} 条")
            if self.kind == "video":
                self._show_caption(0)

        def failed(message):
            self._close_busy()
            self.gen_btn.setEnabled(True)
            QMessageBox.warning(self, "字幕生成失败",
                                f"{message}\n\n可以点击「导入字幕」加载 SRT 文件，"
                                "或稍后重试。")

        run_task(asr.transcribe_text, done, failed, progress, path)

    def _close_busy(self):
        if self._busy:
            self._busy.close()
            self._busy = None

    def import_srt(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入字幕", "", "SRT 字幕 (*.srt);;所有文件 (*.*)")
        if not path:
            return
        try:
            items = asr.parse_srt(path)
        except Exception as exc:
            QMessageBox.warning(self, "字幕解析失败", str(exc))
            return
        if not items:
            QMessageBox.information(self, "没有字幕", "该文件里没有解析到字幕内容。")
            return
        self.subtitles = items
        db_speaking.update_material(self.material["id"], subtitles=items)
        self.material["subtitle_list"] = items
        self._refresh_subtitles()

    # ---------- 播放 / 跟读 ----------
    def _on_cue_selected(self, index):
        if 0 <= index < len(self.subtitles):
            self.current_cue = index
            if self.kind == "video":
                self._show_caption(index)

    def _on_cue_play(self, index):
        self._on_cue_selected(index)
        if 0 <= index < len(self.subtitles):
            start = self.subtitles[index].get("start", 0)
            self.player.setPosition(int(float(start) * 1000))
            self.player.play()

    def _on_position(self, pos):
        if not self.subtitles or not self.isVisible():
            return
        seconds = pos / 1000.0
        idx = -1
        for i, item in enumerate(self.subtitles):
            start = item.get("start")
            if start is None:
                continue
            if float(start) <= seconds:
                idx = i
            else:
                break
        if idx >= 0 and idx != self.current_cue:
            self.current_cue = idx
            self.sub_list.set_current(idx)
            if self.kind == "video":
                self._show_caption(idx)
        if self.kind == "audio":
            duration = self.player.duration()
            if duration > 0:
                self.wave.set_progress(pos / duration)

    def open_edit_dialog(self):
        """编辑字幕文本与时间，保存后写回数据库并刷新列表/叠加字幕。"""
        if not self.material or not self.subtitles:
            QMessageBox.information(self, "还没有字幕",
                                    "请先点击「生成字幕」或「导入字幕」，再编辑字幕。")
            return
        dlg = SubtitleEditDialog(self.subtitles, self,
                                 media_path=self._play_path or self.material.get("path", ""),
                                 is_video=self.kind == "video")
        self.player.pause()   # 编辑字幕时用对话框内的播放器试听，避免两路同时出声
        if dlg.exec_() != QDialog.Accepted:
            return
        items = dlg.result_items()
        if not items:
            return
        self.subtitles = items
        db_speaking.update_material(self.material["id"], subtitles=items)
        self.material["subtitle_list"] = items
        self._refresh_subtitles()
        if self.kind == "video" and 0 <= self.current_cue < len(items):
            self._show_caption(self.current_cue)

    def open_shadow(self):
        if not self.material or not self.material.get("path"):
            return
        if not self.subtitles:
            QMessageBox.information(self, "还没有字幕",
                                    "请先点击「生成字幕」或「导入字幕」，再进行跟读。")
            return
        sentences = [item.get("text", "") for item in self.subtitles]
        start = self.current_cue if self.current_cue >= 0 else 0
        dlg = ShadowDialog(self.material.get("title", "媒体"), sentences, self,
                           media_path=self.material.get("path", ""),
                           is_video=self.kind == "video",
                           items=self.subtitles, start_index=start)
        win = self.window()
        win.hide()
        try:
            dlg.exec_()
        finally:
            win.show()
            win.raise_()
            win.activateWindow()

    def stop(self):
        self.player.stop()
        self._close_busy()
