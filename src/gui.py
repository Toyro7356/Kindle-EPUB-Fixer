"""
Kindle EPUB Fixer — Tkinter GUI (v1.0.0)
支持 HiDPI、文件拖拽、Win11 原生风格、响应式布局。
"""

import ctypes
import os
import struct
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
# Drag & Drop support (Windows WM_DROPFILES)
# ---------------------------------------------------------------------------
WM_DROPFILES = 0x0233
GWL_WNDPROC = -4
HDROP = ctypes.c_void_p
DragAcceptFiles = ctypes.windll.shell32.DragAcceptFiles
DragQueryFile = ctypes.windll.shell32.DragQueryFileW
DragFinish = ctypes.windll.shell32.DragFinish

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_longlong
)
user32 = ctypes.windll.user32
GetWindowLong = user32.GetWindowLongW
SetWindowLong = user32.SetWindowLongW
CallWindowProc = user32.CallWindowProcW


def _make_drop_handler(target_list: List[str], listbox: tk.Listbox) -> WNDPROC:
    original_wndproc = GetWindowLong(listbox.winfo_id(), GWL_WNDPROC)

    def wndproc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:  # type: ignore[misc]
        if msg == WM_DROPFILES:
            hdrop = HDROP(wparam)
            count = DragQueryFile(hdrop, 0xFFFFFFFF, None, 0)
            for i in range(count):
                buf = ctypes.create_unicode_buffer(260)
                DragQueryFile(hdrop, i, buf, 260)
                file_path = buf.value
                if file_path.lower().endswith(".epub") and file_path not in target_list:
                    target_list.append(file_path)
                    listbox.insert("end", Path(file_path).name)
            DragFinish(hdrop)
            return 0
        return CallWindowProc(original_wndproc, hwnd, msg, wparam, lparam)

    return WNDPROC(wndproc)


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class KindleEpubFixerGUI(tk.Tk):
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

        ttk.Button(action_frame, text="打开输出目录", command=self._on_open_output_dir).grid(row=0, column=2)

    def _center_window(self) -> None:
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _enable_drop(self) -> None:
        hwnd = self.file_listbox.winfo_id()
        DragAcceptFiles(hwnd, True)
        self._drop_wndproc = _make_drop_handler(self.input_files, self.file_listbox)
        SetWindowLong(hwnd, GWL_WNDPROC, self._drop_wndproc)

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
        if not self.input_files:
            messagebox.showwarning("提示", "请先添加 EPUB 文件")
            return

        out_dir = self.out_entry.get().strip()
        if out_dir == "留空则与输入文件同目录":
            out_dir = ""
        out_dir = out_dir or None

        self.start_btn.config(state="disabled")
        self.progress["value"] = 0
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

        # 字体缺失预扫描（主线程中执行，确保对话框安全）
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
        if all_missing:
            families_str = ", ".join(sorted(all_missing))
            if messagebox.askyesno(
                "缺失字体",
                f"以下字体在 EPUB 中缺失且非 Kindle 内置字体：\n{families_str}\n\n是否从本地导入这些字体？",
            ):
                for family in sorted(all_missing):
                    fp = filedialog.askopenfilename(
                        title=f"选择字体文件: {family}",
                        filetypes=[
                            ("Font files", "*.ttf *.otf *.woff *.woff2"),
                            ("All files", "*.*"),
                        ],
                    )
                    if fp:
                        imported_fonts_map[family] = fp
                        self._log(f"用户选择导入字体: {family} -> {fp}")

        per_file_imports: Dict[str, Dict[str, str]] = {}
        for epub_path in self.input_files:
            missing = per_file_missing.get(epub_path, set())
            per_file_imports[epub_path] = {
                f: imported_fonts_map[f] for f in missing if f in imported_fonts_map
            }

        thread = threading.Thread(
            target=self._worker,
            args=(out_dir, per_file_imports),
            daemon=True,
        )
        thread.start()

    def _worker(self, out_dir: Optional[str], per_file_imports: Dict[str, Dict[str, str]]) -> None:
        total = len(self.input_files)
        success = 0
        for idx, epub_path in enumerate(self.input_files, start=1):
            basename = Path(epub_path).name
            self._log(f"[{idx}/{total}] 开始处理: {basename}")

            if out_dir:
                output_path = os.path.join(out_dir, f"{Path(basename).stem}.processed.epub")
            else:
                output_path = None

            imported = per_file_imports.get(epub_path, {})
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

            progress = (idx / total) * 100
            self.after(0, lambda v=progress: self.progress.config(value=v))

        self.after(0, self._on_finished, success, total)

    def _on_finished(self, success: int, total: int) -> None:
        self.start_btn.config(state="normal")
        self.progress["value"] = 100
        messagebox.showinfo("处理完成", f"成功 {success} / 总计 {total}")


def main() -> None:
    app = KindleEpubFixerGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
