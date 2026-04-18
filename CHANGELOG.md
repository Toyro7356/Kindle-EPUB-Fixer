# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project follows [Semantic Versioning](https://semver.org/).

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
- Fixed `葬送的芙莉蓮 11` by conservatively repairing invalid or missing `original-resolution` metadata for preserve-layout comics.
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
- Preserved successful processing for validated samples including `义妹生活 03` and `葬送的芙莉蓮 07`.

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
