import os
import re
from pathlib import Path

from lxml import etree

from .constants import NS_OPF, NS_XHTML
from .epub_io import opf_dir
from .opf_metadata import get_effective_book_language
from .text_io import read_text_file, write_text_file
from .utils import write_xhtml_doc


def fix_vertical_writing_mode(opf_path: str) -> int:
    """
    Kindle 对非日文书籍不支持 vertical-rl。将 CSS/xhtml 中的 vertical-rl
    替换为 horizontal-lr，并移除 OPF 中的 primary-writing-mode vertical。
    """
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    root = tree.getroot()
    language = get_effective_book_language(opf_path, root=root)
    if language.startswith("ja"):
        return 0
    modified_opf = False

    # Remove primary-writing-mode meta in OPF
    metadata = root.find(f"{{{NS_OPF}}}metadata")
    if metadata is not None:
        for meta in list(metadata.findall(f"{{{NS_OPF}}}meta")):
            prop = meta.get("property") or meta.get("name") or ""
            text = (meta.text or "").lower()
            if "primary-writing-mode" in prop.lower() or "writing-mode" in prop.lower():
                if "vertical" in text:
                    metadata.remove(meta)
                    modified_opf = True

    # Change spine ppg from rtl to ltr if it was likely vertical book
    spine = root.find(f"{{{NS_OPF}}}spine")
    if spine is not None and spine.get("page-progression-direction") == "rtl":
        # We keep rtl for now unless we find vertical writing mode in CSS
        pass

    if modified_opf:
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)

    # Fix CSS files
    css_files = list(base_dir.rglob("*.css"))
    fixed_css = 0
    for css_path in css_files:
        content = read_text_file(css_path)
        original = content
        # Replace writing-mode values
        content = re.sub(
            r'(writing-mode\s*:\s*)vertical-rl',
            r'\1horizontal-lr',
            content,
            flags=re.IGNORECASE,
        )
        content = re.sub(
            r'(-epub-writing-mode\s*:\s*)vertical-rl',
            r'\1horizontal-lr',
            content,
            flags=re.IGNORECASE,
        )
        content = re.sub(
            r'(-webkit-writing-mode\s*:\s*)vertical-rl',
            r'\1horizontal-lr',
            content,
            flags=re.IGNORECASE,
        )
        if content != original:
            write_text_file(css_path, content)
            fixed_css += 1

    # Fix inline styles in xhtml
    xhtml_items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces={"opf": NS_OPF},
    )
    fixed_html = 0
    for item in xhtml_items:
        href = item.get("href")
        if not href:
            continue
        fp = base_dir / href.replace("/", os.sep)
        if not fp.exists():
            continue
        try:
            doc = etree.parse(str(fp))
        except etree.XMLSyntaxError:
            continue
        root_elem = doc.getroot()
        changed = False
        for elem in root_elem.iter():
            style = elem.get("style") or ""
            if "writing-mode" in style.lower() and "vertical" in style.lower():
                new_style = re.sub(
                    r'writing-mode\s*:\s*vertical-[^;]*',
                    'writing-mode:horizontal-lr',
                    style,
                    flags=re.IGNORECASE,
                )
                elem.set("style", new_style)
                changed = True
            cls = elem.get("class") or ""
            if "vertical" in cls.lower():
                # 保守起见：若 class 名为 vertical-rl 等，仅在不破坏样式前提下保留
                pass
        if changed:
            write_xhtml_doc(doc, fp)
            fixed_html += 1

    return fixed_css + fixed_html
