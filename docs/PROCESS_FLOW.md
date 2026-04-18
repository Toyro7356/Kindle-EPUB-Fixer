# EPUB 处理流程与判断依据

这份文档描述当前版本的完整处理流程、分支判断依据，以及项目刻意保持保守的边界。

目标不是把所有 EPUB 强行改造成同一种模板，而是：
- 优先修复 Kindle / Send to Kindle 明确不兼容的问题
- 尽量保留原书的排版、字体和结构意图
- 对可重排小说与布局敏感内容采用不同强度的处理
- 让分支判断尽量依赖内容特征，而不是来源硬编码

## 总流程

入口位于 [src/core.py](/C:/Users/auror/Documents/code/epub/src/core.py:1)。

处理顺序如下：
1. 解包 EPUB 到临时目录。
2. 定位 OPF。
3. 分析内容结构并识别 `book_type`。
4. 生成 `BookProfile`。
5. 基于 `book_type + BookProfile` 构建 `ProcessingPlan`。
6. 执行始终安全的结构修复。
7. 如果是小说，执行小说兼容修复。
8. 如果不是 `preserve-layout`，执行可重排增强修复。
9. 如果检测到 Kobo / Adobe 标记且不是 `preserve-layout`，执行来源相关清理。
10. 重新打包 EPUB。
11. 对输出结果做结构校验。

## 一、书籍类型识别

实现位置：
- [src/book_type.py](/C:/Users/auror/Documents/code/epub/src/book_type.py:7)

当前只区分两类：
- `comic`
- `novel`

判断依据：
1. 如果 OPF 明确声明 `rendition:layout=pre-paginated`，直接判为 `comic`。
2. 否则遍历 XHTML 页面，统计全文文本量、段落数和 SVG 图片页占比。
3. 如果全文文本足够多，优先判为 `novel`，避免插图较多的小说被误判成漫画。
4. 只有当低文本 SVG 页面占比足够高时，才判为 `comic`。

当前关键阈值：
- `total_p_count >= 50` 或 `total_text_len >= 15000` 时优先判小说
- `comic_like_svg_page_ratio >= 0.85` 时判漫画

设计意图是先防止误杀小说，再识别真正的漫画型内容。

## 二、BookProfile

实现位置：
- [src/book_profile.py](/C:/Users/auror/Documents/code/epub/src/book_profile.py:8)

`BookProfile` 负责描述结构特征，而不是直接决定具体修复动作。

当前主要字段：
- `layout_mode`
- `has_fixed_layout_metadata`
- `has_viewport_pages`
- `has_svg_pages`
- `has_javascript`
- `has_vertical_writing`
- `has_rtl_progression`
- `has_kobo_adobe_markers`
- `svg_page_ratio`
- `viewport_page_ratio`
- `image_like_page_ratio`

### preserve_layout 的含义

`preserve_layout` 是当前最核心的分支判断之一。

触发条件包括：
- `layout_mode == pre-paginated`
- 存在固定版式元数据
- `viewport_page_ratio >= 0.15`
- `svg_page_ratio >= 0.35`
- `image_like_page_ratio >= 0.75`
- 存在竖排特征
- 看起来是强插图、布局敏感内容

这意味着：
- 对疑似精排、固定版式或布局敏感书籍，处理会明显更保守
- 只有明确可重排的内容才进入更激进的修复路径

### layout_mode 的自动推断

即便 OPF 没有写死固定版式，也会做结构推断：
- `viewport_page_ratio >= 0.8` 时推断为 `pre-paginated`
- `image_like_page_ratio >= 0.8` 时推断为 `pre-paginated`

这一步主要解决“书本本身明显是固定版式，但元数据不完整”的情况。

## 三、ProcessingPlan

实现位置：
- [src/core.py](/C:/Users/auror/Documents/code/epub/src/core.py:31)

`ProcessingPlan` 把处理分支显式化，避免逻辑散落在多个 `if` 中难以追踪。

当前字段：
- `book_type`
- `preserve_layout`
- `has_kobo_markers`
- `run_novel_compat_repairs`
- `run_reflow_repairs`
- `run_source_specific_cleanup`

构建规则：
- 小说总是允许执行小说兼容修复
- `preserve_layout == False` 时允许执行可重排增强修复
- `has_kobo_markers and not preserve_layout` 时允许执行来源相关清理

## 四、始终执行的安全修复

实现位置：
- [src/core.py](/C:/Users/auror/Documents/code/epub/src/core.py:52)

这些修复默认被认为不会明显破坏作者排版意图，因此总是执行。

包括：
- WebP 转换与引用同步
- 已知辅助脚本清理
- HTML 结构修复
- 自闭合标签修复
- HTML 头部脏元数据清理
- 封面页图片引用修复
- NCX 父级 `navPoint` 修复
- OPF 保守清理
- 漫画的 Kindle 兼容增强

### 漫画增强的保守模式

实现位置：
- [src/comic_fix.py](/C:/Users/auror/Documents/code/epub/src/comic_fix.py:320)

无论是否 `preserve-layout`，都会补漫画最小必要的 Kindle 兼容修复。

在 `preserve-layout` 模式下：
- 不再强行注入整套 Kindle 私有漫画元数据
- 只在缺失或非法时修 `original-resolution`
- 仍会补 `viewport`
- 保留原书已有的固定版式声明

这样做是因为样本已经证明：
- 某些 preserve-layout 漫画确实需要 `original-resolution` 才能在 Previewer 转换成功
- 但对原本就能正常转换的漫画，过度注入 Kindle 私有元数据反而可能导致 ET 回退

## 五、小说兼容修复

实现位置：
- [src/core.py](/C:/Users/auror/Documents/code/epub/src/core.py:134)

当前只对 `novel` 执行，并且即使 `preserve_layout=True` 也会执行。

包括：
- 非日文小说的 `page-progression-direction="rtl"` 修正为 `ltr`
- 非日文小说的 `vertical-rl` 降级

相关模块：
- [src/opf_sanitize.py](/C:/Users/auror/Documents/code/epub/src/opf_sanitize.py:58)
- [src/vertical_fix.py](/C:/Users/auror/Documents/code/epub/src/vertical_fix.py:14)

原因是这两类问题已经被样本和 Previewer 证明会直接导致 Kobo 小说白屏或无法打开。

## 六、可重排增强修复

实现位置：
- [src/core.py](/C:/Users/auror/Documents/code/epub/src/core.py:89)

只在 `preserve_layout=False` 时执行。

包括：
- 语言标签修复
- 字体处理
- 高风险 CSS transform 降级
- 简单 SVG 包图页转 `<img>`
- 脚注结构保守归一
- stale SVG manifest 属性清理

这些修复对普通可重排小说帮助很大，但对精排书、漫画或强布局内容可能产生不必要扰动，所以默认只在明确可重排路径里启用。

### transform 降级的实际边界

当前不会无差别清空所有 `transform`。

只在 `preserve_layout=False` 时，才会降级已验证会显著提高 Kindle Previewer 失败风险的变换类型，包括：
- `rotate`
- `matrix / matrix3d`
- `skew`
- `perspective`
- 其他 3D transform

不会因为某个文件存在一条高风险 `transform`，就顺便全局清空整份样式里的 `transform-origin`。

### SVG 转换的实际边界

当前不会把所有带 SVG 的页面都改成 `<img>`。

只有满足以下条件时才转换：
- 页面主体没有明显 XHTML 正文文本
- 全页只有一个 SVG
- 该 SVG 只是一个单图外壳
- SVG 内不存在复杂矢量结构、文字叠层、分组、遮罩等复杂内容

因此这更接近“把误导 Kindle 的 SVG 图片外壳还原为普通图片页”，而不是重写作者设计的 SVG 排版。

### 脚注修复的实际边界

实现位置：
- [src/footnote_fix.py](/C:/Users/auror/Documents/code/epub/src/footnote_fix.py:1)

当前脚注策略是保守修复，不追求把所有脚注都改成同一种结构。

规则如下：
- 如果书里已经存在标准 `noteref -> footnote` 结构，则默认不改写
- 不再为已有效的脚注额外注入 synthetic backlink
- 只对明显异常结构做修复，例如：
  - 嵌套 `note` 包裹导致的结构破损
  - Duokan 风格 `ol.duokan-footnote-content` 的容器归一

这样做的原因是 Kindle 对弹窗脚注本身就有黑箱差异，而对已正常工作的脚注额外插入回链，容易导致空弹窗、返回符号外露或注释正文化回归。

## 七、来源相关清理

实现位置：
- [src/core.py](/C:/Users/auror/Documents/code/epub/src/core.py:148)

当前只在以下条件成立时执行：
- 检测到 Kobo / Adobe 标记
- 且 `preserve_layout=False`

动作包括：
- 移除书内脚本标记
- 移除事件处理属性
- 清理残留 JS 文件的 manifest 记录

原因是这类脚本在 Kindle 上往往无效甚至有害，但对布局敏感内容仍保持保守，避免误伤。

## 八、校验与回归

实现位置：
- [src/epub_validator.py](/C:/Users/auror/Documents/code/epub/src/epub_validator.py:45)

当前会检查：
- container / OPF / spine / manifest 一致性
- XHTML 是否可解析
- 图片引用是否断裂
- 是否残留 WebP
- 是否残留脚本
- 漫画元数据与 viewport 是否一致
- `mimetype` 是否正确存储

样本级验证工具：
- [tools/audit_samples.py](/C:/Users/auror/Documents/code/epub/tools/audit_samples.py:1)
- [tools/previewer_audit.py](/C:/Users/auror/Documents/code/epub/tools/previewer_audit.py:1)
- [tools/previewer_compare.py](/C:/Users/auror/Documents/code/epub/tools/previewer_compare.py:1)

当前已确认的验证结果：
- 内部结构审计：`77/77` 通过
- Kindle Previewer 核心样本：`69/69` 处理成功，`0` 回归，`0` 处理后错误
- 脚注专项 Previewer 样本：`4/4` 处理成功

## 九、当前已确认修正过的关键逻辑问题

1. `rendition:*` 曾被过宽地视为固定版式信号，导致部分 Kobo 小说误入 preserve-layout 路径。
2. 小说兼容修复曾被 preserve-layout 阻断，导致部分 Kobo 小说白屏。
3. 漫画在 preserve-layout 路径下曾没有正确应用最小 Kindle 兼容增强。
4. GUI 和核心处理之间曾重复扫描字体。
5. 文本读取逻辑曾散落在多个模块，各自实现。
6. `guide/toc` 曾被盲目指向 `toc.ncx`，导致部分书在 Previewer 中出现未解析链接或内部错误。
7. reflow 路径里的 transform 处理曾一度过宽，现在已收窄到高风险变换。
8. SVG 页面转换曾只要看到 `<svg><image>` 就改写，现在已收窄到单图壳子页。
9. 脚注修复曾会对已经有效的脚注注入额外回链，现在已改为“标准结构不动、异常结构再修”。

## 十、当前刻意保守不做的事

以下内容当前不会默认强制处理：
- 强行改写日文竖排小说为横排
- 强行移除所有作者自带字体
- 对 `preserve-layout` 内容做大规模 CSS 清洗
- 对固定版式内容强行重排
- 为了通过某个样本而写来源硬编码特判

原因很简单：
- 这些动作虽然可能让个别问题样本“更能看”
- 但更容易破坏原书结构和作者意图
- 不符合当前项目的总体方向

## 十一、当前仍然存在的边界

虽然样本回归已经覆盖到当前仓库中的主要问题，但仍然不能保证“所有 EPUB 的所有 Kindle 问题都被穷尽解决”。

仍可能出现新增边界的区域：
- 非常规脚注结构
- 极端复杂的 fixed-layout EPUB
- Kindle 设备端特有的黑箱渲染差异
- 当前样本中尚未出现的危险 CSS / JS 用法
- 图像脚注、弹窗脚注等 Kindle 本身支持较弱的能力

所以当前策略是：
- 先把已知高价值、可通用的问题彻底收敛
- 再基于新样本继续扩边界
