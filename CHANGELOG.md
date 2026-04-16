# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).

Version numbering rules:
- Bug fix patches: `1.0.x`
- Minor feature upgrades: `1.x.0`
- Major rewrites: `2.0.0`

---

## [1.2.0] - 2026-04-15

### Added
- **通用 CSS 清理器** (`src/css_sanitize.py`)
  - 自动移除 Kindle 不支持的 CSS 属性：`position: fixed/sticky`、`z-index`、
    `box-shadow`、`text-shadow`、`animation`、`transition`、`transform`、
    `cursor`、`pointer-events`、`-webkit-*`（白名单除外）、`-moz-*` 等。
  - 同时清理 CSS 文件和 HTML inline style。
  - 依据：Amazon Kindle Publishing Guidelines 对 CSS 支持的明确限制。
- **无效图片引用修复** (`src/image_fix.py`)
  - 处理 HTML 中 `src="self"`、`src="none"`、`src=""`、`src="#"` 等常见占位符错误，
    替换为透明 1x1 GIF data URI，避免 Kindle 解析崩溃。
  - 移除无效的多看/掌阅专属属性 `zy-enlarge-src="self"` 等。
  - 对懒加载占位符 `data-src` 进行提升处理（若主 `src` 无效）。
- **单文件重复 id 修复** (`src/html_fix.py`)
  - 检测并修复单个 XHTML 文件内重复的 `id`，递增重命名（`id-1`, `id-2`），
    并同步更新该文件内所有 `href="#id"`、`src="#id"` 等片段引用。
  - 依据：XML ID 唯一性要求；重复 id 会导致内部链接/NCX/脚注失效。
- **自动注入 dcterms:modified** (`src/opf_sanitize.py`)
  - 若 OPF 缺少 `dcterms:modified`，自动注入当前 UTC 时间。
  - 依据：EPUB 3.0/3.2 规范，该元数据为 required。

### Fixed
- 修复 `epub_validator.py` 对 URL 编码图片路径（如 `%E7%89%B9%E5%85%B8...`）的误报，
  校验前先做 `urllib.parse.unquote` 解码。

### Verified
- 对 42 本不同作者自制的 EPUB 进行批量处理与校验，**全部通过** `epub_validator`。

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
