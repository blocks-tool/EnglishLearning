"""文章视图：朗读、跟读、编辑、导出。"""
import os

from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget,
)

from core import db_speaking, tts
from core.tasks import run_task
from core.textutil import split_sentences, word_count
from core.ui import (
    ARTICLE_FONT, COLORS, ArticleTextBrowser, Card, busy_progress, button, hline, label,
)

from .dialogs import ArticleDialog
from .shadow import ShadowDialog


class ArticleView(QWidget):
    contentChanged = pyqtSignal()

    def __init__(self, player, parent=None):
        super().__init__(parent)
        self.material = None
        self.sentences = []
        self.timings = []
        self.current_index = -1
        self._pending_start = None   # 双击行时记住起始句，语音就绪后从这里播放
        self.player = player   # 由主窗口提供，全窗口共用一个播放器
        self._synth_dialog = None
        self._build()
        self.player.stateChanged.connect(self._on_state)
        self.player.positionChanged.connect(self._on_position)
        self.player.mediaStatusChanged.connect(self._on_media_status)

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
        self.edit_btn = button("编辑")
        self.edit_btn.clicked.connect(self.edit_article)
        head.addWidget(self.edit_btn)
        self.read_btn = button("朗读", "Soft")
        self.read_btn.clicked.connect(self.toggle_read)
        head.addWidget(self.read_btn)
        self.shadow_btn = button("跟读", "Primary")
        self.shadow_btn.clicked.connect(self.open_shadow)
        head.addWidget(self.shadow_btn)
        self.export_btn = button("导出")
        self.export_btn.clicked.connect(self.export_article)
        head.addWidget(self.export_btn)
        lay.addLayout(head)

        card = Card(padding=22)
        self.browser = ArticleTextBrowser()
        self.browser.sentenceClicked.connect(self._on_sentence_clicked)
        self.browser.sentenceDoubleClicked.connect(self._on_sentence_double_clicked)
        card.layout.addWidget(self.browser, 1)
        card.layout.addWidget(hline())
        self.status = label("", 9, COLORS["muted"])
        card.layout.addWidget(self.status)
        lay.addWidget(card, 1)

    # ---------- 数据 ----------
    def set_material(self, material):
        self.player.stop()
        self.player.setVideoOutput(None)
        self.player.setMedia(QMediaContent())   # 清空上一个音视频，进度条总时长归零
        self._close_synth()
        self.material = material
        self.title_label.setText(material.get("title", "文章"))
        content = material.get("content", "")
        self.sentences = split_sentences(content)
        self.timings = []
        self.current_index = -1
        self._pending_start = None
        self.browser.set_article(content, -1, ARTICLE_FONT)
        self.meta_label.setText(
            f"文章 · {len(self.sentences)} 句 · {word_count(content)} 词")
        self.read_btn.setText("朗读")
        self.status.setText("点击「朗读」生成语音后可逐句高亮；「跟读」按句练习发音")

    def _notify_changed(self):
        self.contentChanged.emit()

    # ---------- 朗读 ----------
    def toggle_read(self):
        if not self.sentences:
            QMessageBox.information(self, "没有内容", "这篇文章还没有内容。")
            return
        if self._synth_dialog:
            return   # 正在合成语音，避免底部播放条重复触发
        state = self.player.state()
        if state == QMediaPlayer.PlayingState:
            self.player.pause()
            return
        if state == QMediaPlayer.PausedState and self.timings:
            self.player.play()
            return
        if self.timings:
            self.player.setPosition(0)
            self.player.play()
            return
        self._synthesize()

    def _synthesize(self):
        self.read_btn.setEnabled(False)
        self.status.setText("正在合成全文语音（首次较慢，之后会缓存）…")
        self._synth_dialog = busy_progress(self, "正在合成全文语音…")

        def progress(percent, text):
            if self._synth_dialog:
                self._synth_dialog.setValue(percent)
                self._synth_dialog.setLabelText(f"正在合成：{text}")

        def done(result):
            path, timings, duration = result
            self._close_synth()
            self.read_btn.setEnabled(True)
            self.timings = list(timings)
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
            self.status.setText(f"语音已就绪 · 共 {len(self.sentences)} 句")
            start = self._pending_start
            self._pending_start = None
            if start is not None and 0 <= start < len(self.timings):
                self.player.setPosition(int(self.timings[start][0] * 1000))
            self.player.play()

        def failed(message):
            self._close_synth()
            self.read_btn.setEnabled(True)
            self.status.setText(f"语音合成失败：{message}")
            QMessageBox.warning(self, "语音合成失败", message)

        run_task(tts.synth_sentences, done, failed, progress, self.sentences, 1.0)

    def _close_synth(self):
        if self._synth_dialog:
            self._synth_dialog.close()
            self._synth_dialog = None

    def _on_state(self, state):
        if state == QMediaPlayer.PlayingState:
            self.read_btn.setText("暂停")
        elif state == QMediaPlayer.PausedState:
            self.read_btn.setText("继续朗读")
        else:
            self.read_btn.setText("朗读")

    def _on_finished(self):
        self.current_index = -1
        self.browser.set_article(self.material.get("content", ""), -1, ARTICLE_FONT)

    def _on_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.read_btn.setText("朗读")
            self._on_finished()

    def _on_position(self, pos):
        if not self.timings or not self.isVisible():
            return
        seconds = pos / 1000.0
        idx = 0
        for i, (start, end) in enumerate(self.timings):
            if start <= seconds < end + 0.15:
                idx = i
                break
            if seconds >= end:
                idx = min(i, len(self.timings) - 1)
        if idx != self.current_index:
            self.current_index = idx
            self.browser.set_article(self.material.get("content", ""), idx, ARTICLE_FONT)

    def _on_sentence_clicked(self, index):
        if self.timings and 0 <= index < len(self.timings):
            self.player.setPosition(int(self.timings[index][0] * 1000))
            self.player.play()
        else:
            self.browser.set_article(self.material.get("content", ""), index, ARTICLE_FONT)
            self.current_index = index

    def _on_sentence_double_clicked(self, index):
        """双击某一行：从该行开始朗读；语音还没生成时先合成，再从该行播放。"""
        if not (0 <= index < len(self.sentences)):
            return
        if self.timings:
            self.player.setPosition(int(self.timings[index][0] * 1000))
            self.player.play()
            return
        if self._synth_dialog:
            return
        self._pending_start = index
        self.status.setText(f"正在合成语音，完成后从第 {index + 1} 句开始朗读…")
        self._synthesize()

    # ---------- 跟读 ----------
    def open_shadow(self):
        if not self.sentences:
            QMessageBox.information(self, "没有内容", "请先导入文章内容。")
            return
        start = self.current_index if 0 <= self.current_index < len(self.sentences) else 0
        win = self.window()
        dlg = ShadowDialog(self.material.get("title", "文章"), self.sentences, self,
                           start_index=start)
        win.hide()   # 跟读期间隐藏主窗口
        try:
            dlg.exec_()
        finally:
            win.show()
            win.raise_()
            win.activateWindow()

    # ---------- 编辑 / 导出 ----------
    def edit_article(self):
        dlg = ArticleDialog(self, self.material.get("title", ""), self.material.get("content", ""))
        if dlg.exec_() != QDialog.Accepted:
            return
        title, content = dlg.values()
        db_speaking.update_material(self.material["id"], title=title, content=content)
        self.material["title"] = title
        self.material["content"] = content
        self.set_material(self.material)
        self._notify_changed()

    def export_article(self):
        title = self.material.get("title", "article")
        path, _ = QFileDialog.getSaveFileName(self, "导出文章",
                                              os.path.join(os.path.expanduser("~"), f"{title}.txt"),
                                              "文本文件 (*.txt)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.material.get("content", ""))
        self.status.setText(f"已导出到 {path}")

    def stop(self):
        self.player.stop()
        self._close_synth()
