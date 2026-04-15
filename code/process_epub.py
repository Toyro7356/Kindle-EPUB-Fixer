import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, Optional

from lxml import etree
from PIL import Image

# ---------------------------------------------------------------------------
# 命名空间
# ---------------------------------------------------------------------------
NS_CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
NS_OPF = "http://www.idpf.org/2007/opf"
NS_XHTML = "http://www.w3.org/1999/xhtml"
NS_SVG = "http://www.w3.org/2000/svg"
NS_XLINK = "http://www.w3.org/1999/xlink"
NS_EPUB = "http://www.idpf.org/2007/ops"

NSMAP = {"container": NS_CONTAINER, "opf": NS_OPF}


# ---------------------------------------------------------------------------
# 基础 EPUB 工具
# ---------------------------------------------------------------------------
def unpack_epub(epub_path: str, temp_dir: str) -> None:
    """将 .epub 文件解压到临时目录。"""
    with zipfile.ZipFile(epub_path, "r") as zf:
        zf.extractall(temp_dir)


def repack_epub(temp_dir: str, output_path: str) -> None:
    """
    将临时目录重新打包成标准 .epub 文件。
    确保 mimetype 是第一个被添加且不压缩（STORED）的条目。
    """
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        mimetype_path = os.path.join(temp_dir, "mimetype")
        if os.path.exists(mimetype_path):
            zf.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)

        for root, dirs, files in os.walk(temp_dir):
            dirs[:] = [d for d in dirs if d != "__MACOSX"]
            for file in files:
                abs_path = os.path.join(root, file)
                arcname = os.path.relpath(abs_path, temp_dir).replace(os.sep, "/")
                if arcname == "mimetype":
                    continue
                zf.write(abs_path, arcname)


# ---------------------------------------------------------------------------
# OPF 定位
# ---------------------------------------------------------------------------
def find_opf(temp_dir: str) -> str:
    """通过 META-INF/container.xml 定位 OPF 文件。"""
    container_path = os.path.join(temp_dir, "META-INF", "container.xml")
    if not os.path.exists(container_path):
        raise FileNotFoundError("META-INF/container.xml 不存在")

    tree = etree.parse(container_path)
    rootfiles = tree.xpath("//container:rootfiles/container:rootfile", namespaces=NSMAP)
    for rf in rootfiles:
        full_path = rf.get("full-path")
        if full_path:
            return os.path.join(temp_dir, full_path.replace("/", os.sep))
    raise FileNotFoundError("container.xml 中未找到 rootfile")


def opf_dir(opf_path: str) -> str:
    return os.path.dirname(opf_path)


# ---------------------------------------------------------------------------
# 书籍类型检测：漫画 vs 小说
# ---------------------------------------------------------------------------
def detect_book_type(opf_path: str) -> str:
    """
    根据 OPF 元数据和页面内容自动判断书籍类型。
    如果 rendition:layout=pre-paginated，或超过 50% 的页面是 SVG 图片页，
    则判定为 comic，否则为 novel。
    """
    tree = etree.parse(opf_path)
    root = tree.getroot()
    ns = {"opf": NS_OPF}

    metadata = root.find(f"{{{NS_OPF}}}metadata")
    if metadata is not None:
        for meta in metadata.findall(f"{{{NS_OPF}}}meta"):
            if meta.get("property") == "rendition:layout":
                val = (meta.text or "").strip().lower()
                if val == "pre-paginated":
                    return "comic"

    manifest = root.find(f"{{{NS_OPF}}}manifest")
    items = []
    if manifest is not None:
        items = manifest.xpath(
            "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
            namespaces=ns,
        )

    base_dir = Path(opf_dir(opf_path))
    svg_pages = 0
    total = 0
    for item in items:
        href = item.get("href")
        if not href:
            continue
        file_path = base_dir / href.replace("/", os.sep)
        if not file_path.exists():
            continue
        total += 1
        try:
            doc = etree.parse(str(file_path))
        except etree.XMLSyntaxError:
            continue
        root_elem = doc.getroot()
        for svg in root_elem.iter(f"{{{NS_SVG}}}svg"):
            if list(svg.iter(f"{{{NS_SVG}}}image")):
                svg_pages += 1
                break

    if total > 0 and svg_pages / total >= 0.5:
        return "comic"
    return "novel"


# ---------------------------------------------------------------------------
# 修复 1：webp 图片转 Kindle 兼容格式
# ---------------------------------------------------------------------------
def convert_webp_images(opf_path: str) -> Dict[str, str]:
    """
    将 OPF 目录及其子目录下的所有 .webp 转换为 .jpg（无透明）或 .png（有透明）。
    返回文件名映射：{old_filename: new_filename}
    """
    base_dir = Path(opf_dir(opf_path))
    webp_files = list(base_dir.rglob("*.webp"))
    if not webp_files:
        return {}

    filename_mapping: Dict[str, str] = {}

    for webp_path in webp_files:
        with Image.open(webp_path) as img:
            has_alpha = False
            if img.mode in ("RGBA", "LA"):
                has_alpha = True
            elif img.mode == "P" and "transparency" in img.info:
                has_alpha = True

            ext = ".png" if has_alpha else ".jpg"

            new_path = webp_path.with_suffix(ext)
            stem = webp_path.stem
            counter = 1
            while new_path.exists() and new_path != webp_path:
                new_path = webp_path.with_name(f"{stem}_{counter}{ext}")
                counter += 1

            if ext == ".jpg":
                img.convert("RGB").save(new_path, "JPEG", quality=95)
            else:
                img.save(new_path, "PNG")

            webp_path.unlink()
            filename_mapping[webp_path.name] = new_path.name

    return filename_mapping


def update_opf_webp_refs(opf_path: str, filename_mapping: Dict[str, str]) -> None:
    """更新 OPF manifest 中 webp 的 href 与 media-type。"""
    if not filename_mapping:
        return

    tree = etree.parse(opf_path)
    root = tree.getroot()
    manifest = root.find(f"{{{NS_OPF}}}manifest")
    if manifest is None:
        return

    for item in manifest.findall(f"{{{NS_OPF}}}item"):
        href = item.get("href")
        if not href:
            continue
        old_name = Path(href).name
        if old_name in filename_mapping:
            new_name = filename_mapping[old_name]
            new_href = str(Path(href).parent / new_name).replace("\\", "/")
            item.set("href", new_href)
            if new_name.endswith(".png"):
                item.set("media-type", "image/png")
            else:
                item.set("media-type", "image/jpeg")

    tree.write(opf_path, encoding="utf-8", xml_declaration=True)


def update_html_css_webp_refs(opf_path: str, filename_mapping: Dict[str, str]) -> None:
    """更新 HTML/XHTML/CSS 中对 webp 的引用。"""
    if not filename_mapping:
        return

    base_dir = Path(opf_dir(opf_path))
    text_exts = {".html", ".htm", ".xhtml", ".css", ".ncx", ".xml"}

    for filepath in base_dir.rglob("*"):
        if not filepath.is_file() or filepath.suffix.lower() not in text_exts:
            continue
        content = filepath.read_text(encoding="utf-8")
        modified = False
        for old_name, new_name in filename_mapping.items():
            pattern = re.compile(re.escape(old_name) + r"(?=[\"'\s)\]])")
            if pattern.search(content):
                content = pattern.sub(new_name, content)
                modified = True
        if modified:
            filepath.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# 修复 2：SVG 图片页转换为普通 <img>（仅对小说执行，漫画保留 SVG）
# ---------------------------------------------------------------------------
def convert_svg_pages_to_img(opf_path: str) -> int:
    """
    遍历 OPF manifest 中所有 XHTML，如果页面主体是 SVG 且内含 <image>，
    则将 SVG 替换为等效的 <img> 标签。返回处理的页面数。
    """
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    ns = {"opf": NS_OPF}
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']", namespaces=ns
    )

    converted = 0
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

        for svg in root.iter(f"{{{NS_SVG}}}svg"):
            images = list(svg.iter(f"{{{NS_SVG}}}image"))
            if not images:
                continue

            src = images[0].get(f"{{{NS_XLINK}}}href") or images[0].get("href")
            if not src:
                continue

            img_elem = etree.Element(f"{{{NS_XHTML}}}img", src=src, alt="")
            img_elem.set("style", "width:100%; height:100%; display:block;")

            parent = svg.getparent()
            if parent is not None:
                parent.replace(svg, img_elem)
                modified = True

        if modified:
            head = root.find(f".//{{{NS_XHTML}}}head")
            if head is not None:
                for meta in list(head.findall(f".//{{{NS_XHTML}}}meta")):
                    if meta.get("name") == "Adept.expected.resource":
                        head.remove(meta)
            doc.write(
                str(file_path),
                encoding="utf-8",
                xml_declaration=True,
                doctype="<!DOCTYPE html>",
            )
            converted += 1

    return converted


# ---------------------------------------------------------------------------
# 修复 3：清理 HTML 中的 DRM/不兼容 meta
# ---------------------------------------------------------------------------
def clean_html_meta(opf_path: str) -> None:
    """删除所有 XHTML/HTML 中的 Adept.expected.resource meta。"""
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    ns = {"opf": NS_OPF}
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']", namespaces=ns
    )
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
        head = root.find(f".//{{{NS_XHTML}}}head")
        if head is None:
            continue
        modified = False
        for meta in list(head.findall(f".//{{{NS_XHTML}}}meta")):
            if meta.get("name") == "Adept.expected.resource":
                head.remove(meta)
                modified = True
        if modified:
            doc.write(
                str(file_path),
                encoding="utf-8",
                xml_declaration=True,
                doctype="<!DOCTYPE html>",
            )


# ---------------------------------------------------------------------------
# 修复 4：优化脚注结构以支持 Kindle Pop-up Footnote
# ---------------------------------------------------------------------------
def fix_footnotes_for_kindle(opf_path: str) -> int:
    """
    清理脚注结构：
    1. 移除 aside[epub:type="footnote"] 内部的回链 <a>。
    2. 简化多看风格的 ol/li 包裹结构。
    3. 保留 epub:type="noteref" 和 epub:type="footnote"。
    返回处理的文件数。
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

        # 先收集所有 footnote 元素快照，避免在迭代过程中修改树导致跳过
        footnote_elems = [
            elem for elem in root.iter()
            if elem.get(f"{{{NS_EPUB}}}type") == "footnote"
        ]

        for elem in footnote_elems:
            # 移除回链 <a href="#note_ref...">
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

            # 简化 duokan ol/li 结构
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
            doc.write(
                str(file_path),
                encoding="utf-8",
                xml_declaration=True,
                doctype="<!DOCTYPE html>",
            )
            fixed += 1

    return fixed


# ---------------------------------------------------------------------------
# 修复 5：补全所有 HTML/XHTML 的 DOCTYPE 和基本结构
# ---------------------------------------------------------------------------
def fix_html_structure(opf_path: str) -> int:
    """
    确保所有 XHTML/HTML 文件都有标准的 XML 声明、<!DOCTYPE html>。
    仅在确实缺失 head/body 时才使用 lxml 回写。
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

        content = file_path.read_text(encoding="utf-8")
        original = content

        content = content.lstrip()
        if not content.startswith("<?xml"):
            content = '<?xml version="1.0" encoding="UTF-8"?>\n' + content

        if "<!DOCTYPE" not in content.upper():
            content = re.sub(
                r"<\?xml[^?]*\?>\s*",
                lambda m: m.group(0) + "<!DOCTYPE html>\n",
                content,
                count=1,
                flags=re.IGNORECASE,
            )
            if "<!DOCTYPE" not in content.upper():
                content = "<!DOCTYPE html>\n" + content

        # 检测缺失 head/body 的极端情况
        try:
            doc = etree.fromstring(content.encode("utf-8"))
        except etree.XMLSyntaxError:
            pass
        else:
            root = doc
            tag = root.tag if root.tag else ""
            if tag == f"{{{NS_XHTML}}}html" or tag.lower() == "html":
                has_head = root.find(f"{{{NS_XHTML}}}head") is not None
                has_body = root.find(f"{{{NS_XHTML}}}body") is not None
                if not has_head or not has_body:
                    if not has_head:
                        head = etree.Element(f"{{{NS_XHTML}}}head")
                        root.insert(0, head)
                    if not has_body:
                        body = etree.Element(f"{{{NS_XHTML}}}body")
                        root.append(body)
                    inner = etree.tostring(root, encoding="unicode")
                    content = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n' + inner

        if content != original:
            file_path.write_text(content, encoding="utf-8")
            fixed += 1

    return fixed


# ---------------------------------------------------------------------------
# 修复 6：修复 HTML 中不允许的自闭合标签（<p/> 等）
# ---------------------------------------------------------------------------
def fix_self_closing_tags(opf_path: str) -> int:
    """
    Kindle 的 Enhanced Typesetting 引擎使用 HTML5 解析器，
    对 <p/>、<div/>、<span/> 等非 void 元素的自闭合标签支持极差。
    此函数将它们全部改写为开闭标签对。必须放在所有 DOM 修改之后执行。
    """
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    ns = {"opf": NS_OPF}
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']", namespaces=ns
    )

    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
        # SVG common void-like tags (safe to keep self-closing)
        "path", "rect", "circle", "ellipse", "line", "polyline",
        "polygon", "stop", "use", "animate", "animateTransform",
    }
    NON_VOID_TAGS = {
        "p", "div", "span", "li", "h1", "h2", "h3", "h4", "h5", "h6",
        "dt", "dd", "td", "th", "caption", "legend", "option", "blockquote",
        "pre", "address", "em", "strong", "small", "s", "cite", "q", "dfn",
        "abbr", "data", "time", "code", "var", "samp", "kbd", "sub", "sup",
        "i", "b", "u", "mark", "ruby", "rt", "rp", "bdi", "bdo", "ins", "del",
        "label", "fieldset", "button", "select", "textarea", "form", "table",
        "thead", "tbody", "tfoot", "tr", "colgroup", "col", "dl", "ul", "ol",
        "nav", "section", "article", "aside", "header", "footer", "hgroup",
        "figure", "figcaption", "main", "details", "summary", "command", "menu",
        "title", "style", "script", "noscript", "body", "html", "head",
    }
    pattern = re.compile(rf"<({'|'.join(NON_VOID_TAGS)})(\s+[^>]*)?\s*/>")

    fixed = 0
    for item in items:
        href = item.get("href")
        if not href:
            continue
        file_path = base_dir / href.replace("/", os.sep)
        if not file_path.exists():
            continue

        content = file_path.read_text(encoding="utf-8")
        original = content

        def replacer(m):
            tag = m.group(1).lower()
            if tag in VOID_TAGS:
                return m.group(0)
            attrs = m.group(2) or ""
            return f"<{tag}{attrs}></{tag}>"

        content = pattern.sub(replacer, content)
        if content != original:
            file_path.write_text(content, encoding="utf-8")
            fixed += 1

    return fixed


# ---------------------------------------------------------------------------
# 修复 7：OPF 清理（保留 EPUB 3，根据书籍类型智能保留/删除属性）
# ---------------------------------------------------------------------------
def sanitize_opf_for_kindle(opf_path: str, book_type: str) -> None:
    """
    保留 EPUB 3 格式，根据漫画/小说类型清理 Kindle 不兼容的元数据。
    漫画：保留 fixed-layout 相关声明，支持 Panel View、双页展开、RTL。
    小说：移除 scripted 和 spine 的 page-spread 等属性，保留 RTL。
    """
    tree = etree.parse(opf_path)
    root = tree.getroot()

    # 1. metadata
    metadata = root.find(f"{{{NS_OPF}}}metadata")
    if metadata is not None:
        for meta in list(metadata.findall(f"{{{NS_OPF}}}meta")):
            name = meta.get("name")
            prop = meta.get("property") or ""
            if name == "Adept.expected.resource":
                metadata.remove(meta)
                continue
            if book_type == "novel" and prop.startswith("rendition:"):
                # 小说不需要 fixed-layout 声明，但保留 ibooks 等增强 meta
                metadata.remove(meta)
                continue

    # 2. manifest
    manifest = root.find(f"{{{NS_OPF}}}manifest")
    if manifest is not None:
        for item in manifest.findall(f"{{{NS_OPF}}}item"):
            props = item.get("properties") or ""
            parts = props.split()
            if not parts:
                continue
            if book_type == "comic":
                # 漫画保留 svg 等属性，但删除 scripted（如果有的话，漫画通常没有）
                if "scripted" in parts:
                    parts = [p for p in parts if p != "scripted"]
                    if parts:
                        item.set("properties", " ".join(parts))
                    else:
                        item.attrib.pop("properties", None)
                continue
            else:
                # 小说：只保留 nav，删除 scripted 等
                new_parts = [p for p in parts if p == "nav"]
                if new_parts:
                    item.set("properties", " ".join(new_parts))
                else:
                    item.attrib.pop("properties", None)

    # 3. spine
    spine = root.find(f"{{{NS_OPF}}}spine")
    if spine is not None:
        # 始终保留 page-progression-direction="rtl"（如果存在）
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


# ---------------------------------------------------------------------------
# 主处理入口
# ---------------------------------------------------------------------------
def process_files(temp_dir: str) -> None:
    """
    智能修复入口：自动检测书籍类型（漫画/小说），
    在保留原有显示意图、格式、排版、字体的前提下进行 Kindle 兼容性修复。
    """
    try:
        opf_path = find_opf(temp_dir)
    except FileNotFoundError as e:
        print(f"[Warning] 无法定位 OPF: {e}")
        return

    book_type = detect_book_type(opf_path)
    print(f"[Info] 检测到书籍类型: {book_type}")

    # 1. webp 转换（通用）
    mapping = convert_webp_images(opf_path)
    if mapping:
        print(f"[Info] 转换了 {len(mapping)} 张 webp 图片")
        update_opf_webp_refs(opf_path, mapping)
        update_html_css_webp_refs(opf_path, mapping)

    # 2. SVG 图片页处理：小说转 <img>，漫画保留 SVG
    if book_type == "novel":
        svg_converted = convert_svg_pages_to_img(opf_path)
        if svg_converted:
            print(f"[Info] 转换了 {svg_converted} 个 SVG 图片页面为 <img>")

    # 3. 清理 HTML DRM meta（通用）
    clean_html_meta(opf_path)

    # 4. 修复脚注结构以支持 Kindle Pop-up Footnote（通用）
    ff_fixed = fix_footnotes_for_kindle(opf_path)
    if ff_fixed:
        print(f"[Info] 修复了 {ff_fixed} 个文件的脚注结构以支持 Kindle Pop-up")

    # 5. 补全 HTML 结构（通用）
    fixed_count = fix_html_structure(opf_path)
    if fixed_count:
        print(f"[Info] 已修复 {fixed_count} 个 HTML 文件的 DOCTYPE/结构")

    # 6. OPF 智能清理（根据类型）
    sanitize_opf_for_kindle(opf_path, book_type)
    print(f"[Info] 已根据 {book_type} 类型清理 OPF 不兼容元数据")

    # 7. 最后一步：修复所有自闭合标签（通用，必须最后执行）
    sc_fixed = fix_self_closing_tags(opf_path)
    if sc_fixed:
        print(f"[Info] 已修复 {sc_fixed} 个 HTML 文件中的自闭合标签")


def process_epub(epub_path: str, output_path: Optional[str] = None) -> str:
    """处理 EPUB 文件的主函数。"""
    if output_path is None:
        base, ext = os.path.splitext(epub_path)
        output_path = f"{base}.processed{ext}"

    epub_path = os.path.abspath(epub_path)
    output_path = os.path.abspath(output_path)

    with tempfile.TemporaryDirectory() as temp_dir:
        unpack_epub(epub_path, temp_dir)
        process_files(temp_dir)
        repack_epub(temp_dir, output_path)

    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(f"用法: python {os.path.basename(__file__)} <input.epub> [output.epub]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    result = process_epub(input_file, output_file)
    print(f"处理完成: {result}")
