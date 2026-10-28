"""英语学习助手启动台：单词本学习助手 + 口语学习助手。"""
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget,
)

from core import asr, db_vocab, db_speaking, dictionary, tts
from core.ui import COLORS, Card, apply_theme, button, label


class Launcher(QMainWindow):
    def __init__(self):
        super().__init__()
        self._windows = []
        self.setWindowTitle("英语学习助手")
        self.setFixedSize(1000, 640)
        self._build()

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(40, 34, 40, 26)
        lay.setSpacing(18)

        head = QHBoxLayout()
        logo = QLabel("E")
        logo.setFixedSize(46, 46)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(
            f"background:{COLORS['primary']};color:white;border-radius:12px;"
            "font-size:23px;font-weight:700;")
        head.addWidget(logo)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        texts.addWidget(label("英语学习助手", 24, COLORS["text"], bold=True))
        texts.addWidget(label("离线 · Piper TTS · Qt 桌面应用", 10, COLORS["sub"]))
        head.addLayout(texts)
        head.addStretch(1)
        lay.addLayout(head)

        cards = QHBoxLayout()
        cards.setSpacing(18)
        cards.addWidget(self._make_card(
            "A", "单词本学习助手",
            "背单词 · 批量导入 · 三种掌握状态",
            ["新建 / 删除单词本，单词按名称管理",
             "粘贴多行单词，自动生成音标、释义和例句",
             "例句标注六级真题或英文期刊来源",
             "陌生 / 模糊 / 熟悉 标记，可组合筛选学习"],
            "打开单词本助手", self.open_vocab))
        cards.addWidget(self._make_card(
            "S", "口语学习助手",
            "分组树 · 文章朗读 · 录音跟读评分",
            ["学习库用树组织分组、文章、音频和视频",
             "文章逐句朗读，可倍速、暂停、±n 秒跳转",
             "按句录音跟读，离线打分并指出薄弱单词",
             "音视频离线生成字幕，按字幕逐句跟读"],
            "打开口语助手", self.open_speaking))
        lay.addLayout(cards, 1)

        status = QHBoxLayout()
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background:{COLORS['green']};border-radius:4px;")
        status.addWidget(dot)
        dict_text = "词典已加载" if dictionary.available() else "词典未找到"
        model_text = "字幕模型已就绪" if asr.model_ready() else "字幕模型首次使用时下载"
        status.addWidget(label(
            f"发音：{tts.backend_name()}   ·   ECDICT {dict_text}   ·   {model_text}",
            9, COLORS["sub"]))
        status.addStretch(1)
        status.addWidget(label("v2.0  Qt 版", 9, COLORS["muted"]))
        lay.addLayout(status)

    def _make_card(self, letter, title, tagline, features, action_text, action):
        card = Card(padding=26)
        icon = QLabel(letter)
        icon.setFixedSize(54, 54)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            f"background:{COLORS['blue_soft']};color:{COLORS['primary']};"
            "border-radius:14px;font-size:26px;font-weight:700;")
        card.layout.addWidget(icon)
        card.layout.addWidget(label(title, 19, COLORS["text"], bold=True))
        card.layout.addWidget(label(tagline, 10, COLORS["sub"]))
        card.layout.addSpacing(4)
        for feature in features:
            row = QHBoxLayout()
            dot = QLabel()
            dot.setFixedSize(6, 6)
            dot.setStyleSheet(f"background:{COLORS['primary']};border-radius:3px;")
            row.addWidget(dot, 0, Qt.AlignTop)
            row.addWidget(label(feature, 10, COLORS["text"], wrap=True), 1)
            card.layout.addLayout(row)
        card.layout.addStretch(1)
        btn = button(action_text, "Primary")
        btn.setMinimumHeight(40)
        btn.clicked.connect(action)
        card.layout.addWidget(btn)
        return card

    def _remember(self, window):
        self._windows.append(window)
        window.setAttribute(Qt.WA_DeleteOnClose, True)
        window.destroyed.connect(lambda: self._windows.remove(window)
                                 if window in self._windows else None)
        window.show()

    def open_vocab(self):
        from vocab.window import MainWindow
        db_vocab.init_db()
        self._remember(MainWindow())
        self.close()   # 打开后关闭启动台窗口

    def open_speaking(self):
        from speaking.window import SpeakingWindow
        db_speaking.init_db()
        self._remember(SpeakingWindow())
        self.close()   # 打开后关闭启动台窗口


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("英语学习助手")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    apply_theme(app)
    db_vocab.init_db()
    db_speaking.init_db()
    window = Launcher()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
