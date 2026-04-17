# Kindle EPUB Fixer

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

面向 Kindle / Send to Kindle 的 EPUB 修复工具。

这个项目的目标不是“把所有 EPUB 统一改成某种模板”，而是在尽可能保留作者原始排版意图的前提下，修复 Kindle 明显不兼容、容易白屏、图片丢失、Previewer 内部错误或结构损坏的问题。

## 设计原则

- 优先保留原书语义和布局意图
- 只修复 Kindle 明显不兼容或 EPUB 结构本身有问题的部分
- 对可重排小说和布局敏感书籍采用不同强度的处理
- 不依赖书籍来源硬编码，尽量通过内容特征自动识别
- 如果是 Kindle 先天不支持的能力，不强行伪造

## 主要能力

- 自动识别书籍轮廓
  - 判断是否为可重排、固定版式、漫画倾向、SVG 页面、视口页面、竖排或高图片占比内容
- 图片兼容修复
  - 将 Kindle 不支持的 WebP 转换为 JPG/PNG
  - 同步更新 OPF / HTML / CSS 中的引用
- HTML / XHTML 结构修复
  - 修复非法自闭合标签
  - 修复损坏的闭合标签
  - 清理不安全命名实体与裸 `&`
- CSS 风险降级
  - 仅对可重排内容降级 Kindle Previewer 明显容易失败的高风险变换
  - 当前包括 `matrix/skew/3d` 以及高风险 `rotate(90deg/270deg)`
- SVG 插图页兼容修复
  - 将 SVG 包裹的插图页转换为标准 `<img>`
- 字体兼容处理
  - 检测缺失字体
  - 支持用户补充本地字体
  - 处理字体格式兼容与缺失回退
- Kindle 友好清理
  - 移除已知会干扰 Kindle 的脚本残留
  - 清理过期 SVG 标记
  - 修复 NCX 导航层级
- 结构校验
  - 检查处理后 EPUB 中的 XHTML 是否仍然可被正常解析

## 1.3 预发布改进

- 引入 `book_profile` 自动分析书籍结构，替代简单来源分类
- 重构主处理流程，先做结构层修复，再决定是否进入重排兼容修复
- 新增 `text_io`，提升非 UTF-8 EPUB 的读取稳定性
- 新增 `css_sanitize`，把 Kindle Previewer 明显容易报错的变换抽成通用修复
- 修复 `OVERLOAD 05` 这类带四分之一旋转排版的精排小说
- 保持对 `义妹生活 03`、`葬送的芙莉蓮 07` 等样本的兼容结果
- GUI 默认输出到输入目录下的 `转换后`
- 去掉输出文件名中的 `.processed` 后缀

## 使用方法

### GUI

```bash
python main_gui.py
```

支持：

- 批量添加 EPUB
- 拖拽导入
- 统一指定输出目录
- 实时查看处理日志

### 命令行

```bash
python main.py "input.epub"
python main.py "input.epub" "output.epub"
```

如果不指定输出路径，默认输出到输入文件同目录下的 `转换后` 文件夹。

## 开发与验证

安装依赖：

```bash
pip install -r requirements.txt
```

样本批量审计：

```bash
python tools/audit_samples.py --clean-output
```

Kindle Previewer 对比验证：

```bash
python tools/previewer_compare.py "测试文件\\自制epub\\OVERLOAD 05.epub" --keep-workdir build\\previewer-debug
```

## 打包 EXE

```bash
python build_exe.py
```

默认输出：

```text
dist/Kindle EPUB Fixer.exe
```

## 项目结构

```text
.
├─ src/
│  ├─ core.py
│  ├─ gui.py
│  ├─ book_profile.py
│  ├─ css_sanitize.py
│  ├─ text_io.py
│  ├─ epub_validator.py
│  └─ ...
├─ tools/
│  ├─ audit_samples.py
│  └─ previewer_compare.py
├─ 测试文件/
├─ main.py
├─ main_gui.py
├─ build_exe.py
├─ README.md
└─ CHANGELOG.md
```
