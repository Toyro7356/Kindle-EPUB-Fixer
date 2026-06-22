"""ESJZone scrambled font extraction and EPUB embedding helpers."""

from __future__ import annotations

import base64
import hashlib
import io
import re
from dataclasses import dataclass
from urllib.parse import unquote, unquote_to_bytes

import lxml.etree as etree
from fontTools.ttLib import TTFont


@dataclass(frozen=True)
class EsjzoneEmbeddedFont:
    family: str
    css_family: str
    asset_id: str
    filename: str
    data: bytes
    media_type: str


_DATA_CSS_RE = re.compile(r"data:text/css[^,]*,(?P<payload>.*)$", re.IGNORECASE | re.DOTALL)
_FONT_FACE_RE = re.compile(r"@font-face\s*\{(?P<body>.*?)\}", re.IGNORECASE | re.DOTALL)
_FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*(?P<family>\"[^\"]+\"|'[^']+'|[^;{}\s]+)", re.IGNORECASE)
_FONT_URL_RE = re.compile(r"url\(\s*(?P<quote>[\"']?)(?P<url>data:[^)\"']+)(?P=quote)\s*\)", re.IGNORECASE | re.DOTALL)


def extract_esjzone_font(doc: etree._Element) -> EsjzoneEmbeddedFont | None:
    css = _extract_data_css(doc)
    if not css:
        return None

    face = _FONT_FACE_RE.search(css)
    if not face:
        return None

    block = face.group("body")
    family_match = _FONT_FAMILY_RE.search(block)
    url_match = _FONT_URL_RE.search(block)
    if not family_match or not url_match:
        return None

    family = _strip_css_string(family_match.group("family"))
    font_bytes, media_type = _decode_data_uri(url_match.group("url"))
    if not font_bytes:
        return None

    converted, suffix, converted_media_type = _convert_font_for_epub(font_bytes, media_type)
    digest = hashlib.sha1(converted).hexdigest()[:12]
    css_family = f"esjzone-font-{digest}"
    return EsjzoneEmbeddedFont(
        family=family,
        css_family=css_family,
        asset_id=f"esjzone-font-{digest}",
        filename=f"esjzone-font-{digest}{suffix}",
        data=converted,
        media_type=converted_media_type,
    )


def chapter_font_css(font: EsjzoneEmbeddedFont) -> str:
    quoted_family = _css_quote(font.css_family)
    return (
        "@font-face {\n"
        f"  font-family: \"{quoted_family}\";\n"
        f"  src: url(\"asset:{font.asset_id}\");\n"
        "}\n"
        ".esjzone-scrambled-font {\n"
        f"  font-family: \"{quoted_family}\", serif;\n"
        "}"
    )


def rewrite_chapter_font_family(content: etree._Element, font: EsjzoneEmbeddedFont) -> bool:
    changed = False
    root = content
    for element in content.iter():
        if not isinstance(element.tag, str):
            continue
        style = element.get("style")
        if not style or "font-family" not in style.lower():
            continue
        updated = _replace_font_family(style, font.family, font.css_family)
        if updated != style:
            element.set("style", updated)
            _append_class(element, "esjzone-scrambled-font")
            changed = True

    if changed:
        return True

    applied = False
    for child in root:
        if isinstance(child.tag, str):
            _append_class(child, "esjzone-scrambled-font")
            applied = True

    if applied:
        return True

    _append_class(root, "esjzone-scrambled-font")
    return True


def _extract_data_css(doc: etree._Element) -> str:
    for link in doc.xpath("//link[@href]"):
        href = (link.get("href") or "").strip()
        if not href.lower().startswith("data:text/css"):
            continue
        match = _DATA_CSS_RE.match(href)
        if not match:
            continue
        return unquote(match.group("payload"))

    for style in doc.xpath("//style"):
        text = style.text or ""
        if "@font-face" in text.lower():
            return text
    return ""


def _decode_data_uri(uri: str) -> tuple[bytes, str]:
    if "," not in uri:
        return b"", ""
    meta, payload = uri.split(",", 1)
    media_type = meta[5:].split(";", 1)[0].lower() if meta.lower().startswith("data:") else ""
    try:
        data = base64.b64decode(payload) if "base64" in meta.lower() else unquote_to_bytes(payload)
    except Exception:
        return b"", ""
    return data, media_type


def _convert_font_for_epub(data: bytes, media_type: str) -> tuple[bytes, str, str]:
    font = TTFont(io.BytesIO(data))
    try:
        has_cff = "CFF " in font
        if "GSUB" in font:
            # ESJZone's scrambled fonts rely on cmap glyph swaps. Some reading
            # engines apply GSUB alternates and partially undo that visual swap.
            del font["GSUB"]
        if has_cff:
            _make_cff_kindle_compatible(font)
        font.flavor = None
        output = io.BytesIO()
        font.save(output)
    finally:
        font.close()

    if has_cff:
        return output.getvalue(), ".otf", "font/otf"
    return output.getvalue(), ".ttf", "font/ttf"


def _make_cff_kindle_compatible(font: TTFont) -> None:
    cff = font["CFF "].cff
    if not cff:
        return

    top_dict = cff[0]
    glyph_order = font.getGlyphOrder()
    has_cid_markers = (
        hasattr(top_dict, "ROS")
        or "ROS" in top_dict.rawDict
        or "VORG" in font
        or any(name.startswith("cid") for name in glyph_order)
    )
    if not has_cid_markers:
        return

    # Load lazy CFF data before rewriting names.
    _ = top_dict.charset
    _ = top_dict.CharStrings

    cmap = font.getBestCmap() or {}
    glyph_to_cp = {name: cp for cp, name in cmap.items()}
    rename_map: dict[str, str] = {}
    new_glyph_order: list[str] = []

    for gid, name in enumerate(glyph_order):
        if name == ".notdef":
            new_name = ".notdef"
        elif name in glyph_to_cp:
            new_name = f"uni{glyph_to_cp[name]:04X}"
        else:
            new_name = f"glyph{gid:05d}"
        rename_map[name] = new_name
        new_glyph_order.append(new_name)

    charstrings = getattr(top_dict, "CharStrings", None)
    if charstrings is not None and hasattr(charstrings, "charStrings"):
        charstrings.charStrings = {
            rename_map.get(old_name, old_name): value
            for old_name, value in charstrings.charStrings.items()
        }

    if getattr(top_dict, "charset", None):
        top_dict.charset = [rename_map.get(name, name) for name in top_dict.charset]

    font.setGlyphOrder(new_glyph_order)

    if "cmap" in font:
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap = {
                    cp: rename_map.get(name, name)
                    for cp, name in table.cmap.items()
                }

    try:
        cff.desubroutinize()
    except Exception:
        pass

    fd_array = getattr(top_dict, "FDArray", None)
    if fd_array is not None and len(fd_array) > 0 and hasattr(fd_array[0], "Private"):
        top_dict.Private = fd_array[0].Private

    for attr in ("FDArray", "FDSelect", "ROS", "CIDCount", "CIDFontVersion", "XUID", "UIDBase"):
        if hasattr(top_dict, attr):
            delattr(top_dict, attr)
        if attr in top_dict.rawDict:
            del top_dict.rawDict[attr]

    if "VORG" in font:
        del font["VORG"]


def _strip_css_string(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _css_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _replace_font_family(style: str, original_family: str, css_family: str) -> str:
    family_pattern = re.escape(original_family)
    return re.sub(
        rf"(font-family\s*:\s*)([^;]+)",
        lambda match: match.group(1) + _replace_family_list(match.group(2), family_pattern, css_family),
        style,
        flags=re.IGNORECASE,
    )


def _replace_family_list(value: str, original_family_pattern: str, css_family: str) -> str:
    parts = [part.strip() for part in value.split(",")]
    updated: list[str] = []
    replaced = False
    for part in parts:
        unquoted = _strip_css_string(part)
        if re.fullmatch(original_family_pattern, unquoted, flags=re.IGNORECASE):
            updated.append(f'"{_css_quote(css_family)}"')
            replaced = True
        elif part:
            updated.append(part)
    if not replaced:
        updated.insert(0, f'"{_css_quote(css_family)}"')
    return ", ".join(updated)


def _append_class(element: etree._Element, class_name: str) -> None:
    classes = [item for item in (element.get("class") or "").split() if item]
    if class_name not in classes:
        classes.append(class_name)
        element.set("class", " ".join(classes))
