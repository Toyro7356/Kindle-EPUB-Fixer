from lxml import etree

from .constants import NS_OPF


def sanitize_opf_for_kindle(opf_path: str, book_type: str) -> None:
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
            if book_type == "novel" and prop.startswith("rendition:"):
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
            else:
                # novel: 保留 nav / svg / cover-image，其余清除
                new_parts = [p for p in parts if p in ("nav", "svg", "cover-image")]
                if new_parts:
                    item.set("properties", " ".join(new_parts))
                else:
                    item.attrib.pop("properties", None)

    spine = root.find(f"{{{NS_OPF}}}spine")
    if spine is not None:
        for itemref in spine.findall(f"{{{NS_OPF}}}itemref"):
            if book_type == "novel":
                itemref.attrib.pop("properties", None)
        if "toc" not in spine.attrib and manifest is not None:
            ncx_id = None
            for item in manifest.findall(f"{{{NS_OPF}}}item"):
                if item.get("media-type") == "application/x-dtbncx+xml":
                    ncx_id = item.get("id")
                    break
            if ncx_id:
                spine.set("toc", ncx_id)

    tree.write(opf_path, encoding="utf-8", xml_declaration=True)


def fix_spine_direction_for_novel(opf_path: str) -> bool:
    """
    对非日文小说，若 spine 使用 page-progression-direction=rtl，
    Kindle 可能将其误判为竖排，因此改为 ltr 以提升兼容性。
    """
    tree = etree.parse(opf_path)
    root = tree.getroot()
    metadata = root.find(f"{{{NS_OPF}}}metadata")
    language = ""
    if metadata is not None:
        for dc_lang in metadata.findall(f"{{{NS_OPF}}}language"):
            if dc_lang.text:
                language = dc_lang.text.strip().lower()
                break
    # 如果语言为空，尝试从 dc:language (无命名空间) 获取
    if not language and metadata is not None:
        for dc_lang in metadata:
            if dc_lang.tag == "language" or dc_lang.tag.endswith("}language"):
                if dc_lang.text:
                    language = dc_lang.text.strip().lower()
                    break

    # 日语保留 rtl，其他语言改为 ltr
    if language.startswith("ja"):
        return False

    spine = root.find(f"{{{NS_OPF}}}spine")
    if spine is not None and spine.get("page-progression-direction") == "rtl":
        spine.set("page-progression-direction", "ltr")
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)
        return True
    return False
