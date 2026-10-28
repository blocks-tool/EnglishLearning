"""单词本助手主窗口。"""
import html

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from core import db_vocab, dictionary, tts
from core.ui import COLORS, Card, button, hline, label
from .import_dialog import ImportDialog
from .study import FlashcardWindow, StudyFilterDialog
from .tts_player import Speaker

STATUS_COLOR = {0: COLORS["red"], 1: COLORS["orange"], 2: COLORS["green"]}
STATUS_BG = {0: "#fff1f2", 1: "#fff7e6", 2: "#e9fbf3"}


class NotebookRow(QWidget):
    def __init__(self, name, count, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 8, 4)
        lay.setSpacing(9)
        dot = QLabel()
        dot.setFixedSize(26, 26)
        dot.setAlignment(Qt.AlignCenter)
        dot.setText("A")
        dot.setStyleSheet(
            f"background:{COLORS['blue_soft']};color:{COLORS['primary_dark']};"
            "border-radius:7px;font-weight:700;")
        lay.addWidget(dot)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("font-size:13px;font-weight:600;")
        texts.addWidget(self.name_label)
        self.count_label = QLabel(f"{count} 个单词")
        self.count_label.setStyleSheet(f"font-size:10px;color:{COLORS['muted']};")
        texts.addWidget(self.count_label)
        lay.addLayout(texts, 1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        db_vocab.init_db()
        self.current_nid = None
        self.speaker = Speaker(self)
        self.setWindowTitle("单词本学习助手")
        self.resize(1240, 820)
        self.setMinimumSize(1040, 700)
        self._build()
        self.refresh_notebooks()

    # ---------------- 界面 ----------------
    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(296)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 20, 16, 16)
        side.setSpacing(12)

        brand = QHBoxLayout()
        logo = QLabel("A")
        logo.setFixedSize(36, 36)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(
            f"background:{COLORS['primary']};color:white;border-radius:10px;"
            "font-size:18px;font-weight:700;")
        brand.addWidget(logo)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.addWidget(label("单词本学习助手", 15, COLORS["text"], bold=True))
        brand_text.addWidget(label("Vocab Master · 离线学习", 9, COLORS["muted"]))
        brand.addLayout(brand_text)
        brand.addStretch(1)
        side.addLayout(brand)
        side.addSpacing(6)

        new_btn = button("＋  新建单词本", "Primary")
        new_btn.clicked.connect(self.create_notebook)
        side.addWidget(new_btn)

        side.addWidget(label("我的单词本", 10, COLORS["sub"], bold=True))
        self.notebook_list = QListWidget()
        self.notebook_list.setSpacing(3)
        self.notebook_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.notebook_list.customContextMenuRequested.connect(self._notebook_menu)
        self.notebook_list.currentRowChanged.connect(self._on_notebook_changed)
        side.addWidget(self.notebook_list, 1)

        side.addWidget(hline())
        engine_row = QHBoxLayout()
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background:{COLORS['green']};border-radius:4px;")
        engine_row.addWidget(dot)
        engine_row.addWidget(label(f"发音引擎：{tts.backend_name()}", 9, COLORS["sub"]))
        engine_row.addStretch(1)
        side.addLayout(engine_row)
        dict_ok = dictionary.available()
        side.addWidget(label("离线词典：已加载" if dict_ok else "离线词典：未找到",
                             9, COLORS["sub"] if dict_ok else COLORS["red"]))
        outer.addWidget(sidebar)

        content_wrap = QWidget()
        content_lay = QVBoxLayout(content_wrap)
        content_lay.setContentsMargins(22, 18, 22, 18)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_empty())
        self.stack.addWidget(self._build_content())
        content_lay.addWidget(self.stack)
        outer.addWidget(content_wrap, 1)

    def _build_empty(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        card = Card(padding=40)
        card.layout.addStretch(1)
        icon = QLabel("Aa")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(88, 88)
        icon.setStyleSheet(
            f"background:{COLORS['blue_soft']};color:{COLORS['primary']};"
            "border-radius:24px;font-size:30px;font-weight:700;")
        card.layout.addWidget(icon, 0, Qt.AlignHCenter)
        card.layout.addWidget(label("还没有单词本", 20, COLORS["text"], bold=True), 0, Qt.AlignHCenter)
        card.layout.addWidget(label("新建一个单词本，粘贴单词即可自动生成释义和例句",
                                    11, COLORS["sub"]), 0, Qt.AlignHCenter)
        btn = button("创建第一个单词本", "Primary")
        btn.clicked.connect(self.create_notebook)
        card.layout.addWidget(btn, 0, Qt.AlignHCenter)
        card.layout.addStretch(1)
        lay.addWidget(card)
        return page

    def _build_content(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        card = Card(padding=20)
        lay.addWidget(card)

        head = QHBoxLayout()
        head_text = QVBoxLayout()
        head_text.setSpacing(2)
        self.title_label = label("", 22, COLORS["text"], bold=True)
        head_text.addWidget(self.title_label)
        self.subtitle_label = label("双击任一行可快速切换学习状态", 10, COLORS["muted"])
        head_text.addWidget(self.subtitle_label)
        head.addLayout(head_text)
        head.addStretch(1)
        self.rename_btn = button("重命名", "Ghost")
        self.rename_btn.clicked.connect(self.rename_notebook)
        head.addWidget(self.rename_btn)
        self.delete_btn = button("删除单词本", "Danger")
        self.delete_btn.clicked.connect(self.delete_notebook)
        head.addWidget(self.delete_btn)
        card.layout.addLayout(head)

        self.stats_row = QHBoxLayout()
        self.stats_row.setSpacing(10)
        self.stat_labels = {}
        for key, name, color in (("total", "全部", COLORS["text"]),
                                 ("unknown", "陌生", COLORS["red"]),
                                 ("fuzzy", "模糊", COLORS["orange"]),
                                 ("familiar", "熟悉", COLORS["green"])):
            chip = QLabel()
            chip.setStyleSheet(
                f"background:#f8faff;border:1px solid {COLORS['border']};"
                f"border-radius:9px;padding:7px 12px;color:{color};font-size:11px;")
            self.stat_labels[key] = chip
            self.stats_row.addWidget(chip)
        self.stats_row.addStretch(1)
        card.layout.addLayout(self.stats_row)

        card.layout.addWidget(hline())

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索单词或释义…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self.refresh_words)
        toolbar.addWidget(self.search)
        toolbar.addStretch(1)
        self.import_btn = button("批量导入", "Soft")
        self.import_btn.clicked.connect(self.open_import)
        toolbar.addWidget(self.import_btn)
        self.study_btn = button("开始学习", "Primary")
        self.study_btn.clicked.connect(self.start_study)
        toolbar.addWidget(self.study_btn)
        card.layout.addLayout(toolbar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["单词", "音标", "中文释义", "例句", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._word_menu)
        self.table.cellDoubleClicked.connect(self._cycle_status)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 140)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 260)
        self.table.setColumnWidth(4, 92)
        self.table.verticalHeader().setDefaultSectionSize(54)
        card.layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.footer_label = label("", 10, COLORS["muted"])
        footer.addWidget(self.footer_label)
        footer.addStretch(1)
        footer.addWidget(label("空格/左右键可在学习中翻卡，1/2/3 标记状态", 9, COLORS["muted"]))
        card.layout.addLayout(footer)
        return page

    # ---------------- 数据刷新 ----------------
    def refresh_notebooks(self, keep_id=None):
        keep_id = keep_id or self.current_nid
        self.notebook_list.blockSignals(True)
        self.notebook_list.clear()
        notebooks = db_vocab.list_notebooks()
        target_row = -1
        for i, nb in enumerate(notebooks):
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 54))
            item.setData(Qt.UserRole, nb["id"])
            self.notebook_list.addItem(item)
            self.notebook_list.setItemWidget(item, NotebookRow(nb["name"], nb["count"]))
            if nb["id"] == keep_id:
                target_row = i
        self.notebook_list.blockSignals(False)
        if not notebooks:
            self.current_nid = None
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(1)
        if target_row < 0:
            target_row = 0
        self.notebook_list.setCurrentRow(target_row)
        self.current_nid = self.notebook_list.item(target_row).data(Qt.UserRole)
        self.refresh_header()
        self.refresh_words()

    def _on_notebook_changed(self, row):
        if row < 0:
            return
        item = self.notebook_list.item(row)
        if not item:
            return
        self.current_nid = item.data(Qt.UserRole)
        self.refresh_header()
        self.refresh_words()

    def _notebook_name(self):
        for nb in db_vocab.list_notebooks():
            if nb["id"] == self.current_nid:
                return nb["name"]
        return ""

    def refresh_header(self):
        if not self.current_nid:
            return
        name = self._notebook_name()
        self.title_label.setText(name)
        stats = db_vocab.stats(self.current_nid)
        self.stat_labels["total"].setText(f"全部  {stats['total']}")
        self.stat_labels["unknown"].setText(f"● 陌生  {stats['unknown']}")
        self.stat_labels["fuzzy"].setText(f"● 模糊  {stats['fuzzy']}")
        self.stat_labels["familiar"].setText(f"● 熟悉  {stats['familiar']}")
        self.footer_label.setText(f"共 {stats['total']} 个单词 · 数据保存在本地 data/app.db")

    def refresh_words(self):
        if not self.current_nid:
            return
        keyword = self.search.text().strip()
        rows = db_vocab.list_words(self.current_nid, keyword=keyword)
        self.table.setRowCount(len(rows))
        for i, w in enumerate(rows):
            word_item = QTableWidgetItem(w["word"])
            font = QFont("Microsoft YaHei UI", 11)
            font.setBold(True)
            word_item.setFont(font)
            word_item.setData(Qt.UserRole, w["id"])
            self.table.setItem(i, 0, word_item)

            self.table.setItem(i, 1, QTableWidgetItem(w.get("phonetic") or "—"))

            trans = (w.get("translation") or "词典未收录").replace("\n", "；")
            shown = trans.split("；")[0]
            if len(shown) > 34:
                shown = shown[:34] + "…"
            t_item = QTableWidgetItem(shown)
            t_item.setToolTip(trans)
            if not w.get("translation"):
                t_item.setForeground(QColor("#9ca3af"))
            self.table.setItem(i, 2, t_item)

            ex = w.get("example_en") or ""
            ex_item = QTableWidgetItem(ex)
            ex_item.setToolTip((ex + "\n" + (w.get("example_zh") or "")
                                + "\n来源：" + (w.get("example_source") or "—")))
            ex_item.setForeground(QColor("#374151"))
            self.table.setItem(i, 3, ex_item)

            status = w.get("status", 0)
            pill = QLabel(db_vocab.STATUS_LABELS[status])
            pill.setAlignment(Qt.AlignCenter)
            pill.setFixedHeight(24)
            pill.setStyleSheet(
                f"background:{STATUS_BG[status]};color:{STATUS_COLOR[status]};"
                "border-radius:12px;font-size:10px;font-weight:600;")
            self.table.setCellWidget(i, 4, pill)
            self.table.setRowHeight(i, 54)
        self.refresh_header()

    # ---------------- 单词本操作 ----------------
    def create_notebook(self):
        name, ok = QInputDialog.getText(self, "新建单词本", "单词本名称：")
        if not ok:
            return
        try:
            nid = db_vocab.create_notebook(name)
        except ValueError as exc:
            QMessageBox.warning(self, "无法创建", str(exc))
            return
        self.current_nid = nid
        self.refresh_notebooks(keep_id=nid)

    def rename_notebook(self):
        if not self.current_nid:
            return
        name, ok = QInputDialog.getText(self, "重命名单词本", "名称：", text=self._notebook_name())
        if not ok:
            return
        try:
            db_vocab.rename_notebook(self.current_nid, name)
        except ValueError as exc:
            QMessageBox.warning(self, "无法重命名", str(exc))
            return
        self.refresh_notebooks()

    def delete_notebook(self):
        if not self.current_nid:
            return
        name = self._notebook_name()
        count = db_vocab.count_words(self.current_nid)
        answer = QMessageBox.question(
            self, "删除单词本", f"确定删除「{name}」及其中的 {count} 个单词吗？此操作不可恢复。")
        if answer != QMessageBox.Yes:
            return
        db_vocab.delete_notebook(self.current_nid)
        self.current_nid = None
        self.refresh_notebooks()

    def _notebook_menu(self, pos):
        item = self.notebook_list.itemAt(pos)
        if not item:
            return
        row = self.notebook_list.row(item)
        self.notebook_list.setCurrentRow(row)
        menu = QMenu(self)
        rename = menu.addAction("重命名")
        delete = menu.addAction("删除单词本")
        chosen = menu.exec_(self.notebook_list.mapToGlobal(pos))
        if chosen == rename:
            self.rename_notebook()
        elif chosen == delete:
            self.delete_notebook()

    # ---------------- 单词操作 ----------------
    def open_import(self):
        if not self.current_nid:
            QMessageBox.information(self, "请先新建单词本", "请先新建一个单词本再导入单词。")
            return
        dlg = ImportDialog(self.current_nid, self._notebook_name(), self)
        if dlg.exec_() == QDialog.Accepted:
            self.refresh_notebooks(keep_id=self.current_nid)

    def start_study(self):
        if not self.current_nid:
            return
        stats = db_vocab.stats(self.current_nid)
        if stats["total"] == 0:
            QMessageBox.information(self, "单词本为空", "请先批量导入单词。")
            return
        dlg = StudyFilterDialog(stats, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        # 单词卡打开时隐藏主窗口，关闭后再恢复
        card = FlashcardWindow(self.current_nid, self._notebook_name(), dlg.statuses,
                               shuffle=dlg.shuffle)
        self._study_card = card
        card.finished.connect(self._study_finished)
        card.show()
        self.hide()

    def _study_finished(self, _result=0):
        card = getattr(self, "_study_card", None)
        self._study_card = None
        if card is not None:
            card.deleteLater()
        self.show()
        self.raise_()
        self.activateWindow()
        self.refresh_notebooks(keep_id=self.current_nid)

    def _selected_word(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        return db_vocab.get_word(item.data(Qt.UserRole))

    def _cycle_status(self, row, column):
        if column == 4:
            return
        item = self.table.item(row, 0)
        if not item:
            return
        w = db_vocab.get_word(item.data(Qt.UserRole))
        if not w:
            return
        db_vocab.set_status(w["id"], (w["status"] + 1) % 3)
        self.refresh_words()

    def _word_menu(self, pos):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        self.table.selectRow(index.row())
        w = self._selected_word()
        if not w:
            return
        menu = QMenu(self)
        speak_word = menu.addAction("朗读单词")
        speak_example = menu.addAction("朗读例句")
        menu.addSeparator()
        mark_unknown = menu.addAction("标记为陌生")
        mark_fuzzy = menu.addAction("标记为模糊")
        mark_familiar = menu.addAction("标记为熟悉")
        menu.addSeparator()
        edit = menu.addAction("编辑释义与例句")
        delete = menu.addAction("删除单词")
        chosen = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if chosen == speak_word:
            self.speaker.speak(w["word"])
        elif chosen == speak_example:
            self.speaker.speak(w.get("example_en") or "")
        elif chosen == mark_unknown:
            db_vocab.set_status(w["id"], 0)
            self.refresh_words()
        elif chosen == mark_fuzzy:
            db_vocab.set_status(w["id"], 1)
            self.refresh_words()
        elif chosen == mark_familiar:
            db_vocab.set_status(w["id"], 2)
            self.refresh_words()
        elif chosen == edit:
            self._edit_word(w)
        elif chosen == delete:
            if QMessageBox.question(self, "删除单词", f"确定删除「{w['word']}」吗？") == QMessageBox.Yes:
                db_vocab.delete_word(w["id"])
                self.refresh_notebooks(keep_id=self.current_nid)

    def _edit_word(self, w):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"编辑 - {w['word']}")
        dlg.setMinimumSize(620, 460)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(label(w["word"], 20, COLORS["text"], bold=True))
        lay.addWidget(label("中文释义", 10, COLORS["sub"]))
        from PyQt5.QtWidgets import QTextEdit
        trans = QTextEdit(w.get("translation") or "")
        trans.setFixedHeight(110)
        lay.addWidget(trans)
        lay.addWidget(label("英文例句", 10, COLORS["sub"]))
        ex = QTextEdit(w.get("example_en") or "")
        ex.setFixedHeight(80)
        lay.addWidget(ex)
        lay.addWidget(label("例句翻译", 10, COLORS["sub"]))
        exzh = QTextEdit(w.get("example_zh") or "")
        exzh.setFixedHeight(70)
        lay.addWidget(exzh)
        footer = QHBoxLayout()
        footer.addStretch(1)
        cancel = button("取消")
        cancel.clicked.connect(dlg.reject)
        footer.addWidget(cancel)
        save = button("保存", "Primary")
        footer.addWidget(save)
        lay.addLayout(footer)

        def do_save():
            db_vocab.update_word(w["id"], trans.toPlainText().strip(),
                                 ex.toPlainText().strip(), exzh.toPlainText().strip())
            dlg.accept()

        save.clicked.connect(do_save)
        if dlg.exec_() == QDialog.Accepted:
            self.refresh_words()

    def closeEvent(self, event):  # noqa: N802
        self.speaker.stop()
        super().closeEvent(event)
