# Windows installer

`build_winui.ps1` builds two installer artifacts:

- `dist/KindleEpubFixer.Setup.exe`
- `dist/KindleEpubFixer-<version>-Setup.exe`

The setup executable embeds the full WinUI runtime folder, the Python backend executable,
and the bundled `fonts/` directory. It installs files to a user-selected folder and writes
a standard per-user uninstall entry under:

`HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\KindleEpubFixer`

## Behavior

- The installer is per-user and declares `asInvoker`, so it does not require UAC elevation for the default install path.
- The installer manifest declares `PerMonitorV2` DPI awareness for HiDPI displays.
- The installer executable includes Windows file details: product name, description, company, file version, product version, and informational version.
- Custom install directory is supported.
- Re-running the installer over the same directory performs an overwrite update.
- Existing app processes running from the target directory are closed before replacement.
- `Uninstall.exe` is copied into the install directory.
- Uninstall removes installed files, Start menu/Desktop shortcuts, the uninstall registry entry, and `%LocalAppData%\KindleEpubFixer`.
- User-added fonts and app settings are stored under `%LocalAppData%\KindleEpubFixer`, so normal uninstall removes them too.
- No portable ZIP or portable launcher is produced.

## Release checklist

Before publishing a Windows release:

- Build with `powershell -ExecutionPolicy Bypass -File build_winui.ps1`.
- Confirm `dist/KindleEpubFixer.Setup.exe` and the versioned setup executable exist.
- Smoke-test quiet install, required payload files, app launch, quiet uninstall, and install directory cleanup.
- Confirm the setup manifest contains `requestedExecutionLevel`, `asInvoker`, `dpiAwareness`, and `PerMonitorV2`.
- Publish with a signed annotated tag so GitHub can show the verified tag indicator.

## Test switches

These switches are mainly for smoke tests and automation:

```powershell
dist\KindleEpubFixer.Setup.exe /install /quiet /dir "C:\Path\Kindle EPUB Fixer" /no-start-menu
"C:\Path\Kindle EPUB Fixer\Uninstall.exe" /uninstall /quiet /keep-user-data
```
