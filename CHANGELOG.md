# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.4.0-beta.2] - 2026-04-29

### Changed
- Refined the WinUI shell to use a native `NavigationView` compact rail without the earlier custom expandable sidebar patches.
- Unified the title bar, navigation rail, and content surface around the same Mica tint so the window no longer shows mismatched bands of color.
- Moved the Home page layout to XAML and split task list state into `HomePageViewModel`, reducing the old programmatic UI code.
- Changed informational app dialogs into compact non-blocking WinUI notifications with automatic dismissal and a close button.
- Removed double-click log access and simplified per-book log access to a compact icon button.
- Removed portable package generation and kept the Windows release output focused on normal installer artifacts only.

### Added
- Added resizable book list columns with pointer feedback and smaller minimum column widths.
- Added a fixed right-side action column for the per-book log button so resizing other columns no longer gets blocked by the action area.
- Added persistent default output directory handling that survives app restart and refreshes the Home page after Settings changes.
- Added a dedicated installer manifest with `asInvoker` execution level and `PerMonitorV2` DPI awareness.
- Added installer file version metadata, product metadata, description, company, and informational version details.
- Added `docs/GUI_REFACTOR_PLAN.md` to document the Windows native GUI boundary and the future macOS frontend boundary.

### Fixed
- Fixed several narrow-window layout issues by enforcing the intended minimum window size and letting the task list area shrink instead of the entire page.
- Fixed column resize edge cases around the status column.
- Fixed the default output directory not being remembered after closing and reopening the app.
- Fixed Windows installer UAC prompts caused by installer detection by explicitly declaring `asInvoker`.
- Fixed installer UI scaling metadata for HiDPI displays.

### Verified
- Verified WinUI Release build.
- Verified installer package manifest strings include `asInvoker`, `requestedExecutionLevel`, `PerMonitorV2`, and `dpiAwareness`.
- Verified installer smoke flow: install, required runtime/XBF/PRI payload presence, app launch, quiet uninstall, and install directory cleanup.

## [1.4.0-beta.1] - 2026-04-28

### Changed
- Rebuilt the GUI as a native WinUI 3 / Windows App SDK frontend instead of a Python GUI.
- Reworked the GUI toward a PowerToys-like layout with `NavigationView`, Mica backdrop, Home / Settings / About pages, rounded cards, and modern command bars.
- Upgraded the native frontend target framework to `.NET 10`.
- Made the WinUI root and NavigationView backgrounds transparent enough for the Mica backdrop to show through.
- Reworked EPUB import into a table-style task queue with selectable rows, compact columns, per-book status, and hover log access.
- Replaced the global inline log panel with per-book log flyouts opened near the book title.
- Switched GUI text to `Microsoft YaHei UI` for better Chinese rendering.
- Replaced the previous self-extracting single EXE experiment with a proper installer.
- Removed the old Python GUI entry point and legacy Python GUI packaging path.

### Added
- Added a Settings page for default output directory, user font import, and editable font fallback aliases.
- Added an About page with version, purpose, and bundled font information.
- Added a JSON-lines Python backend entry point for native UI progress and log integration.
- Added native WinUI build scripts and a local .NET SDK installer script.
- Added a Windows installer that supports custom install directories, overwrite updates, Start menu/Desktop shortcuts, and complete uninstall.
- Added versioned release artifacts for the installer and portable ZIP.
- Added installer documentation in `docs/INSTALLER.md`.

### Fixed
- Fixed overlapping command buttons in the Home toolbar.
- Fixed selected-count drift by explicitly syncing task checkbox state before refreshing the summary.
- Fixed WinUI NavigationView pane background/corner artifacts around the Mica layout.
- Fixed log access becoming hard to click by keeping the hover log button hit-testable.
- Fixed backend font discovery so the native GUI can pass both user font directories and bundled font directories to the Python repair backend.
- Fixed installer packaging so app XBF/PRI resources are included alongside the self-contained WinUI publish output.

### Verified
- Verified Python compile checks for the current `src` backend.
- Verified WinUI Release build.
- Verified installer smoke flow: install, overwrite update, bundled backend/font presence, uninstall directory cleanup, and uninstall registry cleanup.

## [1.3.1-beta.2] - 2026-04-19

### Changed
- Changed the single-file Windows build to bundle the whole `fonts/` directory into the EXE.
- Changed frozen runtime asset lookup so the app now reads bundled fonts and font settings from PyInstaller's extracted resource directory, while still allowing external `fonts/` files next to the EXE to override them.

### Fixed
- Fixed the previous `1.3.1-beta.1` packaging gap where bundled `朱雀仿宋` existed in source form but was not actually available inside the one-file EXE.

### Verified
- Verified frozen-mode asset lookup with a simulated `_MEIPASS` runtime path.
- Rebuilt `dist/Kindle EPUB Fixer.exe` as `1.3.1-beta.2`.

## [1.3.1-beta.1] - 2026-04-19

### Added
- Added bundled `Zhuque Fangsong v0.212` under `fonts/common/` as the default open-source fallback for Fangsong-style aliases.
- Added bundled font licensing notes for Zhuque under `fonts/common/LICENSE.zhuque.txt`.

### Changed
- Simplified font handling to a single Kindle-first fallback strategy instead of maintaining multiple profile modes.
- Changed Fangsong-style aliases such as `fangsong`, `fang-song`, `dk-fangsong`, `华文仿宋`, and `方正仿宋` to prefer the bundled Zhuque fallback before system fonts.
- Changed `dk-xiaobiaosong` to resolve as a Song/serif-style fallback instead of importing a system decorative Song variant.
- Changed `youyuan`, `kai`, and `dfkai-sb` handling to prefer Kindle-style `STYuan` / `STKai` chains where possible.
- Moved language metadata repair into the always-safe repair stage so preserve-layout books also get corrected `dc:language` and XHTML `lang/xml:lang`.
- Tightened Kindle builtin font recognition so Windows/system CJK font names are no longer treated as guaranteed Kindle builtins.

### Fixed
- Fixed a fallback ordering issue where bundled Zhuque Fangsong could be skipped by earlier system font matches.
- Fixed the preserve-layout path so books no longer miss language-based Kindle font bucket correction.
- Fixed `ssa` and `sthupo` resolution to import their concrete system fonts deterministically instead of relying on fuzzy matching.

### Verified
- Verified Python compile checks for `main.py`, `main_gui.py`, and the updated `src` modules.
- Verified the current sample set font plan after the Kindle-first refactor: `58` builtin/generic fallbacks, `5` imported fonts, `0` unresolved.
- Verified key mappings on the sample set, including `dk-xiaobiaosong -> serif/STSong`, `youyuan -> STYuan`, `dfkai-sb -> STKai`, and Fangsong aliases importing bundled Zhuque.

## [1.3.0] - 2026-04-19

### Added
- Added `docs/PROCESS_FLOW.md` to document the repair pipeline, branch heuristics, and conservative boundaries.
- Added `src/content_analysis.py` and `src/opf_metadata.py` to centralize content heuristics and metadata inference.
- Added `tools/previewer_audit.py` for resumable full-sample Kindle Previewer auditing.

### Changed
- Reworked the repair pipeline around `BookProfile + ProcessingPlan` so the tool decides repair strength from content structure instead of source-only branching.
- Narrowed SVG page conversion so only simple single-image SVG wrapper pages are converted to `<img>`.
- Refined CSS transform sanitization to target only high-risk Kindle-breaking transforms on the reflow path.
- Changed footnote handling to be conservative by default: already-standard `noteref -> footnote` structures are left untouched, and only clearly non-standard structures are normalized.
- Removed the old `.processed`-style output suffix and kept the default GUI/CLI output under `转换后`.

### Fixed
- Fixed Kobo novel white-screen cases by keeping novel compatibility repairs active even when books are layout-sensitive.
- Fixed Previewer-breaking transform cases such as `吹响吧！上低音号 12` without disturbing preserve-layout books.
- Fixed preserve-layout comic metadata edge cases such as missing or invalid `original-resolution`.
- Fixed over-eager footnote rewriting that could introduce empty popup content, duplicate return marks, or visible inline note regressions on already-valid books.
- Fixed guide `toc` references so they point to readable targets instead of blindly targeting `toc.ncx`.

### Verified
- Verified internal structure auditing on the current sample set: `77/77` passed with `0` validation issues.
- Verified the full Kindle Previewer baseline on the core sample set: `69/69` processed successfully, `0` regressions, `0` processed errors.
- Verified the footnote-focused Previewer set after the conservative footnote fix: `4/4` processed successfully.

## [1.3.0-beta.2] - 2026-04-18

### Added
- Added `tools/previewer_audit.py` for resumable full-sample Kindle Previewer auditing.
- Added `src/content_analysis.py` and `src/opf_metadata.py` to centralize content heuristics and metadata inference.
- Added `docs/PROCESS_FLOW.md` documenting the repair pipeline, branch rules, and conservative boundaries.

### Changed
- Narrowed SVG page conversion so only simple single-image SVG wrapper pages are converted to `<img>`.
- Refined CSS transform sanitization to target high-risk Kindle-breaking transforms in reflow mode instead of broadly stripping all transforms.
- Made guide `toc` references resolve to readable content targets instead of blindly pointing at `toc.ncx`.
- Moved `analyze_epubs_v2.py` report output into `build/` and removed obsolete one-off debug scripts and checked-in generated reports from `tools/`.

### Fixed
- Fixed `吹响吧！上低音号 12` by downgrading Kindle-breaking rotate transforms on the reflow path without touching preserve-layout books.
- Fixed `葬送的芙莉莲 11` by conservatively repairing invalid or missing `original-resolution` metadata for preserve-layout comics.
- Fixed footnote normalization edge cases caused by nested backlink wrappers and Duokan-style note containers.
- Fixed a Previewer regression source where preserve-layout comics could lose ET support after over-eager metadata injection.
- Verified a clean full-sample run: 69/69 processed EPUBs succeed in Kindle Previewer, with 0 regressions and 0 processed errors.

## [1.3.0-beta.1] - 2026-04-17

### Added
- Added `book_profile` based layout analysis for more conservative automatic repair decisions.
- Added `text_io` helpers for BOM-aware and declared-encoding-aware text reading.
- Added `css_sanitize` for generic Kindle-safe transform downgrades in reflow mode.
- Added `tools/audit_samples.py` for batch sample verification.
- Added `tools/previewer_compare.py` for Kindle Previewer original-vs-processed comparisons.

### Changed
- Reworked the repair pipeline so structure repair happens before later content cleanup.
- Unified processing around the `src` pipeline and removed the old duplicated entry under `code/process_epub.py`.
- Changed the default output directory to `转换后`.
- Removed the `.processed` style output suffix.
- Rewrote README, changelog, and GUI copy to remove mojibake and reflect the current repair strategy.

### Fixed
- Fixed malformed XHTML cases with broken closing tags and unsafe entities.
- Fixed text decoding issues on non-UTF-8 EPUB resources.
- Fixed a class of Kindle Previewer internal errors caused by risky CSS transforms in reflowable books.
- Verified `OVERLOAD 05` now converts from `Not Supported + Error` to `Supported + Success` in Kindle Previewer after processing.
- Preserved successful processing for validated samples including `义妹生活 03` and `葬送的芙莉莲 07`.

## [1.1.0] - 2026-04-15

### Added
- Added automatic language detection and metadata repair.
- Added comic fixed-layout metadata normalization.
- Added post-process EPUB validation.
- Added EPUB diff tooling for auditing changes.

### Changed
- Improved font handling and missing-font import flow.
- Reworked drag-and-drop implementation around `tkinterdnd2`.

### Fixed
- Fixed several runtime and compatibility issues in the earlier GUI and image pipeline.

## [1.0.0] - 2026-04-15

### Added
- Initial Kindle-focused EPUB repair pipeline with WebP conversion, SVG page conversion, HTML structure repair, font handling, script removal, and GUI support.
