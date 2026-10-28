"""口语助手 - 导入/编辑文章、编辑字幕对话框。"""
import os

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox,
    QSlider, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from core import media
from core.tasks import run_task
from core.textutil import fmt_time, split_sentences, word_count
from core.ui import COLORS, PlayButton, busy_progress, button, label


class ArticleDialog(QDialog):
    """文章导入 / 编辑（复制粘贴）。"""

    def __init__(self, parent=None, title="", content=""):
        super().__init__(parent)
        self.setWindowTitle("文章导入（复制粘贴）" if not content else "编辑文章")
        self.resize(860, 700)
        self.setMinimumSize(720, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(12)
        lay.addWidget(label("文章导入（复制粘贴）" if not content else "编辑文章",
                            18, COLORS["text"], bold=True))
        lay.addWidget(label("粘贴英文文章，程序会按句号切分，便于逐句朗读和跟读。",
                            10, COLORS["sub"]))

        title_row = QHBoxLayout()
        title_row.addWidget(label("标题", 10, COLORS["sub"]))
        self.title_edit = QLineEdit(title)
        self.title_edit.setPlaceholderText("可留空，将自动取第一句作为标题")
        title_row.addWidget(self.title_edit, 1)
        lay.addLayout(title_row)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("请将文章内容复制粘贴到此处…")
        self.editor.setPlainText(content)
        self.editor.textChanged.connect(self._update_count)
        lay.addWidget(self.editor, 1)

        bottom = QHBoxLayout()
        self.count_label = label("", 10, COLORS["sub"])
        bottom.addWidget(self.count_label)
        bottom.addStretch(1)
        cancel = button("取消")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        self.ok_btn = button("导入" if not content else "保存", "Primary")
        self.ok_btn.clicked.connect(self._accept)
        bottom.addWidget(self.ok_btn)
        lay.addLayout(bottom)
        self._update_count()

    def _update_count(self):
        text = self.editor.toPlainText()
        chars = len(text.strip())
        words = word_count(text)
        sentences = len(split_sentences(text))
        self.count_label.setText(f"字数 {chars} · 单词 {words} · 句子 {sentences}")

    def _accept(self):
        text = self.editor.toPlainText().strip()
        if not text:
            self.count_label.setText("请先粘贴文章内容")
            return
        title = self.title_edit.text().strip()
        if not title:
            first = split_sentences(text)
            title = (first[0] if first else text)[:36]
            if len(title) >= 36:
                title = title[:34] + "…"
        self.accept()

    def values(self):
        text = self.editor.toPlainText().strip()
        title = self.title_edit.text().strip()
        if not title:
            first = split_sentences(text)
            title = (first[0] if first else text)[:36]
        return title, text


class PlaybackPanel(QWidget):
    """原声播放条：播放/暂停、可拖动进度、时间；视频素材附带画面预览。

    缺少解码器时（典型是 MP4）自动用 ffmpeg 转换一次再播放。
    """

    def __init__(self, media_path="", is_video=False, parent=None):
        super().__init__(parent)
        self.media_path = media_path or ""
        self.is_video = bool(is_video)
        self.available = bool(self.media_path and os.path.exists(self.media_path))
        self._dragging = False
        self._fallback_tried = False
        self._busy = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.video = None
        if self.is_video:
            self.video = QVideoWidget()
            self.video.setMinimumHeight(180)
            self.video.setMaximumHeight(240)
            self.video.setStyleSheet("background:#000000;border-radius:8px;")
            lay.addWidget(self.video)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.play_btn = PlayButton(diameter=40)
        self.play_btn.clicked.connect(self.toggle)
        row.addWidget(self.play_btn)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderPressed.connect(self._on_drag_start)
        self.slider.sliderReleased.connect(self._on_drag_end)
        row.addWidget(self.slider, 1)
        self.time_label = label("00:00 / 00:00", 9, COLORS["sub"])
        self.time_label.setFixedWidth(108)
        row.addWidget(self.time_label)
        self._row = row
        lay.addLayout(row)

        self.player = QMediaPlayer(self)
        self.player.setVolume(95)
        if self.video is not None:
            self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.stateChanged.connect(
            lambda state: self.play_btn.set_playing(state == QMediaPlayer.PlayingState))
        if self.available:
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(self.media_path)))
        else:
            self.play_btn.setEnabled(False)

    def add_action(self, widget):
        """在播放按钮与时间之后追加一个操作按钮。"""
        self._row.addWidget(widget)

    def position(self):
        return self.player.position()

    def duration(self):
        return self.player.duration()

    def toggle(self):
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def play(self, at_ms=None):
        if at_ms is not None:
            self.player.setPosition(int(at_ms))
        self.player.play()

    def pause(self):
        self.player.pause()

    def stop(self):
        self._close_busy()
        self.player.stop()

    # ---------- 内部 ----------
    def _on_position(self, pos):
        if not self._dragging:
            self.slider.setValue(pos)
        self.time_label.setText(f"{fmt_time(pos)} / {fmt_time(self.player.duration())}")

    def _on_duration(self, duration):
        self.slider.setRange(0, max(0, duration))
        self.time_label.setText(f"{fmt_time(self.player.position())} / {fmt_time(duration)}")

    def _on_drag_start(self):
        self._dragging = True

    def _on_drag_end(self):
        self._dragging = False
        self.player.setPosition(self.slider.value())

    def _on_status(self, status):
        if status == QMediaPlayer.InvalidMedia:
            self._try_fallback()
        elif status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia):
            self._on_duration(self.player.duration())

    def _try_fallback(self):
        if self._fallback_tried or not self.available:
            return
        self._fallback_tried = True
        self.play_btn.setEnabled(False)
        self.slider.setEnabled(False)
        self.time_label.setText("正在转换…")
        self._busy = busy_progress(self, "当前系统缺少该格式解码器，正在转换…")

        def progress(percent, text=""):
            if self._busy:
                self._busy.setValue(int(percent))

        run_task(media.ensure_playable, self._on_fallback, self._on_fallback_failed,
                 progress, self.media_path, self.is_video)

    def _on_fallback(self, path):
        self._close_busy()
        self.play_btn.setEnabled(True)
        self.slider.setEnabled(True)
        self.time_label.setText("00:00 / 00:00")
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))

    def _on_fallback_failed(self, message):
        self._close_busy()
        self.time_label.setText("无法播放")
        QMessageBox.warning(self, "无法试听该媒体", message)

    def _close_busy(self):
        if self._busy:
            self._busy.close()
            self._busy = None


class SubtitleEditDialog(QDialog):
    """字幕编辑：逐条修改开始/结束时间与中英文文本，可边听原声边校对时间。"""

    def __init__(self, items, parent=None, media_path="", is_video=False):
        super().__init__(parent)
        self.setWindowTitle("编辑字幕")
        self.resize(980, 720)
        self.setMinimumSize(800, 560)
        self.media_path = media_path or ""
        self.is_video = bool(is_video)
        self._items = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        lay.setSpacing(10)
        lay.addWidget(label("编辑字幕", 18, COLORS["text"], bold=True))
        lay.addWidget(label("可直接修改时间（秒）与中英文内容，保存后立即生效。"
                            "选中一行后点「播放选中句」可试听该句位置。",
                            10, COLORS["sub"]))

        self.table = QTableWidget(len(items), 4)
        self.table.setHorizontalHeaderLabels(["开始(秒)", "结束(秒)", "英文字幕", "中文翻译"])
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        for r, item in enumerate(items):
            start = item.get("start")
            end = item.get("end")
            values = [
                f"{float(start):.2f}" if start is not None else "",
                f"{float(end):.2f}" if end is not None else "",
                item.get("text", ""),
                item.get("zh") or item.get("text_zh") or "",
            ]
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(value))
        self.table.resizeRowsToContents()
        lay.addWidget(self.table, 1)
        self._build_player(lay)

        bottom = QHBoxLayout()
        self.count_label = label(f"共 {len(items)} 条", 10, COLORS["sub"])
        bottom.addWidget(self.count_label)
        bottom.addStretch(1)
        cancel = button("取消")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        save = button("保存", "Primary")
        save.clicked.connect(self._accept)
        bottom.addWidget(save)
        lay.addLayout(bottom)

    def _accept(self):
        def parse_time(text, row, name):
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                raise ValueError(f"第 {row + 1} 条：{name}请填写数字（秒）")

        items = []
        try:
            for r in range(self.table.rowCount()):
                def cell(c):
                    it = self.table.item(r, c)
                    return it.text().strip() if it else ""

                start = parse_time(cell(0), r, "开始时间")
                end = parse_time(cell(1), r, "结束时间")
                if start is not None and end is not None and end < start:
                    raise ValueError(f"第 {r + 1} 条：结束时间早于开始时间")
                item = {"text": cell(2), "zh": cell(3)}
                if start is not None:
                    item["start"] = start
                if end is not None:
                    item["end"] = end
                items.append(item)
        except ValueError as exc:
            QMessageBox.warning(self, "时间格式有误",
                                f"{exc}\n例如 12.35 表示第 12.35 秒。")
            return
        self._items = items
        self.accept()

    def result_items(self):
        return getattr(self, "_items", [])

    # ---------- 播放 ----------
    def _build_player(self, lay):
        self._play_end = None
        self.playback = PlaybackPanel(self.media_path, self.is_video, self)
        self.play_row_btn = button("播放选中句", "Soft")
        self.play_row_btn.clicked.connect(self._play_selected)
        self.playback.add_action(self.play_row_btn)
        if not self.playback.available:
            self.play_row_btn.setEnabled(False)
        self.playback.player.positionChanged.connect(self._on_play_position)
        # 手动播放/拖动进度条后取消句尾自动暂停
        self.playback.play_btn.clicked.connect(self._clear_play_end)
        self.playback.slider.sliderReleased.connect(self._clear_play_end)
        lay.addWidget(self.playback)

    def _clear_play_end(self):
        self._play_end = None

    def _on_play_position(self, pos):
        if self._play_end is not None and pos >= self._play_end:
            self.playback.pause()
            self._play_end = None

    def _play_selected(self):
        """播放当前选中句，到该句结束时间自动暂停。"""
        row = self.table.currentRow()
        if row < 0:
            row = 0

        def cell(c):
            item = self.table.item(row, c)
            return item.text().strip() if item else ""

        try:
            start = float(cell(0))
        except ValueError:
            start = 0.0
        try:
            end = float(cell(1))
        except ValueError:
            end = None
        self._play_end = int(end * 1000) if end is not None and end > start else None
        self.playback.play(start * 1000)

    def done(self, result):
        self.playback.stop()
        super().done(result)


class SentenceTimingDialog(QDialog):
    """生成字幕后：文字已按句切分，边播放原声边为每句标注时间轴。"""

    def __init__(self, sentences, media_path="", is_video=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("字幕时间轴")
        self.resize(1000, 780)
        self.setMinimumSize(860, 640)
        self._items = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        lay.setSpacing(10)
        lay.addWidget(label("字幕时间轴", 18, COLORS["text"], bold=True))
        lay.addWidget(label(
            "文字已按句切分。播放原声，在每句开口处点「记录当前时间」，"
            "会自动填入该句开始时间和上一句结束时间并跳到下一句；"
            "也可以直接编辑表格里的文字与时间。", 10, COLORS["sub"], wrap=True))

        self.table = QTableWidget(len(sentences), 4)
        self.table.setHorizontalHeaderLabels(["序号", "字幕文本", "开始(秒)", "结束(秒)"])
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        for r, sentence in enumerate(sentences):
            index_item = QTableWidgetItem(str(r + 1))
            index_item.setFlags(index_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 0, index_item)
            self.table.setItem(r, 1, QTableWidgetItem(sentence))
            self.table.setItem(r, 2, QTableWidgetItem(""))
            self.table.setItem(r, 3, QTableWidgetItem(""))
        self.table.resizeRowsToContents()
        if sentences:
            self.table.setCurrentCell(0, 1)
        lay.addWidget(self.table, 1)

        self.playback = PlaybackPanel(media_path, is_video, self)
        lay.addWidget(self.playback)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.mark_btn = button("记录当前时间", "Primary")
        self.mark_btn.clicked.connect(self._mark_current)
        actions.addWidget(self.mark_btn)
        self.play_row_btn = button("播放此句", "Soft")
        self.play_row_btn.clicked.connect(self._play_selected)
        actions.addWidget(self.play_row_btn)
        self.clear_btn = button("清空该句时间", "Ghost")
        self.clear_btn.clicked.connect(self._clear_row)
        actions.addWidget(self.clear_btn)
        actions.addStretch(1)
        lay.addLayout(actions)
        if not self.playback.available:
            self.mark_btn.setEnabled(False)
            self.play_row_btn.setEnabled(False)

        bottom = QHBoxLayout()
        self.count_label = label(f"共 {len(sentences)} 句", 10, COLORS["sub"])
        bottom.addWidget(self.count_label)
        bottom.addStretch(1)
        cancel = button("取消")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        save = button("保存字幕", "Primary")
        save.clicked.connect(self._accept)
        bottom.addWidget(save)
        lay.addLayout(bottom)

    # ---------- 时间轴 ----------
    def _time(self, row, col):
        item = self.table.item(row, col)
        if not item:
            return None
        text = item.text().strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _mark_current(self):
        """把当前播放位置记为选中句的开始，并把上一句的结束时间对齐到这里。"""
        t = self.playback.position() / 1000.0
        row = self.table.currentRow()
        if row < 0:
            row = 0
        self.table.setItem(row, 2, QTableWidgetItem(f"{t:.2f}"))
        if row > 0:
            prev_start = self._time(row - 1, 2)
            if prev_start is not None and prev_start <= t:
                self.table.setItem(row - 1, 3, QTableWidgetItem(f"{t:.2f}"))
        if row + 1 < self.table.rowCount():
            self.table.setCurrentCell(row + 1, 1)
            self.table.scrollToItem(self.table.item(row + 1, 1),
                                    QAbstractItemView.PositionAtCenter)

    def _play_selected(self):
        row = self.table.currentRow()
        if row < 0:
            row = 0
        start = self._time(row, 2) or 0.0
        self.playback.play(start * 1000)
        self.table.setCurrentCell(row, 1)

    def _clear_row(self):
        row = self.table.currentRow()
        if row < 0:
            return
        self.table.setItem(row, 2, QTableWidgetItem(""))
        self.table.setItem(row, 3, QTableWidgetItem(""))

    def _accept(self):
        rows = []
        try:
            for r in range(self.table.rowCount()):
                def cell(c):
                    item = self.table.item(r, c)
                    return item.text().strip() if item else ""

                text = cell(1)
                if not text:
                    continue
                start = self._parse(cell(2), r, "开始时间")
                end = self._parse(cell(3), r, "结束时间")
                if start is not None and end is not None and end < start:
                    raise ValueError(f"第 {r + 1} 句：结束时间早于开始时间")
                rows.append({"text": text, "start": start, "end": end})
        except ValueError as exc:
            QMessageBox.warning(self, "时间格式有误",
                                f"{exc}\n例如 12.35 表示第 12.35 秒。")
            return
        if not rows:
            QMessageBox.information(self, "没有字幕文字", "请先保留至少一句字幕文本。")
            return

        duration = self.playback.duration() / 1000.0
        untimed = [str(i + 1) for i, row in enumerate(rows) if row["start"] is None]
        if untimed:
            QMessageBox.warning(
                self, "还有句子没有开始时间",
                "第 " + "、".join(untimed[:8]) + (" 等" if len(untimed) > 8 else "") +
                " 句还没有开始时间。\n请播放原声并点「记录当前时间」，"
                "或直接在「开始(秒)」列填写。")
            return
        for i, row in enumerate(rows):
            if row["end"] is None:
                nxt = next((r["start"] for r in rows[i + 1:] if r["start"] is not None), None)
                if nxt is not None and nxt > row["start"]:
                    row["end"] = nxt
                elif duration > row["start"]:
                    row["end"] = duration
                else:
                    row["end"] = row["start"] + 2.0
            if row["end"] <= row["start"]:
                row["end"] = row["start"] + 0.5
        self._items = [{
            "text": row["text"],
            "zh": "",
            "start": round(row["start"], 2),
            "end": round(row["end"], 2),
        } for row in rows]
        self.accept()

    @staticmethod
    def _parse(text, row, name):
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            raise ValueError(f"第 {row + 1} 句：{name}请填写数字（秒）")

    def result_items(self):
        return self._items

    def done(self, result):
        self.playback.stop()
        super().done(result)
