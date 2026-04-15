import os
from pathlib import Path

from lxml import etree

from .constants import NS_OPF, NS_SVG, NS_XHTML, NS_XLINK
from .epub_io import opf_dir
from .utils import write_xhtml_doc


def convert_svg_pages_to_img(opf_path: str) -> int:
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    ns = {"opf": NS_OPF}
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']", namespaces=ns
    )
    converted = 0
    for item in items:
        href = item.get("href")
        if not href:
            continue
        file_path = base_dir / href.replace("/", os.sep)
        if not file_path.exists():
            continue
        try:
            doc = etree.parse(str(file_path))
        except etree.XMLSyntaxError:
            continue

        root = doc.getroot()
        modified = False
        for svg in root.iter(f"{{{NS_SVG}}}svg"):
            images = list(svg.iter(f"{{{NS_SVG}}}image"))
            if not images:
                continue
            src = images[0].get(f"{{{NS_XLINK}}}href") or images[0].get("href")
            if not src:
                continue
            img_elem = etree.Element(f"{{{NS_XHTML}}}img", src=src, alt="")
            # 若 SVG 有 viewBox，优先用 height:auto 保持比例，避免 reflowable 模式下 height:100% 塌陷为 0
            if svg.get("viewBox"):
                img_elem.set("style", "width:100%; height:auto; display:block;")
            else:
                img_elem.set("style", "width:100%; height:100%; display:block;")
            parent = svg.getparent()
            if parent is not None:
                parent.replace(svg, img_elem)
                modified = True

        if modified:
            head = root.find(f".//{{{NS_XHTML}}}head")
            if head is not None:
                for meta in list(head.findall(f".//{{{NS_XHTML}}}meta")):
                    if meta.get("name") == "Adept.expected.resource":
                        head.remove(meta)
            write_xhtml_doc(doc, file_path)
            converted += 1
    return converted


def remove_stale_svg_properties(opf_path: str) -> int:
    """
    若 manifest 中声明了 properties=svg，但对应 xhtml 文件内已无 <svg 标签，则移除该属性。
    防止 Kindle ET 因声明与实际内容不符而崩溃。
    """
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    root = tree.getroot()
    manifest = root.find(f"{{{NS_OPF}}}manifest")
    if manifest is None:
        return 0
    fixed = 0
    for item in manifest.findall(f"{{{NS_OPF}}}item"):
        if item.get("media-type") != "application/xhtml+xml":
            continue
        props = item.get("properties") or ""
        parts = props.split()
        if "svg" not in parts:
            continue
        href = item.get("href")
        if not href:
            continue
        fp = base_dir / href.replace("/", os.sep)
        if not fp.exists():
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                has_svg = "<svg" in f.read()
        except Exception:
            continue
        if not has_svg:
            parts = [p for p in parts if p != "svg"]
            if parts:
                item.set("properties", " ".join(parts))
            else:
                item.attrib.pop("properties", None)
            fixed += 1
    if fixed:
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)
    return fixed
