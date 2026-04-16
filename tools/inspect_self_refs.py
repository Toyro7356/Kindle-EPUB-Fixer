import zipfile
from pathlib import Path

# 找一本有 self 引用问题的 EPUB
epub_path = list(Path("测试文件/自制epub").glob("* 02.epub"))[0]
print(f"Inspecting: {epub_path.name}")

with zipfile.ZipFile(epub_path, 'r') as zf:
    html_files = [n for n in zf.namelist() if n.lower().endswith(('.html', '.xhtml'))]
    for h in html_files[:5]:
        text = zf.read(h).decode('utf-8', errors='ignore')
        if 'src="self"' in text or "src='self'" in text or 'src="none"' in text:
            print(f"\n--- {h} ---")
            # 打印包含 self/none 的 img 标签上下文
            for i, line in enumerate(text.splitlines(), 1):
                if 'src="self"' in line or "src='self'" in line or 'src="none"' in line:
                    print(f"L{i}: {line.strip()[:200]}")
