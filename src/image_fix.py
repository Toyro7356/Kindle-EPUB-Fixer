import re
from pathlib import Path
from typing import Dict

from lxml import etree
from PIL import Image

from .constants import NS_OPF
from .epub_io import opf_dir


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

            webp_path.unlink()
            mapping[webp_path.name] = new_path.name
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
        old_name = Path(href).name
        if old_name in mapping:
            new_name = mapping[old_name]
            new_href = str(Path(href).parent / new_name).replace("\\", "/")
            item.set("href", new_href)
            item.set("media-type", "image/png" if new_name.endswith(".png") else "image/jpeg")
    tree.write(opf_path, encoding="utf-8", xml_declaration=True)


def update_html_css_webp_refs(opf_path: str, mapping: Dict[str, str]) -> None:
    if not mapping:
        return
    base_dir = Path(opf_dir(opf_path))
    text_exts = {".html", ".htm", ".xhtml", ".css", ".ncx", ".xml"}
    for filepath in base_dir.rglob("*"):
        if not filepath.is_file() or filepath.suffix.lower() not in text_exts:
            continue
        content = filepath.read_text(encoding="utf-8")
        modified = False
        for old_name, new_name in mapping.items():
            pattern = re.compile(re.escape(old_name) + r"(?=[\"'\s)\]])")
            if pattern.search(content):
                content = pattern.sub(new_name, content)
                modified = True
        if modified:
            filepath.write_text(content, encoding="utf-8")
