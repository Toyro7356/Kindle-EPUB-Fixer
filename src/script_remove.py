import os
from pathlib import Path

from lxml import etree

from .constants import NS_OPF, NS_XHTML
from .epub_io import opf_dir
from .utils import write_xhtml_doc


def remove_scripts_from_novel(opf_path: str) -> int:
    """
    从小说 XHTML 中移除 <script> 标签与事件属性，并清理 manifest 中的脚本引用。
    Kobo 等平台的脚本在 Kindle 上无意义，且可能触发 ET 崩溃。
    """
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    ns = {"opf": NS_OPF}
    manifest = tree.getroot().find(f"{{{NS_OPF}}}manifest")
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

    # 清理 manifest 中的 script 条目
    if manifest is not None:
        script_items = manifest.xpath(
            "//opf:manifest/opf:item[contains(@media-type,'javascript') or contains(@href,'.js')]",
            namespaces=ns,
        )
        for si in script_items:
            manifest.remove(si)

    if fixed or script_items:
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)

    return fixed
