# Changelog / 更新日志

All notable changes are documented here.

本文件记录值得发布说明的变更，避免列出样本数量或内部验证流水账。

## [Unreleased]

## [2.2.0-beta1] - 2026-07-29

### Added / 新增

- Added authenticated Masiro-to-EPUB conversion using the shared web-novel pipeline, including metadata, chapter ranges, inline and remote images, and output validation.
- 新增基于共享网页小说管线的 Masiro 转 EPUB，支持元数据、章节范围、内嵌与远程图片以及输出校验。
- Added a Masiro desktop page with web login Cookie and browser User-Agent capture for Cloudflare-protected sessions.
- 新增 Masiro 桌面页面，通过网页登录同时获取 Cookie 与浏览器 User-Agent，以支持 Cloudflare 登录态。
- Added optional Masiro paid-chapter purchase through the site's official CSRF-protected payment endpoint, with balance checks, price-change rejection, and duplicate-payment protection.
- 新增可选的 Masiro 付费章节购买，通过站点官方 CSRF 支付接口执行，并包含余额检查、价格变化拒绝和重复支付保护。
- Added complete EPUB metadata for web novels, including descriptions, subjects, publishers, author and translator roles.
- 补全网页小说 EPUB 元数据，包括简介、标签、来源出版者，以及作者和译者角色。
- Added a dedicated EPUB cover page with EPUB 2 and EPUB 3 cover declarations for broader reader compatibility.
- 新增独立 EPUB 封面页，并同时写入 EPUB 2 与 EPUB 3 封面声明，以提升阅读器兼容性。

### Security / 安全

- Masiro automatic purchase is disabled by default and requires a read-only cost preview, explicit desktop confirmation, and a backend hard budget.
- Masiro 自动购买默认关闭；启用时必须先只读预览费用、在桌面端明确确认，并受后端硬预算限制。

### Fixed / 修复

- Fixed the Masiro login window closing immediately when an old authenticated session was detected; it now stays open and can clear only the embedded browser cookies for a clean re-login.
- 修复 Masiro 登录窗口检测到旧登录态后立即关闭的问题；现在窗口会保持打开，并可仅清除内置浏览器 Cookie 后重新登录。
- Fixed older Masiro books whose chapter lists exist only in embedded chapter JSON before browser-side rendering.
- 修复旧版 Masiro 书籍目录仅存在于内嵌章节 JSON、导致后端报告找不到章节的问题。
- Fixed Masiro chapter batches failing after several successful requests by adding source-wide pacing, shared HTTP 429 cooldowns, `Retry-After` handling, and bounded retries.
- 修复 Masiro 连续抓取数章后触发 HTTP 429 的问题，新增书源级请求节流、共享冷却、`Retry-After` 处理和有限重试。

## [2.1.0-beta2] - 2026-06-23

### Added / 新增

- Added a reusable web-novel source adapter architecture with a source registry, shared build orchestration, and a dedicated `sources/esjzone` adapter package.
- 新增可复用的网页小说书源适配架构，包含书源注册表、共享构建编排，以及独立的 `sources/esjzone` 适配包。
- Added generic CLI entry points for future website sources: `--novel-source`, `--novel-url`, `--novel-search`, `--novel-cookie`, and `--novel-cookie-file`.
- 新增面向后续网站书源的通用 CLI 入口：`--novel-source`、`--novel-url`、`--novel-search`、`--novel-cookie`、`--novel-cookie-file`。
- Added normal and slow chapter queues for web-novel fetching. Slow chapters can move to an independent queue instead of blocking normal chapter downloads.
- 新增普通章节队列和慢速章节队列；慢速章节会转入独立队列，不再占用普通章节下载并发。
- Added configurable chapter fetch controls: `--chapter-workers`, `--slow-chapter-workers`, `--chapter-timeout`, `--slow-chapter-timeout`, and `--chapter-retries`.
- 新增章节抓取调节参数：`--chapter-workers`、`--slow-chapter-workers`、`--chapter-timeout`、`--slow-chapter-timeout`、`--chapter-retries`。
- Added unit tests for ESJZone parsing, chapter processing, source registration, chapter selection, slow queue behavior, retry handling, and skip-on-failure behavior.
- 新增 ESJZone 解析、章节处理、书源注册、章节选择、慢速队列、重试和失败跳过行为的单元测试。

### Changed / 调整

- Split ESJZone conversion into smaller modules for client access, models, parsers, assets, chapter processing, and source orchestration.
- 将 ESJZone 转制拆分为客户端访问、模型、解析器、资源、章节处理和书源编排等更小模块。
- Moved common chapter selection and chapter assembly into the shared web-novel build pipeline so future sources can reuse the same behavior.
- 将通用章节选择和章节组装移动到共享网页小说构建管线，便于后续书源复用同一套行为。
- ESJZone chapter fetches now use the shared scheduler and pass per-chapter timeouts to the HTTP client.
- ESJZone 章节抓取改用共享调度器，并将单章超时时间传递给 HTTP 客户端。

### Fixed / 修复

- Chapter fetch failures no longer abort the whole web-novel conversion. Failed chapters retry twice by default and are skipped if they still fail.
- 章节抓取失败不再终止整个网页小说转制；失败章节默认重试 2 次，仍失败则跳过。
- Slow or timing-out chapters no longer hold up the normal chapter queue.
- 慢速或超时章节不再阻塞普通章节队列。
- ESJZone conversion logs are now buffered and flushed in batches so long conversions no longer freeze the WinUI page or log scrolling.
- ESJZone 转制日志现在会缓冲并批量刷新，长时间转制时不再导致 WinUI 页面或日志滚动卡死。
- Backend stderr is drained concurrently with stdout to avoid process pipe backpressure during noisy conversions.
- 后端进程的 stderr 现在会与 stdout 并发读取，避免输出较多时产生管道背压。

## [2.1.0-beta1] - 2026-06-22

### Added / 新增

- Added chapter-level ESJZone scrambled-font embedding: chapters with site-provided anti-scraping fonts now extract the WOFF2 data font, convert it to an EPUB font resource, add it to OPF, and apply it only to that chapter.
- 新增 ESJZone 章节级混淆字体嵌入：检测到站点反爬字体的章节会提取 WOFF2 data 字体、转换为 EPUB 字体资源、写入 OPF，并且只作用于对应章节。

### Changed / 调整

- Upgraded the beta build toolchain to .NET SDK 10.0.301, Windows App SDK 2.2.0, and current Python package baselines.
- beta 构建工具链升级到 .NET SDK 10.0.301、Windows App SDK 2.2.0，以及当前 Python 依赖基线。
- Generated web-novel EPUBs can now carry non-image assets such as fonts, while ordinary image handling remains unchanged.
- 网页小说 EPUB 生成器现在可携带字体等非图片资源，同时保持普通图片处理逻辑不变。

### Fixed / 修复

- Fixed ESJZone chapters that render garbled text on Kindle because the source page relies on a per-page custom font encoding.
- Removed GSUB substitution tables from extracted ESJZone fonts so Kindle/Calibre do not partially substitute scrambled glyphs back to the wrong visible characters.
- 修复 ESJZone 章节因依赖每页自定义字体编码而在 Kindle 上显示错乱的问题。
- Removed source `data:text/css` font links from generated XHTML after externalizing the font into EPUB resources.
- 字体外置为 EPUB 资源后，会从生成 XHTML 中移除原网页的 `data:text/css` 字体链接。

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
