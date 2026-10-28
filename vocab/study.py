"""单词学习：学习范围选择 + 单词卡。"""
import html
import random

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QShortcut, QStyle, QVBoxLayout, QWidget,
)

from core import db_vocab
from core.examples import highlight
from core.ui import COLORS, Card, button, hline, label
from .tts_player import Speaker

STATUS_COLOR = {0: COLORS["red"], 1: COLORS["orange"], 2: COLORS["green"]}
STATUS_BG = {0: "#fff1f2", 1: "#fff7e6", 2: "#e9fbf3"}


class StudyFilterDialog(QDialog):
    def __init__(self, stats, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择学习范围")
        self.setFixedSize(430, 460)
        self.statuses = []
        self.shuffle = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 18)
        lay.setSpacing(14)
        lay.addWidget(label("选择要学习的单词", 17, COLORS["text"], bold=True))
        lay.addWidget(label("可任意组合。默认学习「陌生 + 模糊」。", 10, COLORS["sub"]))

        self.checks = {}
        options = [
            (db_vocab.STATUS_UNKNOWN, "陌生", stats["unknown"], COLORS["red"], True),
            (db_vocab.STATUS_FUZZY, "模糊", stats["fuzzy"], COLORS["orange"], True),
            (db_vocab.STATUS_FAMILIAR, "熟悉", stats["familiar"], COLORS["green"], False),
        ]
        for status, name, count, color, checked in options:
            row = QFrame()
            row.setStyleSheet(
                f"QFrame{{background:#fff;border:1px solid {COLORS['border']};border-radius:10px;}}")
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(14, 10, 14, 10)
            box = QCheckBox()
            box.setChecked(checked)
            box.setStyleSheet("QCheckBox::indicator{width:18px;height:18px;}")
            box.setProperty("status", status)
            self.checks[status] = box
            row_lay.addWidget(box)
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background:{color};border-radius:4px;")
            row_lay.addWidget(dot)
            row_lay.addWidget(label(name, 12, COLORS["text"], bold=True))
            row_lay.addStretch(1)
            row_lay.addWidget(label(f"{count} 词", 10, COLORS["sub"]))
            row.mousePressEvent = lambda e, b=box: b.setChecked(not b.isChecked())
            lay.addWidget(row)

        shuffle_row = QFrame()
        shuffle_row.setStyleSheet(
            f"QFrame{{background:#fff;border:1px solid {COLORS['border']};border-radius:10px;}}")
        shuffle_lay = QHBoxLayout(shuffle_row)
        shuffle_lay.setContentsMargins(14, 10, 14, 10)
        self.shuffle_box = QCheckBox()
        self.shuffle_box.setChecked(False)
        self.shuffle_box.setStyleSheet("QCheckBox::indicator{width:18px;height:18px;}")
        shuffle_lay.addWidget(self.shuffle_box)
        shuffle_lay.addWidget(label("随机单词", 12, COLORS["text"], bold=True))
        shuffle_lay.addStretch(1)
        shuffle_lay.addWidget(label("打乱学习顺序", 10, COLORS["sub"]))
        shuffle_row.mousePressEvent = lambda e: self.shuffle_box.setChecked(
            not self.shuffle_box.isChecked())
        lay.addWidget(shuffle_row)

        lay.addStretch(1)
        footer = QHBoxLayout()
        all_btn = button("全量学习", "Ghost")
        all_btn.clicked.connect(self._select_all)
        footer.addWidget(all_btn)
        footer.addStretch(1)
        cancel = button("取消")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        start = button("开始学习", "Primary")
        start.clicked.connect(self._start)
        footer.addWidget(start)
        lay.addLayout(footer)

    def _select_all(self):
        for box in self.checks.values():
            box.setChecked(True)

    def _start(self):
        selected = [s for s, box in self.checks.items() if box.isChecked()]
        if not selected:
            QMessageBox.warning(self, "请选择范围", "至少选择一种学习状态，或点击「全量学习」。")
            return
        self.statuses = sorted(selected)
        self.shuffle = self.shuffle_box.isChecked()
        self.accept()


class FlashcardWindow(QDialog):
    def __init__(self, notebook_id, notebook_name, statuses, shuffle=False, parent=None):
        super().__init__(parent)
        self.notebook_id = notebook_id
        self.notebook_name = notebook_name
        self.words = db_vocab.list_words(notebook_id, statuses)
        if shuffle:
            random.shuffle(self.words)
        self.index = 0
        self.revealed = False
        self.speaker = Speaker(self)
        self.setWindowTitle(f"学习 - {notebook_name}")
        self.resize(860, 700)
        self.setMinimumSize(760, 620)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 20, 26, 20)
        lay.setSpacing(14)

        top = QHBoxLayout()
        top.addWidget(label(f"正在学习 · {self.notebook_name}", 15, COLORS["text"], bold=True))
        top.addStretch(1)
        self.auto_play = QCheckBox("自动播放单词读音")
        self.auto_play.setChecked(True)
        self.auto_play.setStyleSheet("QCheckBox::indicator{width:16px;height:16px;}")
        top.addWidget(self.auto_play)
        top.addSpacing(8)
        self.progress_label = label("", 10, COLORS["sub"])
        top.addWidget(self.progress_label)
        close_btn = button("结束学习", "Ghost")
        close_btn.clicked.connect(self.accept)
        top.addWidget(close_btn)
        lay.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setRange(0, max(1, len(self.words)))
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        lay.addWidget(self.progress)

        self.card = Card(padding=30)
        self.card.setMinimumHeight(380)
        clue = QHBoxLayout()
        self.word_label = QLabel()
        self.word_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.word_label.setAlignment(Qt.AlignCenter)
        clue.addWidget(self.word_label, 1)
        self.card.layout.addLayout(clue)

        self.phonetic_label = label("", 13, COLORS["sub"])
        self.phonetic_label.setAlignment(Qt.AlignCenter)
        self.card.layout.addWidget(self.phonetic_label)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.speak_btn = button("朗读单词", "Soft")
        self.speak_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume))
        self.speak_btn.clicked.connect(self._speak_word)
        actions.addWidget(self.speak_btn)
        actions.addStretch(1)
        self.card.layout.addLayout(actions)

        self.card.layout.addWidget(hline())

        self.reveal_btn = button("显示释义与例句 ▼", "Ghost")
        self.reveal_btn.clicked.connect(self.toggle_reveal)
        self.card.layout.addWidget(self.reveal_btn, 0, Qt.AlignHCenter)

        self.detail = QWidget()
        detail_lay = QVBoxLayout(self.detail)
        detail_lay.setContentsMargins(10, 0, 10, 0)
        detail_lay.setSpacing(10)
        self.trans_label = label("", 15, COLORS["text"], wrap=True)
        detail_lay.addWidget(self.trans_label)
        self.example_label = QLabel()
        self.example_label.setWordWrap(True)
        self.example_label.setTextFormat(Qt.RichText)
        self.example_label.setStyleSheet("font-size:15px; color:#1f2937;")
        detail_lay.addWidget(self.example_label)
        self.example_zh = label("", 12, COLORS["sub"], wrap=True)
        detail_lay.addWidget(self.example_zh)
        src_row = QHBoxLayout()
        self.source_label = QLabel()
        self.source_label.setStyleSheet(
            f"background:{COLORS['blue_soft']};color:{COLORS['primary_dark']};"
            "border-radius:8px;padding:3px 9px;font-size:10px;")
        src_row.addWidget(self.source_label, 0)
        src_row.addStretch(1)
        self.example_speak = button("朗读例句", "Ghost")
        self.example_speak.setIcon(self.style().standardIcon(QStyle.SP_MediaVolume))
        self.example_speak.clicked.connect(self._speak_example)
        src_row.addWidget(self.example_speak)
        detail_lay.addLayout(src_row)
        self.detail.setVisible(False)
        self.card.layout.addWidget(self.detail)
        self.card.layout.addStretch(1)
        lay.addWidget(self.card, 1)

        mark_tip = label("这个单词你掌握得怎么样？（1/2/3 标记，←/→ 上一个/下一个，空格显示释义）", 10, COLORS["sub"])
        mark_tip.setAlignment(Qt.AlignCenter)
        lay.addWidget(mark_tip)

        marks = QHBoxLayout()
        marks.setSpacing(12)
        self.mark_buttons = {}
        self._mark_names = {0: "陌生", 1: "模糊", 2: "熟悉"}
        for status, text in ((0, "陌生"), (1, "模糊"), (2, "熟悉")):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(46)
            btn.clicked.connect(lambda _=False, s=status: self.mark(s))
            self.mark_buttons[status] = btn
            marks.addWidget(btn, 1)
        lay.addLayout(marks)
        self._update_mark_styles()

        nav = QHBoxLayout()
        self.prev_btn = button("「 上一个")
        self.prev_btn.clicked.connect(self.prev_word)
        nav.addWidget(self.prev_btn)
        nav.addStretch(1)
        self.pos_label = label("", 10, COLORS["muted"])
        nav.addWidget(self.pos_label)
        nav.addStretch(1)
        self.next_btn = button("下一个 」")
        self.next_btn.clicked.connect(self.next_word)
        nav.addWidget(self.next_btn)
        lay.addLayout(nav)

        # 快捷键在任何焦点下都生效：← 上一个，→ 下一个
        prev_sc = QShortcut(QKeySequence(Qt.Key_Left), self)
        prev_sc.setContext(Qt.WindowShortcut)
        prev_sc.activated.connect(self.prev_word)
        next_sc = QShortcut(QKeySequence(Qt.Key_Right), self)
        next_sc.setContext(Qt.WindowShortcut)
        next_sc.activated.connect(self.next_word)
        self._shortcuts = (prev_sc, next_sc)

        # 按钮不抢焦点，避免方向键 / 空格被聚焦按钮吃掉
        for w in (self.prev_btn, self.next_btn, self.reveal_btn, self.speak_btn,
                  self.example_speak, *self.mark_buttons.values()):
            w.setFocusPolicy(Qt.NoFocus)

    def _update_mark_styles(self):
        """选中项实心高亮 + 对勾，未选中项弱化，让当前状态一眼可辨。"""
        for status, btn in self.mark_buttons.items():
            color = STATUS_COLOR[status]
            name = self._mark_names[status]
            if btn.isChecked():
                btn.setText(f"✓ {name}")
                btn.setStyleSheet(f"""
                    QPushButton{{background:{color};border:2px solid {color};border-radius:11px;
                        color:#ffffff;font-size:13px;font-weight:700;}}
                """)
            else:
                btn.setText(name)
                btn.setStyleSheet(f"""
                    QPushButton{{background:#f3f4f6;border:1px solid {COLORS['border']};
                        border-radius:11px;color:{COLORS['muted']};font-size:13px;font-weight:600;}}
                    QPushButton:hover{{border-color:{color};color:{color};background:{STATUS_BG[status]};}}
                """)

    # ---------- 展示 ----------
    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        if not self.words:
            QMessageBox.information(self, "没有单词", "所选范围内没有单词，请调整学习范围。")
            self.reject()
            return
        w = self.words[self.index]
        word = w["word"]
        self.word_label.setText(
            f"<span style='font-size:44px;font-weight:700;color:{COLORS['text']};'>{html.escape(word)}</span>")
        self.phonetic_label.setText(w.get("phonetic") or "音标缺失")
        translation = (w.get("translation") or "词典未收录释义").replace("\n", "；")
        self.trans_label.setText(translation)
        self.example_label.setText(highlight(w.get("example_en") or "", word))
        self.example_zh.setText(w.get("example_zh") or "")
        source = w.get("example_source") or "无例句来源"
        self.source_label.setText(f"来源：{source}")
        self.example_label.setVisible(bool(w.get("example_en")))
        self.example_zh.setVisible(bool(w.get("example_zh")))
        self.source_label.setVisible(bool(w.get("example_en")))
        self.example_speak.setVisible(bool(w.get("example_en")))

        self.revealed = False
        self.detail.setVisible(False)
        self.reveal_btn.setText("显示释义与例句 ▼")
        current = w.get("status", 0)
        for status, btn in self.mark_buttons.items():
            btn.setChecked(status == current)
        self._update_mark_styles()
        self.progress_label.setText(f"{self.index + 1} / {len(self.words)}")
        self.progress.setValue(self.index + 1)
        self.pos_label.setText(f"{self.index + 1} / {len(self.words)}")
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index < len(self.words) - 1)
        if self.auto_play.isChecked():
            self._speak_word()

    def toggle_reveal(self):
        self.revealed = not self.revealed
        self.detail.setVisible(self.revealed)
        self.reveal_btn.setText("收起释义 ▲" if self.revealed else "显示释义与例句 ▼")

    def _speak_word(self):
        if self.words:
            self.speaker.speak(self.words[self.index]["word"], 1.0)

    def _speak_example(self):
        if self.words and self.words[self.index].get("example_en"):
            self.speaker.speak(self.words[self.index]["example_en"], 1.0)

    # ---------- 操作 ----------
    def mark(self, status):
        if not self.words:
            return
        w = self.words[self.index]
        db_vocab.set_status(w["id"], status)
        w["status"] = status
        for s, btn in self.mark_buttons.items():
            btn.setChecked(s == status)
        self._update_mark_styles()
        if self.index < len(self.words) - 1:
            self.index += 1
            self.refresh()
        else:
            self.progress.setValue(len(self.words))
            QMessageBox.information(self, "本轮完成",
                                    f"已完成本轮 {len(self.words)} 个单词的学习。")
            self.accept()

    def prev_word(self):
        if self.index > 0:
            self.index -= 1
            self.speaker.stop()
            self.refresh()

    def next_word(self):
        if self.index < len(self.words) - 1:
            self.index += 1
            self.speaker.stop()
            self.refresh()

    def keyPressEvent(self, event):  # noqa: N802
        key = event.key()
        if key == Qt.Key_1:
            self.mark(0)
        elif key == Qt.Key_2:
            self.mark(1)
        elif key == Qt.Key_3:
            self.mark(2)
        elif key == Qt.Key_Space:
            self.toggle_reveal()
        elif key == Qt.Key_Left:
            self.prev_word()
        elif key == Qt.Key_Right:
            self.next_word()
        elif key == Qt.Key_Escape:
            self.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):  # noqa: N802
        self.speaker.stop()
        super().closeEvent(event)
