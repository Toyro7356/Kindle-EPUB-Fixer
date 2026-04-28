# Windows installer

`build_winui.ps1` builds two distribution artifacts:

- `dist/KindleEpubFixer.Setup.exe`
- `dist/KindleEpubFixer-<version>-Setup.exe`
- `dist/KindleEpubFixer.Portable.zip`
- `dist/KindleEpubFixer-<version>-Portable.zip`

The setup executable embeds the full WinUI runtime folder, the Python backend executable,
and the bundled `fonts/` directory. It installs files to a user-selected folder and writes
a standard per-user uninstall entry under:

`HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\KindleEpubFixer`

## Behavior

- Custom install directory is supported.
- Re-running the installer over the same directory performs an overwrite update.
- Existing app processes running from the target directory are closed before replacement.
- `Uninstall.exe` is copied into the install directory.
- Uninstall removes installed files, Start menu/Desktop shortcuts, the uninstall registry entry, and `%LocalAppData%\KindleEpubFixer`.
- User-added fonts and app settings are stored under `%LocalAppData%\KindleEpubFixer`, so normal uninstall removes them too.

## Test switches

These switches are mainly for smoke tests and automation:

```powershell
dist\KindleEpubFixer.Setup.exe /install /quiet /dir "C:\Path\Kindle EPUB Fixer" /no-start-menu
"C:\Path\Kindle EPUB Fixer\Uninstall.exe" /uninstall /quiet /keep-user-data
```
