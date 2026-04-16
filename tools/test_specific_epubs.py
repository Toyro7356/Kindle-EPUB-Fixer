import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, os.getcwd())

from src.core import process_epub
from src.epub_validator import validate_epub

base = Path("测试文件/自制epub")
epubs = sorted(base.glob("*.epub"))

# 挑选有特定问题的 EPUB 进行深度验证
# 根据分析报告，索引 5 有 self 引用，索引 6/7/8 也有 self 引用
targets = [epubs[5], epubs[6], epubs[7], epubs[35], epubs[40]]  # 有 self/none 或 css unsafe 的

for epub in targets:
    out = str(epub).replace(".epub", ".tested.epub")
    print(f"\n{'='*60}")
    print(f"Testing: {epub.name}")
    print(f"{'='*60}")
    try:
        result = process_epub(str(epub), out, log=lambda msg: print(f"  [LOG] {msg}"))
        print(f"  Output: {result}")
        issues = validate_epub(result, "novel")
        if issues:
            print("  [VALIDATOR WARNINGS]")
            for issue in issues:
                print(f"    - {issue}")
        else:
            print("  [VALIDATOR] Passed")

        # 抽查处理后的 CSS 和 HTML
        with zipfile.ZipFile(out, 'r') as zf:
            # 检查是否有 -webkit- 残留
            css_files = [n for n in zf.namelist() if n.lower().endswith('.css')]
            if css_files:
                ctext = zf.read(css_files[0]).decode('utf-8', errors='ignore')
                has_webkit = '-webkit-' in ctext
                has_transform = 'transform:' in ctext.lower() or '-webkit-transform' in ctext.lower()
                print(f"  [POST-CHECK] {css_files[0]}: webkit={has_webkit}, transform={has_transform}")

            # 检查 self/none 引用
            html_files = [n for n in zf.namelist() if n.lower().endswith(('.html', '.xhtml', '.htm'))]
            bad_refs = 0
            for h in html_files[:10]:
                ht = zf.read(h).decode('utf-8', errors='ignore')
                if 'src="self"' in ht or "src='self'" in ht or 'src="none"' in ht:
                    bad_refs += 1
            if bad_refs:
                print(f"  [POST-CHECK] Found {bad_refs} files still with self/none img refs")
            else:
                print(f"  [POST-CHECK] No self/none img refs in sampled files")

    except Exception as e:
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()
