# Kindle EPUB Fixer

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Kindle EPUB Fixer 是面向 Kindle / Send to Kindle 的 EPUB 兼容性修复与网页小说转制工具。

Kindle EPUB Fixer repairs EPUB files for Kindle and Send to Kindle, and can also turn supported web novel sources into Kindle-friendly EPUB files.

## 核心原则 / Principles

- 尽量保留原书的排版、字体和结构意图，只修复明确的 Kindle 兼容性问题。
- Keep the original book design whenever possible, and repair only clear Kindle compatibility problems.
- 对普通可重排小说、漫画、固定版式和布局敏感内容采用不同处理强度。
- Use different repair levels for reflowable novels, comics, fixed-layout books, and layout-sensitive content.
- ESJZone 等网页来源先读取为统一小说对象，再交给独立 EPUB 生成管线。
- Web sources such as ESJZone are normalized into a shared novel model before EPUB generation.

## 功能 / Features

- EPUB 结构修复：OPF、XHTML、NCX、manifest、spine、语言元数据和基础资源引用。
- EPUB structure repair for OPF, XHTML, NCX, manifest, spine, language metadata, and resource links.
- 图片兼容：WebP 转换、封面引用修复、缺失或冲突资源路径修复。
- Image compatibility fixes, including WebP conversion, cover references, and broken or colliding paths.
- 字体兼容：保留可用字体，清理坏引用，必要时回落到 Kindle 字体或内置开源仿宋。
- Font handling that keeps valid embedded fonts, removes broken references, and falls back to Kindle fonts or bundled Zhuque Fangsong when needed.
- 保守的脚注、SVG、CSS transform 和固定版式处理，避免为单本书过度改写。
- Conservative handling for footnotes, SVG pages, CSS transforms, and fixed-layout content.
- 原生 WinUI 3 桌面界面，支持批量修复、日志查看、字体设置和 ESJZone 转制。
- Native WinUI 3 desktop app with batch repair, logs, font settings, and ESJZone conversion.
- ESJZone：网页登录获取 Cookie、自动读取书籍信息和目录、可选章节范围、正文图片资源化、Kindle 友好 EPUB 输出。
- ESJZone support: web login cookie capture, metadata and TOC parsing, optional chapter ranges, image packaging, and Kindle-friendly EPUB output.

## 使用 / Usage

### Windows GUI

下载发布页中的安装包并运行：

Download the setup package from Releases and run it:

```text
KindleEpubFixer-<version>-Setup.exe
```

本地构建安装包：

Build the installer locally:

```powershell
powershell -ExecutionPolicy Bypass -File build_winui.ps1
```

输出文件：

Artifacts:

```text
dist/KindleEpubFixer.Setup.exe
dist/KindleEpubFixer-<version>-Setup.exe
```

### Command Line

```bash
python main.py "input.epub"
python main.py "input.epub" "output.epub"
python main.py esjzone "https://www.esjzone.cc/detail/xxxx.html" "output.epub"
```

未指定输出路径时，结果会写入输入文件旁边的 `转换后` 文件夹。

When no output path is provided, the result is written to a `转换后` folder next to the input file.

## 开发 / Development

```bash
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m compileall -q src main.py main_backend.py build_backend.py
```

WinUI 构建需要 .NET SDK。没有全局 SDK 时可以安装到仓库本地：

WinUI builds require the .NET SDK. To install it locally:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_dotnet_sdk.ps1
```

## 文档 / Docs

- [处理流程 / Processing flow](docs/PROCESS_FLOW.md)
- [安装器 / Installer](docs/INSTALLER.md)
- [GUI 架构 / GUI architecture](docs/GUI_REFACTOR_PLAN.md)
- [字体库 / Font library](fonts/README.md)
- [贡献指南 / Contributing](CONTRIBUTING.md)

## 发布 / Release

Beta 版本从 `beta` 分支打签名 tag，GitHub Actions 会构建安装包并创建 prerelease。

Beta releases are tagged from `beta` with a signed tag. GitHub Actions builds the installer and creates a prerelease.

```bash
git tag -s v2.0.0-beta.1 -m "release: v2.0.0-beta.1"
git push origin beta v2.0.0-beta.1
```
