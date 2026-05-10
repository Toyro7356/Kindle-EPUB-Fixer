# Font Library / 字体库

This directory contains bundled fonts and font fallback settings.

此目录保存内置字体和字体回落配置。

## Scanned Paths / 扫描路径

The backend scans:

后端会扫描：

- `fonts/`
- `fonts/common/`
- `fonts/user/`
- `%LocalAppData%\KindleEpubFixer\fonts`

The Windows installer packages the repository `fonts/` directory with the app.

Windows 安装器会把仓库内的 `fonts/` 一起打包。

## Bundled Font / 内置字体

- `fonts/common/ZhuqueFangsong-Regular.ttf`
- Source: `TrionesType/zhuque`
- Version: `v0.212`
- License: SIL Open Font License 1.1
- License copy: `fonts/common/LICENSE.zhuque.txt`

用途：

- Fangsong-style fallback.
- 仿宋类字体回落。
- Missing-font completion when a Kindle generic family is not enough.
- 当 Kindle 通用字体族不足以表达原字体角色时用于补全。

## Settings / 配置

Default settings:

默认配置：

```text
fonts/font-settings.json
```

Installed user settings:

安装版用户配置：

```text
%LocalAppData%\KindleEpubFixer\fonts\font-settings.json
```

`family_aliases` maps private EPUB family names to font files or fallback family names.

`family_aliases` 用于把 EPUB 内的私有字体名映射到字体文件或回落字体族。

Example:

示例：

```json
{
  "family_aliases": {
    "dk-fangsong": ["common/ZhuqueFangsong-Regular.ttf", "serif"],
    "title": ["Amazon Ember", "serif"],
    "body-sans": ["sans-serif"]
  }
}
```

## Supported Formats / 支持格式

- `.ttf`
- `.otf`
- `.ttc`
- `.otc`
- `.woff`
- `.woff2`

## Policy / 策略

- Keep valid embedded EPUB fonts.
- 保留 EPUB 中有效的内嵌字体。
- Prefer Kindle-recognized families or generic families when they express the role well.
- 能表达字体角色时，优先使用 Kindle 可识别字体族或通用字体族。
- Import bundled or user fonts only when a real font file is needed.
- 只有确实需要真实字体文件时，才导入内置或用户字体。
- Do not commit commercial fonts unless their license allows redistribution.
- 不要提交没有再分发授权的商业字体。
