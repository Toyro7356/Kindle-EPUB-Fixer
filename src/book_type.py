import os
from pathlib import Path

from lxml import etree

from .constants import NS_OPF, NS_SVG, NS_XHTML
from .epub_io import opf_dir


def detect_book_type(opf_path: str) -> str:
    tree = etree.parse(opf_path)
    root = tree.getroot()
    ns = {"opf": NS_OPF}

    metadata = root.find(f"{{{NS_OPF}}}metadata")
    if metadata is not None:
        for meta in metadata.findall(f"{{{NS_OPF}}}meta"):
            if meta.get("property") == "rendition:layout":
                if (meta.text or "").strip().lower() == "pre-paginated":
                    return "comic"

    manifest = root.find(f"{{{NS_OPF}}}manifest")
    items = []
    if manifest is not None:
        items = manifest.xpath(
            "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
            namespaces=ns,
        )

    base_dir = Path(opf_dir(opf_path))
    svg_pages = total = 0
    total_text_len = 0
    total_p_count = 0
    for item in items:
        href = item.get("href")
        if not href:
            continue
        file_path = base_dir / href.replace("/", os.sep)
        if not file_path.exists():
            continue
        total += 1
        try:
            doc = etree.parse(str(file_path))
        except etree.XMLSyntaxError:
            continue
        xhtml_root = doc.getroot()
        body = xhtml_root.find(f".//{{{NS_XHTML}}}body")
        p_count = len(body.findall(f".//{{{NS_XHTML}}}p")) if body is not None else 0
        text_len = len("".join(body.itertext())) if body is not None else 0
        total_p_count += p_count
        total_text_len += text_len

        has_svg_image = False
        for svg in xhtml_root.iter(f"{{{NS_SVG}}}svg"):
            if list(svg.iter(f"{{{NS_SVG}}}image")):
                has_svg_image = True
                break

        if has_svg_image:
            # 小说中的插图页虽然包含全屏 SVG，但周围通常有文字说明或较多段落。
            # 如果页面内段落>2或文字长度>300，视为文字页，避免误判为漫画。
            if p_count > 2 or text_len > 300:
                continue
            svg_pages += 1

    # 如果全书存在大量文字段落，明确为小说（防止插图极多的小说被误判）
    if total > 0 and (total_p_count >= 50 or total_text_len >= 15000):
        return "novel"

    # 阈值从 0.5 提高到 0.85，防止插图较多的小说被误判为漫画
    if total > 0 and svg_pages / total >= 0.85:
        return "comic"
    return "novel"
