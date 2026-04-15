# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/zh-CN/).

Version numbering rules:
- Bug fix patches: `1.0.x`
- Minor feature upgrades: `1.x.0`
- Major rewrites: `2.0.0`

---

## [1.0.0] - 2026-04-15

### Added
- Automatic comic / novel detection based on `rendition:layout` and SVG page ratio.
- WebP to JPG/PNG conversion with automatic reference updates in OPF, HTML, and CSS.
- SVG-to-`<img>` conversion for novels to prevent Kindle Enhanced Typesetting crashes.
- Kindle Pop-up Footnote restructuring (removes duokan-style back-links).
- Illegal self-closing tag repair (`<p/>`, `<div/>`, etc.) and DOCTYPE injection.
- Font compatibility pipeline:
  - Detects missing embedded fonts against Kindle built-in font whitelist.
  - Prompts user to import missing fonts.
  - Converts WOFF/WOFF2 to TTF/OTF.
  - Subsets embedded fonts to reduce file size.
- Vertical writing mode fix: downgrades `vertical-rl` to `horizontal-lr` for non-Japanese books.
- Spine direction fix: changes `page-progression-direction="rtl"` to `"ltr"` for non-Japanese novels.
- Script removal for novels: strips `<script>` tags and JavaScript manifest entries.
- GUI with HiDPI support, drag-and-drop file import, Win11 native styling, and responsive layout.

### Fixed
- Comic pages no longer get incorrectly identified as novels when they contain many SVG illustrations.
- Novel pages with SVG illustrations no longer retain stale `properties="svg"` in the manifest after conversion.
- Fixed Previewer `internal error` caused by missing `<!DOCTYPE html>` and illegal self-closing tags.
