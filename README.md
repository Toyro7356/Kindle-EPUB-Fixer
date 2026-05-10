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
  - 支持通过设置页配置私有字体别名，用户字体保存在 `%LocalAppData%\KindleEpubFixer\fonts`
  - 默认内置 `朱雀仿宋 v0.212` 作为仿宋类字体优先回退
  - Windows 安装器内置 `fonts/` 资源，无需额外复制字体目录
- 脚注/角注保守修复
  - 已经符合标准 `noteref -> footnote` 结构的脚注默认不改写
  - 只对明显非标准、嵌套异常或 Duokan 风格容器做保守归一
- Kindle 友好清理
  - 移除已知会干扰 Kindle 的脚本残留
  - 清理过期 SVG 标记
  - 修复 NCX 导航层级
- 输出结构校验
  - 检查处理后 EPUB 中的 XHTML、manifest、spine、图片引用和基础元数据是否仍然有效
- ESJZone 网页转制
  - 从 ESJZone 详情页自动获取书籍信息、目录、正文与正文图片并生成 EPUB
  - 默认使用 `https://www.esjzone.cc/`，同时兼容旧的 `https://www.esjzone.one/` 详情页
  - 支持弹出网页登录并自动读取 Cookie，也可以手动粘贴和选择记住 Cookie
  - 章节范围留空时默认抓取全部章节，可输入 `10` 或 `1-10` 做小范围测试
  - 目录只写入可点击章节，自动跳过 ESJZone 详情页里不可点击的分卷标题
  - ESJZone 作为书源读取器输出统一小说对象，再交给独立 EPUB 转换管线
  - 转换管线直接生成 Kindle 友好的 EPUB，并对输出结构做校验

## 1.4.0 正式版重点

- 修复缺失字体清理逻辑，避免相邻的单行 `@font-face` 被一起删除，保留原 EPUB 自带的标题、目录、制作信息和强调段落字体
- 确认仿宋类缺失字体会自动补全为内置 `朱雀仿宋`，并清理旧的坏 `@font-face` 引用，避免输出后继续出现断开的字体资源
- 兼容内部 ZIP 路径含 Windows 非法字符的 EPUB，解包时安全重命名并同步修正文档、样式、OPF、NCX 等引用
- 修复 WebP 转换后同名资源碰撞导致的图片丢失，图片、字体引用现在按完整相对路径重写
- 清理过期 `META-INF/encryption.xml`，避免无实际加密资源的 EPUB 在阅读器里被误判为 DRM
- 兼容 Python 3.14 环境下临时目录不可写的问题，处理 EPUB 时改用项目可控的临时工作目录创建方式
- 本地构建脚本改为使用仓库内 `.dotnet`、NuGet 缓存和 CLI home，减少对用户目录权限与全局环境的依赖

## 1.4.0-beta.2 重点

- 继续收敛原生 WinUI 3 / Windows App SDK 前端，恢复到更标准的 `NavigationView` 架构
- 统一 Mica 背景取色，清理标题栏、导航栏和内容区色块不一致的问题
- 任务列表支持可调列宽、固定右侧日志操作列和更小的最小列宽
- 默认保存位置会持久化到 `%LocalAppData%\KindleEpubFixer`，关闭软件再打开仍会记住
- 普通提示改为右上角小通知，几秒后自动消失，也可手动关闭
- Windows 安装器只输出正常安装版，支持自定义目录、覆盖更新、完整卸载、HiDPI 和非管理员安装
- 安装包补全文件详细信息，包含产品名、描述、版本和发布信息

## 1.4.0-beta.1 重点

- 原生 WinUI 3 / Windows App SDK 前端替代旧 Python GUI
- 新增安装器 `KindleEpubFixer.Setup.exe`，支持自定义目录、覆盖更新和完整卸载
- 新增设置页、关于页、默认输出目录、用户字体导入与字体回落别名编辑
- 任务列表改为表格/队列式交互，支持选择、删除、单本状态和日志查看
- 内置字体库随安装器分发，后端同时扫描用户字体目录和内置字体目录

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

### Native WinUI 3 GUI

```bash
powershell -ExecutionPolicy Bypass -File build_winui.ps1
```

构建后会生成：

```text
dist/KindleEpubFixer.Setup.exe
dist/KindleEpubFixer-<version>-Setup.exe
```

如果本机没有 .NET SDK，先安装到项目本地：

```bash
powershell -ExecutionPolicy Bypass -File tools/install_dotnet_sdk.ps1
```

GUI 现已改为原生 WinUI 3 / Windows App SDK 前端；Python 只作为 EPUB 修复后端。

支持：
- 批量添加 EPUB
- PowerToys / Windows 11 风格的 `NavigationView` 页面结构
- 表格式任务队列、单本选择、单本进度、可调列宽与单本日志
- 设置默认输出目录
- 管理字体库与字体回落别名
- 从 ESJZone 详情页转制 EPUB
- 查看版本、内置字体与项目说明

### 命令行

```bash
python main.py "input.epub"
python main.py "input.epub" "output.epub"
python main.py esjzone "https://www.esjzone.cc/detail/xxxx.html" "output.epub"
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

## Native WinUI 打包

```bash
powershell -ExecutionPolicy Bypass -File build_winui.ps1
```

默认输出：

```text
dist/KindleEpubFixer.Setup.exe
```

安装器说明见 [docs/INSTALLER.md](docs/INSTALLER.md)。

## 项目结构

```text
.
├─ native/
│  └─ KindleEpubFixer.WinUI/
│     ├─ MainWindow.xaml
│     ├─ Views/
│     ├─ Models/
│     └─ Services/
├─ src/
│  ├─ core.py
│  ├─ backend_cli.py
│  ├─ book_profile.py
│  ├─ css_sanitize.py
│  ├─ text_io.py
│  ├─ epub_validator.py
│  └─ ...
├─ tools/
│  ├─ audit_samples.py
│  ├─ previewer_compare.py
│  ├─ previewer_audit.py
│  └─ install_dotnet_sdk.ps1
├─ 测试文件/
├─ docs/
├─ main.py
├─ main_backend.py
├─ build_backend.py
├─ build_winui.ps1
├─ README.md
└─ CHANGELOG.md
```
