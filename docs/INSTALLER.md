# Windows Installer / Windows 安装器

`build_winui.ps1` creates the Windows setup executable.

`build_winui.ps1` 会生成 Windows 安装包。

## Artifacts / 产物

```text
dist/KindleEpubFixer.Setup.exe
dist/KindleEpubFixer-<version>-Setup.exe
```

The installer embeds:

安装包内置：

- WinUI desktop app.
- WinUI 桌面程序。
- Python backend executable.
- Python 后端可执行文件。
- Bundled `fonts/` resources.
- 仓库内置 `fonts/` 字体资源。
- App assets and runtime files.
- 应用资源和运行时文件。

## Behavior / 行为

- Per-user installer, defaulting to `%LocalAppData%\Programs\Kindle EPUB Fixer`.
- 当前是用户级安装器，默认安装到 `%LocalAppData%\Programs\Kindle EPUB Fixer`。
- Uses `asInvoker`, so the default path does not require administrator rights.
- 使用 `asInvoker`，默认路径不需要管理员权限。
- Supports custom install folders, overwrite update, Start menu shortcut, optional desktop shortcut, and uninstall.
- 支持自定义目录、覆盖更新、开始菜单快捷方式、可选桌面快捷方式和卸载。
- App settings and user fonts live under `%LocalAppData%\KindleEpubFixer`.
- 应用设置和用户字体保存在 `%LocalAppData%\KindleEpubFixer`。

## Build / 构建

```powershell
powershell -ExecutionPolicy Bypass -File build_winui.ps1
```

If the machine has no .NET SDK:

如果本机没有 .NET SDK：

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_dotnet_sdk.ps1
```

## Silent Switches / 静默参数

```powershell
dist\KindleEpubFixer.Setup.exe /install /quiet /dir "C:\Path\Kindle EPUB Fixer" /no-start-menu
"C:\Path\Kindle EPUB Fixer\Uninstall.exe" /uninstall /quiet /keep-user-data
```

## Release / 发布

Signed beta tags trigger GitHub Actions. The workflow builds the installer on Windows and uploads both setup executables to a GitHub prerelease.

签名 beta tag 会触发 GitHub Actions，在 Windows runner 上构建安装包，并把两个安装器上传到 GitHub prerelease。
