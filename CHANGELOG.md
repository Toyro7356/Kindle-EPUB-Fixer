# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).

Version numbering rules:
- Bug fix patches: `1.0.x`
- Minor feature upgrades: `1.x.0`
- Major rewrites: `2.0.0`

---

## [1.1.0] - 2026-04-15

### Added
- **自动语言检测与修正** (`src/language_fix.py`)
  - 根据正文文本自动识别 `zh-CN`、`zh-TW`、`ja`、`ko`。
  - 同步修正 OPF 与所有 XHTML 的 `lang` / `xml:lang` 属性。
- **漫画固定布局元数据注入** (`src/comic_fix.py`)
  - 为漫画 EPUB 自动补全 Amazon Kindle 所需的 fixed-layout 元数据：
    `fixed-layout`、`original-resolution`、`book-type=comic`、`zero-gutter`、
    `zero-margin`、`orientation-lock`、`region-mag`。
  - 自动检测或从首图推断分辨率，并确保每页包含 `viewport` meta。
- **后处理验证器** (`src/epub_validator.py`)
  - 对最终 EPUB 进行结构校验：manifest / spine 一致性、图片引用有效性、
    残留 WebP / JS / 内联脚本检测、漫画 viewport 与分辨率检查。
- **差异审计工具** (`tools/diff_epub.py`)
  - 对比原始与处理后的 EPUB，精确列出所有增删改内容，用于审计引擎行为。
- **GUI 取消处理按钮**
  - 点击"开始处理"后，按钮变为"取消处理"，可随时中断当前任务。
  - 取消信号会穿透字体选择对话框的等待状态，立即安全退出。

### Changed
- **字体处理增强**
  - 若 EPUB 引用的字体文件完全缺失，自动移除对应的 `@font-face` 规则，
    并回退到 Kindle 内置中文字体（`宋体, SimSun, serif`）。
  - 字体预扫描移至后台工作线程，彻底解决"开始处理"时的界面卡顿。
  - 字体缺失提示改为 `askyesnocancel`：支持导入、跳过、或**取消整个任务**。
  - 导入字体时点击"取消"，将弹出"是否跳过剩余字体？"选项，避免无限循环。
- **拖拽实现重构**
  - 将 ctypes `WM_DROPFILES` 实现彻底替换为 `tkinterdnd2`，解决 64 位 Windows
    下 `WNDPROC` / `CallWindowProc` 指针类型不匹配导致的拖拽崩溃（`0xc0000005`）。
  - 打包脚本 (`build_exe.py`) 自动内嵌 `tkinterdnd2` 原生 DLL/Tcl 资源。

### Fixed
- 修复 `src/image_fix.py` 中的 `NameError`（缺失 `NS_OPF` 导入）。
- 修复 GUI 工作线程中未定义变量导致的运行时异常。

---

## [1.0.0] - 2026-04-15

### Added
- Automatic comic / novel detection based on `rendition:layout` and SVG page ratio.
- WebP to JPG/PNG conversion with automatic reference updates in OPF, HTML, and CSS.
- SVG-to-`<img>` conversion for novels to prevent Kindle Enhanced Typesetting crashes.
- Kindle Pop-up Footnote restructuring (removes duokan-style back-links).
- Illegal self-closing tag repair (`<p/>`, `<div/>`, etc.) and DOCTYPE injection.
- Font compatibility pipeline:
  - Detects missing embedded fonts against Kindle built-in font whitelist.
  - Prompts user to import missing fonts.
  - Converts WOFF/WOFF2 to TTF/OTF.
  - Subsets embedded fonts to reduce file size.
- Vertical writing mode fix: downgrades `vertical-rl` to `horizontal-lr` for non-Japanese books.
- Spine direction fix: changes `page-progression-direction="rtl"` to `"ltr"` for non-Japanese novels.
- Script removal for novels: strips `<script>` tags and JavaScript manifest entries.
- GUI with HiDPI support, drag-and-drop file import, Win11 native styling, and responsive layout.

### Fixed
- Comic pages no longer get incorrectly identified as novels when they contain many SVG illustrations.
- Novel pages with SVG illustrations no longer retain stale `properties="svg"` in the manifest after conversion.
- Fixed Previewer `internal error` caused by missing `<!DOCTYPE html>` and illegal self-closing tags.
