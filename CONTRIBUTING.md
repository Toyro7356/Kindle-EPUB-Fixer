# Contributing

感谢你为 Kindle EPUB Fixer 做贡献。

这个项目的核心目标不是把所有 EPUB 改成统一模板，而是在尽可能保留作者原始排版、字体和结构意图的前提下，修复 Kindle / Send to Kindle 的明确兼容性问题。

在开始提交代码前，建议先阅读：
- [README.md](README.md)
- [docs/PROCESS_FLOW.md](docs/PROCESS_FLOW.md)

## 贡献原则

- 优先做通用修复，不为单一本书写来源硬编码特判。
- 优先修结构错误、兼容性错误和 Kindle 明确不支持的内容。
- 尽量减少对原始排版、字体、版式和语义的扰动。
- 对布局敏感、固定版式、疑似精排内容保持保守。
- 如果某项能力是 Kindle 先天支持较弱或不支持，不强行伪造。

一个简单判断标准：
- “这是 EPUB 规范问题或 Kindle 明确兼容问题” -> 值得修
- “这是某一本书的私人排版偏好” -> 默认不要硬改

## 分支策略

仓库长期保持这套结构：
- `main`：稳定正式版分支
- `beta`：日常开发与测试分支
- `tag`：每次 beta / 正式发布的版本快照

约定如下：
- 日常修复、新样本收敛、新功能开发，优先提交到 `beta`
- 通过样本验证、Previewer 验证和必要的实机验证后，再从 `beta` 合并到 `main`
- 正式发布只从 `main` 打 tag
- 测试版从 `beta` 打 tag

推荐版本格式：
- Beta：`v1.3.1-beta.1`
- 正式版：`v1.3.1`

## 开发流程

推荐日常流程：
1. 从 `beta` 开始开发。
2. 完成修改后跑本地验证。
3. 确认没有回归后提交到 `beta`。
4. 当一轮修复足够稳定时，将 `beta` 合并到 `main`。
5. 在 `main` 上打正式版标签并发布。

如果只是本地单人维护，也建议遵守这个节奏，不要长期直接在 `main` 上开发。

## 开发环境

安装依赖：

```bash
pip install -r requirements.txt
```

启动 GUI：

```bash
python main_gui.py
```

命令行处理：

```bash
python main.py "input.epub"
python main.py "input.epub" "output.epub"
```

打包 EXE：

```bash
python build_exe.py
```

## 验证要求

任何会影响处理逻辑的改动，至少应跑以下验证中的一部分，并根据改动范围扩大验证范围。

结构审计：

```bash
python tools/audit_samples.py --report build/audit-report.json --output-dir build/audit-output
```

单本 Previewer 对比：

```bash
python tools/previewer_compare.py "测试文件\\自制epub\\OVERLOAD 05.epub" --keep-workdir build\\previewer-debug
```

全量 Previewer 审计：

```bash
python tools/previewer_audit.py --report build/previewer-audit.json --workdir build/previewer-audit --timeout-seconds 1200
```

如果修改涉及以下区域，建议额外重点验证：
- `footnote_fix.py`：角注/脚注专项样本
- `comic_fix.py` / `svg_fix.py`：漫画、固定版式、SVG 页样本
- `css_sanitize.py` / `vertical_fix.py`：Kobo 小说和精排敏感样本
- `font_handler.py`：自制 EPUB 和缺字库样本

## 代码修改建议

- 保持修复逻辑可解释，尽量让“为什么修”和“为什么不修”都说得清楚。
- 新增判断规则时，优先复用 `BookProfile`、`ContentAnalysis` 和 `ProcessingPlan`，不要把逻辑散落到多个模块里。
- 如果修复只应该发生在可重排路径，请明确放在 reflow 分支里。
- 如果修复可能影响精排内容，请先考虑是否应该只在 `preserve-layout=False` 时执行。
- 对脚注、SVG、字体、漫画元数据这类高风险区域，默认从保守策略出发。

## 提交建议

提交信息尽量简洁明确，例如：
- `fix(footnote): avoid rewriting already-valid noteref structures`
- `fix(css): narrow risky transform downgrades`
- `docs: document beta/main release workflow`
- `release: ship v1.3.1`

如果一次改动同时涉及逻辑、文档和发布文件，优先保证提交信息能表达“这次改动的核心目的”。

## 不建议的做法

- 不要为了通过某一本样本而写死书名、来源或目录名判断。
- 不要默认大规模清洗固定版式或疑似精排内容。
- 不要轻易移除作者自带字体、脚注或排版结构，除非它们已经明确造成 Kindle 问题。
- 不要在没有验证的情况下直接改 `main` 并发正式版。

## 发布流程

推荐正式发布步骤：
1. 在 `beta` 完成修复并验证。
2. 更新 `README.md`、`CHANGELOG.md`、`docs/PROCESS_FLOW.md` 和版本号。
3. 重新打包 EXE。
4. 将 `beta` 合并到 `main`。
5. 在 `main` 上打正式 tag。
6. 发布 GitHub Release，并上传 EXE。

推荐测试发布步骤：
1. 在 `beta` 完成一轮阶段性修复。
2. 更新 beta 版本号和变更说明。
3. 打包 EXE。
4. 在 `beta` 上打 `-beta.x` tag。
5. 发布 prerelease。

## 最后

如果你准备做的是：
- 修复一个明确的 Kindle 兼容问题
- 用通用方法解决，而不是样本特判
- 并且愿意补上验证

那这通常就是一个值得推进的改动。
