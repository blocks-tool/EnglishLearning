"""Qt 通用界面层：主题样式、播放器控制条、波形、评分环、字幕列表等。"""
import html
import os

import numpy as np
from PyQt5.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap,
    QPolygonF,
)
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QProgressDialog, QPushButton, QSizePolicy, QSlider, QSpinBox,
    QStyle, QTextBrowser, QVBoxLayout, QWidget,
)

from .textutil import fmt_time

COLORS = {
    "bg": "#f4f7fc",
    "card": "#ffffff",
    "border": "#e6eaf2",
    "text": "#111827",
    "sub": "#6b7280",
    "muted": "#9ca3af",
    "primary": "#3478f6",
    "primary_dark": "#2563d8",
    "blue_soft": "#e9f1fe",
    "red": "#ef4444",
    "orange": "#f59e0b",
    "green": "#10b981",
    "purple": "#8b5cf6",
    "sidebar": "#ffffff",
}

ARTICLE_FONT = 22       # 文章阅读区字号
ARTICLE_LINE_HEIGHT = 1.8
ARTICLE_ROW_GAP = 16    # 句与句之间的行间距


def apply_theme(app):
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(QSS)


QSS = f"""
* {{
    font-family: "Microsoft YaHei UI", "PingFang SC", "Segoe UI";
    outline: none;
}}
QMainWindow, QDialog {{ background: {COLORS['bg']}; }}
QWidget {{ color: {COLORS['text']}; }}
QLabel {{ background: transparent; }}
QFrame#Card {{
    background: {COLORS['card']};
    border: 1px solid {COLORS['border']};
    border-radius: 14px;
}}
QFrame#Sidebar {{
    background: {COLORS['sidebar']};
    border-right: 1px solid {COLORS['border']};
}}
QFrame#Divider {{ background: {COLORS['border']}; max-height: 1px; min-height: 1px; border: none; }}
QPushButton {{
    background: #ffffff;
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 6px 12px;
    color: {COLORS['text']};
}}
QPushButton:hover {{ background: #f7f9ff; border-color: #cfd9ee; }}
QPushButton:pressed {{ background: #edf2ff; }}
QPushButton:disabled {{ color: {COLORS['muted']}; background: #f6f7fa; }}
QPushButton#Primary {{
    background: {COLORS['primary']};
    border: 1px solid {COLORS['primary']};
    color: #ffffff;
    font-weight: 600;
    padding: 7px 16px;
}}
QPushButton#Primary:hover {{ background: {COLORS['primary_dark']}; }}
QPushButton#Primary:disabled {{ background: #a9c1ff; border-color: #a9c1ff; }}
QPushButton#Soft {{
    background: {COLORS['blue_soft']};
    border: 1px solid #d7e3ff;
    color: {COLORS['primary_dark']};
    font-weight: 600;
}}
QPushButton#Soft:hover {{ background: #dbe7ff; }}
QPushButton#Danger {{ color: {COLORS['red']}; }}
QPushButton#Danger:hover {{ background: #fff1f1; border-color: #fbcaca; }}
QPushButton#Ghost {{ background: transparent; border: none; color: {COLORS['sub']}; padding: 4px 8px; }}
QPushButton#Ghost:hover {{ background: #f0f3f9; color: {COLORS['text']}; }}
QPushButton#PlayButton {{
    background: transparent;
    border: none;
    padding: 0px;
}}
QPushButton#Round {{ border-radius: 16px; min-width: 32px; max-width: 32px;
    min-height: 32px; max-height: 32px; padding: 0px; }}
QPushButton#SentencePlay {{
    border-radius: 13px; min-width: 26px; max-width: 26px;
    min-height: 26px; max-height: 26px; padding: 0px;
    color: {COLORS['primary']}; background: {COLORS['blue_soft']}; border: none;
    font-size: 11px;
}}
QPushButton#SentencePlay:hover {{ background: #d9e6ff; }}
QPushButton#RecordButton {{
    background: #fff1f2; border: 1px solid #fecdd3; color: {COLORS['red']};
    border-radius: 9px; font-weight: 600; padding: 8px 18px;
}}
QPushButton#RecordButton:hover {{ background: #ffe4e6; }}
QLineEdit, QSpinBox, QComboBox {{
    background: #ffffff; border: 1px solid {COLORS['border']};
    border-radius: 8px; padding: 5px 9px; min-height: 20px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: #9db8ff; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: #ffffff; border: 1px solid {COLORS['border']};
    selection-background-color: {COLORS['blue_soft']};
    selection-color: {COLORS['text']}; padding: 4px;
}}
QTextEdit, QTextBrowser, QPlainTextEdit {{
    background: #ffffff; border: 1px solid {COLORS['border']};
    border-radius: 10px; padding: 8px; selection-background-color: #cfe0ff;
}}
QTextBrowser#ArticleBody {{ border: none; background: transparent; padding: 0px; }}
QSlider::groove:horizontal {{
    height: 4px; background: #e3e8f2; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {COLORS['primary']}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #ffffff; border: 2px solid {COLORS['primary']};
    width: 12px; height: 12px; margin: -5px 0; border-radius: 7px;
}}
QSlider::groove:vertical {{ width: 4px; background: #e3e8f2; border-radius: 2px; }}
QSlider::handle:vertical {{ background: {COLORS['primary']}; height: 12px; margin: 0 -5px;
    border-radius: 6px; }}
QTreeWidget {{
    background: transparent; border: none; show-decoration-selected: 1;
}}
QTreeWidget::item {{ height: 34px; border-radius: 8px; padding-left: 2px; }}
QTreeWidget::item:hover {{ background: #f2f5fc; }}
QTreeWidget::item:selected {{ background: {COLORS['blue_soft']}; color: {COLORS['primary_dark']}; }}
QTreeWidget::branch {{ background: transparent; }}
QListWidget {{
    background: transparent; border: none;
}}
QListWidget::item {{ border-radius: 8px; padding: 4px; }}
QListWidget::item:hover {{ background: #f7f9ff; }}
QListWidget::item:selected {{ background: {COLORS['blue_soft']}; color: {COLORS['text']}; }}
QTableWidget {{
    background: #ffffff; alternate-background-color: #fbfcfe;
    border: none; gridline-color: #eef1f7; selection-background-color: #e8f0ff;
    selection-color: {COLORS['text']};
}}
QTableWidget::item {{ padding: 8px 6px; border-bottom: 1px solid #f1f4f9; }}
QHeaderView::section {{
    background: #f8faff; border: none; border-bottom: 1px solid {COLORS['border']};
    padding: 9px 6px; color: {COLORS['sub']}; font-weight: 600;
}}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #d6dce8; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #bcc7db; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #d6dce8; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
QTabWidget::pane {{ border: 1px solid {COLORS['border']}; border-radius: 10px; background: #fff; }}
QTabBar::tab {{
    background: transparent; color: {COLORS['sub']}; padding: 7px 16px;
    border-radius: 8px; margin-right: 4px;
}}
QTabBar::tab:selected {{ background: {COLORS['blue_soft']}; color: {COLORS['primary_dark']}; font-weight: 600; }}
QProgressBar {{
    background: #edf1f8; border: none; border-radius: 4px; height: 8px; text-align: center;
}}
QProgressBar::chunk {{ background: {COLORS['primary']}; border-radius: 4px; }}
QMenu {{
    background: #ffffff; border: 1px solid {COLORS['border']}; border-radius: 8px; padding: 5px;
}}
QMenu::item {{ padding: 7px 20px; border-radius: 5px; }}
QMenu::item:selected {{ background: {COLORS['blue_soft']}; }}
QToolTip {{
    background: #1f2937; color: white; border: none; padding: 5px 8px; border-radius: 5px;
}}
QSplitter::handle {{ background: transparent; }}
"""


def hline():
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.HLine)
    return line


def label(text="", size=10, color=None, bold=False, wrap=False):
    lb = QLabel(text)
    f = QFont("Microsoft YaHei UI", size)
    f.setBold(bold)
    lb.setFont(f)
    if color:
        lb.setStyleSheet(f"color:{color};")
    lb.setWordWrap(wrap)
    return lb


def button(text, kind=None, tooltip=None, size=None):
    btn = QPushButton(text)
    if kind:
        btn.setObjectName(kind)
    if tooltip:
        btn.setToolTip(tooltip)
    if size:
        btn.setMinimumHeight(size)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


class PlayButton(QPushButton):
    """圆形播放/暂停按钮：自绘图标，悬停加深，避免字符图标模糊。"""

    def __init__(self, parent=None, diameter=46):
        super().__init__(parent)
        self.setObjectName("PlayButton")
        self._playing = False
        self._hover = False
        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip("播放 / 暂停")

    def set_playing(self, playing):
        if self._playing != playing:
            self._playing = playing
            self.update()

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        d = min(self.width(), self.height())
        if not self.isEnabled():
            color = QColor("#bfd0f7")
        elif self._hover:
            color = QColor(COLORS["primary_dark"])
        else:
            color = QColor(COLORS["primary"])
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(1, 1, d - 2, d - 2)

        painter.setBrush(QColor("#ffffff"))
        cx, cy = d / 2.0, d / 2.0
        if self._playing:
            bar_w, bar_h, gap = d * 0.10, d * 0.34, d * 0.13
            top = cy - bar_h / 2
            painter.drawRoundedRect(QRectF(cx - gap / 2 - bar_w, top, bar_w, bar_h),
                                    bar_w / 2, bar_w / 2)
            painter.drawRoundedRect(QRectF(cx + gap / 2, top, bar_w, bar_h),
                                    bar_w / 2, bar_w / 2)
        else:
            w, h = d * 0.30, d * 0.36
            shift = d * 0.035   # 视觉居中，三角形略向右移
            triangle = QPolygonF([
                QPointF(cx - w / 2 + shift, cy - h / 2),
                QPointF(cx - w / 2 + shift, cy + h / 2),
                QPointF(cx + w / 2 + shift, cy),
            ])
            painter.drawPolygon(triangle)


class Card(QFrame):
    def __init__(self, parent=None, padding=18, radius=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(padding, padding, padding, padding)
        self.layout.setSpacing(12)


class PlayerBar(QWidget):
    """完整播放控制条：进度、暂停/恢复、±n 秒、倍速、上一句/下一句。"""

    prevClicked = pyqtSignal()
    nextClicked = pyqtSignal()
    rateChanged = pyqtSignal(float)
    finished = pyqtSignal()

    def __init__(self, parent=None, navigation=True):
        super().__init__(parent)
        self.player = None
        self.toggle_handler = None   # 指定后，播放按钮改由该回调处理（如文章朗读）
        self.skip_seconds = 5
        self._duration = 0
        self._seeking = False
        self._build(navigation)
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._sync_position)

    def _build(self, navigation):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.slider.sliderReleased.connect(self._on_seek)
        self.time_label = label("00:00 / 00:00", 9, COLORS["sub"])
        self.time_label.setMinimumWidth(96)
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row1.addWidget(self.slider, 1)
        row1.addWidget(self.time_label)
        outer.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.rewind_btn = button("« 5s", None, "快退")
        self.rewind_btn.setFixedHeight(32)
        self.rewind_btn.setMinimumWidth(64)
        self.rewind_btn.clicked.connect(lambda: self.skip(-self.skip_seconds))
        self.prev_btn = button("|«", "Round", "上一句")
        self.prev_btn.clicked.connect(self.prevClicked.emit)
        self.play_btn = PlayButton(diameter=46)
        self.play_btn.clicked.connect(self.toggle)
        self.next_btn = button("»|", "Round", "下一句")
        self.next_btn.clicked.connect(self.nextClicked.emit)
        self.forward_btn = button("5s »", None, "快进")
        self.forward_btn.setFixedHeight(32)
        self.forward_btn.setMinimumWidth(64)
        self.forward_btn.clicked.connect(lambda: self.skip(self.skip_seconds))

        self.volume_icon = button("", "Ghost", "静音")
        self.volume_icon.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume))
        self.volume_icon.setIconSize(QSize(16, 16))
        self.volume_icon.setFixedWidth(28)
        self.volume_icon.clicked.connect(self._toggle_mute)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(90)
        self.volume.setFixedWidth(70)
        self.volume.valueChanged.connect(self._on_volume)

        row2.addWidget(self.rewind_btn)
        if navigation:
            row2.addWidget(self.prev_btn)
        row2.addWidget(self.play_btn)
        if navigation:
            row2.addWidget(self.next_btn)
        row2.addWidget(self.forward_btn)
        row2.addStretch(1)
        row2.addWidget(self.volume_icon)
        row2.addWidget(self.volume)
        outer.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(6)
        row3.addWidget(label("快进/快退时长", 9, COLORS["sub"]))
        self.skip_spin = QSpinBox()
        self.skip_spin.setRange(1, 120)
        self.skip_spin.setValue(5)
        self.skip_spin.setSuffix(" 秒")
        self.skip_spin.setFixedWidth(82)
        row3.addWidget(self.skip_spin)
        row3.addWidget(label("(默认 5 秒)", 9, COLORS["muted"]))
        row3.addSpacing(14)
        row3.addWidget(label("播放速度", 9, COLORS["sub"]))
        self.speed_combo = QComboBox()
        for r in ("0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"):
            self.speed_combo.addItem(r)
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.setFixedWidth(76)
        self.speed_combo.currentTextChanged.connect(self._on_speed_combo)
        row3.addWidget(self.speed_combo)
        self.apply_btn = button("应用", "Soft")
        self.apply_btn.clicked.connect(self._apply_settings)
        row3.addWidget(self.apply_btn)
        row3.addStretch(1)
        outer.addLayout(row3)

        self.prev_btn.setVisible(navigation)
        self.next_btn.setVisible(navigation)

    # ---------- 绑定播放器 ----------
    def set_player(self, player):
        self.player = player
        player.positionChanged.connect(self._on_position)
        player.durationChanged.connect(self._on_duration)
        player.stateChanged.connect(self._on_state)
        player.volumeChanged.connect(self._on_volume_changed)
        player.setVolume(self.volume.value())
        player.mediaStatusChanged.connect(self._on_media_status)

    def set_navigation(self, visible):
        self.prev_btn.setVisible(visible)
        self.next_btn.setVisible(visible)

    def play_file(self, path, autoplay=True):
        if not self.player or not path:
            return
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        if autoplay:
            self.player.play()

    def load_file(self, path):
        self.play_file(path, autoplay=False)

    def toggle(self):
        if self.toggle_handler:
            self.toggle_handler()
            return
        if not self.player or not self.player.media().canonicalUrl().isValid():
            return
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def pause(self):
        if self.player and self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()

    def stop(self):
        if self.player:
            self.player.stop()

    def skip(self, seconds):
        if not self.player or self._duration <= 0:
            return
        pos = self.player.position() + int(seconds * 1000)
        self.player.setPosition(max(0, min(self._duration, pos)))

    def seek_ms(self, ms):
        if self.player:
            self.player.setPosition(max(0, int(ms)))

    def set_rate(self, rate):
        if self.player:
            self.player.setPlaybackRate(rate)
        text = f"{rate:g}x"
        self.speed_combo.blockSignals(True)
        self.speed_combo.setCurrentText(text)
        self.speed_combo.blockSignals(False)

    # ---------- 内部 ----------
    def _on_seek(self):
        self._seeking = False
        if self.player and self._duration:
            self.player.setPosition(int(self.slider.value() / 1000 * self._duration))

    def _on_position(self, pos):
        if self._seeking or self._duration <= 0:
            return
        self.slider.blockSignals(True)
        self.slider.setValue(int(pos / self._duration * 1000))
        self.slider.blockSignals(False)
        self.time_label.setText(f"{fmt_time(pos)} / {fmt_time(self._duration)}")

    def _on_duration(self, duration):
        self._duration = max(0, duration)
        if self._duration == 0:
            # 媒体被清空（如切换到文章）：进度条一并归零
            self.slider.blockSignals(True)
            self.slider.setValue(0)
            self.slider.blockSignals(False)
        self.time_label.setText(f"{fmt_time(0)} / {fmt_time(self._duration)}")

    def _on_state(self, state):
        self.play_btn.set_playing(state == QMediaPlayer.PlayingState)
        if state == QMediaPlayer.PlayingState:
            self._timer.start()
        else:
            self._timer.stop()

    def _sync_position(self):
        if self.player:
            self._on_position(self.player.position())

    def _on_volume(self, value):
        if self.player:
            self.player.setVolume(value)
        self.volume_icon.setIcon(self.style().standardIcon(
            QStyle.SP_MediaVolumeMuted if value == 0 else QStyle.SP_MediaVolume))

    def _on_volume_changed(self, value):
        if self.volume.value() != value:
            self.volume.blockSignals(True)
            self.volume.setValue(value)
            self.volume.blockSignals(False)

    def _toggle_mute(self):
        if self.volume.value() > 0:
            self.volume.setValue(0)
        else:
            self.volume.setValue(90)

    def _apply_settings(self):
        self.skip_seconds = self.skip_spin.value()
        self.rewind_btn.setText(f"« {self.skip_seconds}s")
        self.forward_btn.setText(f"{self.skip_seconds}s »")
        try:
            rate = float(self.speed_combo.currentText().replace("x", ""))
        except ValueError:
            rate = 1.0
        self.set_rate(rate)
        self.rateChanged.emit(rate)

    def _on_speed_combo(self, text):
        """选择倍速后立即生效，无需再点“应用”。"""
        try:
            rate = float(text.replace("x", ""))
        except ValueError:
            return
        if self.player:
            self.player.setPlaybackRate(rate)
        self.rateChanged.emit(rate)

    def _on_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.finished.emit()


class VideoStage(QWidget):
    """视频画面 + 底部字幕叠加。"""

    def __init__(self, parent=None, min_height=300):
        super().__init__(parent)
        self.setMinimumHeight(min_height)
        self.setStyleSheet("background:#0b1020;border-radius:12px;")
        self.video = QVideoWidget(self)
        self.video.setStyleSheet("background:#0b1020;")
        self.caption = QLabel(self)
        self.caption.setWordWrap(True)
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setStyleSheet(
            "background:rgba(12,18,32,185);color:#ffffff;border-radius:8px;"
            "padding:8px 14px;font-size:18px;font-weight:600;")
        self.caption.hide()

    def set_caption(self, text, font_size=18, visible=True):
        self.caption.setText((text or "").replace("\n", "<br>"))
        self.caption.setStyleSheet(
            "background:rgba(12,18,32,185);color:#ffffff;border-radius:8px;"
            f"padding:8px 14px;font-size:{font_size}px;font-weight:600;")
        self.caption.setVisible(bool(text) and visible)
        self._place()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._place()

    def _place(self):
        self.video.setGeometry(0, 0, self.width(), self.height())
        if not self.caption.isVisible():
            return
        width = max(220, self.width() - 56)
        fm = QFontMetrics(self.caption.font())
        text = self.caption.text()
        rect = fm.boundingRect(0, 0, width, 2000, Qt.TextWordWrap, text)
        height = min(int(self.height() * 0.42), rect.height() + 20)
        self.caption.setGeometry((self.width() - width) // 2,
                                 max(8, self.height() - height - 18), width, height)
        self.caption.raise_()


def busy_progress(parent, text):
    # 用非模态：Windows 上关闭窗口模态的 QProgressDialog 时，
    # 若同时有播放器/线程信号在排队，偶发原生崩溃（0xC0000409）。
    dlg = QProgressDialog(text, "", 0, 100, parent)
    dlg.setWindowTitle("请稍候")
    dlg.setWindowModality(Qt.NonModal)
    dlg.setCancelButton(None)
    dlg.setMinimumDuration(0)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    dlg.setValue(0)
    dlg.show()
    return dlg


class WaveformWidget(QWidget):
    """音频波形（参考音、我的录音共用）。"""

    def __init__(self, parent=None, color="#2f6bff", height=56):
        super().__init__(parent)
        self._samples = None
        self._progress = 0.0
        self._color = QColor(color)
        self.setMinimumHeight(height)
        self.setMaximumHeight(height * 2)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_samples(self, samples, progress=0.0):
        self._samples = None if samples is None else np.asarray(samples, dtype=np.float32)
        self._progress = progress
        self.update()

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def set_progress(self, value):
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(0, 2, -1, -2)
        painter.fillRect(rect, QColor("#ffffff"))
        center = rect.center().y()
        painter.setPen(QPen(QColor("#eef1f8"), 1))
        painter.drawLine(rect.left(), center, rect.right(), center)
        if self._samples is None or len(self._samples) == 0:
            painter.setPen(QColor("#b6bfd0"))
            painter.drawText(rect, Qt.AlignCenter, "暂无音频")
            return
        peaks = self._samples
        n = len(peaks)
        bar_w = 2.2
        step = max(1.0, rect.width() / n)
        half = rect.height() / 2 - 1
        painter.setPen(Qt.NoPen)
        split = int(n * self._progress)
        for i in range(n):
            h = max(1.5, float(peaks[i]) * half)
            x = rect.left() + i * step
            color = self._color if i <= split else QColor("#c8d2e4")
            painter.setBrush(color)
            painter.drawRoundedRect(int(x), int(center - h), int(bar_w), int(h * 2), 1, 1)


class ScoreRing(QWidget):
    def __init__(self, parent=None, size=96):
        super().__init__(parent)
        self.score = 0
        self._size = size
        self.setFixedSize(size, size)

    def set_score(self, score):
        self.score = int(score)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(6, 6, -6, -6)
        painter.setPen(QPen(QColor("#edf1f8"), 9, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, 90 * 16, -360 * 16)
        score = max(0, min(100, self.score))
        if score >= 85:
            color = QColor(COLORS["green"])
        elif score >= 70:
            color = QColor(COLORS["primary"])
        elif score >= 55:
            color = QColor(COLORS["orange"])
        else:
            color = QColor(COLORS["red"])
        painter.setPen(QPen(color, 9, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, 90 * 16, int(-360 * 16 * score / 100))
        painter.setPen(QColor(COLORS["text"]))
        f = QFont("Microsoft YaHei UI", 17)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(self.rect().adjusted(0, -4, 0, -4), Qt.AlignCenter, str(score))
        painter.setPen(QColor(COLORS["sub"]))
        f2 = QFont("Microsoft YaHei UI", 8)
        painter.setFont(f2)
        painter.drawText(self.rect().adjusted(0, 26, 0, 26), Qt.AlignCenter, "分")


_play_marker_cache = {}


def play_marker_url(active=True):
    """生成文章行首播放标识（蓝色圆形 + 白色三角），返回本地文件 URL。"""
    key = "active" if active else "blank"
    if key in _play_marker_cache:
        return _play_marker_cache[key]
    from .paths import CACHE_DIR

    folder = os.path.join(CACHE_DIR, "ui")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"article_marker_{key}.png")
    if not os.path.exists(path):
        pix = QPixmap(40, 40)
        pix.fill(Qt.transparent)
        if active:
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(COLORS["primary"]))
            painter.drawEllipse(2, 2, 36, 36)
            painter.setBrush(QColor("#ffffff"))
            w, h, shift = 11.0, 14.0, 1.5
            painter.drawPolygon(QPolygonF([
                QPointF(20 - w / 2 + shift, 20 - h / 2),
                QPointF(20 - w / 2 + shift, 20 + h / 2),
                QPointF(20 + w / 2 + shift, 20),
            ]))
            painter.end()
        pix.save(path, "PNG")
    url = QUrl.fromLocalFile(path).toString()
    _play_marker_cache[key] = url
    return url


class ArticleTextBrowser(QTextBrowser):
    """文章正文，支持点击句子定位 / 当前句高亮。"""
    sentenceClicked = pyqtSignal(int)
    sentenceDoubleClicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ArticleBody")
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.anchorClicked.connect(self._on_anchor)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._sentences = []
        self._current = -1
        self._content = ""
        self._base_size = ARTICLE_FONT
        self.auto_scroll = True

    def set_article(self, content, current=-1, base_size=ARTICLE_FONT):
        """一句一行排版，浅蓝高亮当前句，可点击定位，默认自动滚动到当前句。"""
        from .textutil import split_sentences

        self._content = content or ""
        self._current = current
        self._base_size = base_size
        self._sentences = list(split_sentences(self._content))
        line_height = int(base_size * ARTICLE_LINE_HEIGHT)
        lines = []
        marker = (f"<img src='{play_marker_url(True)}' width='24' height='24' "
                  "style='vertical-align:middle;'> ")
        spacer = (f"<img src='{play_marker_url(False)}' width='24' height='24' "
                  "style='vertical-align:middle;'> ")
        for idx, sent in enumerate(self._sentences):
            safe = html.escape(sent)
            if idx == current:
                # 段落级背景覆盖整行；句首显示播放按钮图标
                lines.append(
                    f"<p style='margin:0 0 {ARTICLE_ROW_GAP}px 0;"
                    f"background-color:#dce9ff;'>"
                    f"<a name='s:{idx}' href='s:{idx}' style='text-decoration:none;'>"
                    f"{marker}<span style='color:#1e57d6;'>{safe}</span></a></p>")
            else:
                # 空白占位图，保证各行文字左对齐
                lines.append(
                    f"<p style='margin:0 0 {ARTICLE_ROW_GAP}px 0;'>"
                    f"<a name='s:{idx}' href='s:{idx}' "
                    f"style='color:#1f2937;text-decoration:none;'>{spacer}{safe}</a></p>")
        self.setHtml(f"<div style='font-size:{base_size}px; line-height:{line_height}px;'>"
                     f"{''.join(lines)}</div>")
        if self.auto_scroll and 0 <= current < len(self._sentences):
            self.scrollToAnchor(f"s:{current}")

    def set_sentences(self, sentences, current=-1, base_size=15, highlight=True):
        self._sentences = list(sentences)
        self._current = current
        parts = []
        for i, text in enumerate(self._sentences):
            safe = html.escape(text)
            if highlight and i == current:
                style = ("background:#dbeafe; color:#123a8a; border-radius:6px;"
                         "padding:2px 3px; text-decoration:none;")
                parts.append(f"<a href='s:{i}' style=\"{style}\">{safe}</a>")
            else:
                parts.append(f"<a href='s:{i}' style=\"color:#1f2937;text-decoration:none;\">{safe}</a>")
        body = "<br><br>".join(parts)
        self.setHtml(f"<div style='font-size:{base_size}px; line-height:190%;'>{body}</div>")
        if 0 <= current < len(self._sentences):
            cursor = self.textCursor()
            cursor.movePosition(cursor.Start)
            self.setTextCursor(cursor)

    def set_current(self, index, base_size=None):
        if index == self._current:
            return
        if self._content:
            self.set_article(self._content, index, base_size or self._base_size)
        else:
            self.set_sentences(self._sentences, index, base_size or self._base_size)

    def _on_anchor(self, url):
        try:
            idx = int(url.toString().split(":", 1)[1])
        except Exception:
            return
        self.sentenceClicked.emit(idx)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        anchor = self.anchorAt(event.pos())
        if anchor:
            try:
                self.sentenceDoubleClicked.emit(int(anchor.split(":", 1)[1]))
            except Exception:
                pass
        super().mouseDoubleClickEvent(event)


class SubtitleList(QListWidget):
    """字幕/句子列表，每行带一个播放按钮和时间。"""
    sentencePlay = pyqtSignal(int)
    sentenceSelected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSpacing(2)
        self.itemClicked.connect(self._on_click)
        self.itemDoubleClicked.connect(self._on_double_click)
        self.itemSelectionChanged.connect(self._on_select)
        self._rows = []
        self._last_width = 0

    def set_items(self, items, bilingual=True, font_size=12):
        self.clear()
        self._rows = []
        self._last_width = 0
        for i, item in enumerate(items):
            text = item.get("text", "")
            zh = item.get("zh") or item.get("text_zh") or ""
            start = item.get("start")
            time_text = fmt_time(start * 1000) if start is not None else ""
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(4, 6, 6, 6)
            lay.setSpacing(8)
            play = QPushButton("▶")
            play.setObjectName("SentencePlay")
            play.setCursor(Qt.PointingHandCursor)
            play.clicked.connect(lambda _=False, idx=i: self.sentencePlay.emit(idx))
            lay.addWidget(play, 0, Qt.AlignTop)
            texts = QVBoxLayout()
            texts.setSpacing(3)
            main = QLabel(text)
            main.setWordWrap(True)
            main.setStyleSheet(f"font-size:{font_size}px; color:#1f2937;")
            texts.addWidget(main)
            if bilingual and zh:
                sub = QLabel(zh)
                sub.setWordWrap(True)
                sub.setStyleSheet(f"font-size:{max(10, font_size - 2)}px; color:#7b8494;")
                texts.addWidget(sub)
            lay.addLayout(texts, 1)
            tl = QLabel(time_text)
            tl.setStyleSheet("color:#9aa3b2; font-size:10px;")
            tl.setAlignment(Qt.AlignRight | Qt.AlignTop)
            lay.addWidget(tl)
            item_widget = QListWidgetItem()
            item_widget.setSizeHint(QSize(0, 56))
            self.addItem(item_widget)
            self.setItemWidget(item_widget, row)
            self._rows.append(row)
        QTimer.singleShot(0, self._apply_item_heights)

    def _apply_item_heights(self):
        """按当前宽度逐行测量换行后的文字高度，保证每行文字完整显示。"""
        width = self.viewport().width()
        if width < 80 or not self._rows:
            return
        self._last_width = width
        row_width = width - 4
        for i, row in enumerate(self._rows):
            row.setFixedWidth(row_width)
            lay = row.layout()
            margins = lay.contentsMargins()
            play_w = lay.itemAt(0).widget().sizeHint().width()
            time_w = lay.itemAt(2).widget().sizeHint().width()
            text_w = max(60, row_width - margins.left() - margins.right()
                         - play_w - time_w - lay.spacing() * 2)
            texts_lay = lay.itemAt(1).layout()
            height = margins.top() + margins.bottom()
            for j in range(texts_lay.count()):
                lbl = texts_lay.itemAt(j).widget()
                lbl.ensurePolished()
                fm = QFontMetrics(lbl.font())
                rect = fm.boundingRect(0, 0, text_w, 100000,
                                       Qt.TextWordWrap, lbl.text())
                height += rect.height()
            height += texts_lay.spacing() * max(0, texts_lay.count() - 1)
            self.item(i).setSizeHint(QSize(0, max(56, height + 4)))

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if abs(self.viewport().width() - self._last_width) > 6:
            self._apply_item_heights()

    def _on_click(self, item):
        self.sentenceSelected.emit(self.row(item))

    def _on_double_click(self, item):
        # 双击字幕：跳到该句并开始播放
        self.sentencePlay.emit(self.row(item))

    def _on_select(self):
        row = self.currentRow()
        if row >= 0:
            self.sentenceSelected.emit(row)

    def set_current(self, index):
        if 0 <= index < self.count():
            self.setCurrentRow(index)

    def set_play_icon(self, index, playing):
        if not (0 <= index < len(self._rows)):
            return
        btn = self._rows[index].findChild(QPushButton)
        if btn:
            btn.setText("❚❚" if playing else "▶")


class MicLevelBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = 0.0
        self.setFixedHeight(8)
        self.setMinimumWidth(120)

    def set_level(self, value):
        self.level = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#edf1f8"))
        painter.drawRoundedRect(rect, 4, 4)
        width = int(rect.width() * min(1.0, self.level * 5))
        if width > 0:
            painter.setBrush(QColor(COLORS["green"] if self.level < 0.5 else COLORS["orange"]))
            painter.drawRoundedRect(0, 0, width, rect.height(), 4, 4)


def standard_icon(widget, sp):
    return widget.style().standardIcon(sp)
