"""口语学习助手主窗口：学习库树 + 文章/媒体视图。"""
import os
import shutil
import time

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtMultimedia import QMediaPlayer
from PyQt5.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QMainWindow,
    QMenu, QMessageBox, QStackedWidget, QStyle, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from core import asr, db_speaking, tts
from core.paths import DATA_DIR
from core.ui import COLORS, Card, PlayerBar, button, hline, label
from .article_view import ArticleView
from .dialogs import ArticleDialog
from .media_view import MediaView


class SpeakingWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        db_speaking.init_db()
        self.current_group = None
        self.current_material = None
        self.setWindowTitle("口语学习助手")
        self.resize(1320, 860)
        self.setMinimumSize(1080, 720)
        self._build()
        self.refresh_tree()

    # ---------------- 界面 ----------------
    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(304)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 18, 14, 14)
        side.setSpacing(10)

        brand = QHBoxLayout()
        logo = QLabel("S")
        logo.setFixedSize(36, 36)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet(
            f"background:{COLORS['primary']};color:white;border-radius:10px;"
            "font-size:17px;font-weight:700;")
        brand.addWidget(logo)
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(label("口语学习助手", 15, COLORS["text"], bold=True))
        text.addWidget(label("Speaking Coach · 离线练习", 9, COLORS["muted"]))
        brand.addLayout(text)
        brand.addStretch(1)
        side.addLayout(brand)
        side.addSpacing(2)

        top_row = QHBoxLayout()
        top_row.addWidget(label("学习库", 10, COLORS["sub"], bold=True))
        top_row.addStretch(1)
        new_group = button("＋ 新建组", "Ghost")
        new_group.clicked.connect(self.create_group)
        top_row.addWidget(new_group)
        side.addLayout(top_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(16)
        self.tree.setAnimated(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.currentItemChanged.connect(self._on_tree_changed)
        side.addWidget(self.tree, 1)

        side.addWidget(hline())
        side.addWidget(label("导入到当前分组", 9, COLORS["sub"]))
        imp_row = QHBoxLayout()
        imp_row.setSpacing(6)
        for text_, kind in (("文章", "article"), ("音频", "audio"), ("视频", "video")):
            btn = button(text_, "Soft")
            btn.clicked.connect(lambda _=False, k=kind: self.import_material(k))
            imp_row.addWidget(btn)
        side.addLayout(imp_row)

        engine = QHBoxLayout()
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background:{COLORS['green']};border-radius:4px;")
        engine.addWidget(dot)
        engine.addWidget(label(f"朗读：{tts.backend_name()}", 9, COLORS["sub"]))
        engine.addStretch(1)
        side.addLayout(engine)
        status = "字幕识别：Vosk 离线模型已就绪" if asr.model_ready() else \
            "字幕识别：首次生成时自动下载模型"
        side.addWidget(label(status, 9, COLORS["sub"]))
        outer.addWidget(sidebar)

        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(20, 16, 20, 14)
        content_lay.setSpacing(12)
        self.player = QMediaPlayer(self)
        self.player.setVolume(95)
        self.stack = QStackedWidget()
        self.empty = self._build_empty()
        self.article_view = ArticleView(self.player)
        self.article_view.contentChanged.connect(self._on_content_changed)
        self.media_view = MediaView(self.player)
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.article_view)
        self.stack.addWidget(self.media_view)
        content_lay.addWidget(self.stack, 1)

        # 底部统一播放器：文章朗读与音视频播放共用
        bar_card = Card(padding=12)
        self.player_bar = PlayerBar(navigation=False)
        self.player_bar.set_player(self.player)
        bar_card.layout.addWidget(self.player_bar)
        content_lay.addWidget(bar_card, 0)
        outer.addWidget(content, 1)
        self.stack.setCurrentWidget(self.empty)

    def _build_empty(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        card = Card(padding=40)
        card.layout.addStretch(1)
        icon = QLabel("Aa")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(92, 92)
        icon.setStyleSheet(
            f"background:{COLORS['blue_soft']};color:{COLORS['primary']};"
            "border-radius:24px;font-size:30px;font-weight:700;")
        card.layout.addWidget(icon, 0, Qt.AlignHCenter)
        self.empty_title = label("开始你的口语练习", 21, COLORS["text"], bold=True)
        self.empty_title.setAlignment(Qt.AlignCenter)
        card.layout.addWidget(self.empty_title)
        hint = label("在左侧新建分组，导入文章、音频或视频。\n"
                     "支持逐句朗读、录音跟读评分、自动生成字幕。",
                     11, COLORS["sub"])
        hint.setAlignment(Qt.AlignCenter)
        card.layout.addWidget(hint)
        row = QHBoxLayout()
        row.addStretch(1)
        for text_, kind, kind_style in (("导入文章", "article", "Primary"),
                                        ("导入音频", "audio", "Soft"),
                                        ("导入视频", "video", "Soft")):
            btn = button(text_, kind_style)
            btn.clicked.connect(lambda _=False, k=kind: self.import_material(k))
            row.addWidget(btn)
        row.addStretch(1)
        card.layout.addLayout(row)
        card.layout.addStretch(1)
        lay.addWidget(card)
        return page

    # ---------------- 树 ----------------
    def refresh_tree(self, select_material=None, select_group=None):
        self.tree.blockSignals(True)
        self.tree.clear()
        root = QTreeWidgetItem(["学习库"])
        font = QFont("Microsoft YaHei UI", 10)
        font.setBold(True)
        root.setFont(0, font)
        root.setIcon(0, self.style().standardIcon(QStyle.SP_DirHomeIcon))
        root.setData(0, Qt.UserRole, ("root", 0))
        self.tree.addTopLevelItem(root)
        target_item = None
        for group in db_speaking.list_groups():
            g_item = QTreeWidgetItem([f"{group['name']}   {db_speaking.material_counts(group['id'])}"])
            gfont = QFont("Microsoft YaHei UI", 10)
            gfont.setBold(True)
            g_item.setFont(0, gfont)
            g_item.setIcon(0, self.style().standardIcon(QStyle.SP_DirClosedIcon))
            g_item.setData(0, Qt.UserRole, ("group", group["id"]))
            root.addChild(g_item)
            for m in db_speaking.list_materials(group["id"]):
                m_item = QTreeWidgetItem([m["title"]])
                icon = {"article": QStyle.SP_FileIcon,
                        "audio": QStyle.SP_MediaVolume,
                        "video": QStyle.SP_MediaPlay}.get(m["kind"], QStyle.SP_FileIcon)
                m_item.setIcon(0, self.style().standardIcon(icon))
                m_item.setData(0, Qt.UserRole, ("material", m["id"]))
                g_item.addChild(m_item)
                if select_material and m["id"] == select_material:
                    target_item = m_item
                if select_group and group["id"] == select_group and not select_material:
                    target_item = g_item
        root.setExpanded(True)
        for i in range(root.childCount()):
            root.child(i).setExpanded(True)
        self.tree.blockSignals(False)
        if target_item is not None:
            self.tree.setCurrentItem(target_item)
        else:
            self.tree.setCurrentItem(root)
            self.stack.setCurrentWidget(self.empty)

    def _on_tree_changed(self, current, previous):
        if current is None:
            return
        data = current.data(0, Qt.UserRole)
        if not data:
            return
        kind, ident = data
        if kind == "material":
            material = db_speaking.get_material(ident)
            if not material:
                return
            self._stop_views()
            self.current_group = material["group_id"]
            self.current_material = ident
            if material["kind"] == "article":
                self.article_view.set_material(material)
                self.stack.setCurrentWidget(self.article_view)
                # 文章页底部播放按钮改为触发文章朗读，而不是继续播放上一个音视频
                self.player_bar.toggle_handler = self.article_view.toggle_read
            else:
                self.media_view.set_material(material)
                self.stack.setCurrentWidget(self.media_view)
                self.player_bar.toggle_handler = None
        elif kind == "group":
            self.current_group = ident
            self.current_material = None
            self._stop_views()
            self.player_bar.toggle_handler = None
            group = next((g for g in db_speaking.list_groups() if g["id"] == ident), None)
            name = group["name"] if group else "分组"
            self.empty_title.setText(name)
            self.stack.setCurrentWidget(self.empty)
        else:
            self.current_group = None
            self.current_material = None
            self._stop_views()
            self.player_bar.toggle_handler = None
            self.empty_title.setText("开始你的口语练习")
            self.stack.setCurrentWidget(self.empty)

    def _stop_views(self):
        self.article_view.stop()
        self.media_view.stop()

    def _tree_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, ident = data
        menu = QMenu(self)
        if kind == "group":
            self.tree.setCurrentItem(item)
            add_article = menu.addAction("导入文章")
            add_audio = menu.addAction("导入音频")
            add_video = menu.addAction("导入视频")
            menu.addSeparator()
            rename = menu.addAction("重命名分组")
            delete = menu.addAction("删除分组")
            chosen = menu.exec_(self.tree.viewport().mapToGlobal(pos))
            if chosen == add_article:
                self.import_material("article")
            elif chosen == add_audio:
                self.import_material("audio")
            elif chosen == add_video:
                self.import_material("video")
            elif chosen == rename:
                self.rename_group(ident)
            elif chosen == delete:
                self.delete_group(ident)
        elif kind == "material":
            self.tree.setCurrentItem(item)
            open_item = menu.addAction("打开")
            rename = menu.addAction("重命名")
            delete = menu.addAction("删除")
            chosen = menu.exec_(self.tree.viewport().mapToGlobal(pos))
            if chosen == open_item:
                self._on_tree_changed(item, None)
            elif chosen == rename:
                self.rename_material(ident)
            elif chosen == delete:
                self.delete_material(ident)

    # ---------------- 分组 / 素材 ----------------
    def create_group(self):
        name, ok = QInputDialog.getText(self, "新建分组", "分组名称：")
        if not ok or not name.strip():
            return
        gid = db_speaking.create_group(name)
        self.refresh_tree(select_group=gid)

    def rename_group(self, gid):
        group = next((g for g in db_speaking.list_groups() if g["id"] == gid), None)
        if not group:
            return
        name, ok = QInputDialog.getText(self, "重命名分组", "分组名称：", text=group["name"])
        if not ok or not name.strip():
            return
        db_speaking.rename_group(gid, name)
        self.refresh_tree(select_group=gid)

    def delete_group(self, gid):
        group = next((g for g in db_speaking.list_groups() if g["id"] == gid), None)
        if not group:
            return
        if QMessageBox.question(self, "删除分组",
                                f"确定删除分组「{group['name']}」及其中所有素材吗？") != QMessageBox.Yes:
            return
        db_speaking.delete_group(gid)
        self.current_group = None
        self.current_material = None
        self._stop_views()
        self.refresh_tree()

    def _target_group(self):
        if self.current_group:
            return self.current_group
        groups = db_speaking.list_groups()
        if groups:
            return groups[0]["id"]
        return db_speaking.create_group("默认分组")

    def import_material(self, kind):
        gid = self._target_group()
        if kind == "article":
            dlg = ArticleDialog(self)
            if dlg.exec_() != QDialog.Accepted:
                return
            title, content = dlg.values()
            mid = db_speaking.add_material(gid, "article", title, content=content)
            self.refresh_tree(select_material=mid)
            return
        if kind == "audio":
            filt = "音频 (*.mp3 *.wav *.m4a *.aac *.flac *.ogg);;所有文件 (*.*)"
        else:
            filt = "视频 (*.mp4 *.mov *.mkv *.avi *.wmv *.webm);;所有文件 (*.*)"
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", filt)
        if not path:
            return
        dest_dir = os.path.join(DATA_DIR, "media")
        os.makedirs(dest_dir, exist_ok=True)
        base = os.path.basename(path)
        dest = os.path.join(dest_dir, f"{int(time.time() * 1000)}_{base}")
        try:
            shutil.copy2(path, dest)
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", f"复制文件失败：{exc}")
            return
        mid = db_speaking.add_material(gid, kind, os.path.splitext(base)[0], path=dest)
        self.refresh_tree(select_material=mid)

    def rename_material(self, mid):
        material = db_speaking.get_material(mid)
        if not material:
            return
        name, ok = QInputDialog.getText(self, "重命名", "标题：", text=material["title"])
        if not ok or not name.strip():
            return
        db_speaking.update_material(mid, title=name.strip())
        self.refresh_tree(select_material=mid)

    def delete_material(self, mid):
        material = db_speaking.get_material(mid)
        if not material:
            return
        if QMessageBox.question(self, "删除素材",
                                f"确定删除「{material['title']}」吗？") != QMessageBox.Yes:
            return
        db_speaking.delete_material(mid)
        self.current_material = None
        self._stop_views()
        self.refresh_tree(select_group=material["group_id"])

    def _on_content_changed(self):
        if self.current_material:
            self.refresh_tree(select_material=self.current_material)

    def closeEvent(self, event):  # noqa: N802
        self._stop_views()
        super().closeEvent(event)
