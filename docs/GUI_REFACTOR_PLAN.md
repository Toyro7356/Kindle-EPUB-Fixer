# GUI Refactor Plan

This document defines the direction for the native GUI after `1.4.0-beta.2`.
The goal is to keep the application small, native, maintainable, and ready for
a future macOS frontend without diluting the Windows experience.

## Goals

- Keep EPUB repair logic in the Python backend.
- Keep each desktop frontend native to its platform.
- Use a stable JSON-lines backend protocol as the shared boundary.
- Prefer declarative UI and small view code-behind files.
- Follow WinUI 3 conventions on Windows: Mica, NavigationView, CommandBar,
  InfoBar notifications, ContentDialog only for forms that require user input,
  theme resources, and accessible keyboard focus.
- Keep installer, update, and uninstall behavior predictable.

## Boundaries

### Backend Core

Owned by `src/`.

- EPUB unpacking, analysis, repair, validation, and logging.
- Machine-readable events emitted by `src/backend_cli.py`.
- No Windows UI concepts, shell paths, or WinUI-specific strings.

### Windows Frontend

Owned by `native/KindleEpubFixer.WinUI/`.

- WinUI 3 shell, navigation, notifications, input dialogs, file/folder pickers, launchers.
- Windows material treatment such as Mica and acrylic fallback surfaces.
- Per-user settings under `%LocalAppData%\KindleEpubFixer`.
- Windows installer integration.

### Future macOS Frontend

Expected future root: `native/KindleEpubFixer.Mac/`.

- Native macOS UI using SwiftUI/AppKit conventions.
- macOS-specific settings, file importer/exporter, app bundle, and installer.
- Reuse only the backend CLI protocol and shared product concepts, not WinUI
  controls, visual resources, or Windows shell assumptions.

## Windows Architecture Direction

### Shell

- `MainWindow` owns only the app frame: backdrop, NavigationView, title/status,
  minimum size, page navigation, and crash guard hooks.
- Pages own their own local workflows.
- Visual resources should move out of `App.xaml` into focused dictionaries once
  the surface stabilizes.

### Pages

- Prefer XAML for layout.
- Code-behind should be limited to WinUI API calls that are awkward to bind:
  file pickers, ContentDialog, Flyout placement, and shell launching.
- Shared task state should live in small observable models or view models.

### Backend Integration

- `BackendRunner` remains the Windows process bridge.
- The backend protocol should stay JSON-lines and event-based:
  `version`, `progress`, `log`, `done`, `error`.
- Future frontends should be able to implement their own runner without touching
  Python repair logic.

### Packaging

- Keep the installer per-user and reversible.
- Keep the installer payload explicit: bundled WinUI output, backend, fonts,
  and assets.
- Smoke tests should cover install, overwrite install, launch-critical files,
  uninstall, and optional user-data preservation.

## Refactor Phases

1. Move the Home page from programmatic control construction to XAML.
2. Split task state and workflow orchestration away from UI surface code.
3. Move the main window shell from programmatic construction to XAML.
4. Normalize styles/resources around WinUI theme resources instead of ad hoc
   per-control brushes.
5. Reduce `MainWindow` to a thin native shell and move reusable helpers into
   services.
6. Add focused installer/package smoke scripts so release packaging is tested
   without manual clicking.
7. Freeze the backend CLI contract before starting macOS work.

## Current First Step

`Views/HomePage.xaml` now owns the Home layout. `HomePage.xaml.cs` keeps the
existing workflow but is much smaller and limited to picker/dialog/task-runner
logic. `ViewModels/HomePageViewModel.cs` owns task list state and selection
summary.

`MainWindow.xaml` now owns the WinUI shell structure: NavigationView, title
area, status text, notification host, and content host. `MainWindow.xaml.cs`
keeps native window behavior such as Mica, navigation, minimum size enforcement,
app-wide notifications, and icon setup.

The current notification rule is:

- Use compact `InfoBar` notifications for success, warning, and short status
  messages.
- Use `ContentDialog` only when the user must enter or confirm structured data.
- Keep task logs in per-row flyouts instead of global blocking dialogs.
