"""
修复 NCX 目录结构中与 Kindle 转换器不兼容的 navPoint 层级问题。

KindleGen / KDP 对 NCX 的约束：
- 如果一个 navPoint 包含子 navPoint，父 navPoint 的 content src 要么不带锚点，
  要么必须与第一个子 navPoint 的 content src 完全一致。
- 常见报错 "E24011: 父章节中不包含目录部分" 通常因为父节点指向了 #锚点，
  而子节点指向了同一文件的无锚点版本。
"""

from pathlib import Path

from lxml import etree

from .epub_io import opf_dir

NS_NCX = "http://www.daisy.org/z3986/2005/ncx/"


def fix_ncx_parent_navpoints(opf_path: str) -> int:
    """
    修复 NCX 中带子 navPoint 的父 navPoint 的 content src 格式。
    若父 src 含 # 锚点且与第一个子节点指向同一文件，则将父 src 改为无锚点路径。
    返回修改的 navPoint 数量。
    """
    base_dir = Path(opf_dir(opf_path))
    ncx_path = _find_ncx_path(base_dir, opf_path)
    if not ncx_path or not ncx_path.exists():
        return 0

    tree = etree.parse(str(ncx_path))
    ns = {"ncx": NS_NCX}
    navpoints = tree.xpath("//ncx:navPoint", namespaces=ns)
    fixed = 0

    for parent in navpoints:
        children = parent.xpath("ncx:navPoint", namespaces=ns)
        if not children:
            continue

        content_elems = parent.xpath("ncx:content", namespaces=ns)
        if not content_elems:
            continue
        parent_src = content_elems[0].get("src") or ""

        child_content = children[0].xpath("ncx:content", namespaces=ns)
        if not child_content:
            continue
        child_src = child_content[0].get("src") or ""

        parent_file = parent_src.split("#")[0]
        child_file = child_src.split("#")[0]

        # 若父 src 含锚点，且与第一个子节点指向同一文件，则把父改为无锚点
        if "#" in parent_src and parent_file == child_file:
            content_elems[0].set("src", child_file)
            fixed += 1

    if fixed:
        tree.write(str(ncx_path), encoding="utf-8", xml_declaration=True)
    return fixed


def _find_ncx_path(base_dir: Path, opf_path: str) -> Path:
    """根据 OPF 中的 NCX 引用找到 NCX 实际路径。"""
    tree = etree.parse(opf_path)
    ns = {"opf": "http://www.idpf.org/2007/opf"}
    items = tree.xpath(
        "//opf:item[@media-type='application/x-dtbncx+xml']",
        namespaces=ns,
    )
    if not items:
        return Path()
    href = items[0].get("href")
    if not href:
        return Path()
    return base_dir / href.replace("/", "\\" if "\\" in str(base_dir) else "/")
