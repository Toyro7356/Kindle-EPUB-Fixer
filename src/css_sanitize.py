import os
import re
from pathlib import Path

from lxml import etree

from .constants import NS_OPF
from .epub_io import opf_dir
from .text_io import read_text_file, write_text_file
from .utils import write_xhtml_doc


_RISKY_TRANSFORM_VALUE_RE = re.compile(
    r"(matrix|matrix3d|skew|skewx|skewy|perspective|rotate|rotatex|rotatey|rotatez|rotate3d|translate3d|scale3d)\s*\(",
    re.IGNORECASE,
)
_TRANSFORM_DECL_RE = re.compile(
    r"(?P<prop>-webkit-transform|-ms-transform|-moz-transform|-o-transform|transform)\s*:\s*(?P<value>[^;]+);",
    re.IGNORECASE,
)
_QUARTER_TURN_ROTATE_RE = re.compile(
    r"rotate(?:z)?\(\s*(?P<angle>[+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*(?P<unit>deg|turn|rad)\s*\)",
    re.IGNORECASE,
)


def _is_risky_rotate_value(transform_value: str) -> bool:
    for match in _QUARTER_TURN_ROTATE_RE.finditer(transform_value):
        angle = float(match.group("angle"))
        unit = match.group("unit").lower()
        if unit == "deg":
            normalized = angle % 360
            if normalized in {90.0, 270.0}:
                return True
        elif unit == "turn":
            normalized = angle % 1
            if normalized in {0.25, 0.75}:
                return True
        elif unit == "rad":
            normalized = angle % 6.283185307179586
            if abs(normalized - 1.5707963267948966) <= 1e-3 or abs(normalized - 4.71238898038469) <= 1e-3:
                return True
    return False


def _sanitize_style_text(style_text: str) -> tuple[str, bool]:
    changed = False

    def _replace_transform(match: re.Match[str]) -> str:
        nonlocal changed
        value = (match.group("value") or "").strip()
        normalized = value.lower()
        if normalized == "none":
            return match.group(0)
        if _RISKY_TRANSFORM_VALUE_RE.search(value) or _is_risky_rotate_value(value):
            changed = True
            return f"{match.group('prop')}: none;"
        return match.group(0)

    updated = _TRANSFORM_DECL_RE.sub(_replace_transform, style_text)
    if changed:
        updated = re.sub(r";{2,}", ";", updated)
    return updated, changed


def downgrade_risky_css_for_kindle(opf_path: str) -> int:
    base_dir = Path(opf_dir(opf_path))
    changed_files = 0

    for css_path in base_dir.rglob("*.css"):
        original = read_text_file(css_path)
        updated, changed = _sanitize_style_text(original)
        if changed and updated != original:
            write_text_file(css_path, updated)
            changed_files += 1

    tree = etree.parse(opf_path)
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces={"opf": NS_OPF},
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

        modified = False
        for elem in doc.getroot().iter():
            style = elem.get("style")
            if not style:
                continue
            updated_style, changed = _sanitize_style_text(style)
            if changed and updated_style != style:
                elem.set("style", updated_style.strip())
                modified = True

        if modified:
            write_xhtml_doc(doc, file_path)
            changed_files += 1

    return changed_files
