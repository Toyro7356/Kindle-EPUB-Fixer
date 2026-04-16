import os
import re
from pathlib import Path

from lxml import etree

from .constants import NS_EPUB, NS_OPF, NS_XHTML
from .epub_io import opf_dir
from .utils import write_xhtml_doc


def _extract_note_number(href: str) -> str:
    """从 #note011 或 #note_ref011 中提取数字。"""
    m = re.search(r"#note(?:_ref)?(\d+)", href)
    return m.group(1) if m else ""


def _replace_footnote_icons(root) -> bool:
    """
    将 duokan / zhangyue 的大图标 <img> 替换为小的上标文字标记。
    返回是否发生修改。
    """
    modified = False
    for a_tag in list(root.iter(f"{{{NS_XHTML}}}a")):
        cls = a_tag.get("class") or ""
        if "duokan-footnote" not in cls and "zhangyue-footnote" not in cls:
            continue
        # 只处理内部包含 img 的 a 标签
        imgs = a_tag.findall(f"{{{NS_XHTML}}}img")
        if not imgs:
            continue

        num = _extract_note_number(a_tag.get("href") or "")
        label = f"[{num}]" if num else "[注]"

        for img in imgs:
            a_tag.remove(img)

        sup = etree.Element(f"{{{NS_XHTML}}}sup")
        sup.text = label
        a_tag.insert(0, sup)
        modified = True
    return modified


def _unwrap_note_elements(root) -> bool:
    """
    展开非标准的 <note> 标签：
    - 把 <note> 内部非 <aside> 的内容保留在原文位置
    - 把 <aside epub:type="footnote"> 从 <note> 中提取出来，稍后统一移动
    返回是否发生修改。
    """
    modified = False
    for note in list(root.iter()):
        # lxml 中无法直接用 root.iter("note") 匹配无命名空间标签？
        # 实际上 <note> 无命名空间，tag 就是 "note"
        if note.tag != f"{{{NS_XHTML}}}note":
            continue
        parent = note.getparent()
        if parent is None:
            continue

        idx = list(parent).index(note)
        # 提取 aside 元素，剩下的保留
        aside_elems = [child for child in note if isinstance(child.tag, str) and "aside" in child.tag]
        other_children = [child for child in note if child not in aside_elems]

        # 先插入 aside（暂时放在原位，后面会统一移动到 body 末尾）
        for aside in aside_elems:
            parent.insert(idx + 1, aside)
            idx += 1

        # 再插入其他子元素
        for child in other_children:
            parent.insert(idx + 1, child)
            idx += 1

        # 移除 <note> 本身
        parent.remove(note)
        modified = True
    return modified


def _move_footnotes_to_body_end(root) -> bool:
    """
    把所有 <aside epub:type="footnote"> 移动到 <body> 末尾，
    避免它们嵌套在 <p> 或 <note> 中打断正文流。
    返回是否发生修改。
    """
    modified = False
    body = root.find(f".//{{{NS_XHTML}}}body")
    if body is None:
        return False

    footnotes = [
        elem for elem in root.iter()
        if elem.get(f"{{{NS_EPUB}}}type") == "footnote" and elem.tag == f"{{{NS_XHTML}}}aside"
    ]

    for aside in footnotes:
        parent = aside.getparent()
        if parent is body:
            continue
        if parent is None:
            continue
        parent.remove(aside)
        body.append(aside)
        modified = True
    return modified


def _sanitize_footnote_content(root) -> bool:
    """
    对 <aside epub:type="footnote"> 内部进行 Kindle 优化：
    1. 移除回链 <a href="#note_ref...">
    2. 将 ol.duokan-footnote-content 转换为 div.footnote-content
    """
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
    return modified


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

        # Step 1: 替换大图标为上标文字
        if _replace_footnote_icons(root):
            modified = True

        # Step 2: 展开 <note> 标签
        if _unwrap_note_elements(root):
            modified = True

        # Step 3: 将内联 footnote 移到 body 末尾
        if _move_footnotes_to_body_end(root):
            modified = True

        # Step 4: 清理 footnote 内部结构
        if _sanitize_footnote_content(root):
            modified = True

        if modified:
            write_xhtml_doc(doc, file_path)
            fixed += 1

    # Step 5: 清理孤立的 note 图标图片（在所有 HTML 处理完后统一执行一次）
    _remove_orphan_note_images(opf_path)

    return fixed


def _remove_orphan_note_images(opf_path: str) -> int:
    """
    清理 manifest 中不再被引用的 note 图标图片（如 note.png / note.webp）。
    返回移除的条目数。
    """
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    root = tree.getroot()
    manifest = root.find(f"{{{NS_OPF}}}manifest")
    if manifest is None:
        return 0

    # 收集所有 note 图片候选
    note_items = []
    for item in manifest.findall(f"{{{NS_OPF}}}item"):
        href = item.get("href") or ""
        lower = href.lower()
        if "note" in lower and lower.endswith((".png", ".webp", ".jpg", ".jpeg", ".gif", ".bmp", ".svg")):
            note_items.append((item, href))

    if not note_items:
        return 0

    # 扫描所有 HTML/CSS 文本内容，检查是否还有引用
    referenced = set()
    for filepath in base_dir.rglob("*"):
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in {".html", ".htm", ".xhtml", ".css", ".ncx"}:
            continue
        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception:
            continue
        for _, href in note_items:
            filename = Path(href).name
            if filename in content:
                referenced.add(href)

    removed = 0
    for item, href in note_items:
        if href in referenced:
            continue
        fp = base_dir / href.replace("/", os.sep)
        if fp.exists():
            fp.unlink()
        manifest.remove(item)
        removed += 1

    if removed:
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)
    return removed
