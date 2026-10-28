"""主窗口：左侧单词本，右侧单词表格+统计。清新蓝白风格。
表格行控件复用 + 单例 Tooltip + 搜索过滤，避免词多时大量重建控件。"""
import csv
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk

import db
from ui_import import ImportDialog
from ui_flashcard import FlashcardWindow

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# 配色（清透蓝白风格）
BG = "#edf4ff"
SIDEBAR_BG = "#f4f8ff"
CARD_BG = "#ffffff"
PRIMARY = "#3183f7"
PRIMARY_DARK = "#1764dc"
GREEN = "#20b66a"
GREEN_HOVER = "#159957"
TEXT_DARK = "#1b2d56"
TEXT_MUTED = "#7788a8"
BORDER = "#dce8fa"

HIGHLIGHT = "#eaf2ff"


class WordTooltip:
    """全局单例悬浮提示：attach 后文本存到控件的 _tooltip_text 属性，
    行复用时直接改文本即可，无需为每个单元格创建 Tooltip 对象。"""

    def __init__(self):
        self._timer = None
        self._window = None
        self._widget = None

    def attach(self, widget):
        widget._tooltip_text = ""
        widget.bind("<Enter>", lambda _e, w=widget: self._schedule(w), add="+")
        widget.bind("<Leave>", lambda _e: self.hide(), add="+")

    def _schedule(self, widget):
        self.hide()
        self._widget = widget
        self._timer = widget.after(450, lambda: self._show(widget))

    def _show(self, widget):
        self._timer = None
        text = getattr(widget, "_tooltip_text", "")
        if not text or not widget.winfo_exists():
            return
        x = widget.winfo_rootx() + 12
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        self._window = tk.Toplevel(widget)
        self._window.wm_overrideredirect(True)
        self._window.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._window, text=text, justify="left",
            background="#fffbe8", foreground="#334155",
            relief="solid", borderwidth=1,
            font=("Segoe UI", 10), padx=7, pady=4,
            wraplength=560,
        ).pack()

    def hide(self):
        if self._timer is not None and self._widget is not None:
            try:
                self._widget.after_cancel(self._timer)
            except tk.TclError:
                pass
        self._timer = None
        if self._window is not None:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
            self._window = None


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("单词本学习助手")
        self.geometry("1200x770")
        self.minsize(1000, 640)
        self.configure(fg_color=BG)

        self.current_notebook_id = None
        self._notebook_buttons = []
        self._drag_notebook_id = None
        self._drag_started = False
        self._current_stats = {"total": 0, "unknown": 0, "fuzzy": 0, "familiar": 0}
        self._tooltip = WordTooltip()
        self._search_job = None

        self._build_layout()
        self._refresh_notebooks()

    # ---------- 布局 ----------
    def _build_layout(self):
        # 左侧栏
        left = ctk.CTkFrame(self, width=234, corner_radius=0, fg_color=SIDEBAR_BG)
        left.pack(side="left", fill="y", padx=0, pady=0)
        left.pack_propagate(False)

        sidebar_title = ctk.CTkFrame(left, fg_color="transparent")
        sidebar_title.pack(fill="x", padx=20, pady=(22, 2))
        ctk.CTkLabel(
            sidebar_title, text="▤", width=32, height=32, corner_radius=8,
            fg_color="#dceaff", text_color=PRIMARY,
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(
            sidebar_title, text="我的单词本",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color=TEXT_DARK,
        ).pack(side="left")
        ctk.CTkLabel(left, text="拖拽调整顺序 · 右键重命名",
                     font=ctk.CTkFont(size=12),
                     text_color=TEXT_MUTED).pack(padx=64, pady=(0, 18), anchor="w")

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(padx=18, pady=(0, 12), fill="x")
        ctk.CTkButton(btn_row, text="＋  新建", width=99, height=38,
                      fg_color=PRIMARY, hover_color=PRIMARY_DARK,
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=self._on_new_notebook).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="▤  删除", width=92, height=38,
                      fg_color=SIDEBAR_BG, text_color=TEXT_MUTED,
                      hover_color="#e9f1ff", border_width=1, border_color=BORDER,
                      font=ctk.CTkFont(size=13),
                      command=self._on_delete_notebook).pack(side="left")

        self.nb_list = ctk.CTkScrollableFrame(
            left, label_text=None, fg_color="transparent", corner_radius=12)
        self.nb_list.pack(padx=12, pady=(6, 16), fill="both", expand=True)

        # 右侧主区
        right = ctk.CTkFrame(self, corner_radius=0, fg_color=BG)
        right.pack(side="right", fill="both", expand=True, padx=0, pady=0)

        # 顶部卡片：图标+标题+统计+操作按钮
        header_card = ctk.CTkFrame(
            right, fg_color=CARD_BG, corner_radius=16,
            border_width=1, border_color="#e8f0fc",
        )
        header_card.pack(fill="x", padx=18, pady=(14, 12))

        h_left = ctk.CTkFrame(header_card, fg_color="transparent")
        h_left.pack(side="left", padx=18, pady=14, anchor="w")

        # 左侧小图标方块
        icon_box = ctk.CTkLabel(
            h_left, text="☷", width=46, height=46,
            corner_radius=12, fg_color="#eaf2ff", text_color=PRIMARY,
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        icon_box.pack(side="left", padx=(0, 14))

        h_text = ctk.CTkFrame(h_left, fg_color="transparent")
        h_text.pack(side="left")
        self.title_label = ctk.CTkLabel(h_text, text="请选择或新建一个单词本",
                                         font=ctk.CTkFont(size=21, weight="bold"),
                                         text_color=TEXT_DARK)
        self.title_label.pack(anchor="w")
        self.stats_label = ctk.CTkLabel(h_text, text="", font=ctk.CTkFont(size=12),
                                         text_color=TEXT_MUTED)
        self.stats_label.pack(anchor="w", pady=(2, 0))

        # 右侧按钮
        h_btns = ctk.CTkFrame(header_card, fg_color="transparent")
        h_btns.pack(side="right", padx=18, pady=14)
        ctk.CTkButton(h_btns, text="▶  开始学习", width=144, height=40,
                      fg_color=GREEN, hover_color=GREEN_HOVER,
                      font=ctk.CTkFont(size=14, weight="bold"),
                      corner_radius=9,
                      command=self._on_study).pack(side="left", padx=(0, 10))
        ctk.CTkButton(h_btns, text="☷  批量导入", width=136, height=40,
                      fg_color=CARD_BG, text_color=PRIMARY,
                      hover_color="#f0f7ff", border_width=1, border_color="#9fc4ff",
                      font=ctk.CTkFont(size=14),
                      command=self._on_import).pack(side="left")

        # 表格卡片
        self.table_columns = (
            ("单词", 2, 210, PRIMARY_DARK),
            ("音标", 2, 210, "#98a4b8"),
            ("中文释义", 5, 230, "#8b6845"),
            ("标签", 2, 140, TEXT_DARK),
            ("状态", 1, 84, TEXT_MUTED),
        )

        table_card = ctk.CTkFrame(
            right, fg_color=CARD_BG, corner_radius=16,
            border_width=1, border_color="#e8f0fc",
        )
        table_card.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        table_card.grid_rowconfigure(2, weight=1)

        # 搜索条
        search_bar = ctk.CTkFrame(table_card, fg_color="transparent")
        search_bar.grid(row=0, column=0, columnspan=len(self.table_columns),
                        sticky="ew", padx=12, pady=(12, 0))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_changed)
        ctk.CTkEntry(
            search_bar, textvariable=self.search_var, width=280, height=32,
            placeholder_text="🔍 搜索单词 / 释义",
        ).pack(side="left")
        self.table_count_label = ctk.CTkLabel(
            search_bar, text="", text_color=TEXT_MUTED, font=ctk.CTkFont(size=11))
        self.table_count_label.pack(side="right")

        header = ctk.CTkFrame(table_card, fg_color="#edf4ff", corner_radius=9)
        header.grid(row=1, column=0, columnspan=len(self.table_columns),
                    sticky="ew", padx=(12, 26), pady=(10, 0))
        for index, (title, weight, min_width, _) in enumerate(self.table_columns):
            header.grid_columnconfigure(index, weight=weight, minsize=min_width)
            ctk.CTkLabel(
                header, text=title, height=36, anchor="w", justify="left",
                text_color="#4c5f83",
                font=ctk.CTkFont(size=14, weight="bold"),
            ).grid(row=0, column=index, sticky="nsew", padx=8)

        self.word_rows = ctk.CTkScrollableFrame(
            table_card, fg_color=CARD_BG, corner_radius=0,
            scrollbar_button_color="#c9d8f0",
            scrollbar_button_hover_color="#a8bedf",
        )
        self.word_rows.grid(
            row=2, column=0, columnspan=len(self.table_columns),
            sticky="nsew", padx=12, pady=(4, 12),
        )
        for index, (_, weight, min_width, _) in enumerate(self.table_columns):
            self.word_rows.grid_columnconfigure(
                index, weight=weight, minsize=min_width)

        self.selected_word_id = None
        self._table_rows = []        # 复用的行控件：[{"cells": [...], "word_id": int|None}]
        self._word_to_row = {}       # word_id -> 行下标
        self._word_data_by_id = {}
        self._word_status_labels = {}

        self.empty_label = ctk.CTkLabel(
            self.word_rows, text="（暂无单词）", text_color=TEXT_MUTED,
            font=ctk.CTkFont(size=14))

        # 底部操作条（透明浮在表格下方）
        bottom = ctk.CTkFrame(right, fg_color="transparent")
        bottom.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkButton(bottom, text="✏ 编辑释义", width=100, height=30,
                      fg_color=CARD_BG, text_color=PRIMARY_DARK,
                      hover_color="#f0f7ff", border_width=1, border_color=PRIMARY,
                      font=ctk.CTkFont(size=12),
                      command=self._on_edit_word).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bottom, text="删除选中单词", width=110, height=30,
                      fg_color=CARD_BG, text_color="#94a3b8",
                      hover_color="#fef2f2", border_width=1, border_color="#fecaca",
                      font=ctk.CTkFont(size=12),
                      command=self._on_delete_word).pack(side="left", padx=(0, 8))
        ctk.CTkButton(bottom, text="⇩ 导出 CSV", width=100, height=30,
                      fg_color=CARD_BG, text_color=PRIMARY_DARK,
                      hover_color="#f0f7ff", border_width=1, border_color=PRIMARY,
                      font=ctk.CTkFont(size=12),
                      command=self._on_export).pack(side="left")
        ctk.CTkLabel(bottom, text="双击行切换状态：陌生 → 模糊 → 熟悉",
                     text_color=TEXT_MUTED, font=ctk.CTkFont(size=11)).pack(side="right")

    # ---------- 统计 ----------
    @staticmethod
    def _stats_text(s):
        return (f"共 {s['total']} 词    陌生 {s['unknown']}    "
                f"模糊 {s['fuzzy']}    熟悉 {s['familiar']}")

    def _refresh_stats(self):
        if self.current_notebook_id is None:
            return
        self._current_stats = db.stats(self.current_notebook_id)
        self.stats_label.configure(text=self._stats_text(self._current_stats))

    # ---------- 单词本 ----------
    def _refresh_notebooks(self):
        for w in self.nb_list.winfo_children():
            w.destroy()
        self._notebook_buttons = []
        nbs = db.list_notebooks()
        if not nbs:
            self.current_notebook_id = None
            self._current_stats = {"total": 0, "unknown": 0, "fuzzy": 0, "familiar": 0}
            ctk.CTkLabel(self.nb_list, text="（暂无单词本）", text_color=TEXT_MUTED).pack(pady=20)
            self.title_label.configure(text="请选择或新建一个单词本")
            self.stats_label.configure(text="")
            self._refresh_words()
            return
        notebook_ids = {nb["id"] for nb in nbs}
        if self.current_notebook_id not in notebook_ids:
            self.current_notebook_id = nbs[0]["id"]
        cur = next(nb for nb in nbs if nb["id"] == self.current_notebook_id)
        self.title_label.configure(text=cur["name"])
        self._current_stats = db.stats(self.current_notebook_id)
        self.stats_label.configure(text=self._stats_text(self._current_stats))
        for nb in nbs:
            selected = (nb["id"] == self.current_notebook_id)
            if selected:
                fg = PRIMARY
                tc = "#ffffff"
                hover = PRIMARY_DARK
                border = PRIMARY
            else:
                fg = CARD_BG
                tc = TEXT_DARK
                hover = "#eaf2ff"
                border = BORDER
            lbl = ctk.CTkButton(
                self.nb_list, text=f"▣  {nb['name']}    ›", anchor="w",
                fg_color=fg, text_color=tc, hover_color=hover,
                border_width=1 if selected else 0, border_color=border,
                corner_radius=11, height=46,
                font=ctk.CTkFont(size=13, weight="bold" if selected else "normal"),
            )
            lbl.pack(fill="x", pady=5, padx=6)
            for surface in (lbl._canvas, lbl._text_label):
                if surface is None:
                    continue
                surface.bind(
                    "<ButtonPress-1>",
                    lambda event, nid=nb["id"]: self._on_notebook_drag_start(event, nid),
                    add="+")
                surface.bind("<B1-Motion>", self._on_notebook_drag_motion, add="+")
                surface.bind(
                    "<ButtonRelease-1>",
                    lambda event, nid=nb["id"]: self._on_notebook_drag_end(event, nid),
                    add="+")
                surface.bind(
                    "<Button-3>",
                    lambda event, nid=nb["id"], name=nb["name"]: self._rename_notebook(nid, name),
                    add="+")
            self._notebook_buttons.append((nb["id"], lbl))
        self._refresh_words()

    def _select_notebook(self, nid):
        self.current_notebook_id = nid
        self._refresh_notebooks()

    def _on_notebook_button_click(self, notebook_id):
        if self._drag_started:
            return
        self._select_notebook(notebook_id)

    def _on_notebook_drag_start(self, event, notebook_id):
        self._drag_notebook_id = notebook_id
        self._drag_started = False
        self._drag_start_y = event.y_root
        self._drag_button = next(
            button for nid, button in self._notebook_buttons if nid == notebook_id)
        self._drag_button_text = self._drag_button.cget("text")

    def _on_notebook_drag_motion(self, event):
        if self._drag_notebook_id is None:
            return
        if abs(event.y_root - self._drag_start_y) >= 5:
            self._drag_started = True
        if not self._drag_started:
            return
        self._drag_button.configure(text=f"↕  {self._drag_button_text}",
                                    fg_color="#f59e0b", hover_color="#d97706")
        others = [(nid, btn) for nid, btn in self._notebook_buttons if nid != self._drag_notebook_id]
        target_index = len(others)
        for index, (_, btn) in enumerate(others):
            midpoint = btn.winfo_rooty() + btn.winfo_height() / 2
            if event.y_root < midpoint:
                target_index = index
                break
        new_order = others[:target_index] + [(self._drag_notebook_id, self._drag_button)] + others[target_index:]
        if [i[0] for i in new_order] != [i[0] for i in self._notebook_buttons]:
            self._notebook_buttons = new_order
            for _, btn in self._notebook_buttons:
                btn.pack_forget()
            for _, btn in self._notebook_buttons:
                btn.pack(fill="x", pady=5, padx=6)
            self.nb_list.update_idletasks()

    def _on_notebook_drag_end(self, event, notebook_id):
        if self._drag_notebook_id is None:
            return
        self._drag_notebook_id = None
        if not self._drag_started:
            self._on_notebook_button_click(notebook_id)
            return
        ordered_ids = [nid for nid, _ in self._notebook_buttons]
        try:
            current_ids = [nb["id"] for nb in db.list_notebooks()]
            if ordered_ids != current_ids:
                db.reorder_notebooks(ordered_ids)
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("排序失败", str(error))
        self._drag_started = False
        self._refresh_notebooks()

    def _on_new_notebook(self):
        dialog = ctk.CTkInputDialog(text="输入新单词本名称：", title="新建单词本")
        name = dialog.get_input()
        if not name:
            return
        try:
            nid = db.create_notebook(name)
        except ValueError as e:
            messagebox.showerror("错误", str(e))
            return
        self.current_notebook_id = nid
        self._refresh_notebooks()

    def _rename_notebook(self, nid, old_name):
        name = simpledialog.askstring("重命名单词本", "输入新名称：",
                                      initialvalue=old_name, parent=self)
        if not name or name.strip() == old_name:
            return
        try:
            db.rename_notebook(nid, name)
        except ValueError as e:
            messagebox.showerror("错误", str(e))
            return
        self._refresh_notebooks()

    def _on_delete_notebook(self):
        if not self.current_notebook_id:
            messagebox.showinfo("提示", "请先选择要删除的单词本")
            return
        if not messagebox.askyesno("确认", "删除单词本将同时删除其中所有单词，确定？"):
            return
        db.delete_notebook(self.current_notebook_id)
        self.current_notebook_id = None
        self._refresh_notebooks()

    # ---------- 单词表格（行复用） ----------
    def _on_search_changed(self, *_):
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(180, self._apply_search)

    def _apply_search(self):
        self._search_job = None
        self._refresh_words()

    def _make_row(self, row_index):
        """创建一行 5 个单元格，事件绑定一次，后续通过行下标定位单词。"""
        self.word_rows.grid_rowconfigure(row_index, minsize=44)
        cells = []
        for column in range(len(self.table_columns)):
            cell = ctk.CTkLabel(
                self.word_rows, text="", anchor="w", justify="left",
                corner_radius=7 if column in (3, 4) else 0,
                font=ctk.CTkFont(size=18),
            )
            self._tooltip.attach(cell)
            surfaces = [cell]
            surfaces.extend(cell.winfo_children())
            for surface in surfaces:
                surface.bind(
                    "<Button-1>",
                    lambda _event, idx=row_index: self._on_row_click(idx),
                    add="+",
                )
                surface.bind(
                    "<Double-Button-1>",
                    lambda _event, idx=row_index: self._on_row_double_click_idx(idx),
                    add="+",
                )
            cells.append(cell)
        return {"cells": cells, "word_id": None, "index": row_index}

    def _set_row(self, row, row_index, word):
        word_id = word["id"]
        row["word_id"] = word_id
        # 复用行时恢复行高（隐藏时已重置为 0）
        self.word_rows.grid_rowconfigure(row_index, minsize=44)
        status_text, status_color, status_bg = self._status_style(word["status"])
        values = (
            (word["word"], PRIMARY_DARK, None),
            (word["phonetic"] or "", "#98a4b8", None),
            (word["translation"] or "", "#8b6845", None),
            (word["tag"] or "-", "#3278cc",
             "#e8f2ff" if word["tag"] else "#f0f2f5"),
            (status_text, status_color, status_bg),
        )
        for column, (text, color, bg) in enumerate(values):
            cell = row["cells"][column]
            cell.configure(text=text, text_color=color, fg_color=bg or "transparent")
            cell._tooltip_text = text if column >= 2 and text else ""
            cell.grid(row=row_index, column=column, sticky="ew", padx=8, pady=3)
        self._word_status_labels[word_id] = row["cells"][4]

    def _hide_row(self, row):
        row["word_id"] = None
        for cell in row["cells"]:
            cell.grid_remove()
        # 行高配置一并清除，否则切到词少的本子时仍出现滚动条
        self.word_rows.grid_rowconfigure(row["index"], minsize=0)

    def _refresh_words(self):
        self._tooltip.hide()
        self._word_to_row = {}
        self._word_data_by_id = {}
        self._word_status_labels = {}
        if self.current_notebook_id is None:
            words = []
        else:
            words = db.list_words(self.current_notebook_id)
        total = len(words)
        query = self.search_var.get().strip().lower()
        if query:
            words = [w for w in words
                     if query in w["word"].lower()
                     or query in (w["translation"] or "").lower()]
        # 行控件复用：不够才新建，多余隐藏，避免词多时大量创建/销毁控件
        while len(self._table_rows) < len(words):
            self._table_rows.append(self._make_row(len(self._table_rows)))
        for index, row in enumerate(self._table_rows):
            if index < len(words):
                word = words[index]
                self._set_row(row, index, word)
                self._word_to_row[word["id"]] = index
                self._word_data_by_id[word["id"]] = word
            else:
                self._hide_row(row)
        if not words:
            self.empty_label.configure(
                text="（没有匹配的单词）" if query else "（暂无单词，点右上角批量导入）")
            self.empty_label.grid(
                row=0, column=0, columnspan=len(self.table_columns), pady=30)
        else:
            self.empty_label.grid_remove()
        if query:
            self.table_count_label.configure(text=f"显示 {len(words)} / 共 {total} 词")
        else:
            self.table_count_label.configure(text="")
        # 保留选中行高亮
        if self.selected_word_id in self._word_to_row:
            self._apply_row_highlight(self._word_to_row[self.selected_word_id], True)
        else:
            self.selected_word_id = None

    @staticmethod
    def _status_style(status):
        styles = {
            db.STATUS_UNKNOWN: ("陌生", "#d94b4b", "#fff0f0"),
            db.STATUS_FUZZY: ("模糊", "#b7791f", "#fff6df"),
            db.STATUS_FAMILIAR: ("熟悉", "#3278cc", "#e8f2ff"),
        }
        return styles[status]

    def _on_row_click(self, row_index):
        word_id = self._table_rows[row_index]["word_id"]
        if word_id is not None:
            self._select_word_row(word_id)

    def _on_row_double_click_idx(self, row_index):
        word_id = self._table_rows[row_index]["word_id"]
        if word_id is not None:
            self._on_row_double_click(word_id)

    def _apply_row_highlight(self, row_index, selected):
        row = self._table_rows[row_index]
        for column, cell in enumerate(row["cells"]):
            if column in (3, 4):
                continue
            cell.configure(fg_color=HIGHLIGHT if selected else "transparent")

    def _select_word_row(self, word_id):
        old = self.selected_word_id
        if old in self._word_to_row:
            self._apply_row_highlight(self._word_to_row[old], False)
        self.selected_word_id = word_id
        if word_id in self._word_to_row:
            self._apply_row_highlight(self._word_to_row[word_id], True)

    def _on_row_double_click(self, word_id):
        word = self._word_data_by_id.get(word_id)
        if word is None:
            return
        cur = word["status"]
        nxt = (cur + 1) % 3
        db.set_status(word_id, nxt)
        word["status"] = nxt
        status_text, status_color, status_bg = self._status_style(nxt)
        self._word_status_labels[word_id].configure(
            text=status_text, text_color=status_color, fg_color=status_bg,
        )
        status_keys = {
            db.STATUS_UNKNOWN: "unknown",
            db.STATUS_FUZZY: "fuzzy",
            db.STATUS_FAMILIAR: "familiar",
        }
        self._current_stats[status_keys[cur]] -= 1
        self._current_stats[status_keys[nxt]] += 1
        self.stats_label.configure(text=self._stats_text(self._current_stats))

    def _on_delete_word(self):
        if self.selected_word_id is None:
            return
        if not messagebox.askyesno("确认", "删除选中的单词？"):
            return
        db.delete_word(self.selected_word_id)
        self.selected_word_id = None
        # 轻量刷新：行控件复用不销毁，滚动位置保持
        self._refresh_words()
        self._refresh_stats()

    def _on_edit_word(self):
        if self.selected_word_id is None:
            messagebox.showinfo("提示", "请先选中要编辑的单词")
            return
        word = self._word_data_by_id.get(self.selected_word_id)
        if not word:
            messagebox.showinfo("提示", "请先选中要编辑的单词")
            return
        dlg = EditWordDialog(self, word)
        self.wait_window(dlg)
        self._refresh_words()
        self._refresh_stats()

    def _on_export(self):
        if self.current_notebook_id is None:
            messagebox.showinfo("提示", "请先选择一个单词本")
            return
        words = db.list_words(self.current_notebook_id)
        if not words:
            messagebox.showinfo("提示", "当前单词本还没有单词")
            return
        nb_name = self.title_label.cget("text")
        path = filedialog.asksaveasfilename(
            parent=self, title="导出 CSV",
            defaultextension=".csv", initialfile=f"{nb_name}.csv",
            filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["word", "phonetic", "translation",
                                 "definition", "tag", "collins", "status"])
                for w in words:
                    writer.writerow([
                        w["word"], w["phonetic"], w["translation"],
                        w["definition"], w["tag"], w["collins"],
                        db.STATUS_LABELS.get(w["status"], w["status"]),
                    ])
        except OSError as e:
            messagebox.showerror("导出失败", str(e))
            return
        messagebox.showinfo("导出完成", f"已导出 {len(words)} 词到：\n{path}")

    # ---------- 导入/学习 ----------
    def _on_import(self):
        if self.current_notebook_id is None:
            messagebox.showinfo("提示", "请先选择或新建一个单词本")
            return
        dlg = ImportDialog(self, self.current_notebook_id)
        self.wait_window(dlg)
        self._refresh_words()
        self._refresh_stats()

    def _on_study(self):
        if self.current_notebook_id is None:
            messagebox.showinfo("提示", "请先选择一个单词本")
            return
        words = db.list_words(self.current_notebook_id)
        if not words:
            messagebox.showinfo("提示", "当前单词本还没有单词")
            return
        s = db.stats(self.current_notebook_id)
        dlg = StudyFilterDialog(self, s)
        self.wait_window(dlg)
        if dlg.result is None:
            return
        study = FlashcardWindow(self, self.current_notebook_id,
                                status_filter=dlg.result["statuses"],
                                shuffle=dlg.result["shuffle"],
                                on_close=self._on_study_closed)
        study.lift()
        study.focus_force()
        # 进入学习时隐藏主窗口，关闭单词卡后在 _on_study_closed 中恢复
        self.withdraw()

    def _on_study_closed(self):
        """关闭单词卡后恢复主窗口，并同步学习后的状态。"""
        self.deiconify()
        self.lift()
        self.focus_force()
        self._refresh_after_study()

    def _refresh_after_study(self):
        """仅同步学习后变化的状态和统计，保留现有单词行。"""
        if self.current_notebook_id is None:
            return
        words = db.list_word_statuses(self.current_notebook_id)
        stats = {"total": len(words), "unknown": 0, "fuzzy": 0, "familiar": 0}
        status_keys = {
            db.STATUS_UNKNOWN: "unknown",
            db.STATUS_FUZZY: "fuzzy",
            db.STATUS_FAMILIAR: "familiar",
        }
        for word in words:
            word_id = word["id"]
            status = word["status"]
            stats[status_keys[status]] += 1
            cached_word = self._word_data_by_id.get(word_id)
            if cached_word is not None and cached_word["status"] != status:
                cached_word["status"] = status
                text, color, bg = self._status_style(status)
                status_label = self._word_status_labels.get(word_id)
                if status_label is not None:
                    status_label.configure(text=text, text_color=color, fg_color=bg)
        self._current_stats = stats
        self.stats_label.configure(text=self._stats_text(stats))


class StudyFilterDialog(ctk.CTkToplevel):
    def __init__(self, master, stats):
        super().__init__(master)
        self.title("选择学习范围")
        self.geometry("360x400")
        self.configure(fg_color=CARD_BG)
        self.transient(master)
        self.grab_set()
        self.result = None

        ctk.CTkLabel(self, text="本次学习哪些状态的单词？",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(pady=(20, 14))

        self.var_unknown = ctk.BooleanVar(value=True)
        self.var_fuzzy = ctk.BooleanVar(value=True)
        self.var_familiar = ctk.BooleanVar(value=False)
        self.var_shuffle = ctk.BooleanVar(value=True)

        ctk.CTkCheckBox(self, text=f"陌生（{stats['unknown']} 词）",
                       variable=self.var_unknown,
                       fg_color=PRIMARY).pack(anchor="w", padx=40, pady=6)
        ctk.CTkCheckBox(self, text=f"模糊（{stats['fuzzy']} 词）",
                       variable=self.var_fuzzy,
                       fg_color=PRIMARY).pack(anchor="w", padx=40, pady=6)
        ctk.CTkCheckBox(self, text=f"熟悉（{stats['familiar']} 词）",
                       variable=self.var_familiar,
                       fg_color=PRIMARY).pack(anchor="w", padx=40, pady=6)
        ctk.CTkCheckBox(self, text="随机打乱顺序",
                       variable=self.var_shuffle,
                       fg_color=PRIMARY).pack(anchor="w", padx=40, pady=(14, 6))

        ctk.CTkLabel(self, text="（全不勾选 = 学习全部单词）",
                     text_color=TEXT_MUTED, font=ctk.CTkFont(size=11)).pack(pady=(8, 0))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=20)
        ctk.CTkButton(row, text="开始学习", width=120, height=36,
                      fg_color=GREEN, hover_color=GREEN_HOVER,
                      command=self._ok).pack(side="left", padx=8)
        ctk.CTkButton(row, text="取消", width=120, height=36,
                      fg_color="#e2e8f0", text_color=TEXT_DARK,
                      hover_color="#cbd5e1",
                      command=self._cancel).pack(side="left", padx=8)

    def _ok(self):
        selected = []
        if self.var_unknown.get():
            selected.append(db.STATUS_UNKNOWN)
        if self.var_fuzzy.get():
            selected.append(db.STATUS_FUZZY)
        if self.var_familiar.get():
            selected.append(db.STATUS_FAMILIAR)
        # 全不勾选 = 学习全部（与界面提示一致，之前会直接取消学习）
        if not selected:
            selected = [db.STATUS_UNKNOWN, db.STATUS_FUZZY, db.STATUS_FAMILIAR]
        self.result = {"statuses": selected, "shuffle": self.var_shuffle.get()}
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class EditWordDialog(ctk.CTkToplevel):
    def __init__(self, master, word):
        super().__init__(master)
        self.word = word
        self.title(f"编辑单词：{word['word']}")
        self.geometry("560x500")
        self.configure(fg_color=CARD_BG)
        self.transient(master)
        self.grab_set()

        ctk.CTkLabel(self, text=f"✏  {word['word']}",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(18, 12))

        ctk.CTkLabel(self, text="音标：", anchor="w").pack(fill="x", padx=24)
        self.phonetic_entry = ctk.CTkEntry(self, height=34)
        self.phonetic_entry.pack(fill="x", padx=24, pady=(0, 12))
        self.phonetic_entry.insert(0, word.get("phonetic") or "")

        ctk.CTkLabel(self, text="中文释义：", anchor="w").pack(fill="x", padx=24)
        self.trans_box = ctk.CTkTextbox(self, height=80)
        self.trans_box.pack(fill="x", padx=24, pady=(0, 12))
        self.trans_box.insert("1.0", word.get("translation") or "")

        ctk.CTkLabel(self, text="英文释义 / 例句参考：", anchor="w").pack(fill="x", padx=24)
        self.def_box = ctk.CTkTextbox(self, height=130)
        self.def_box.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        self.def_box.insert("1.0", word.get("definition") or "")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=14)
        ctk.CTkButton(row, text="保存", width=110, height=36,
                      fg_color=PRIMARY, hover_color=PRIMARY_DARK,
                      command=self._save).pack(side="left", padx=8)
        ctk.CTkButton(row, text="取消", width=110, height=36,
                      fg_color="#e2e8f0", text_color=TEXT_DARK,
                      command=self.destroy).pack(side="left", padx=8)

    def _save(self):
        db.update_word(
            self.word["id"],
            phonetic=self.phonetic_entry.get().strip(),
            translation=self.trans_box.get("1.0", "end").strip(),
            definition=self.def_box.get("1.0", "end").strip(),
        )
        self.destroy()
