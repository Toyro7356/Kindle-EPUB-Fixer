import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont
from lxml import etree

from .constants import NS_OPF
from .epub_io import find_opf, opf_dir
from .utils import LogCallback, _default_log

# ---------------------------------------------------------------------------
# Kindle built-in fonts (case-insensitive)
# ---------------------------------------------------------------------------
KINDLE_BUILTIN_FONTS = {
    # English / Latin
    "bookerly",
    "amazon ember",
    "ember",
    "baskerville",
    "caecilia",
    "caecilia condensed",
    "futura",
    "georgia",
    "helvetica",
    "palatino",
    "times new roman",
    "times",
    "arial",
    "courier",
    "courier new",
    "comic sans",
    "comic sans ms",
    "trebuchet ms",
    "verdana",
    "garamond",
    "lucida",
    "optima",
    "athelas",
    "iowan old style",
    # Generic
    "serif",
    "sans-serif",
    "sans serif",
    "monospace",
    "cursive",
    "fantasy",
    "default",
    "initial",
    "inherit",
    "none",
    # Japanese
    "\u6e38\u660e\u671d",
    "\u6e38\u30b4\u30b7\u30c3\u30af",
    "yu mincho",
    "yu gothic",
    "hiragino mincho pron",
    "hiragino mincho",
    "hiragino kaku gothic pron",
    "hiragino kaku gothic",
    "hiragino maru gothic pron",
    "hiragino maru gothic",
    "\u30d2\u30e9\u30ae\u30ce\u660e\u671d pron",
    "\u30d2\u30e9\u30ae\u30ce\u89d2\u30b4 pron",
    "\u30d2\u30e9\u30ae\u30ce\u4e38\u30b4 pron",
    "ms mincho",
    "ms gothic",
    "ms pmincho",
    "ms pgothic",
    "meiryo",
    "\u30e1\u30a4\u30ea\u30aa",
    "osaka",
    "kozuka mincho",
    "kozuka gothic",
    # Simplified Chinese
    "\u5b8b\u4f53",
    "simsun",
    "\u9ed1\u4f53",
    "simhei",
    "\u6977\u4f53",
    "kaiti",
    "\u4eff\u5b8b",
    "fangsong",
    "\u65b9\u6b63\u5170\u4ead\u9ed1",
    "\u65b9\u6b63\u5170\u4ead\u5b8b",
    "source han sans",
    "source han serif",
    "noto sans cjk sc",
    "noto serif cjk sc",
    "pingfang sc",
    "heiti sc",
    "songti sc",
    "kaiti sc",
    "fangsong sc",
    "baiti",
    # Traditional Chinese
    "\u7d30\u660e\u9ad4",
    "mingliu",
    "pmingliu",
    "\u65b0\u7d30\u660e\u9ad4",
    "\u5fae\u8edf\u6b63\u9ed1\u9ad4",
    "microsoft jhenghei",
    "jhenghei",
    "heiti tc",
    "songti tc",
    "noto sans cjk tc",
    "noto serif cjk tc",
    "pingfang tc",
    # Korean
    "batang",
    "gulim",
    "dotum",
    "malgun gothic",
}


def _parse_css_font_faces(css_content: str):
    content = re.sub(r"/\*.*?\*/", "", css_content, flags=re.DOTALL)
    faces = []
    for m in re.finditer(r"@font-face\s*\{([^}]*)\}", content, re.IGNORECASE):
        block = m.group(1)
        fm = re.search(
            r'font-family\s*:\s*["\']?([^";\']+)["\']?\s*;',
            block,
            re.IGNORECASE,
        )
        sm = re.search(r'src\s*:\s*([^;]+);', block, re.IGNORECASE)
        if not fm:
            continue
        family = fm.group(1).strip().strip('"\'').lower()
        src_url = None
        fmt = None
        if sm:
            src_decl = sm.group(1)
            um = re.search(
                r'url\s*\(\s*["\']?([^"\')]+)["\']?\s*\)',
                src_decl,
                re.IGNORECASE,
            )
            if um:
                src_url = um.group(1)
                fm_match = re.search(
                    r'format\s*\(\s*["\']?([^"\')]+)["\']?\s*\)',
                    src_decl,
                    re.IGNORECASE,
                )
                fmt = fm_match.group(1).lower() if fm_match else None
        faces.append({"family": family, "src_url": src_url, "format": fmt})
    return faces


def scan_fonts(temp_dir: str) -> Tuple[Dict[str, Dict], Set[str], list]:
    """
    扫描 EPUB 中的字体引用。
    返回 (embedded: {family_lower: info}, missing: set(family_lower), css_files: [Path])
    """
    base_dir = Path(temp_dir)
    opf_path = find_opf(temp_dir)
    css_files = list(base_dir.rglob("*.css"))
    embedded: Dict[str, Dict] = {}
    missing: Set[str] = set()

    for css_path in css_files:
        content = css_path.read_text(encoding="utf-8")
        faces = _parse_css_font_faces(content)
        for face in faces:
            family = face["family"].strip()
            src_url = face["src_url"]
            if not src_url:
                if family not in KINDLE_BUILTIN_FONTS:
                    missing.add(family)
                continue
            if src_url.startswith(("http://", "https://", "data:")):
                if family not in KINDLE_BUILTIN_FONTS:
                    missing.add(family)
                continue
            if src_url.startswith("/"):
                resolved = (base_dir / src_url.lstrip("/")).resolve()
            else:
                resolved = (css_path.parent / src_url).resolve()
            try:
                resolved.relative_to(base_dir.resolve())
            except ValueError:
                if family not in KINDLE_BUILTIN_FONTS:
                    missing.add(family)
                continue
            if resolved.exists():
                fmt = face["format"]
                if not fmt:
                    ext = resolved.suffix.lower()
                    if ext == ".woff2":
                        fmt = "woff2"
                    elif ext == ".woff":
                        fmt = "woff"
                    elif ext in (".ttf", ".otf"):
                        fmt = ext.lstrip(".")
                embedded[family] = {
                    "path": resolved,
                    "format": fmt,
                    "css_path": css_path,
                    "src_url": src_url,
                }
            else:
                if family not in KINDLE_BUILTIN_FONTS:
                    missing.add(family)
    return embedded, missing, css_files


def handle_fonts(
    temp_dir: str,
    log: LogCallback = _default_log,
    imported_fonts: Optional[Dict[str, str]] = None,
) -> None:
    """
    处理 EPUB 中的字体：导入缺失字体、转换不支持格式、子集化以减小体积。
    imported_fonts: {family_lower: source_file_path}
    """
    imported_fonts = imported_fonts or {}
    opf_path = find_opf(temp_dir)
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    manifest = tree.getroot().find(f"{{{NS_OPF}}}manifest")

    embedded, missing, css_files = scan_fonts(temp_dir)

    # ---- 导入用户提供的缺失字体 ----
    if imported_fonts and missing:
        fonts_dir = base_dir / "Fonts"
        fonts_dir.mkdir(exist_ok=True)
        for family in list(missing):
            if family not in imported_fonts:
                continue
            src_file = Path(imported_fonts[family])
            if not src_file.exists():
                log(f"[Warning] 用户导入的字体文件不存在: {src_file}")
                continue
            target_path = fonts_dir / src_file.name
            counter = 1
            stem = src_file.stem
            while target_path.exists():
                target_path = fonts_dir / f"{stem}_{counter}{src_file.suffix}"
                counter += 1
            shutil.copy(str(src_file), str(target_path))

            # 更新 CSS 中该 font-family 对应的 @font-face src
            for css_path in css_files:
                css_rel = os.path.relpath(target_path, css_path.parent).replace(os.sep, "/")
                css_content = css_path.read_text(encoding="utf-8")
                pattern = re.compile(
                    rf'@font-face\s*\{{[^}}]*font-family\s*:\s*["\']?{re.escape(family)}["\']?\s*;[^}}]*\}}',
                    re.IGNORECASE,
                )

                def _make_replacer(rel):
                    def _replace_src(block_match):
                        block = block_match.group(0)
                        return re.sub(
                            r'url\s*\(\s*["\']?[^"\')]+["\']?\s*\)',
                            f'url({rel})',
                            block,
                            count=1,
                        )
                    return _replace_src

                new_css, count = pattern.subn(_make_replacer(css_rel), css_content)
                if count:
                    css_path.write_text(new_css, encoding="utf-8")

            # 添加 OPF manifest 条目
            if manifest is not None:
                opf_rel = os.path.relpath(target_path, base_dir).replace(os.sep, "/")
                media_type = "font/ttf"
                if target_path.suffix.lower() == ".otf":
                    media_type = "font/otf"
                new_id = f"font-{family.replace(' ', '-')}"
                existing_ids = {
                    item.get("id") for item in manifest.findall(f"{{{NS_OPF}}}item")
                }
                base_id = new_id
                c = 1
                while new_id in existing_ids:
                    new_id = f"{base_id}-{c}"
                    c += 1
                item = etree.SubElement(manifest, f"{{{NS_OPF}}}item")
                item.set("id", new_id)
                item.set("href", opf_rel)
                item.set("media-type", media_type)

            embedded[family] = {
                "path": target_path,
                "format": target_path.suffix.lower().lstrip("."),
                "css_path": css_files[0] if css_files else None,
                "src_url": os.path.relpath(target_path, base_dir).replace(os.sep, "/"),
            }
            missing.discard(family)
            log(f"已导入缺失字体: {family} -> {target_path.name}")

    if missing:
        log(
            f"[Warning] 以下字体缺失且非 Kindle 内置: {', '.join(sorted(missing))}"
        )

    # ---- 收集全书使用到的字符 ----
    chars: Set[str] = set()
    xhtml_items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces={"opf": NS_OPF},
    )
    for item in xhtml_items:
        href = item.get("href")
        if not href:
            continue
        fp = base_dir / href.replace("/", os.sep)
        if not fp.exists():
            continue
        try:
            doc = etree.parse(str(fp))
            chars.update("".join(doc.getroot().itertext()))
        except etree.XMLSyntaxError:
            pass
    chars.update(chr(i) for i in range(32, 127))
    chars.update("\n\r\t")
    text = "".join(chars)

    # ---- 转换格式 + 子集化 ----
    renamed: Dict[str, str] = {}  # old_basename -> new_basename
    for family, info in list(embedded.items()):
        font_path = info["path"]
        if not font_path.exists():
            continue
        original_name = font_path.name
        ext = font_path.suffix.lower()
        converted = False

        if ext in (".woff", ".woff2"):
            try:
                font = TTFont(str(font_path))
                new_path = font_path.with_suffix(".ttf")
                font.save(str(new_path))
                font_path.unlink()
                font_path = new_path
                converted = True
                log(f"字体格式转换: {original_name} -> {font_path.name}")
            except Exception as e:
                log(f"[Warning] 字体格式转换失败 {original_name}: {e}")
                continue

        if font_path.exists() and font_path.stat().st_size > 50 * 1024 and text:
            try:
                font = TTFont(str(font_path))
                options = Options()
                options.hinting = False
                options.desubroutinize = True
                subsetter = Subsetter(options=options)
                subsetter.populate(text=text)
                subsetter.subset(font)
                tmp = font_path.with_suffix(".subset" + font_path.suffix)
                font.save(str(tmp))
                font_path.unlink()
                tmp.rename(font_path)
                log(f"字体子集化: {font_path.name}")
            except Exception as e:
                log(f"[Warning] 字体子集化失败 {font_path.name}: {e}")

        if converted:
            renamed[original_name] = font_path.name
            embedded[family]["path"] = font_path
            embedded[family]["format"] = font_path.suffix.lower().lstrip(".")

    # ---- 更新 CSS 引用 ----
    if renamed:
        for css_path in css_files:
            content = css_path.read_text(encoding="utf-8")
            modified = False
            for old_name, new_name in renamed.items():
                pattern = re.compile(re.escape(old_name) + r'(?=["\'\s)\]])')
                if pattern.search(content):
                    content = pattern.sub(new_name, content)
                    modified = True
            if modified:
                css_path.write_text(content, encoding="utf-8")

    # ---- 更新 OPF manifest ----
    if manifest is not None and renamed:
        for item in manifest.findall(f"{{{NS_OPF}}}item"):
            href = item.get("href")
            if not href:
                continue
            old_name = Path(href).name
            if old_name in renamed:
                new_name = renamed[old_name]
                new_href = str(Path(href).parent / new_name).replace("\\", "/")
                item.set("href", new_href)
                if new_name.endswith(".otf"):
                    item.set("media-type", "font/otf")
                else:
                    item.set("media-type", "font/ttf")
    tree.write(opf_path, encoding="utf-8", xml_declaration=True)
