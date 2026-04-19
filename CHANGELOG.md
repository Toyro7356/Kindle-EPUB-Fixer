# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project follows [Semantic Versioning](https://semver.org/).

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
