# Contributing / 贡献指南

谢谢你参与 Kindle EPUB Fixer。

Thank you for contributing to Kindle EPUB Fixer.

## 方向 / Direction

- 修复通用 Kindle / Send to Kindle 兼容性问题，不为单本书写硬编码特判。
- Fix general Kindle and Send to Kindle compatibility issues. Do not hard-code one specific book.
- 保留原书的语义、排版、字体和结构意图。
- Preserve the original book semantics, layout, fonts, and structure whenever possible.
- 对固定版式、漫画、复杂 SVG、脚注和字体处理保持保守。
- Be conservative around fixed layout, comics, complex SVG, footnotes, and fonts.
- 网页小说来源应先转成统一小说模型，再交给转换管线。
- Web novel sources should normalize data into the shared novel model before EPUB generation.

## 分支 / Branches

- `main`: stable releases.
- `main`: 正式版分支。
- `beta`: prerelease and active integration.
- `beta`: 测试版和日常集成分支。
- Feature branches should start from `beta` unless the change is an urgent release fix.
- 功能分支默认从 `beta` 拉出，除非是正式版紧急修复。

Recommended tag names:

推荐 tag 命名：

```text
v2.0.0-beta.1
v2.0.0
```

## 开发环境 / Development

```bash
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m compileall -q src main.py main_backend.py build_backend.py
```

WinUI build:

```powershell
powershell -ExecutionPolicy Bypass -File build_winui.ps1
```

If no .NET SDK is available:

如果没有 .NET SDK：

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_dotnet_sdk.ps1
```

## 验证 / Validation

Choose checks that match the risk of the change:

按改动风险选择验证：

- Python backend changes: compile the backend and run targeted EPUB conversion checks.
- Python 后端改动：编译后端并跑相关 EPUB 转换检查。
- WinUI changes: build the WinUI project and check the touched workflow.
- WinUI 改动：构建 WinUI，并检查受影响流程。
- Release changes: run `build_winui.ps1` or let the tag workflow build the installer.
- 发布改动：运行 `build_winui.ps1`，或交给 tag workflow 构建安装包。

Useful commands:

常用命令：

```bash
python tools/audit_samples.py --report build/audit-report.json --output-dir build/audit-output
python tools/previewer_compare.py "input.epub" --keep-workdir build/previewer-debug
```

## 提交 / Commits

Use short, concrete commit messages:

提交信息保持简短明确：

```text
fix: preserve embedded title fonts
feat: add ESJZone EPUB importer
docs: refresh bilingual release notes
release: ship v2.0.0-beta.1
```

## 发布 / Release

Beta release:

测试版发布：

1. Merge feature work into `beta`.
2. Update versions, README, changelog, and docs.
3. Commit with a signed commit.
4. Create a signed tag from `beta`.
5. Push `beta` and the tag. GitHub Actions builds the installer and creates the prerelease.

正式版发布从 `main` 打 tag。Beta 发布从 `beta` 打 tag。

Stable releases are tagged from `main`. Beta releases are tagged from `beta`.

Stable release:

正式版发布：

1. Finish and push the `beta` release candidate.
2. Merge `beta` into `main`.
3. Update the stable changelog section so it includes all beta changes since the previous stable release.
4. Create a signed stable tag from `main`.
5. Push `main` and the tag. GitHub Actions builds the installer and creates the stable release.
