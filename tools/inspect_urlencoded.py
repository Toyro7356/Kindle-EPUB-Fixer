import zipfile
from pathlib import Path
from urllib.parse import unquote

# 遍历找到包含 Section0002 的 EPUB
base = Path("测试文件/自制epub")
for epub_path in base.glob("*.epub"):
    with zipfile.ZipFile(epub_path, 'r') as zf:
        html_files = [n for n in zf.namelist() if "Section0002" in n and n.lower().endswith('.xhtml')]
        if not html_files:
            continue
        for h in html_files:
            text = zf.read(h).decode('utf-8', errors='ignore')
            if '%E7%89%B9' in text or '%E5%85%B8' in text:
                print(f"Found in: {epub_path.name}")
                for i, line in enumerate(text.splitlines(), 1):
                    if '<img' in line and '%' in line:
                        print(f"\n--- {h} L{i} ---")
                        print(line.strip()[:300])
                        import re
                        m = re.search(r'src=["\']([^"\']+)["\']', line)
                        if m:
                            src = m.group(1)
                            decoded = unquote(src)
                            print(f"  raw src: {src}")
                            print(f"  decoded: {decoded}")
                            base_p = Path(h).parent.as_posix()
                            resolved = (Path(base_p) / decoded).as_posix()
                            print(f"  resolved: {resolved}")
                            namelist = zf.namelist()
                            print(f"  in zip (resolved): {resolved in namelist}")
                            similar = [n for n in namelist if '小冊子' in n or '%E5%B0%8F' in n]
                            if similar:
                                print(f"  similar files: {similar}")
                break
