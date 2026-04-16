# Kindle EPUB Fixer

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

智能修复 EPUB 文件，提升 Amazon Kindle / Send to Kindle 兼容性。

---

## 功能特性

- **漫画 & 小说自动识别**
  - 漫画：保留 SVG 页面、Fixed-Layout、Panel View、双页展开
  - 小说：启用 Enhanced Typesetting（字体调整、布局调整、Pop-up 脚注）

- **WebP 转 Kindle 兼容格式**
  - 自动将 `.webp` 转为 `.jpg/.png`
  - 同步更新 OPF、HTML、CSS 中的所有引用

- **修复 HTML 结构缺陷**
  - 补全 `<!DOCTYPE html>`
  - 修复非法自闭合标签（`<p/>`、`<div/>` 等）
  - 解决 Kindle Previewer `internal error`

- **SVG 插图页安全转换（仅小说）**
  - 将 SVG 包装的图片页转为标准 `<img>`
  - 自动清理 manifest 中过时的 `properties="svg"` 声明
  - 避免 Kindle ET 因声明与实际内容不一致而崩溃

- **恢复 Kindle Pop-up 脚注**
  - 将多看/自制 EPUB 的 `ol/li` 脚注结构转为 Kindle 原生弹窗注释

- **字体兼容性处理**
  - 检测缺失字体并与 Kindle 内置字体白名单比对
  - 支持用户导入缺失字体
  - 自动将 WOFF/WOFF2 转为 TTF/OTF
  - 对大于 50KB 的字体进行子集化，仅保留实际使用的字符

- **竖排兼容修正（非日文）**
  - 将 CSS 和 XHTML 中的 `vertical-rl` 降级为 `horizontal-lr`
  - 对非日文小说，将 `page-progression-direction="rtl"` 修正为 `"ltr"`

---

## 使用方式

### GUI 模式（推荐）

双击 `Kindle EPUB Fixer.exe`，或通过 Python 启动：

```bash
python main_gui.py
```

界面支持：
- **多文件批量处理**
- **拖拽导入**：直接将 EPUB 文件拖入文件列表区域
- **缺失字体提示**：自动检测并询问是否导入本地字体
- **实时日志**：处理过程实时显示，支持复制

操作步骤：
1. 点击 **添加 EPUB 文件** 或将文件拖入列表（支持多选）。
2. （可选）指定 **输出目录**，默认与输入文件同目录。
3. 点击 **开始处理**。

### 命令行模式

```bash
python main.py "input.epub"
# 默认生成 input.processed.epub

python main.py "input.epub" "output.epub"
```

---

## 项目结构

```
.
├── src/
│   ├── __init__.py          # 包入口
│   ├── __version__.py       # 版本信息
│   ├── gui.py               # Tkinter GUI（HiDPI / 拖拽 / Win11 风格 / 取消任务）
│   ├── core.py              # 主调度入口
│   ├── epub_io.py           # EPUB 解包/打包/OPF 定位
│   ├── book_type.py         # 漫画/小说自动识别
│   ├── image_fix.py         # WebP 转换
│   ├── svg_fix.py           # SVG 插图页处理
│   ├── html_fix.py          # HTML 结构修复
│   ├── footnote_fix.py      # Pop-up 脚注转换
│   ├── opf_sanitize.py      # OPF 元数据清理
│   ├── font_handler.py      # 字体检测/导入/转换/子集化/回退
│   ├── vertical_fix.py      # 竖排降级处理
│   ├── script_remove.py     # 脚本清理
│   ├── language_fix.py      # 自动语言检测与修正
│   ├── comic_fix.py         # 漫画固定布局元数据注入
│   ├── css_sanitize.py      # 清理 Kindle 不支持的 CSS 属性
│   ├── epub_validator.py    # 后处理结构验证
│   ├── constants.py         # XML 命名空间常量
│   └── utils.py             # 通用工具函数
├── tools/
│   └── diff_epub.py         # 原始 vs 处理后 EPUB 差异审计
├── main.py                  # CLI 入口
├── main_gui.py              # GUI 入口
├── build_exe.py             # PyInstaller 打包脚本
├── requirements.txt
├── CHANGELOG.md
├── README.md
└── LICENSE
```

---

## 打包 EXE

安装依赖：

```bash
pip install -r requirements.txt
```

运行打包脚本：

```bash
python build_exe.py
```

打包完成后，`dist/Kindle EPUB Fixer.exe` 即为单文件可执行程序。

---

## 常见问题（FAQ）

### Q: 为什么处理后排版从竖排变成了横排？
A: Kindle 对非日文书籍不支持 `vertical-rl`。程序会自动将竖排降级为横排，否则 Kindle Previewer 会直接报错拒绝转换。

### Q: 为什么小说里的彩色插图页被转换了？
A: 某些小说的插图页使用 `<svg>` 包装图片。Kindle 的 Enhanced Typesetting（ET）在 reflowable 模式下对 SVG 支持有限，容易导致白屏或崩溃。程序会将这些页面安全地转换为 `<img>`，同时清理 manifest 中的过时声明。

### Q: Publisher Font / Page Flip 动画失效了怎么办？
A: 请确保原始 EPUB 中包含 `ibooks:specified-fonts=true` 元数据，并且没有被误识别为漫画。如果问题持续，请检查 Previewer 是否缓存了旧结果（建议重命名文件后再次测试）。

### Q: 漫画翻页不显示图片？
A: 如果原始漫画文件缺少 `rendition:layout=pre-paginated` 等 fixed-layout 元数据，Kindle 可能无法正确渲染。本程序**不会**自动补全这些元数据（因为贸然添加可能导致 rigid 模式分页错误），建议确认原始文件本身在 Kindle 上的兼容性。

---

## 依赖

- Python >= 3.10
- [Pillow](https://python-pillow.org/)
- [lxml](https://lxml.de/)
- [fonttools](https://fonttools.readthedocs.io/)
- [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2)（GUI 拖拽支持）
- [PyInstaller](https://pyinstaller.org/)（仅打包时需要）

---

## License

[MIT](LICENSE)
