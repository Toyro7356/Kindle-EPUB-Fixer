import os
from pathlib import Path

from lxml import etree

from .constants import NS_OPF, NS_SVG, NS_XHTML, NS_XLINK
from .epub_io import opf_dir
from .utils import write_xhtml_doc


_ALLOWED_SIMPLE_SVG_TAGS = {
    f"{{{NS_SVG}}}svg",
    f"{{{NS_SVG}}}image",
    f"{{{NS_SVG}}}title",
    f"{{{NS_SVG}}}desc",
    f"{{{NS_SVG}}}metadata",
}


def _has_meaningful_xhtml_text(elem: etree._Element) -> bool:
    for node in elem.iter():
        if not isinstance(node.tag, str):
            continue
        if node.tag.startswith(f"{{{NS_SVG}}}"):
            continue
        if (node.text or "").strip() or (node.tail or "").strip():
            return True
    return False


def _find_simple_image_svg(root: etree._Element) -> tuple[etree._Element | None, str | None]:
    """
    Only convert SVG wrappers that are effectively a full-page single image shell.
    This avoids damaging decorative or genuinely authored SVG layouts.
    """
    body = root.find(f".//{{{NS_XHTML}}}body")
    if body is None or _has_meaningful_xhtml_text(body):
        return None, None

    svgs = list(body.iter(f"{{{NS_SVG}}}svg"))
    if len(svgs) != 1:
        return None, None

    svg = svgs[0]
    for node in svg.iter():
        if node.tag not in _ALLOWED_SIMPLE_SVG_TAGS:
            return None, None

    images = list(svg.iter(f"{{{NS_SVG}}}image"))
    if len(images) != 1:
        return None, None

    image = images[0]
    if image.getparent() is not svg:
        return None, None

    src = image.get(f"{{{NS_XLINK}}}href") or image.get("href")
    if not src:
        return None, None

    return svg, src


def convert_svg_pages_to_img(opf_path: str) -> int:
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    ns = {"opf": NS_OPF}
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces=ns,
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
        svg, src = _find_simple_image_svg(root)
        if svg is None or src is None:
            continue

        img_elem = etree.Element(f"{{{NS_XHTML}}}img", src=src, alt="")
        img_elem.set("style", "width:100%; height:auto; display:block;")
        parent = svg.getparent()
        if parent is None:
            continue
        parent.replace(svg, img_elem)

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
    If manifest declares properties=svg but the XHTML no longer contains SVG,
    remove the stale property so Kindle does not infer the wrong rendering mode.
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
