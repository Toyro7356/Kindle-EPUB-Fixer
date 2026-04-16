import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())

from src.core import process_epub
from src.epub_validator import validate_epub

base = Path("测试文件/自制epub")
epubs = sorted(base.glob("*.epub"))

failures = []
success = 0

for epub in epubs:
    out = str(epub).replace(".epub", ".tested.epub")
    try:
        result = process_epub(str(epub), out, log=lambda msg: None)
        issues = validate_epub(result, "novel")
        if issues:
            failures.append((epub.name, "validation: " + "; ".join(issues[:3])))
        else:
            success += 1
    except Exception as e:
        failures.append((epub.name, str(e)))

print(f"Success: {success}/{len(epubs)}")
if failures:
    print("Failures:")
    for name, reason in failures:
        print(f"  - {name}: {reason}")
else:
    print("All passed!")
