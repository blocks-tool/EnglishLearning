"""单词卡学习窗口：状态筛选 + 乱序 + 离线发音 + 键盘快捷键 + 三档标记。"""
import random
import customtkinter as ctk
import tkinter.messagebox as mbox
import db
import tts

# 状态配色（与主界面统一）
STATUS_COLORS = {
    db.STATUS_UNKNOWN:  {"bg": "#fee2e2", "fg": "#b91c1c", "btn": "#ef4444"},
    db.STATUS_FUZZY:    {"bg": "#fef3c7", "fg": "#b45309", "btn": "#f59e0b"},
    db.STATUS_FAMILIAR: {"bg": "#d1fae5", "fg": "#047857", "btn": "#10b981"},
}


class FlashcardWindow(ctk.CTkToplevel):
    def __init__(self, master, notebook_id, status_filter=None, shuffle=False, on_close=None):
        """status_filter: list of int，要学习的状态。None/空表示全量。
        shuffle: True 时随机打乱学习顺序。"""
        super().__init__(master)
        self.notebook_id = notebook_id
        self.on_close = on_close

        self.title("单词卡学习")
        # 不使用 transient：主窗口会被隐藏，transient 子窗口会跟着一起隐藏
        if master is not None and master.winfo_exists():
            x = max(master.winfo_rootx() + (master.winfo_width() - 760) // 2, 0)
            y = max(master.winfo_rooty() + (master.winfo_height() - 640) // 2, 0)
            self.geometry(f"760x640+{x}+{y}")
        else:
            self.geometry("760x640")
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._closed = False

        # 按筛选条件加载单词
        if status_filter:
            pool = []
            for s in status_filter:
                pool.extend(db.list_words(notebook_id, status=s))
        else:
            pool = db.list_words(notebook_id)
        if shuffle:
            random.shuffle(pool)
        self.words = pool
        self.index = 0
        self.revealed = False
        self._playing_target = None
        self._audio_request_id = 0
        self._mark_seq = 0

        self._build_layout()
        self._bind_shortcuts()
        self._show_current()

    def _build_layout(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 4))
        self.progress = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=12), text_color="#888")
        self.progress.pack(side="left")
        self.var_autoplay = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(top, text="自动播放单词读音", variable=self.var_autoplay,
                        command=self._on_autoplay_toggle,
                        font=ctk.CTkFont(size=12), text_color="#666",
                        fg_color="#2980b9", checkbox_width=18, checkbox_height=18,
                        width=20).pack(side="right")
        self.var_autoadv = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(top, text="标记后自动下一张", variable=self.var_autoadv,
                        font=ctk.CTkFont(size=12), text_color="#666",
                        fg_color="#2980b9", checkbox_width=18, checkbox_height=18,
                        width=20).pack(side="right", padx=(0, 18))

        self.card = ctk.CTkFrame(self, corner_radius=16, fg_color="#f8f9fa")
        self.card.pack(fill="both", expand=True, padx=20, pady=8)

        self.word_label = ctk.CTkLabel(self.card, text="",
                                       font=ctk.CTkFont(size=36, weight="bold"))
        self.word_label.pack(pady=(20, 2))

        # 状态徽章：紧跟单词下方
        self.status_badge = ctk.CTkLabel(
            self.card, text="", font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8, padx=12, pady=3)
        self.status_badge.pack(pady=(0, 4))

        self.phonetic_label = ctk.CTkLabel(self.card, text="",
                                           font=ctk.CTkFont(size=16), text_color="#666")
        self.phonetic_label.pack(pady=(0, 10))

        audio_row = ctk.CTkFrame(self.card, fg_color="transparent")
        audio_row.pack(pady=(0, 10))
        self.word_audio_btn = ctk.CTkButton(audio_row, text="🔊 读单词", width=120,
                                            command=self._toggle_word_audio)
        self.word_audio_btn.pack(side="left", padx=6)
        self.def_audio_btn = ctk.CTkButton(audio_row, text="🔊 读例句/释义", width=140,
                                           fg_color="#8e44ad", hover_color="#6c3483",
                                           command=self._toggle_def_audio)
        self.def_audio_btn.pack(side="left", padx=6)

        self.detail_box = ctk.CTkTextbox(self.card, height=170, font=ctk.CTkFont(size=14),
                                         fg_color="white", activate_scrollbars=True)
        self.detail_box.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self.detail_box.configure(state="disabled")

        self.reveal_btn = ctk.CTkButton(self.card, text="显示释义 ▼",
                                        fg_color="#2980b9", hover_color="#2471a3",
                                        command=self._toggle_reveal)
        self.reveal_btn.pack(pady=(0, 14))

        mark_row = ctk.CTkFrame(self, fg_color="transparent")
        mark_row.pack(pady=8)
        self.mark_buttons = {}
        for status, label, emoji in [
            (db.STATUS_UNKNOWN, "陌生", "✗"),
            (db.STATUS_FUZZY, "模糊", "~"),
            (db.STATUS_FAMILIAR, "熟悉", "✓"),
        ]:
            color = STATUS_COLORS[status]
            btn = ctk.CTkButton(
                mark_row, text=f"{emoji} {label}", width=140, height=36,
                fg_color=color["btn"], hover_color=color["btn"],
                font=ctk.CTkFont(size=13, weight="bold"),
                command=lambda s=status: self._mark(s))
            btn.pack(side="left", padx=8)
            self.mark_buttons[status] = btn

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(pady=(0, 4))
        ctk.CTkButton(nav, text="← 上一张", width=120, fg_color="#95a5a6",
                      command=self._prev).pack(side="left", padx=8)
        ctk.CTkButton(nav, text="下一张 →", width=120, fg_color="#2980b9",
                      command=self._next).pack(side="left", padx=8)

        ctk.CTkLabel(self, text="空格 显示/隐藏释义 · 1/2/3 标记 陌生/模糊/熟悉 · ←/→ 翻卡 · A 读单词 · Esc 退出",
                     font=ctk.CTkFont(size=11), text_color="#9aa4b2").pack(pady=(0, 10))

    def _bind_shortcuts(self):
        self.bind("<space>", lambda _e: self._toggle_reveal())
        self.bind("<Key-1>", lambda _e: self._mark(db.STATUS_UNKNOWN))
        self.bind("<Key-2>", lambda _e: self._mark(db.STATUS_FUZZY))
        self.bind("<Key-3>", lambda _e: self._mark(db.STATUS_FAMILIAR))
        self.bind("<Left>", lambda _e: self._prev())
        self.bind("<Right>", lambda _e: self._next())
        self.bind("<a>", lambda _e: self._toggle_word_audio())
        self.bind("<A>", lambda _e: self._toggle_word_audio())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.focus_set()

    def _show_current(self):
        if self._closed:
            return
        # 翻卡时停止上一段朗读
        self._audio_request_id += 1
        tts.stop()
        self._playing_target = None
        if hasattr(self, "word_audio_btn"):
            self._refresh_audio_buttons()
        if not self.words:
            self.word_label.configure(text="本组没有单词")
            self.phonetic_label.configure(text="")
            self.detail_box.configure(state="normal")
            self.detail_box.delete("1.0", "end")
            self.detail_box.configure(state="disabled")
            self.progress.configure(text="")
            return
        w = self.words[self.index]
        self.revealed = False
        self.reveal_btn.configure(text="显示释义 ▼")
        self.word_label.configure(text=w["word"])
        self.phonetic_label.configure(text=f"/{w['phonetic']}/" if w["phonetic"] else "")
        self.detail_box.configure(state="normal")
        self.detail_box.delete("1.0", "end")
        self.detail_box.configure(state="disabled")
        self._refresh_status_ui(w["status"])
        # 自动发音：稍作延迟，避免窗口还没画出来就开始播
        if self.var_autoplay.get():
            self.after(120, lambda idx=self.index: self._autoplay_word(idx))

    def _autoplay_word(self, expected_index):
        """当前卡片切换完成后自动读单词；用户已在播放则不打断。"""
        if self._closed or not self.words:
            return
        if self.index != expected_index or not self.var_autoplay.get():
            return
        if self._playing_target is not None:
            return
        self._start_audio("word", self.words[self.index]["word"])

    def _on_autoplay_toggle(self):
        self._autoplay_word(self.index)

    def _refresh_status_ui(self, status):
        """更新状态徽章和标记按钮高亮。"""
        c = STATUS_COLORS[status]
        self.status_badge.configure(
            text=f"当前状态：{db.STATUS_LABELS[status]}",
            fg_color=c["bg"], text_color=c["fg"])
        for s, btn in self.mark_buttons.items():
            sc = STATUS_COLORS[s]
            if s == status:
                btn.configure(fg_color=sc["btn"], text_color="white",
                              border_width=2, border_color="#1e293b")
            else:
                btn.configure(fg_color="#e2e8f0", text_color="#475569",
                              border_width=0)
        self.progress.configure(
            text=f"第 {self.index + 1} / {len(self.words)} 词"
        )

    def _toggle_reveal(self):
        if not self.words:
            return
        self.revealed = not self.revealed
        w = self.words[self.index]
        self.detail_box.configure(state="normal")
        self.detail_box.delete("1.0", "end")
        if self.revealed:
            text = ""
            if w["translation"]:
                text += f"【释义】\n{w['translation']}\n\n"
            if w["definition"]:
                text += f"【英文释义 / 例句参考】\n{w['definition']}\n\n"
            tags = []
            if w["tag"]:
                tags.append(w["tag"])
            if w["collins"]:
                tags.append(f"柯林斯{w['collins']}星")
            if tags:
                text += f"【标签】{'  '.join(tags)}"
            self.detail_box.insert("end", text.strip() or "（暂无释义）")
            self.reveal_btn.configure(text="隐藏释义 ▲")
        else:
            self.reveal_btn.configure(text="显示释义 ▼")
        self.detail_box.configure(state="disabled")

    def _toggle_word_audio(self):
        if not self.words:
            return
        if self._playing_target == "word" and tts.is_playing():
            self._stop_audio()
        else:
            self._start_audio("word", self.words[self.index]["word"])

    def _toggle_def_audio(self):
        if not self.words:
            return
        w = self.words[self.index]
        text = w["definition"] or w["translation"] or w["word"]
        if self._playing_target == "def" and tts.is_playing():
            self._stop_audio()
        else:
            self._start_audio("def", text)

    def _start_audio(self, target, text):
        self._audio_request_id += 1
        request_id = self._audio_request_id
        self._playing_target = target
        self._refresh_audio_buttons()
        tts.speak(
            text,
            on_finished=lambda: self._on_audio_finished(request_id),
            on_error=lambda error: self._on_audio_error(request_id, error),
        )

    def _stop_audio(self):
        self._audio_request_id += 1
        tts.stop()
        self._playing_target = None
        self._refresh_audio_buttons()

    def _on_audio_finished(self, request_id):
        """切回 UI 线程恢复当前播放对应的按钮状态。"""
        if self._closed:
            return
        self.after(0, lambda: self._reset_audio_buttons(request_id))

    def _on_audio_error(self, request_id, error):
        if self._closed:
            return
        self.after(0, lambda: self._show_audio_error(request_id, error))

    def _show_audio_error(self, request_id, error):
        if request_id == self._audio_request_id:
            mbox.showerror("播放失败", str(error), parent=self)

    def _reset_audio_buttons(self, request_id):
        if request_id != self._audio_request_id:
            return
        self._playing_target = None
        self._refresh_audio_buttons()

    def _refresh_audio_buttons(self):
        if self._playing_target == "word":
            self.word_audio_btn.configure(text="⏹ 停止", fg_color="#c0392b", hover_color="#96281b")
        else:
            self.word_audio_btn.configure(text="🔊 读单词", fg_color=["#979DA2", "#565B5E"],
                                          hover_color=["#7a7f84", "#3f4345"])
        if self._playing_target == "def":
            self.def_audio_btn.configure(text="⏹ 停止", fg_color="#c0392b", hover_color="#96281b")
        else:
            self.def_audio_btn.configure(text="🔊 读例句/释义", fg_color="#8e44ad",
                                         hover_color="#6c3483")

    def _mark(self, status):
        if not self.words:
            return
        self._mark_seq += 1
        wid = self.words[self.index]["id"]
        db.set_status(wid, status)
        self.words[self.index]["status"] = status
        self._refresh_status_ui(status)
        # 自动跳下一张：延迟期间用户手动翻页/再标记则取消
        if self.var_autoadv.get() and self.index < len(self.words) - 1:
            seq = self._mark_seq
            marked_index = self.index
            self.after(220, lambda: self._auto_advance(seq, marked_index))

    def _auto_advance(self, seq, marked_index):
        if self._closed or seq != self._mark_seq or self.index != marked_index:
            return
        self._next()

    def _next(self):
        if self.index < len(self.words) - 1:
            self.index += 1
            self._show_current()

    def _prev(self):
        if self.index > 0:
            self.index -= 1
            self._show_current()

    def destroy(self):
        if self._closed:
            return
        self._closed = True
        self._audio_request_id += 1
        tts.stop()
        super().destroy()
        # 关闭单词卡后恢复主窗口
        if self.on_close:
            self.on_close()
