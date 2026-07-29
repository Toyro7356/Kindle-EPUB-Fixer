# Processing Flow / 处理流程

This document describes the repair and web-novel conversion boundaries.

本文说明 EPUB 修复与网页小说转制的处理边界。

## Repair Pipeline / 修复管线

Entry point: `src/core.py`

入口：`src/core.py`

1. Unpack the EPUB safely.
2. Locate OPF and manifest resources.
3. Analyze content structure and infer book type.
4. Build `BookProfile` and `ProcessingPlan`.
5. Run always-safe structure repairs.
6. Run novel compatibility repairs when applicable.
7. Run font compatibility handling.
8. Run reflow-only enhancements when layout is not sensitive.
9. Repack the EPUB.
10. Validate the output structure.

中文流程：

1. 安全解包 EPUB。
2. 定位 OPF 和资源清单。
3. 分析内容结构并推断书籍类型。
4. 构建 `BookProfile` 和 `ProcessingPlan`。
5. 执行始终安全的结构修复。
6. 在适用时执行小说兼容修复。
7. 执行字体兼容处理。
8. 只在布局不敏感时执行可重排增强修复。
9. 重新打包 EPUB。
10. 校验输出结构。

## Book Profile / 书籍画像

`BookProfile` describes layout signals. It does not directly rewrite content.

`BookProfile` 描述版式信号，本身不直接改写内容。

Important signals:

主要信号：

- fixed-layout metadata.
- 固定版式元数据。
- viewport-heavy pages.
- viewport 页面占比。
- SVG page ratio.
- SVG 页面占比。
- image-like page ratio.
- 图片化页面占比。
- vertical writing.
- 竖排特征。
- script usage.
- 脚本使用情况。
- Kobo or Adobe markers.
- Kobo 或 Adobe 标记。

`preserve_layout` becomes true when the book looks fixed-layout, image-heavy, vertical, or otherwise layout-sensitive.

当书籍看起来像固定版式、图片化、竖排或布局敏感内容时，会进入 `preserve_layout`。

## Processing Plan / 处理计划

`ProcessingPlan` makes repair decisions explicit:

`ProcessingPlan` 让修复分支显式化：

- `run_novel_compat_repairs`
- `run_reflow_repairs`
- `run_source_specific_cleanup`
- `preserve_layout`

This prevents high-risk cleanup from being applied to layout-sensitive books.

这样可以避免高风险清理误伤布局敏感书籍。

## Safe Repairs / 安全修复

These repairs are designed to be low-risk:

这些修复默认风险较低：

- WebP conversion and image reference updates.
- WebP 转换和图片引用同步。
- XHTML structure repair.
- XHTML 结构修复。
- language metadata repair.
- 语言元数据修复。
- cover reference repair.
- 封面引用修复。
- NCX hierarchy repair.
- NCX 层级修复。
- stale encryption metadata cleanup.
- 过期加密元数据清理。
- output validation.
- 输出校验。

## Reflow-Only Repairs / 仅可重排修复

These only run when the book is not layout-sensitive:

这些只在书籍不属于布局敏感内容时执行：

- high-risk CSS transform downgrade.
- 高风险 CSS transform 降级。
- simple SVG image-wrapper conversion.
- 简单 SVG 图片外壳转换。
- conservative footnote normalization.
- 保守脚注规范化。
- script and event-handler cleanup.
- 脚本和事件处理清理。

The intent is to fix common Kindle failures without flattening the author's layout.

目标是修复常见 Kindle 失败点，而不是抹平作者排版。

## Font Strategy / 字体策略

The font handler prefers this order:

字体处理优先级：

1. Valid embedded fonts from the EPUB.
2. EPUB 中有效的内嵌字体。
3. Kindle-recognized family names and generic families.
4. Kindle 可识别字体族和通用字体族。
5. User or bundled fonts when a real font file is needed.
6. 需要真实字体文件时，再使用用户字体或内置字体。

Bundled Zhuque Fangsong is used for Fangsong-style aliases when appropriate.

仿宋类别名在适用时会回落到内置朱雀仿宋。

## Web Novel Pipeline / 网页小说管线

Web sources do not pass through the repair engine first.

网页来源不会先进入 EPUB 修复引擎。

Flow:

流程：

1. Source reader logs in or receives Cookie.
2. 书源读取器登录或接收 Cookie。
3. Reader extracts metadata, cover, TOC, chapters, and images.
4. 读取器提取元数据、封面、目录、章节和图片。
5. Reader returns a normalized `NovelBook`.
6. 读取器返回统一的 `NovelBook`。
7. Source-specific chapter CSS and assets, such as ESJZone scrambled fonts, are attached to the relevant chapters only.
8. 站点特定的章节 CSS 和资源（例如 ESJZone 混淆字体）只挂载到对应章节。
9. `KindleNovelEpubConverter` generates EPUB structure directly.
10. `KindleNovelEpubConverter` 直接生成 EPUB 结构。
11. The generated EPUB is validated.
12. 校验生成的 EPUB。

This keeps website-specific logic separate from Kindle EPUB generation.

这样可以把站点解析逻辑和 Kindle EPUB 生成逻辑分开。

## Web Novel Source Architecture

The web-novel path is split into reusable layers:

- `novel_source.py`: normalized book, chapter, asset, source, and read-option models.
- `novel_build.py`: shared build orchestration, chapter selection, normal/slow chapter scheduling, retry handling, and EPUB conversion handoff.
- `source_registry.py`: maps source ids such as `esjzone` to source adapters.
- `sources/esjzone/`: ESJZone adapter package with client, parser, asset, chapter processor, model, and source modules.
- `sources/masiro/`: authenticated Masiro adapter with Cookie/User-Agent HTTP access, detail and chapter parsing, and image packaging.
- `novel_epub.py`: site-independent EPUB writer.

A future website should implement a source adapter that returns `NovelBook` data and should reuse the shared chapter scheduler and EPUB writer instead of duplicating conversion logic.

## Chapter Fetch Scheduler

Web-novel chapter fetching uses two queues:

1. The normal queue handles ordinary chapters with `chapter_workers` workers and `chapter_timeout_seconds` timeout.
2. Chapters that time out, or explicitly report slow behavior, move to the slow queue.
3. The slow queue uses `slow_chapter_workers` workers and `slow_chapter_timeout_seconds` timeout, so slow chapters do not occupy normal queue slots.
4. Non-timeout failures retry up to `chapter_retries` times.
5. Chapters that still fail are skipped and logged; the book continues as long as at least one chapter succeeds.
6. Prepared chapters are written in original chapter order, even when fetches complete out of order.

Default values are conservative: 4 normal workers, 2 slow workers, 12 seconds for normal timeout, 60 seconds for slow timeout, and 2 retries.

## ESJZone Scrambled Fonts / ESJZone 混淆字体

Some ESJZone chapters render readable text only through a page-specific `@font-face` data font.

部分 ESJZone 章节依赖每页特定的 `@font-face` data 字体才能显示正确文本。

For those chapters, the reader:

对应章节的读取器会：

1. Extract the `data:text/css` font rule from the chapter page.
2. 从章节页面提取 `data:text/css` 字体规则。
3. Decode the embedded WOFF2 font and save it as an EPUB font asset.
4. 解码内嵌 WOFF2 字体并保存为 EPUB 字体资源。
5. Add chapter-level CSS that references the packaged font through a relative EPUB path.
6. 添加章节级 CSS，通过 EPUB 相对路径引用已打包字体。
7. Apply the font only to the affected chapter body.
8. 只对受影响章节正文套用该字体。

The extracted font is normalized for reading engines: WOFF2 compression is removed, CID-keyed CFF markers are converted away when present, and GSUB substitution tables are dropped so Kindle/Calibre render the same scrambled cmap glyphs as the web page instead of partially substituting them back.

Chapters without such a font keep the normal generated styling and receive no extra font asset.

没有此类字体的章节保持普通生成样式，不会额外添加字体资源。

## Masiro Authentication and Access

Masiro pages require an authenticated browser session. The desktop login window captures the site Cookie and the matching browser User-Agent because Cloudflare may validate both values. The backend uses those values only for Masiro requests.

The adapter reads metadata from `novelView`, collects chapter links from the episode lists or embedded chapter JSON, and extracts readable content from `.box-body.nvl-content`. Automatic purchase is disabled by default, so priced entries are skipped without a request.

When the user enables automatic purchase, WinUI first runs a read-only preview for the selected range. It shows the paid chapter count, total cost, and account balance, and requires an explicit confirmation. The confirmed total becomes a backend hard budget. For each priced chapter, the backend verifies the official payment page fields and CSRF token before posting to `/admin/pay`; it stops if the price or chapter id changes. Ambiguous network responses are verified with a read-only chapter request and are never retried as another payment POST.

Masiro also applies a source-wide request gate: at most two normal chapter workers are used, request starts are spaced apart, and any HTTP 429 response creates one shared cooldown for all workers. The client honors `Retry-After` when supplied and otherwise uses bounded increasing delays.
