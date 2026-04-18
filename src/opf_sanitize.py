import os
from pathlib import Path

from lxml import etree

from .constants import NS_OPF
from .epub_io import opf_dir
from .opf_metadata import get_effective_book_language


def sanitize_opf_for_kindle(opf_path: str, book_type: str, preserve_layout: bool = False) -> None:
    tree = etree.parse(opf_path)
    root = tree.getroot()

    metadata = root.find(f"{{{NS_OPF}}}metadata")
    if metadata is not None:
        for meta in list(metadata.findall(f"{{{NS_OPF}}}meta")):
            name = meta.get("name")
            prop = meta.get("property") or ""
            if name == "Adept.expected.resource":
                metadata.remove(meta)
                continue
            if not preserve_layout and book_type == "novel" and prop.startswith("rendition:"):
                metadata.remove(meta)
                continue

    manifest = root.find(f"{{{NS_OPF}}}manifest")
    if manifest is not None:
        for item in manifest.findall(f"{{{NS_OPF}}}item"):
            props = item.get("properties") or ""
            parts = props.split()
            if not parts:
                continue
            if book_type == "comic":
                if "scripted" in parts:
                    parts = [p for p in parts if p != "scripted"]
                    if parts:
                        item.set("properties", " ".join(parts))
                    else:
                        item.attrib.pop("properties", None)
                continue
            if not preserve_layout:
                new_parts = [p for p in parts if p in ("nav", "svg", "cover-image")]
                if new_parts:
                    item.set("properties", " ".join(new_parts))
                else:
                    item.attrib.pop("properties", None)

    spine = root.find(f"{{{NS_OPF}}}spine")
    if spine is not None:
        for itemref in spine.findall(f"{{{NS_OPF}}}itemref"):
            if not preserve_layout:
                itemref.attrib.pop("properties", None)
        if "toc" not in spine.attrib and manifest is not None:
            ncx_id = None
            for item in manifest.findall(f"{{{NS_OPF}}}item"):
                if item.get("media-type") == "application/x-dtbncx+xml":
                    ncx_id = item.get("id")
                    break
            if ncx_id:
                spine.set("toc", ncx_id)

    _ensure_guide_references(root, opf_path)

    tree.write(opf_path, encoding="utf-8", xml_declaration=True)


def fix_spine_direction_for_novel(opf_path: str) -> bool:
    tree = etree.parse(opf_path)
    root = tree.getroot()
    language = get_effective_book_language(opf_path, root=root)

    if language.startswith("ja"):
        return False

    spine = root.find(f"{{{NS_OPF}}}spine")
    if spine is not None and spine.get("page-progression-direction") == "rtl":
        spine.set("page-progression-direction", "ltr")
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)
        return True
    return False


def _ensure_guide_references(root: etree._Element, opf_path: str) -> None:
    manifest = root.find(f"{{{NS_OPF}}}manifest")
    guide = root.find(f"{{{NS_OPF}}}guide")
    if manifest is None:
        return

    cover_href = None
    nav_href = None
    ncx_href = None

    for item in manifest.findall(f"{{{NS_OPF}}}item"):
        href = item.get("href")
        if not href:
            continue
        props = (item.get("properties") or "").split()
        media_type = item.get("media-type") or ""
        if "cover-image" in props and cover_href is None:
            cover_href = href
        if "nav" in props and nav_href is None:
            nav_href = href
        if media_type == "application/x-dtbncx+xml" and ncx_href is None:
            ncx_href = href

    toc_target = nav_href or _resolve_ncx_toc_target(opf_path, ncx_href)
    if not cover_href and not toc_target:
        return

    if guide is None:
        guide = etree.SubElement(root, f"{{{NS_OPF}}}guide")

    existing_types = {ref.get("type"): ref for ref in guide.findall(f"{{{NS_OPF}}}reference")}

    if cover_href and "cover" not in existing_types:
        ref = etree.SubElement(guide, f"{{{NS_OPF}}}reference")
        ref.set("type", "cover")
        ref.set("title", "Cover")
        ref.set("href", cover_href)

    if toc_target and "toc" not in existing_types:
        ref = etree.SubElement(guide, f"{{{NS_OPF}}}reference")
        ref.set("type", "toc")
        ref.set("title", "Table of Contents")
        ref.set("href", toc_target)


def _resolve_ncx_toc_target(opf_path: str, ncx_href: str | None) -> str | None:
    if not ncx_href:
        return None

    base_dir = Path(opf_dir(opf_path))
    ncx_path = base_dir / ncx_href.replace("/", os.sep)
    if not ncx_path.exists():
        return None

    try:
        tree = etree.parse(str(ncx_path))
    except Exception:
        return None

    ns = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
    for content in tree.xpath("//ncx:navMap//ncx:content", namespaces=ns):
        src = (content.get("src") or "").strip()
        if src and not src.lower().endswith(".ncx"):
            return src
    return None
