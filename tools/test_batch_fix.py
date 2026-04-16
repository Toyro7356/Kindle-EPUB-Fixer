import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.getcwd())

from src.core import process_epub
from src.epub_validator import validate_epub
from tools.diff_epub import diff_epub

base = Path("测试文件/自制epub")
epubs = sorted(base.glob("*.epub"))

# 挑选前 5 本做快速测试
test_epubs = epubs[:5]

for epub in test_epubs:
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
    except Exception as e:
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()
