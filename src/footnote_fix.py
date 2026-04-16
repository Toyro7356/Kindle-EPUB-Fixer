import os
import re
from pathlib import Path

from lxml import etree

from .constants import NS_EPUB, NS_OPF, NS_XHTML
from .epub_io import opf_dir
from .utils import write_xhtml_doc


def fix_footnotes_for_kindle(opf_path: str) -> int:
    """
    优化脚注结构以支持 Kindle Pop-up，同时保持原有视觉样式不变。

    处理策略：
    1. 限制 duokan/zhangyue 脚注图标 (note.png/webp) 的显示尺寸，
       避免在 Kindle 上渲染得过大，但保留图片本身和可点击性。
    2. 移除 footnote 内容块中的回链 <a href="#note_ref...">（Kindle 不需要）。
    3. 将 ol.duokan-footnote-content 转为 div.footnote-content（提升兼容性）。
    4. 不移动 <aside> 位置，不拆解 <note> 标签，不替换图标为文字。
    """
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

        # ---- 1. 限制 note 图标尺寸 ----
        for img in root.iter(f"{{{NS_XHTML}}}img"):
            src = (img.get("src") or "").lower()
            cls = (img.get("class") or "").lower()
            alt = (img.get("alt") or "").lower()
            # 识别 note 图标（路径含 note，或 class 含 footnote，或 alt 含 note/注）
            is_note_icon = (
                "note" in Path(src).name
                or "footnote" in cls
                or "zhangyue-footnote" in cls
                or "duokan-footnote" in cls
                or alt in ("note", "注")
            )
            if not is_note_icon:
                continue
            # 如果已经有限制尺寸的样式/属性，跳过
            style = img.get("style") or ""
            if "max-width" in style or "max-height" in style or "width" in style or "height" in style:
                continue
            if img.get("width") or img.get("height"):
                continue
            # 添加温和的限制：最大 1.2em，保持 inline 特性
            new_style = "max-width:1.2em; max-height:1.2em; vertical-align:super;".strip()
            if style:
                new_style = style.rstrip(";") + "; " + new_style
            img.set("style", new_style)
            # 确保 alt 有值
            if not img.get("alt"):
                img.set("alt", "注")
            modified = True

        # ---- 2. 移除回链 <a href="#note_ref..."> ----
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

        # ---- 3. 转换 ol.duokan-footnote-content 为 div ----
        for ol in list(root.iter(f"{{{NS_XHTML}}}ol")):
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
