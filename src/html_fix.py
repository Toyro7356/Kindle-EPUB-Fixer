import os
import re
from pathlib import Path

from lxml import etree

from .constants import NS_OPF, NS_XHTML
from .epub_io import opf_dir
from .utils import write_xhtml_doc


def fix_html_structure(opf_path: str) -> int:
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
                lambda m: m.group(0).rstrip() + "\n<!DOCTYPE html>\n",
                content,
                count=1,
                flags=re.IGNORECASE,
            )
            if "<!DOCTYPE" not in content.upper():
                content = "<!DOCTYPE html>\n" + content

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
                        root.insert(0, etree.Element(f"{{{NS_XHTML}}}head"))
                    if not has_body:
                        root.append(etree.Element(f"{{{NS_XHTML}}}body"))
                    inner = etree.tostring(root, encoding="unicode")
                    content = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n' + inner

        if content != original:
            file_path.write_text(content, encoding="utf-8")
            fixed += 1
    return fixed


def fix_self_closing_tags(opf_path: str) -> int:
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    ns = {"opf": NS_OPF}
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']", namespaces=ns
    )

    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
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


def clean_html_meta(opf_path: str) -> None:
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
            write_xhtml_doc(doc, file_path)


def fix_duplicate_ids(opf_path: str) -> int:
    """
    修复单个 HTML/XHTML 文件内重复的 id。
    对重复 id 递增重命名（如 id -> id-1, id-2），
    并同步更新该文件内所有指向这些 id 的片段引用（href="#id"、src="#id" 等）。
    返回修改的文件数。
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

        # 1. 收集重复 id
        id_counts = {}
        id_elements = []
        for elem in root.iter():
            eid = elem.get("id")
            if eid:
                id_counts[eid] = id_counts.get(eid, 0) + 1
                id_elements.append((elem, eid))

        duplicates = {k for k, v in id_counts.items() if v > 1}
        if not duplicates:
            continue

        # 2. 生成重命名映射（保留第一次出现）
        rename_map = {}
        seen = {}
        for elem, eid in id_elements:
            if eid not in duplicates:
                continue
            seen[eid] = seen.get(eid, 0) + 1
            if seen[eid] == 1:
                continue  # 保留第一个
            new_id = f"{eid}-{seen[eid] - 1}"
            # 确保新 id 也不冲突
            base_new = new_id
            counter = 1
            while new_id in id_counts or new_id in rename_map.values():
                new_id = f"{base_new}-{counter}"
                counter += 1
            rename_map[eid] = new_id
            elem.set("id", new_id)
            id_counts[new_id] = 1

        # 3. 更新文件内所有片段引用
        def _update_ref(value: str, mapping: dict) -> str:
            if not value or value.startswith("http"):
                return value
            for old_id, new_id in mapping.items():
                # 匹配 #old_id 或 url(#old_id)
                if value == f"#{old_id}":
                    return f"#{new_id}"
                if f"#{old_id}" in value:
                    value = value.replace(f"#{old_id}", f"#{new_id}")
            return value

        for elem in root.iter():
            for attr in ("href", "src", "poster", "cite", "longdesc", "formaction", "usemap"):
                val = elem.get(attr)
                if val:
                    new_val = _update_ref(val, rename_map)
                    if new_val != val:
                        elem.set(attr, new_val)
            # SVG xlink:href
            xlink = "{http://www.w3.org/1999/xlink}href"
            val = elem.get(xlink)
            if val:
                new_val = _update_ref(val, rename_map)
                if new_val != val:
                    elem.set(xlink, new_val)

        write_xhtml_doc(doc, file_path)
        fixed += 1
    return fixed
