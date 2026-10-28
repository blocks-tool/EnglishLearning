"""批量导入对话框：粘贴或从 txt/csv 文件导入单词列表，后台线程查词典补全释义。"""
import csv
import threading
import customtkinter as ctk
import tkinter.messagebox as mbox
from tkinter import filedialog
import db
import dictionary


class ImportDialog(ctk.CTkToplevel):
    def __init__(self, master, notebook_id):
        super().__init__(master)
        self.notebook_id = notebook_id
        self.title("批量导入单词")
        self.geometry("560x560")
        self.transient(master)
        self.grab_set()
        self._importing = False

        ctk.CTkLabel(self, text="粘贴单词，每行一个：",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=16, pady=(14, 4))

        self.textbox = ctk.CTkTextbox(self, height=240, font=ctk.CTkFont(size=14))
        self.textbox.pack(fill="both", expand=True, padx=16, pady=6)

        file_row = ctk.CTkFrame(self, fg_color="transparent")
        file_row.pack(fill="x", padx=16)
        ctk.CTkButton(file_row, text="📂 从 txt / csv 文件导入…", width=190, height=28,
                      fg_color="#eef4ff", text_color="#1764dc",
                      hover_color="#dbe9ff", border_width=1, border_color="#9fc4ff",
                      font=ctk.CTkFont(size=12),
                      command=self._load_file).pack(side="left")
        ctk.CTkLabel(file_row, text="自动去重、自动查词典补全释义",
                     text_color="#888", font=ctk.CTkFont(size=12)).pack(side="left", padx=10)

        self.status = ctk.CTkLabel(self, text="", text_color="#2980b9")
        self.status.pack(padx=16, pady=(4, 0), anchor="w")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=12)
        self.import_btn = ctk.CTkButton(btns, text="导入", width=120, command=self._do_import)
        self.import_btn.pack(side="left", padx=8)
        ctk.CTkButton(btns, text="取消", width=120, fg_color="#95a5a6",
                      command=self.destroy).pack(side="left", padx=8)

    def _load_file(self):
        path = filedialog.askopenfilename(
            parent=self, title="选择单词文件",
            filetypes=[("单词文件", "*.txt *.csv"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
                content = f.read()
        except OSError as e:
            mbox.showerror("读取失败", str(e), parent=self)
            return
        words = []
        if path.lower().endswith(".csv"):
            try:
                for record in csv.reader(content.splitlines()):
                    if record and record[0].strip():
                        words.append(record[0].strip())
            except csv.Error:
                words = [line.strip() for line in content.splitlines() if line.strip()]
        else:
            words = [line.strip() for line in content.splitlines() if line.strip()]
        # 跳过可能的表头
        if words and words[0].lower() in ("word", "单词"):
            words = words[1:]
        self.textbox.delete("1.0", "end")
        self.textbox.insert("1.0", "\n".join(words))
        self.status.configure(text=f"已载入 {len(words)} 行，点击「导入」开始")

    def _do_import(self):
        if self._importing:
            return
        raw = self.textbox.get("1.0", "end").strip()
        if not raw:
            mbox.showinfo("提示", "请先粘贴单词", parent=self)
            return
        words = []
        seen = set()
        for line in raw.splitlines():
            w = line.strip()
            if not w:
                continue
            # 允许一行 "word 释义" 这种格式，只取第一个词
            w = w.split()[0]
            key = w.lower()
            if key in seen:
                continue
            seen.add(key)
            words.append(w)

        if not words:
            mbox.showinfo("提示", "没有解析到有效单词", parent=self)
            return

        self._importing = True
        self.import_btn.configure(state="disabled")
        self.status.configure(text=f"正在查询词典（共 {len(words)} 词）...")
        threading.Thread(target=self._lookup_worker, args=(words,), daemon=True).start()

    def _lookup_worker(self, words):
        """后台线程查词典，进度通过 after 回投 UI 线程，避免窗口假死。"""
        rows = []
        not_found = []
        total = len(words)
        for i, w in enumerate(words, 1):
            try:
                info = dictionary.lookup(w)
            except Exception:
                info = None
            if info is None:
                not_found.append(w)
                rows.append({
                    "word": w, "phonetic": "", "translation": "",
                    "definition": "", "tag": "", "collins": 0,
                })
            else:
                rows.append(info)
            if i % 5 == 0 or i == total:
                self._post(lambda i=i, w=w: self.status.configure(
                    text=f"查询中 {i}/{total}: {w}"))
        self._post(lambda: self._finish_import(rows, not_found))

    def _post(self, fn):
        """窗口已关闭时静默丢弃回调。"""
        try:
            if self.winfo_exists():
                self.after(0, fn)
        except Exception:
            pass

    def _finish_import(self, rows, not_found):
        self._importing = False
        added, skipped = db.add_words(self.notebook_id, rows)
        msg = f"成功导入 {added} 词"
        if skipped:
            msg += f"，跳过重复 {skipped} 词"
        if not_found:
            msg += f"\n词典未收录 {len(not_found)} 词（仍已入库）：{', '.join(not_found[:10])}"
            if len(not_found) > 10:
                msg += " ..."
        mbox.showinfo("导入完成", msg, parent=self)
        self.destroy()
