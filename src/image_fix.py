import posixpath
import re
from pathlib import Path
from typing import Dict
from urllib.parse import quote, unquote

import lxml.etree as etree
from PIL import Image

from .constants import NS_OPF
from .epub_io import opf_dir
from .text_io import read_text_file, write_text_file


def _relative_to_base(path: Path, base_dir: Path) -> str:
    return path.relative_to(base_dir).as_posix()


def _normalize_href_path(href: str) -> str:
    return posixpath.normpath(unquote(href).replace("\\", "/")).lstrip("/")


def _quote_ref(path: str) -> str:
    return "/".join(quote(segment, safe="-._~") for segment in path.split("/"))


def _reference_variants(path: str) -> set[str]:
    quoted = _quote_ref(path)
    variants = {path, quoted}
    if not path.startswith("."):
        variants.add(f"./{path}")
        variants.add(f"./{quoted}")
    return variants


def convert_webp_images(opf_path: str) -> Dict[str, str]:
    base_dir = Path(opf_dir(opf_path))
    webp_files = list(base_dir.rglob("*.webp"))
    if not webp_files:
        return {}

    mapping: Dict[str, str] = {}
    for webp_path in webp_files:
        with Image.open(webp_path) as img:
            has_alpha = img.mode in ("RGBA", "LA") or (
                img.mode == "P" and "transparency" in img.info
            )
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

            old_rel = _relative_to_base(webp_path, base_dir)
            webp_path.unlink()
            mapping[old_rel] = _relative_to_base(new_path, base_dir)
    return mapping


def update_opf_webp_refs(opf_path: str, mapping: Dict[str, str]) -> None:
    if not mapping:
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
        old_rel = _normalize_href_path(href)
        if old_rel in mapping:
            new_href = mapping[old_rel]
            item.set("href", new_href)
            item.set("media-type", "image/png" if new_href.endswith(".png") else "image/jpeg")
    tree.write(opf_path, encoding="utf-8", xml_declaration=True)


def update_html_css_webp_refs(opf_path: str, mapping: Dict[str, str]) -> None:
    if not mapping:
        return
    base_dir = Path(opf_dir(opf_path))
    text_exts = {".html", ".htm", ".xhtml", ".css", ".ncx", ".xml"}
    for filepath in base_dir.rglob("*"):
        if not filepath.is_file() or filepath.suffix.lower() not in text_exts:
            continue
        content = read_text_file(filepath)
        doc_rel = _relative_to_base(filepath, base_dir)
        doc_dir = posixpath.dirname(doc_rel) or "."
        updated = content
        for old_rel, new_rel in mapping.items():
            old_ref = posixpath.relpath(old_rel, doc_dir)
            new_ref = posixpath.relpath(new_rel, doc_dir)
            for old_variant in _reference_variants(old_ref):
                pattern = re.compile(re.escape(old_variant) + r"(?=[\"'\s)\]#]|$)")
                updated = pattern.sub(_quote_ref(new_ref), updated)
        if updated != content:
            content = updated
            write_text_file(filepath, content)
