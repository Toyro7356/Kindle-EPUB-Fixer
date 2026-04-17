from lxml import etree

from .constants import NS_OPF


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

    _ensure_guide_references(root)

    tree.write(opf_path, encoding="utf-8", xml_declaration=True)


def fix_spine_direction_for_novel(opf_path: str) -> bool:
    tree = etree.parse(opf_path)
    root = tree.getroot()
    metadata = root.find(f"{{{NS_OPF}}}metadata")
    language = ""
    if metadata is not None:
        for dc_lang in metadata.findall(f"{{{NS_OPF}}}language"):
            if dc_lang.text:
                language = dc_lang.text.strip().lower()
                break
    if not language and metadata is not None:
        for dc_lang in metadata:
            if dc_lang.tag == "language" or dc_lang.tag.endswith("}language"):
                if dc_lang.text:
                    language = dc_lang.text.strip().lower()
                    break

    if language.startswith("ja"):
        return False

    spine = root.find(f"{{{NS_OPF}}}spine")
    if spine is not None and spine.get("page-progression-direction") == "rtl":
        spine.set("page-progression-direction", "ltr")
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)
        return True
    return False


def _ensure_guide_references(root: etree._Element) -> None:
    manifest = root.find(f"{{{NS_OPF}}}manifest")
    guide = root.find(f"{{{NS_OPF}}}guide")
    if manifest is None:
        return

    cover_href = None
    toc_href = None
    nav_href = None

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
        if media_type == "application/x-dtbncx+xml" and toc_href is None:
            toc_href = href

    toc_target = nav_href or toc_href
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
