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
from .book_profile import detect_book_profile
from .content_analysis import ContentAnalysis, analyze_content
from .core import process_files, resolve_output_path
from .epub_io import find_opf, repack_epub, unpack_epub
from .epub_validator import validate_epub
from .font_handler import FontScanResult, ImportedFontSpec, resolve_missing_font_plan, scan_fonts

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    _TKDND_AVAILABLE = True
except Exception:
    DND_FILES = None  # type: ignore[assignment]
    TkinterDnD = None  # type: ignore[assignment]
    _TKDND_AVAILABLE = False

_BaseTk = TkinterDnD.Tk if _TKDND_AVAILABLE else tk.Tk
PLACEHOLDER_OUTPUT = "留空则输出到输入目录下的 转换后 文件夹"


class KindleEpubFixerGUI(_BaseTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{__title__} v{__version__}")
        self.geometry("980x700")
        self.minsize(860, 620)
        self.configure(bg="#f3efe7")

        self.input_files: List[str] = []
        self._log_queue: List[tuple[str, str]] = []
        self._log_lock = threading.Lock()
        self._font_event = threading.Event()
        self._font_result: Optional[Dict[str, ImportedFontSpec]] = None
        self._cancelled = False
        self._is_running = False
        self._font_cache: Dict[str, ImportedFontSpec] = {}

        self._setup_theme()
        self._build_ui()
        self._enable_drop()
        self._center_window()
        self._schedule_log_flush()

    def _setup_theme(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background="#f3efe7")
        style.configure("Card.TFrame", background="#fffaf1")
        style.configure("Hero.TLabel", background="#f3efe7", font=("Microsoft YaHei UI", 20, "bold"), foreground="#1f2937")
        style.configure("Muted.TLabel", background="#f3efe7", font=("Microsoft YaHei UI", 10), foreground="#6b7280")
        style.configure("Section.TLabelframe", background="#fffaf1")
        style.configure("Section.TLabelframe.Label", background="#fffaf1", foreground="#374151", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"))

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=3)
        self.rowconfigure(5, weight=4)

        header = ttk.Frame(self, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text=__title__, style="Hero.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="尽量保留原书排版语义，只修复 Kindle 明显不兼容或结构异常的部分。",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, text=f"v{__version__}", style="Muted.TLabel").grid(row=0, column=1, sticky="e")

        summary = ttk.Frame(self, style="App.TFrame")
        summary.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 8))
        summary.columnconfigure(0, weight=1)
        self.summary_var = tk.StringVar(value="已选择 0 本 EPUB")
        self.status_var = tk.StringVar(value="等待开始")
        ttk.Label(summary, textvariable=self.summary_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(summary, textvariable=self.status_var, style="Muted.TLabel").grid(row=0, column=1, sticky="e")

        file_frame = ttk.LabelFrame(self, text="输入文件", style="Section.TLabelframe")
        file_frame.grid(row=3, column=0, sticky="nsew", padx=18, pady=8)
        file_frame.columnconfigure(0, weight=1)
        file_frame.rowconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(
            file_frame,
            height=10,
            font=("Microsoft YaHei UI", 10),
            bg="#fffdf8",
            relief="flat",
            borderwidth=0,
            selectmode="extended",
            activestyle="none",
        )
        self.file_listbox.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        file_scroll = ttk.Scrollbar(file_frame, orient="vertical", command=self.file_listbox.yview)
        file_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.file_listbox.config(yscrollcommand=file_scroll.set)

        file_buttons = ttk.Frame(file_frame, style="Card.TFrame")
        file_buttons.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        ttk.Button(file_buttons, text="添加 EPUB", command=self._on_add_files).pack(side="left")
        ttk.Button(file_buttons, text="移除选中", command=self._on_remove_selected).pack(side="left", padx=(8, 0))
        ttk.Button(file_buttons, text="清空列表", command=self._on_clear_files).pack(side="left", padx=(8, 0))

        output_frame = ttk.LabelFrame(self, text="输出位置", style="Section.TLabelframe")
        output_frame.grid(row=4, column=0, sticky="ew", padx=18, pady=8)
        output_frame.columnconfigure(0, weight=1)

        self.out_entry = ttk.Entry(output_frame, font=("Microsoft YaHei UI", 10))
        self.out_entry.grid(row=0, column=0, sticky="ew", padx=(10, 8), pady=10)
        self.out_entry.insert(0, PLACEHOLDER_OUTPUT)
        self.out_entry.configure(foreground="#6b7280")
        self.out_entry.bind("<FocusIn>", self._on_output_focus_in)
        self.out_entry.bind("<FocusOut>", self._on_output_focus_out)

        ttk.Button(output_frame, text="选择目录", command=self._on_browse_output).grid(row=0, column=1, padx=(0, 8), pady=10)
        ttk.Button(output_frame, text="打开输出目录", command=self._on_open_output_dir).grid(row=0, column=2, padx=(0, 10), pady=10)

        log_frame = ttk.LabelFrame(self, text="处理日志", style="Section.TLabelframe")
        log_frame.grid(row=5, column=0, sticky="nsew", padx=18, pady=8)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame,
            font=("Consolas", 9) if sys.platform == "win32" else ("Monospace", 9),
            wrap="word",
            state="disabled",
            bg="#fffdf8",
            relief="flat",
            borderwidth=0,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        self.log_text.tag_config("info", foreground="#111827")
        self.log_text.tag_config("warn", foreground="#b45309")
        self.log_text.tag_config("error", foreground="#b91c1c")
        self.log_text.tag_config("success", foreground="#047857")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=10)
        self.log_text.config(yscrollcommand=log_scroll.set)

        footer = ttk.Frame(self, style="App.TFrame")
        footer.grid(row=6, column=0, sticky="ew", padx=18, pady=(8, 18))
        footer.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(footer, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 16))

        self.start_btn = ttk.Button(footer, text="开始处理", style="Primary.TButton", command=self._on_start)
        self.start_btn.grid(row=0, column=1)

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
        for raw_path in self.tk.splitlist(event.data):
            self._add_file(raw_path.strip())

    def _on_output_focus_in(self, _event=None) -> None:
        if self.out_entry.get() == PLACEHOLDER_OUTPUT:
            self.out_entry.delete(0, "end")
            self.out_entry.configure(foreground="#111827")

    def _on_output_focus_out(self, _event=None) -> None:
        if not self.out_entry.get().strip():
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, PLACEHOLDER_OUTPUT)
            self.out_entry.configure(foreground="#6b7280")

    def _displayed_output_dir(self) -> Optional[str]:
        value = self.out_entry.get().strip()
        if not value or value == PLACEHOLDER_OUTPUT:
            return None
        return value

    def _log(self, msg: str, level: str = "info") -> None:
        with self._log_lock:
            self._log_queue.append((msg, level))

    def _schedule_log_flush(self) -> None:
        self._flush_logs()
        self.after(100, self._schedule_log_flush)

    def _flush_logs(self) -> None:
        with self._log_lock:
            batch = self._log_queue[:]
            self._log_queue.clear()
        if not batch:
            return
        self.log_text.configure(state="normal")
        for msg, level in batch:
            self.log_text.insert("end", msg + "\n", level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _refresh_summary(self) -> None:
        self.summary_var.set(f"已选择 {len(self.input_files)} 本 EPUB")

    def _add_file(self, file_path: str) -> None:
        if not file_path.lower().endswith(".epub"):
            return
        if file_path in self.input_files:
            return
        self.input_files.append(file_path)
        self.file_listbox.insert("end", Path(file_path).name)
        self._refresh_summary()

    def _on_add_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="选择 EPUB 文件",
            filetypes=[("EPUB files", "*.epub"), ("All files", "*.*")],
        )
        for file_path in files:
            self._add_file(file_path)

    def _on_remove_selected(self) -> None:
        for index in reversed(self.file_listbox.curselection()):
            self.file_listbox.delete(index)
            del self.input_files[index]
        self._refresh_summary()

    def _on_clear_files(self) -> None:
        self.file_listbox.delete(0, "end")
        self.input_files.clear()
        self._refresh_summary()

    def _on_browse_output(self) -> None:
        selected = filedialog.askdirectory(title="选择输出目录")
        if selected:
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, selected)
            self.out_entry.configure(foreground="#111827")

    def _on_open_output_dir(self) -> None:
        out_dir = self._displayed_output_dir()
        if out_dir and os.path.isdir(out_dir):
            os.startfile(out_dir)
            return
        if self.input_files:
            default_dir = str((Path(self.input_files[0]).resolve().parent / "转换后"))
            if os.path.isdir(default_dir):
                os.startfile(default_dir)
                return
        messagebox.showinfo("提示", "还没有可打开的输出目录。")

    def _prompt_font_import(self, missing_families: set[str], book_name: str) -> None:
        needed = [family for family in sorted(missing_families) if family not in self._font_cache]
        imported: Dict[str, ImportedFontSpec] = {}

        if not needed:
            self._font_result = imported
            self._font_event.set()
            return

        answer = messagebox.askyesnocancel(
            "缺失字体",
            (
                f"{book_name} 仍有缺失字体未能自动匹配：\n{', '.join(needed)}\n\n"
                "是否现在选择本地字体文件继续补全？\n"
                "选择“否”将跳过这些字体，程序会改用 Kindle 可兼容的回退字体。"
            ),
        )

        if answer is None:
            self._cancelled = True
        elif answer:
            for family in needed:
                file_path = filedialog.askopenfilename(
                    title=f"选择字体文件：{family}",
                    filetypes=[("Font files", "*.ttf *.otf *.ttc *.otc *.woff *.woff2"), ("All files", "*.*")],
                )
                if not file_path:
                    continue
                spec = ImportedFontSpec(path=file_path, source="manual")
                self._font_cache[family] = spec
                imported[family] = spec
                self._log(f"用户导入字体: {family} -> {file_path}")

        self._font_result = imported
        self._font_event.set()

    def _request_fonts_for_book(self, missing_families: set[str], book_name: str) -> Dict[str, ImportedFontSpec]:
        cached = {family: self._font_cache[family] for family in missing_families if family in self._font_cache}
        if self._cancelled:
            return cached
        uncached = {family for family in missing_families if family not in self._font_cache}
        if not uncached:
            return cached
        self._font_event.clear()
        self._font_result = None
        self.after(0, lambda: self._prompt_font_import(uncached, book_name))
        self._font_event.wait()
        return cached | (self._font_result or {})

    def _reset_log_view(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _on_start(self) -> None:
        if self._is_running:
            return
        if not self.input_files:
            messagebox.showwarning("提示", "请先添加 EPUB 文件。")
            return

        self._cancelled = False
        self._is_running = True
        self.progress.configure(value=0)
        self.status_var.set("准备处理中")
        self._reset_log_view()
        self.start_btn.configure(text="取消处理", command=self._on_cancel)

        threading.Thread(target=self._worker, daemon=True).start()

    def _on_cancel(self) -> None:
        if not self._is_running:
            return
        self._cancelled = True
        self._font_event.set()
        self.status_var.set("正在取消")
        self._log("用户请求取消任务...", "warn")

    def _process_single_book(self, epub_path: str, output_dir: Optional[str]) -> tuple[str, list[str]]:
        book_name = Path(epub_path).name
        output_target = resolve_output_path(epub_path, output_dir if output_dir else None)

        with tempfile.TemporaryDirectory() as temp_dir:
            unpack_epub(epub_path, temp_dir)
            opf_path = find_opf(temp_dir)
            content_analysis = analyze_content(opf_path)
            profile = detect_book_profile(opf_path, content_analysis)
            self._log(
                f"  -> 书籍轮廓: mode={profile.layout_mode}, preserve={profile.preserve_layout}, svg={profile.has_svg_pages}, js={profile.has_javascript}"
            )

            imported_fonts: Dict[str, ImportedFontSpec] = {}
            font_scan: Optional[FontScanResult] = None
            font_scan = scan_fonts(temp_dir)
            missing = set(font_scan.missing)
            if missing:
                self._log(f"  -> 检测到缺失字体: {', '.join(sorted(missing))}", "warn")
                auto_plan = resolve_missing_font_plan(missing)
                if auto_plan.imported:
                    for family, spec in auto_plan.imported.items():
                        self._font_cache.setdefault(family, spec)
                    self._log(
                        "  -> 已自动匹配可导入字体: "
                        + ", ".join(f"{family} -> {Path(spec.path).name}" for family, spec in sorted(auto_plan.imported.items())),
                        "info",
                    )
                    imported_fonts.update(auto_plan.imported)
                if auto_plan.builtin_fallbacks:
                    self._log(
                        "  -> 将使用 Kindle 回落字体: "
                        + ", ".join(
                            f"{family} -> {', '.join(families[:2])}"
                            for family, families in sorted(auto_plan.builtin_fallbacks.items())
                        ),
                        "info",
                    )
                if auto_plan.unresolved:
                    self._log(f"  -> 仍未自动匹配的字体: {', '.join(sorted(auto_plan.unresolved))}", "warn")
                    imported_fonts.update(self._request_fonts_for_book(auto_plan.unresolved, book_name))
            if self._cancelled:
                raise RuntimeError("任务已取消")

            book_type = process_files(
                temp_dir,
                log=lambda msg: self._log(f"  -> {msg}"),
                imported_fonts=imported_fonts,
                profile=profile,
                font_scan=font_scan,
                content_analysis=content_analysis,
            )
            repack_epub(temp_dir, output_target)
            issues = validate_epub(output_target, book_type)
            return output_target, issues

    def _worker(self) -> None:
        total = len(self.input_files)
        success = 0
        output_dir = self._displayed_output_dir()

        for index, epub_path in enumerate(self.input_files, start=1):
            if self._cancelled:
                break

            book_name = Path(epub_path).name
            self.status_var.set(f"处理中 {index}/{total}: {book_name}")
            self._log(f"[{index}/{total}] 开始处理 {book_name}")

            try:
                result_path, issues = self._process_single_book(epub_path, output_dir)
                if issues:
                    self._log(f"  -> 输出完成，但有 {len(issues)} 条校验告警", "warn")
                    for issue in issues[:5]:
                        self._log(f"     - {issue}", "warn")
                else:
                    self._log(f"  -> 完成: {result_path}", "success")
                success += 1
            except Exception as exc:
                self._log(f"  -> 错误: {exc}", "error")

            progress = (index / total) * 100
            self.after(0, lambda value=progress: self.progress.configure(value=value))

        self.after(0, self._on_finished, success, total)

    def _on_finished(self, success: int, total: int) -> None:
        self._is_running = False
        self.start_btn.configure(text="开始处理", command=self._on_start)
        self.progress.configure(value=100 if not self._cancelled else self.progress["value"])
        if self._cancelled:
            self.status_var.set("任务已取消")
            messagebox.showinfo("已取消", f"已完成 {success} / {total} 本。")
        else:
            self.status_var.set("处理完成")
            messagebox.showinfo("处理完成", f"成功完成 {success} / {total} 本。")


def main() -> None:
    app = KindleEpubFixerGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
