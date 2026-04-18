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


def _has_standard_kindle_footnotes(root: etree._Element) -> bool:
    footnote_ids = {
        (elem.get("id") or "").strip()
        for elem in root.iter()
        if elem.get(f"{{{NS_EPUB}}}type") == "footnote" and (elem.get("id") or "").strip()
    }
    if not footnote_ids:
        return False

    for a_tag in root.iter(f"{{{NS_XHTML}}}a"):
        if a_tag.get(f"{{{NS_EPUB}}}type") != "noteref":
            continue
        href = (a_tag.get("href") or "").strip()
        if not href.startswith("#"):
            continue
        if href[1:] in footnote_ids:
            return True
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

        # Leave already-standard noteref -> footnote pairs untouched.
        # Kindle popup behavior is sensitive here, and adding synthetic backrefs
        # can regress books whose note structure already works.
        if _has_standard_kindle_footnotes(root):
            continue

        for elem in list(root.iter()):
            if _unwrap_nested_note(elem):
                modified = True

        footnote_elems = [
            elem for elem in root.iter()
            if elem.get(f"{{{NS_EPUB}}}type") == "footnote"
        ]

        for elem in footnote_elems:
            if _normalize_duokan_footnote_lists(elem):
                modified = True

        if modified:
            write_xhtml_doc(doc, file_path)
            fixed += 1

    return fixed
