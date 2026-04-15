"""
Kindle EPUB Fixer — Tkinter GUI (v1.0.0)
支持 HiDPI、文件拖拽、Win11 原生风格、响应式布局。
"""

import ctypes
import os
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from .__version__ import __title__, __version__
from .core import process_epub, scan_fonts, unpack_epub

# ---------------------------------------------------------------------------
# HiDPI support (Windows)
# ---------------------------------------------------------------------------
try:
    # Windows 10/11 Per-Monitor V2 DPI Awareness
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Drag & Drop support (tkinterdnd2)
# ---------------------------------------------------------------------------
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _TKDND_AVAILABLE = True
except Exception:
    _TKDND_AVAILABLE = False
    TkinterDnD = None  # type: ignore[misc,assignment]
    DND_FILES = None  # type: ignore[misc,assignment]

_BaseTk = TkinterDnD.Tk if _TKDND_AVAILABLE else tk.Tk


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class KindleEpubFixerGUI(_BaseTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{__title__} v{__version__}")
        self.geometry("800x600")
        self.minsize(720, 540)
        self.configure(bg=self._bg())

        self.input_files: List[str] = []
        self.output_dir: Optional[str] = None
        self._log_queue: List[str] = []
        self._log_lock = threading.Lock()
        self._after_id: Optional[str] = None
        self._font_event = threading.Event()
        self._font_result: Optional[Dict[str, str]] = None
        self._cancelled = False

        self._setup_theme()
        self._build_ui()
        self._center_window()
        self._enable_drop()

        # Start log flusher
        self._schedule_log_flush()

    # -----------------------------------------------------------------------
    # Theme / styling
    # -----------------------------------------------------------------------
    def _bg(self) -> str:
        return "SystemButtonFace"

    def _setup_theme(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        # Configure Treeview-like modern look for text widget border
        style.configure("Modern.TFrame", background=self._bg())
        style.configure("Card.TFrame", background="white")
        style.configure("Title.TLabel", font=("Microsoft YaHei", 16, "bold"))
        style.configure("Subtitle.TLabel", font=("Microsoft YaHei", 10))
        style.configure("Heading.TLabel", font=("Microsoft YaHei", 10, "bold"))

    # -----------------------------------------------------------------------
    # Layout
    # -----------------------------------------------------------------------
    def _build_ui(self) -> None:
        # Use grid for responsive layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=3)  # file list area
        self.rowconfigure(4, weight=4)  # log area

        # --- Header ---
        header = ttk.Frame(self, style="Modern.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text=__title__, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="智能修复 EPUB，提升 Kindle / Send to Kindle 兼容性", style="Subtitle.TLabel").grid(
            row=1, column=0, sticky="w"
        )
        ttk.Label(header, text=f"v{__version__}", foreground="gray").grid(row=0, column=1, sticky="e")

        # --- File list ---
        file_frame = ttk.LabelFrame(self, text="输入文件（支持拖拽 EPUB 到下方区域）")
        file_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=8)
        file_frame.columnconfigure(0, weight=1)
        file_frame.rowconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(
            file_frame,
            height=6,
            font=("Microsoft YaHei", 9),
            selectmode="extended",
            relief="solid",
            borderwidth=1,
        )
        self.file_listbox.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        file_scroll = ttk.Scrollbar(file_frame, orient="vertical", command=self.file_listbox.yview)
        file_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.file_listbox.config(yscrollcommand=file_scroll.set)

        file_btn_frame = ttk.Frame(file_frame)
        file_btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(file_btn_frame, text="添加 EPUB 文件", command=self._on_add_files).pack(side="left", padx=(0, 8))
        ttk.Button(file_btn_frame, text="清空列表", command=self._on_clear_files).pack(side="left")
        ttk.Button(file_btn_frame, text="移除选中", command=self._on_remove_selected).pack(side="left", padx=(8, 0))

        # --- Output directory ---
        out_frame = ttk.LabelFrame(self, text="输出目录")
        out_frame.grid(row=3, column=0, sticky="ew", padx=16, pady=8)
        out_frame.columnconfigure(0, weight=1)

        self.out_entry = ttk.Entry(out_frame, font=("Microsoft YaHei", 9))
        self.out_entry.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.out_entry.insert(0, "留空则与输入文件同目录")
        self.out_entry.config(foreground="gray")
        self.out_entry.bind("<FocusIn>", self._on_out_entry_focus)
        self.out_entry.bind("<FocusOut>", self._on_out_entry_unfocus)

        ttk.Button(out_frame, text="浏览…", command=self._on_browse_output).grid(row=0, column=1, padx=(0, 8), pady=8)

        # --- Log area (Text widget) ---
        log_frame = ttk.LabelFrame(self, text="处理日志")
        log_frame.grid(row=4, column=0, sticky="nsew", padx=16, pady=8)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            height=10,
            font=("Consolas", 9) if sys.platform == "win32" else ("Monospace", 9),
            wrap="word",
            state="disabled",
            relief="solid",
            borderwidth=1,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.log_text.tag_config("info", foreground="black")
        self.log_text.tag_config("warn", foreground="#b45309")
        self.log_text.tag_config("error", foreground="#dc2626")
        self.log_text.tag_config("success", foreground="#15803d")

        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self.log_text.config(yscrollcommand=log_scroll.set)

        # --- Progress & Actions ---
        action_frame = ttk.Frame(self)
        action_frame.grid(row=5, column=0, sticky="ew", padx=16, pady=(8, 16))
        action_frame.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(action_frame, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 16))

        self.start_btn = ttk.Button(action_frame, text="开始处理", command=self._on_start)
        self.start_btn.grid(row=0, column=1, padx=(0, 8))
        self._is_running = False

        ttk.Button(action_frame, text="打开输出目录", command=self._on_open_output_dir).grid(row=0, column=2)

    def _center_window(self) -> None:
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _enable_drop(self) -> None:
        if not _TKDND_AVAILABLE:
            return
        self.file_listbox.drop_target_register(DND_FILES)
        self.file_listbox.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event=None) -> None:
        if event is None or not event.data:
            return
        files = self.tk.splitlist(event.data)
        for f in files:
            f = f.strip()
            if f.lower().endswith(".epub") and f not in self.input_files:
                self.input_files.append(f)
                self.file_listbox.insert("end", Path(f).name)

    # -----------------------------------------------------------------------
    # Output entry placeholder
    # -----------------------------------------------------------------------
    def _on_out_entry_focus(self, _event=None) -> None:
        if self.out_entry.get() == "留空则与输入文件同目录":
            self.out_entry.delete(0, "end")
            self.out_entry.config(foreground="black")

    def _on_out_entry_unfocus(self, _event=None) -> None:
        if not self.out_entry.get().strip():
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, "留空则与输入文件同目录")
            self.out_entry.config(foreground="gray")

    # -----------------------------------------------------------------------
    # Logging (thread-safe, batched)
    # -----------------------------------------------------------------------
    def _log(self, msg: str, level: str = "info") -> None:
        with self._log_lock:
            self._log_queue.append((msg, level))

    def _schedule_log_flush(self) -> None:
        self._flush_logs()
        self._after_id = self.after(120, self._schedule_log_flush)

    def _flush_logs(self) -> None:
        with self._log_lock:
            batch = self._log_queue[:]
            self._log_queue.clear()
        if not batch:
            return
        self.log_text.config(state="normal")
        for msg, level in batch:
            self.log_text.insert("end", msg + "\n", level)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # -----------------------------------------------------------------------
    # File list actions
    # -----------------------------------------------------------------------
    def _on_add_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="选择 EPUB 文件",
            filetypes=[("EPUB files", "*.epub"), ("All files", "*.*")],
        )
        for f in files:
            if f not in self.input_files:
                self.input_files.append(f)
                self.file_listbox.insert("end", Path(f).name)

    def _on_clear_files(self) -> None:
        self.input_files.clear()
        self.file_listbox.delete(0, "end")

    def _on_remove_selected(self) -> None:
        selection = list(self.file_listbox.curselection())
        for idx in reversed(selection):
            self.file_listbox.delete(idx)
            del self.input_files[idx]

    def _on_browse_output(self) -> None:
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, directory)
            self.out_entry.config(foreground="black")

    def _on_open_output_dir(self) -> None:
        out_dir = self.out_entry.get().strip()
        if out_dir == "留空则与输入文件同目录":
            out_dir = ""
        if out_dir and os.path.isdir(out_dir):
            os.startfile(out_dir)
        elif self.input_files:
            os.startfile(os.path.dirname(self.input_files[0]))
        else:
            messagebox.showwarning("提示", "没有可用的输出目录")

    # -----------------------------------------------------------------------
    # Processing
    # -----------------------------------------------------------------------
    def _on_start(self) -> None:
        if self._is_running:
            return
        if not self.input_files:
            messagebox.showwarning("提示", "请先添加 EPUB 文件")
            return

        out_dir = self.out_entry.get().strip()
        if out_dir == "留空则与输入文件同目录":
            out_dir = ""
        out_dir = out_dir or None

        self._is_running = True
        self.start_btn.config(text="取消处理", command=self._on_cancel)
        self.progress["value"] = 0
        self._cancelled = False
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

        thread = threading.Thread(
            target=self._worker,
            args=(out_dir,),
            daemon=True,
        )
        thread.start()

    def _prompt_font_import(self, all_missing: set) -> None:
        """在主线程中执行字体导入对话框。"""
        families_str = ", ".join(sorted(all_missing))
        answer = messagebox.askyesnocancel(
            "缺失字体",
            f"以下字体在 EPUB 中缺失且非 Kindle 内置字体：\n{families_str}\n\n是否从本地导入这些字体？",
        )

        imported: Dict[str, str] = {}
        if answer is True:
            families = sorted(all_missing)
            for idx, family in enumerate(families):
                fp = filedialog.askopenfilename(
                    title=f"选择字体文件: {family} ({idx+1}/{len(families)})",
                    filetypes=[
                        ("Font files", "*.ttf *.otf *.woff *.woff2"),
                        ("All files", "*.*"),
                    ],
                )
                if fp:
                    imported[family] = fp
                    self._log(f"用户选择导入字体: {family} -> {fp}")
                else:
                    # 用户取消了选择，询问是否继续为剩余字体导入
                    remaining = families[idx + 1:]
                    if remaining:
                        cont = messagebox.askyesno(
                            "跳过剩余字体",
                            f"未选择 {family} 的字体文件。\n\n是否继续为剩余的 {len(remaining)} 个字体导入？",
                        )
                        if not cont:
                            break
        elif answer is False:
            self._log("用户选择不导入缺失字体，将继续处理（使用回退字体）")
        else:  # answer is None (取消 / 点叉)
            self._log("用户取消处理任务")
            self._cancelled = True

        self._font_result = imported
        self._font_event.set()

    def _worker(self, out_dir: Optional[str]) -> None:
        total = len(self.input_files)

        # 1. 字体缺失预扫描（在工作线程中执行，避免 UI 卡顿）
        all_missing: set = set()
        per_file_missing: Dict[str, set] = {}
        self._log("正在扫描字体引用...")
        for epub_path in self.input_files:
            try:
                with tempfile.TemporaryDirectory() as td:
                    unpack_epub(epub_path, td)
                    _, missing, _ = scan_fonts(td)
                    if missing:
                        all_missing.update(missing)
                        per_file_missing[epub_path] = missing
            except Exception as e:
                self._log(f"[Warning] 字体预扫描失败 {Path(epub_path).name}: {e}", "warn")

        imported_fonts_map: Dict[str, str] = {}
        if all_missing and not self._cancelled:
            self._font_event.clear()
            self._font_result = None
            self.after(0, lambda: self._prompt_font_import(all_missing))
            self._font_event.wait()
            imported_fonts_map = self._font_result or {}

        # 2. 逐文件处理
        success = 0
        for idx, epub_path in enumerate(self.input_files, start=1):
            if self._cancelled:
                self._log("处理已取消")
                break

            basename = Path(epub_path).name
            self._log(f"[{idx}/{total}] 开始处理: {basename}")

            if out_dir:
                output_path = os.path.join(out_dir, f"{Path(basename).stem}.processed.epub")
            else:
                output_path = None

            missing_for_file = per_file_missing.get(epub_path, set())
            imported = {k: imported_fonts_map[k] for k in missing_for_file if k in imported_fonts_map}
            try:
                result = process_epub(
                    epub_path,
                    output_path,
                    log=lambda msg: self._log(f"  -> {msg}"),
                    imported_fonts=imported,
                )
                self._log(f"  -> 完成: {result}", "success")
                success += 1
            except Exception as exc:
                self._log(f"  -> 错误: {exc}", "error")

            progress = ((idx if not self._cancelled else idx - 1) / total) * 100
            self.after(0, lambda v=progress: self.progress.config(value=v))

        self.after(0, self._on_finished, success, total)

    def _on_cancel(self) -> None:
        if not self._is_running:
            return
        self._cancelled = True
        self._font_event.set()
        self._log("用户请求取消任务...", "warn")

    def _on_finished(self, success: int, total: int) -> None:
        self._is_running = False
        self.start_btn.config(text="开始处理", command=self._on_start, state="normal")
        if self.progress["value"] < 100:
            self.progress["value"] = 100
        if self._cancelled:
            messagebox.showinfo("处理取消", f"已完成 {success} / 总计 {total}")
        else:
            messagebox.showinfo("处理完成", f"成功 {success} / 总计 {total}")


def main() -> None:
    app = KindleEpubFixerGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
