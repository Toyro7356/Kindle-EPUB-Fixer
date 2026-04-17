import os
import re
from html.entities import html5
from pathlib import Path

from lxml import etree

from .constants import NS_OPF, NS_XHTML
from .epub_io import opf_dir
from .text_io import read_text_file, write_text_file
from .utils import write_xhtml_doc


BROKEN_CLOSING_TAG_RE = re.compile(r"(?<!<)/([A-Za-z][A-Za-z0-9:_-]*)>")
HTML_ENTITY_RE = re.compile(r"&([A-Za-z][A-Za-z0-9]+);")
BARE_AMP_RE = re.compile(r"&(?!#\d+;|#x[0-9A-Fa-f]+;|[A-Za-z][A-Za-z0-9]+;)")

_XML_PREDEFINED_ENTITIES = {"amp", "lt", "gt", "apos", "quot"}


def repair_common_markup_damage(content: str) -> str:
    content = BROKEN_CLOSING_TAG_RE.sub(r"</\1>", content)

    def _replace_entity(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in _XML_PREDEFINED_ENTITIES:
            return match.group(0)
        replacement = html5.get(f"{name};")
        if replacement:
            return replacement
        return match.group(0)

    content = HTML_ENTITY_RE.sub(_replace_entity, content)
    content = BARE_AMP_RE.sub("&amp;", content)
    return content


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

        content = read_text_file(file_path)
        original = content
        content = repair_common_markup_damage(content)

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
            write_text_file(file_path, content)
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

        content = read_text_file(file_path)
        original = content
        content = repair_common_markup_damage(content)

        def replacer(m):
            tag = m.group(1).lower()
            if tag in VOID_TAGS:
                return m.group(0)
            attrs = m.group(2) or ""
            return f"<{tag}{attrs}></{tag}>"

        content = pattern.sub(replacer, content)
        if content != original:
            write_text_file(file_path, content)
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
