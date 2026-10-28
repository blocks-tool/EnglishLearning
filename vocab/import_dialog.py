"""批量导入单词对话框：粘贴多行单词 → 自动补全释义 / 例句（标注来源）。"""
import re

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from core import db_vocab, dictionary, examples
from core.tasks import run_task
from core.ui import COLORS, Card, button, label


class ImportDialog(QDialog):
    def __init__(self, notebook_id, notebook_name, parent=None):
        super().__init__(parent)
        self.notebook_id = notebook_id
        self.rows = []
        self._generating = False
        self.setWindowTitle("批量导入单词")
        self.setMinimumSize(980, 720)
        self._build(notebook_name)

    def _build(self, notebook_name):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)

        head = QHBoxLayout()
        title = label("批量导入单词", 18, COLORS["text"], bold=True)
        head.addWidget(title)
        head.addSpacing(10)
        head.addWidget(label(f"导入到「{notebook_name}」", 10, COLORS["sub"]))
        head.addStretch(1)
        lay.addLayout(head)

        hint = label("每行一个单词（自动去重）。点击「生成释义与例句」后，"
                     "程序会从离线词典补全音标和中文释义，并从六级真题 / 英文期刊例句库匹配例句。",
                     10, COLORS["sub"], wrap=True)
        lay.addWidget(hint)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("请把单词复制粘贴到这里，每行一个，例如：\n"
                                       "crucial\nphenomenon\nsustainable")
        self.editor.setMinimumHeight(150)
        self.editor.textChanged.connect(self._update_count)
        lay.addWidget(self.editor, 1)

        row = QHBoxLayout()
        self.count_label = label("已输入 0 个单词", 10, COLORS["sub"])
        row.addWidget(self.count_label)
        row.addStretch(1)
        self.gen_btn = button("生成释义与例句", "Soft")
        self.gen_btn.clicked.connect(self.generate)
        row.addWidget(self.gen_btn)
        lay.addLayout(row)

        preview_head = QHBoxLayout()
        preview_head.addWidget(label("导入预览", 12, COLORS["text"], bold=True))
        preview_head.addStretch(1)
        self.preview_info = label("", 10, COLORS["muted"])
        preview_head.addWidget(self.preview_info)
        lay.addLayout(preview_head)

        card = Card(padding=0)
        card.layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["单词", "音标", "中文释义", "例句", "来源"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 250)
        self.table.setColumnWidth(4, 150)
        self.table.verticalHeader().setDefaultSectionSize(54)
        card.layout.addWidget(self.table)
        lay.addWidget(card, 2)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        lay.addWidget(self.progress)

        footer = QHBoxLayout()
        self.tip = label("", 10, COLORS["sub"])
        footer.addWidget(self.tip)
        footer.addStretch(1)
        cancel = button("取消")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.import_btn = button("导入单词本", "Primary")
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self.do_import)
        footer.addWidget(self.import_btn)
        lay.addLayout(footer)

    # ---------- 输入解析 ----------
    def _parse_words(self):
        words, seen = [], set()
        for line in self.editor.toPlainText().splitlines():
            w = line.strip().lower()
            if not w:
                continue
            if not re.match(r"^[a-z][a-z'-]*$", w):
                continue
            if w in seen:
                continue
            seen.add(w)
            words.append(w)
        return words

    def _update_count(self):
        count = len(self._parse_words())
        self.count_label.setText(f"已输入 {count} 个有效单词")
        if self.rows and count != len(self.rows):
            self.rows = []
            self.table.setRowCount(0)
            self.import_btn.setEnabled(False)
            self.preview_info.setText("")

    # ---------- 生成 ----------
    def generate(self):
        words = self._parse_words()
        if not words:
            self.tip.setText("没有识别到有效英文单词")
            return
        if len(words) > 800:
            words = words[:800]
            self.tip.setText("单次最多导入 800 个单词，已自动截取前 800 个")
        self._generating = True
        self.gen_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.preview_info.setText("正在查询离线词典…")

        def work(progress):
            rows = []
            total = len(words)
            for i, w in enumerate(words):
                info = dictionary.lookup(w) or {}
                ex = examples.build_example(w)
                rows.append({
                    "word": w,
                    "phonetic": f"/{info.get('phonetic', '').strip('/')}/" if info.get("phonetic") else "",
                    "translation": info.get("translation", "").replace("\n", " ").strip(),
                    "definition": info.get("definition", ""),
                    "tag": info.get("tag", ""),
                    "collins": info.get("collins", 0),
                    "example_en": ex["en"],
                    "example_zh": ex["zh"],
                    "example_source": ex["source"],
                })
                progress(int((i + 1) * 100 / total), w)
            return rows

        run_task(work, self._on_generated, self._on_error, self._on_progress,
                 *[])

    def _on_progress(self, percent, word):
        self.progress.setValue(percent)
        self.preview_info.setText(f"正在生成：{word}")

    def _on_error(self, message):
        self._generating = False
        self.gen_btn.setEnabled(True)
        self.progress.setVisible(False)
        self.tip.setText(f"生成失败：{message}")

    def _on_generated(self, rows):
        self._generating = False
        self.gen_btn.setEnabled(True)
        self.progress.setValue(100)
        self.progress.setVisible(False)
        self.rows = rows
        self._fill_table(rows)
        found = sum(1 for r in rows if r["translation"])
        banked = sum(1 for r in rows if "生成" not in r["example_source"])
        self.preview_info.setText(f"{len(rows)} 个单词 · 词典命中 {found} · 真题/期刊例句 {banked}")
        self.import_btn.setEnabled(bool(rows))
        if len(rows) < len(self._parse_words()):
            self.tip.setText("部分单词已去重或格式不正确")

    def _fill_table(self, rows):
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(r["word"]))
            self.table.setItem(i, 1, QTableWidgetItem(r["phonetic"]))
            trans = r["translation"].split("；")[0]
            if len(trans) > 60:
                trans = trans[:60] + "…"
            item = QTableWidgetItem(trans or "词典未收录")
            item.setToolTip(r["translation"] or "词典未收录")
            if not r["translation"]:
                item.setForeground(Qt.gray)
            self.table.setItem(i, 2, item)
            ex_item = QTableWidgetItem(r["example_en"])
            ex_item.setToolTip(r["example_en"] + "\n" + r["example_zh"])
            self.table.setItem(i, 3, ex_item)
            src = QTableWidgetItem(r["example_source"])
            src.setForeground(Qt.darkBlue)
            self.table.setItem(i, 4, src)
            for col in range(5):
                cell = self.table.item(i, col)
                if cell:
                    cell.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.table.item(i, 0).setFont(_bold_font())

    def do_import(self):
        if not self.rows:
            return
        if self._generating:
            self.tip.setText("例句还在生成中，请稍候")
            return
        added, skipped = db_vocab.add_words(self.notebook_id, self.rows)
        self.tip.setText(f"已导入 {added} 个，跳过重复 {skipped} 个")
        self.done(1)


def _bold_font():
    from PyQt5.QtGui import QFont
    f = QFont("Microsoft YaHei UI", 10)
    f.setBold(True)
    return f
