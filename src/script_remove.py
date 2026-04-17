import os
from pathlib import Path

from lxml import etree

from .constants import NS_OPF, NS_XHTML
from .epub_io import opf_dir
from .utils import write_xhtml_doc

KNOWN_HELPER_SCRIPT_NAMES = {
    "script.js",
    "notereplace.js",
    "torich-1.0.js",
}


def _is_known_helper_script(src: str) -> bool:
    name = Path(src).name.lower()
    return name in KNOWN_HELPER_SCRIPT_NAMES or name.startswith("jquery-")


def remove_known_helper_scripts(opf_path: str) -> int:
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    root = tree.getroot()
    ns = {"opf": NS_OPF}
    manifest = root.find(f"{{{NS_OPF}}}manifest")
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces=ns,
    )

    helper_hrefs: set[str] = set()
    if manifest is not None:
        for item in manifest.findall(f"{{{NS_OPF}}}item"):
            href = item.get("href") or ""
            media_type = (item.get("media-type") or "").lower()
            if "javascript" in media_type or href.lower().endswith(".js"):
                if _is_known_helper_script(href):
                    helper_hrefs.add(href.replace("\\", "/"))

    fixed_docs = 0
    cleaned_items: set[str] = set()
    for item in items:
        href = item.get("href") or ""
        href_name = Path(href).name.lower()
        file_path = base_dir / href.replace("/", os.sep)
        if not file_path.exists():
            continue
        try:
            doc = etree.parse(str(file_path))
        except etree.XMLSyntaxError:
            continue

        modified = False
        for script in list(doc.getroot().iter(f"{{{NS_XHTML}}}script")):
            src = (script.get("src") or "").replace("\\", "/")
            remove_script = False
            if src and _is_known_helper_script(src):
                remove_script = True
            if href_name in {"navigation-documents.xhtml", "navigation-toc.xhtml", "toc.xhtml", "toc.html", "toc.htm"}:
                remove_script = True
            if remove_script:
                parent = script.getparent()
                if parent is not None:
                    parent.remove(script)
                    modified = True

        if modified:
            for elem in doc.getroot().iter():
                for attr in list(elem.attrib):
                    if attr.startswith("on"):
                        elem.attrib.pop(attr)

        if modified:
            write_xhtml_doc(doc, file_path)
            fixed_docs += 1
            cleaned_items.add(href.replace("\\", "/"))

    removed_manifest_items = 0
    if manifest is not None and helper_hrefs:
        for item in list(manifest.findall(f"{{{NS_OPF}}}item")):
            href = (item.get("href") or "").replace("\\", "/")
            if href in helper_hrefs or _is_known_helper_script(href):
                manifest.remove(item)
                removed_manifest_items += 1
                continue
            if href in cleaned_items:
                props = (item.get("properties") or "").split()
                if "scripted" in props:
                    props = [part for part in props if part != "scripted"]
                    if props:
                        item.set("properties", " ".join(props))
                    else:
                        item.attrib.pop("properties", None)

    deleted_files = 0
    for js_path in base_dir.rglob("*.js"):
        if _is_known_helper_script(js_path.name):
            try:
                js_path.unlink()
                deleted_files += 1
            except OSError:
                pass

    if fixed_docs or removed_manifest_items or deleted_files:
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)

    return fixed_docs + removed_manifest_items + deleted_files


def remove_scripts_from_book(opf_path: str) -> int:
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    ns = {"opf": NS_OPF}
    manifest = tree.getroot().find(f"{{{NS_OPF}}}manifest")
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

        for script in list(root.iter(f"{{{NS_XHTML}}}script")):
            parent = script.getparent()
            if parent is not None:
                parent.remove(script)
                modified = True

        for elem in root.iter():
            for attr in list(elem.attrib.keys()):
                if attr.startswith("on"):
                    elem.attrib.pop(attr)
                    modified = True

        if modified:
            write_xhtml_doc(doc, file_path)
            fixed += 1

    script_items = []
    if manifest is not None:
        script_items = manifest.xpath(
            "//opf:manifest/opf:item[contains(@media-type,'javascript') or contains(@href,'.js')]",
            namespaces=ns,
        )
        for si in script_items:
            manifest.remove(si)

    deleted_js = 0
    for js_path in base_dir.rglob("*.js"):
        try:
            js_path.unlink()
            deleted_js += 1
        except OSError:
            pass

    if fixed or script_items or deleted_js:
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)

    return fixed
