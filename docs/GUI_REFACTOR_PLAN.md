# GUI Architecture / GUI 架构

The desktop app is a native WinUI 3 frontend over a Python EPUB backend.

桌面端是原生 WinUI 3 前端，核心 EPUB 处理由 Python 后端提供。

## Goals / 目标

- Keep repair and conversion logic in `src/`.
- 修复和转制逻辑保留在 `src/`。
- Keep Windows UI code in `native/KindleEpubFixer.WinUI/`.
- Windows UI 代码集中在 `native/KindleEpubFixer.WinUI/`。
- Keep the backend protocol JSON-lines based and frontend-neutral.
- 后端协议保持 JSON-lines，避免绑定具体前端。
- Prefer simple XAML layouts with small code-behind files.
- 优先使用 XAML 布局，让 code-behind 保持小而清晰。

## Boundaries / 边界

### Backend / 后端

- EPUB unpacking, analysis, repair, validation, and web novel conversion.
- EPUB 解包、分析、修复、校验和网页小说转制。
- Emits events such as `version`, `progress`, `log`, `done`, and `error`.
- 输出 `version`、`progress`、`log`、`done`、`error` 等事件。
- No WinUI controls, Windows shell assumptions, or UI layout decisions.
- 不包含 WinUI 控件、Windows Shell 假设或界面布局决策。

### WinUI Frontend / WinUI 前端

- Navigation, file pickers, folder pickers, dialogs, notifications, and settings.
- 负责导航、文件选择、目录选择、弹窗、通知和设置。
- Runs the backend process and renders JSON-lines events.
- 启动后端进程并渲染 JSON-lines 事件。
- Stores per-user settings under `%LocalAppData%\KindleEpubFixer`.
- 用户设置保存在 `%LocalAppData%\KindleEpubFixer`。

## Current Pages / 当前页面

- Home: batch EPUB repair.
- 主页：批量 EPUB 修复。
- ESJZone: web login, Cookie handling, chapter range selection, and EPUB generation.
- ESJZone：网页登录、Cookie、章节范围和 EPUB 生成。
- Settings: output directory and font library settings.
- 设置：输出目录和字体库。
- About: version and project information.
- 关于：版本和项目信息。

## Future Work / 后续方向

- Keep shared workflows in services instead of page code-behind.
- 共享流程沉到 service，避免页面代码膨胀。
- Keep future macOS or other frontends on the same backend protocol.
- 后续 macOS 或其他前端复用同一后端协议。
- Add small release smoke scripts only where they reduce manual packaging risk.
- 只在能减少发布风险时增加小型发布检查脚本。
