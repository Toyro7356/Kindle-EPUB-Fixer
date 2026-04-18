import os
from pathlib import Path

from lxml import etree

from .constants import NS_EPUB, NS_OPF, NS_XHTML
from .epub_io import opf_dir
from .utils import write_xhtml_doc


def _footnote_block_candidates(elem: etree._Element) -> list[etree._Element]:
    return [
        node
        for node in elem.iter()
        if isinstance(node.tag, str)
        and etree.QName(node).localname.lower() in {"p", "div", "li"}
    ]


def _preferred_backlink_container(elem: etree._Element) -> etree._Element:
    for node in elem.iter():
        if not isinstance(node.tag, str):
            continue
        if etree.QName(node).localname.lower() != "div":
            continue
        classes = (node.get("class") or "").split()
        if "footnote-content" in classes:
            return node

    block_candidates = _footnote_block_candidates(elem)
    return block_candidates[-1] if block_candidates else elem


def _is_descendant(ancestor: etree._Element, node: etree._Element) -> bool:
    current = node.getparent()
    while current is not None:
        if current is ancestor:
            return True
        current = current.getparent()
    return False


def _unwrap_element_preserving_children(elem: etree._Element) -> bool:
    parent = elem.getparent()
    if parent is None:
        return False

    insert_at = list(parent).index(elem)
    if elem.text and elem.text.strip():
        if insert_at == 0:
            parent.text = (parent.text or "") + elem.text
        else:
            prev = parent[insert_at - 1]
            prev.tail = (prev.tail or "") + elem.text

    for child in list(elem):
        elem.remove(child)
        parent.insert(insert_at, child)
        insert_at += 1

    if elem.tail:
        if insert_at == 0:
            parent.text = (parent.text or "") + elem.tail
        else:
            prev = parent[insert_at - 1]
            prev.tail = (prev.tail or "") + elem.tail

    parent.remove(elem)
    return True


def _ensure_backlink_shape(
    elem: etree._Element,
    href: str,
    preferred_container: etree._Element,
) -> bool:
    modified = False
    backlinks = [
        a_tag
        for a_tag in elem.iter(f"{{{NS_XHTML}}}a")
        if (a_tag.get("href") or "") == href
    ]

    if backlinks:
        backlink = backlinks[0]
        for extra in backlinks[1:]:
            extra_parent = extra.getparent()
            if extra_parent is not None:
                extra_parent.remove(extra)
                modified = True
    else:
        backlink = etree.Element(f"{{{NS_XHTML}}}a")
        backlink.set("href", href)
        modified = True

    if backlink.get("class") != "footnote-backref":
        backlink.set("class", "footnote-backref")
        modified = True

    has_visible_content = bool((backlink.text or "").strip()) or len(backlink) > 0
    if not has_visible_content:
        backlink.text = "\u21A9"
        modified = True

    current_parent = backlink.getparent()
    if current_parent is not None and _is_descendant(backlink, preferred_container):
        if _unwrap_element_preserving_children(backlink):
            modified = True
        current_parent = backlink.getparent()

    if current_parent is not preferred_container:
        if current_parent is not None:
            current_parent.remove(backlink)
        preferred_container.insert(0, backlink)
        modified = True

    return modified


def _unwrap_nested_note(elem: etree._Element) -> bool:
    if not isinstance(elem.tag, str):
        return False
    if etree.QName(elem).localname.lower() != "note":
        return False

    has_noteref = any(
        node.get(f"{{{NS_EPUB}}}type") == "noteref"
        for node in elem.iter()
    )
    has_footnote = any(
        node.get(f"{{{NS_EPUB}}}type") == "footnote"
        for node in elem.iter()
    )
    if not (has_noteref and has_footnote):
        return False

    return _unwrap_element_preserving_children(elem)


def _normalize_duokan_footnote_lists(elem: etree._Element) -> bool:
    modified = False
    for ol in list(elem.iter(f"{{{NS_XHTML}}}ol")):
        cls = ol.get("class") or ""
        if "duokan-footnote-content" not in cls:
            continue

        new_div = etree.Element(f"{{{NS_XHTML}}}div")
        new_div.set("class", "footnote-content")
        for li in ol.findall(f"{{{NS_XHTML}}}li"):
            for child in list(li):
                new_div.append(child)
            if li.text and li.text.strip():
                p = etree.Element(f"{{{NS_XHTML}}}p")
                p.text = li.text.strip()
                new_div.append(p)

        parent = ol.getparent()
        if parent is not None:
            parent.replace(ol, new_div)
            modified = True

    return modified


def fix_footnotes_for_kindle(opf_path: str) -> int:
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    ns = {"opf": NS_OPF}
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces=ns,
    )
    fixed = 0
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
        note_targets: dict[str, str] = {}

        for elem in list(root.iter()):
            if _unwrap_nested_note(elem):
                modified = True

        for a_tag in root.iter(f"{{{NS_XHTML}}}a"):
            if a_tag.get(f"{{{NS_EPUB}}}type") != "noteref":
                continue

            href_val = a_tag.get("href") or ""
            if not href_val.startswith("#"):
                continue

            note_id = href_val[1:]
            ref_id = a_tag.get("id") or ""
            if not ref_id:
                ref_id = f"note_ref_auto_{len(note_targets) + 1}"
                a_tag.set("id", ref_id)
                modified = True

            note_targets.setdefault(note_id, ref_id)

        footnote_elems = [
            elem for elem in root.iter()
            if elem.get(f"{{{NS_EPUB}}}type") == "footnote"
        ]

        for elem in footnote_elems:
            if _normalize_duokan_footnote_lists(elem):
                modified = True

            footnote_id = elem.get("id") or ""
            backref_id = note_targets.get(footnote_id)
            if not backref_id:
                continue

            target = _preferred_backlink_container(elem)
            if _ensure_backlink_shape(elem, f"#{backref_id}", target):
                modified = True

        if modified:
            write_xhtml_doc(doc, file_path)
            fixed += 1

    return fixed
