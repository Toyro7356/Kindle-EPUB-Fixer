# Kindle EPUB Fixer

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

面向 Kindle / Send to Kindle 的 EPUB 修复工具。

这个项目的目标不是把所有 EPUB 强行改成统一模板，而是在尽可能保留作者原始排版、字体和结构意图的前提下，修复 Kindle 明显不兼容、容易白屏、图片丢失、Previewer 报错或 EPUB 结构损坏的问题。

处理流程、分支判断依据与设计边界见 [docs/PROCESS_FLOW.md](docs/PROCESS_FLOW.md)。

当前验证结果：
- 内部结构审计 `77/77` 通过，`0` 校验问题
- Kindle Previewer 核心样本全量验证 `69/69` 处理成功，`0` 回归，`0` 处理后错误
- 角注专项 Previewer 验证 `4/4` 处理成功

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
  - 当前主要处理 `rotate`、`matrix`、`skew`、`perspective` 和 3D transform，不碰 `preserve-layout` 书籍
- SVG 插图页兼容修复
  - 只将“单图壳子”式 SVG 页面转换为标准 `<img>`
  - 不主动改写复杂 SVG、文字叠层或版式型 SVG 页面
- 字体兼容处理
  - 检测缺失字体
  - 支持用户补充本地字体
  - 优先回退到 Kindle 可识别字体，再在必要时导入字体
  - 处理字体格式兼容与缺失回退
  - 支持通过 `fonts/font-settings.json` 配置私有字体别名
  - 默认内置 `朱雀仿宋 v0.212` 作为仿宋类字体优先回退
  - 单文件 Windows EXE 现已内置 `fonts/` 资源，无需额外复制字体目录
- 脚注/角注保守修复
  - 已经符合标准 `noteref -> footnote` 结构的脚注默认不改写
  - 只对明显非标准、嵌套异常或 Duokan 风格容器做保守归一
- Kindle 友好清理
  - 移除已知会干扰 Kindle 的脚本残留
  - 清理过期 SVG 标记
  - 修复 NCX 导航层级
- 输出结构校验
  - 检查处理后 EPUB 中的 XHTML、manifest、spine、图片引用和基础元数据是否仍然有效

## 1.3 正式版重点

- 引入 `BookProfile + ProcessingPlan` 自动分支，替代来源硬编码
- 主处理流程重构为“先结构修复，再按内容类型选择修复强度”
- 新增 `text_io`，提升非 UTF-8 EPUB 的读取稳定性
- 新增 `css_sanitize`，把 Previewer 高风险 transform 收敛为通用修复
- 新增 `previewer_audit`，支持可恢复的全量 Previewer 审计
- 修复 `吹响吧！上低音号 12` 这类由旋转排版触发的 Previewer 错误
- 修复 preserve-layout 漫画缺失 `original-resolution` 时的转换失败
- 去掉输出文件名中的 `.processed` 后缀
- 脚注策略改为“标准结构不动、异常结构再修”，避免空弹窗、额外回链和正文注入回归

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

批量结构审计：

```bash
python tools/audit_samples.py --report build/audit-report.json --output-dir build/audit-output
```

Kindle Previewer 对比验证：

```bash
python tools/previewer_compare.py "测试文件\\自制epub\\OVERLOAD 05.epub" --keep-workdir build\\previewer-debug
```

Kindle Previewer 全量审计：

```bash
python tools/previewer_audit.py --report build/previewer-audit.json --workdir build/previewer-audit --timeout-seconds 1200
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
│  ├─ previewer_compare.py
│  ├─ previewer_audit.py
│  └─ analyze_epubs_v2.py
├─ 测试文件/
├─ docs/
├─ main.py
├─ main_gui.py
├─ build_exe.py
├─ README.md
└─ CHANGELOG.md
```
