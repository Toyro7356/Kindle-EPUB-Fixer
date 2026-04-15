import os
from pathlib import Path

from lxml import etree

from .constants import NS_EPUB, NS_OPF, NS_XHTML
from .epub_io import opf_dir
from .utils import write_xhtml_doc


def fix_footnotes_for_kindle(opf_path: str) -> int:
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    ns = {"opf": NS_OPF}
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']", namespaces=ns
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

        footnote_elems = [
            elem for elem in root.iter()
            if elem.get(f"{{{NS_EPUB}}}type") == "footnote"
        ]

        for elem in footnote_elems:
            for a_tag in list(elem.iter(f"{{{NS_XHTML}}}a")):
                href_val = a_tag.get("href") or ""
                if href_val.startswith("#note_ref"):
                    parent = a_tag.getparent()
                    if parent is not None:
                        idx = list(parent).index(a_tag)
                        for child in reversed(list(a_tag)):
                            parent.insert(idx + 1, child)
                        parent.remove(a_tag)
                        modified = True

            for ol in list(elem.iter(f"{{{NS_XHTML}}}ol")):
                cls = ol.get("class") or ""
                if "duokan-footnote-content" in cls:
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

        if modified:
            write_xhtml_doc(doc, file_path)
            fixed += 1
    return fixed
