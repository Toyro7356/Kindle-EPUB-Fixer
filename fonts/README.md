# Font Library

这个目录用于放置可被程序自动扫描的预置字体，以及字体回落配置。

程序会自动扫描以下位置中的字体文件：

- `fonts/`
- `fonts/common/`
- `fonts/user/`

当前仓库默认预置了一套仿宋字体：

- `fonts/common/ZhuqueFangsong-Regular.ttf`
  - 来源：`TrionesType/zhuque`
  - 版本：`v0.212`
  - 授权：`SIL Open Font License 1.1`
  - 许可证副本：`fonts/common/LICENSE.zhuque.txt`

单文件 Windows EXE 会把整个 `fonts/` 目录一起打包进去。
运行时会优先读取 EXE 同目录下的外部 `fonts/` 覆盖；如果没有外部覆盖，则自动回落到 EXE 内置资源。

支持的字体格式：

- `.ttf`
- `.otf`
- `.ttc`
- `.otc`
- `.woff`
- `.woff2`

## 配置文件

默认配置文件是 [font-settings.json](C:/Users/auror/Documents/code/epub/fonts/font-settings.json)。

它现在主要控制一件事：

- `family_aliases`
  - 用于把书内私有字体别名，手动绑定到你指定的字体文件或字体家族名

`family_aliases` 的每个值都按顺序尝试：

1. 相对 `fonts/` 的字体文件路径，比如 `common/title.ttf`
2. 绝对路径字体文件
3. 系统已安装字体名称
4. Kindle / 通用字体家族名，比如 `Amazon Ember`、`Bookerly`、`serif`

示例：

```json
{
  "family_aliases": {
    "title": ["common/title.ttf", "Amazon Ember", "Futura"],
    "cont": ["common/cont.ttf", "Amazon Ember", "Helvetica"],
    "dk-songti": ["common/dk-songti.ttf", "Source Han Serif SC", "宋体"]
  }
}
```

## 当前回落策略

- 默认只保留 Kindle 字体优先策略
- 会优先回退到 Kindle 可识别的字体族名或通用字体族，比如 `STSong`、`STKai`、`TBMincho`、`serif`、`sans-serif`
- 只有当这条路无法稳定表达原字体角色时，才会继续尝试系统字体或预置字体
- 仿宋相关别名默认会优先命中仓库内置的 `朱雀仿宋`

## 处理逻辑

- 程序会先尝试 `family_aliases` 中的显式映射。
- 如果没有命中，再按内置的 Kindle 优先角色回落做自动映射。
- 如果仍然没有合适结果，再尝试系统字体库。
- GUI 在这些都失败后，才会提示手动选字体文件。

## 建议

- `fonts/common/` 放你长期想复用的字体。
- `fonts/user/` 放临时测试字体。
- 真正有版权风险的商业字体，不建议直接提交到公开仓库。
