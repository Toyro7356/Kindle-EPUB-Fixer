# Changelog / 更新日志

All notable changes are documented here.

本文件记录值得发布说明的变更，避免列出样本数量或内部验证流水账。

## [2.0.1] - 2026-05-10

### Fixed / 修复

- Fixed generated XHTML when source HTML contains browser-tolerated but XML-invalid attributes such as `width:`.
- 修复网页源码含有 `width:` 等浏览器可容忍、但 XML 不合法属性时生成的 XHTML 校验错误。
- Sanitized generated novel metadata, navigation, and body fragments for XML-invalid control characters.
- 清理生成小说 EPUB 的元数据、目录和正文片段中的 XML 非法控制字符。
- Dropped ESJZone images that still fail to download instead of leaving remote image references inside the EPUB.
- ESJZone 图片下载失败时不再把远程图片引用留在 EPUB 内部。

## [2.0.0] - 2026-05-10

### Added / 新增

- Added a shared web-novel source model and a standalone Kindle EPUB generation pipeline.
- 新增网页小说统一书源模型和独立 Kindle EPUB 生成管线。
- Added ESJZone conversion with web login Cookie capture, metadata parsing, chapter fetching, image handling, chapter ranges, and output validation.
- 新增 ESJZone 转制：网页登录 Cookie、书籍信息、目录、正文、图片、章节范围和输出校验。
- Added WinUI controls for ESJZone conversion, remembered Cookie storage, output directory selection, progress, and logs.
- 新增 WinUI ESJZone 页面，支持记住 Cookie、选择输出目录、进度和日志。
- Added GitHub Actions release automation for signed beta and stable tags.
- 新增签名 beta / 正式 tag 触发的 GitHub Actions 自动构建与上传。

### Changed / 调整

- Changed generated web-novel EPUBs to avoid the repair engine and emit Kindle-friendly EPUB directly.
- 网页小说转制改为直接生成 Kindle 友好 EPUB，不再依赖修复引擎二次处理。
- Changed the default ESJZone host to `https://www.esjzone.cc/` while keeping `.one` detail links supported.
- ESJZone 默认站点改为 `https://www.esjzone.cc/`，同时保留 `.one` 详情页兼容。
- Changed generated web-novel styling to use generic Kindle-friendly fonts: `sans-serif` body text and `serif` headings.
- 生成 EPUB 的字体策略改为 Kindle 友好的通用族：正文 `sans-serif`，标题 `serif`。
- Changed navigation generation to keep only clickable chapter entries and skip non-clickable volume headings.
- 目录只写入可点击章节，跳过网页上的不可点击分卷标题。
- Changed WebP and animated image assets to static JPEG first frames for Kindle compatibility.
- WebP 和动画图片转为静态 JPEG 首帧，以提高 Kindle 兼容性。
- Changed release automation so tags containing `-` become prereleases and stable tags become normal releases.
- 发布自动化改为：带 `-` 的 tag 发布为 prerelease，正式 tag 发布为普通 release。

### Fixed / 修复

- Fixed ESJZone Cookie handoff so pasted UTF-8 BOMs and line breaks do not break HTTP headers.
- 修复 Cookie 粘贴中的 BOM 和换行导致请求头非法的问题。
- Fixed generated XHTML structure so Sigil does not need to repair missing document wrappers.
- 修复生成 XHTML 的基础结构，避免 Sigil 打开时自动修复。
- Fixed ESJZone author metadata extraction, duplicate TOC entries, and non-clickable chapter headings.
- 修复 ESJZone 作者元数据、目录重复和不可点击章节标题问题。
- Fixed artificial blank paragraphs while preserving intentional scene breaks.
- 删除正文里的假空行，同时保留场景或视角切换留白。
- Fixed inline `data:image`, lazy-loaded images, and `srcset` image sources so they are written as EPUB resources.
- 修复正文内嵌图片、懒加载图片和 `srcset` 图片源，确保写入 EPUB 资源。
- Fixed ESJZone image downloads when remote image filenames contain Chinese, Japanese, or other non-ASCII characters.
- 修复 ESJZone 远程图片文件名包含中文、日文或其他非 ASCII 字符时下载失败的问题。
- Fixed stale encryption metadata cleanup and image path rewriting inherited from the 1.4 line.
- 保留 1.4 线中的旧加密元数据清理和图片路径重写修复。
- Fixed WinUI start-button responsiveness and live log scrolling/wrapping.
- 修复 WinUI 开始按钮短暂卡顿、日志不实时刷新和不自动滚动的问题。

## [2.0.0-beta.1] - 2026-05-10

- First public beta of the ESJZone-to-EPUB pipeline and release automation.
- ESJZone 转 EPUB 管线和发布自动化的首个公开 beta。

## [1.4.0] - 2026-05-08

### Added / 新增

- Added safe unpacking for EPUB ZIP paths that are invalid on Windows.
- 新增对 Windows 非法内部路径的安全解包和引用重写。
- Added stale encryption metadata cleanup to avoid false DRM warnings.
- 新增过期加密元数据清理，避免误报 DRM。
- Added output validation for broken font references.
- 新增坏字体引用校验。

### Changed / 调整

- Rewrote image and font references with full relative paths to avoid basename collisions.
- 图片和字体引用改为按完整相对路径重写，避免同名资源冲突。
- Improved missing-font completion and bundled Zhuque Fangsong fallback.
- 改进缺失字体补全和内置朱雀仿宋回落。

### Fixed / 修复

- Fixed disappearing images after WebP conversion.
- 修复 WebP 转换后图片丢失。
- Fixed false DRM reports from stale Duokan encryption metadata.
- 修复多看旧加密元数据导致的 DRM 误报。
- Fixed Fangsong-style aliases so they resolve to the bundled fallback when appropriate.
- 修复仿宋类字体别名补全。

## [1.4.0-beta.1 - 1.4.0-beta.3] - 2026-04-28 to 2026-05-07

- Rebuilt the desktop frontend as native WinUI 3 and introduced the Windows installer.
- 将桌面前端重建为原生 WinUI 3，并引入 Windows 安装器。
- Added settings, About page, batch task table, per-book logs, and bundled font discovery.
- 新增设置页、关于页、批量任务表、单书日志和内置字体发现。
- Refined the installer, layout, notifications, and missing-font cleanup.
- 持续改进安装器、界面布局、通知和缺失字体清理。

## [1.3.x] - 2026-04

- Introduced `BookProfile` and `ProcessingPlan` so repair strength is decided from content structure.
- 引入 `BookProfile` 和 `ProcessingPlan`，根据内容结构决定修复强度。
- Added conservative handling for CSS transforms, SVG pages, footnotes, and fixed-layout metadata.
- 新增对 CSS transform、SVG 页面、脚注和固定版式元数据的保守处理。
- Improved text decoding, language metadata repair, and output naming.
- 改进文本解码、语言元数据修复和输出命名。

## [1.1.0] - 2026-04-15

- Added language repair, comic metadata normalization, validation, and EPUB diff tooling.
- 新增语言修复、漫画元数据规范化、输出校验和 EPUB 差异工具。

## [1.0.0] - 2026-04-15

- Initial Kindle-focused EPUB repair pipeline.
- 初始版本：面向 Kindle 的 EPUB 修复管线。
