import os
import re
from pathlib import Path
from typing import Dict

from lxml import etree
from PIL import Image

from .constants import NS_OPF
from .epub_io import opf_dir
from .utils import write_xhtml_doc


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


def clean_invalid_image_refs(opf_path: str) -> int:
    """
    清理 HTML 中无效的图片引用与阅读器专属属性。
    1. 将 <img src="self"> / <img src="none"> / <img src=""> / <img src="#">
       替换为透明 1x1 GIF data URI，避免 Kindle 解析错误。
    2. 移除 zy-enlarge-src="self" / zy-enlarge-src="none" 等
       多看/掌阅专属且值无效的属性。
    3. 对 data-src 懒加载占位符：若 src 缺失或无效，且 data-src 指向有效资源，
       则将 data-src 提升为 src 并移除 data-src。
    返回修改的文件数。
    """
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    ns = {"opf": NS_OPF}
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces=ns,
    )
    placeholder = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
    invalid_src_values = {"self", "none", "#", ""}
    fixed = 0
    for item in items:
        href = item.get("href")
        if not href:
            continue
        fp = base_dir / href.replace("/", os.sep)
        if not fp.exists():
            continue
        try:
            doc = etree.parse(str(fp))
        except etree.XMLSyntaxError:
            continue
        root = doc.getroot()
        changed = False
        for img in root.iter("{http://www.w3.org/1999/xhtml}img"):
            src = img.get("src", "").strip().lower()
            if src in invalid_src_values:
                img.set("src", placeholder)
                if not img.get("alt"):
                    img.set("alt", "")
                changed = True

            # 移除无效的多看/掌阅 zy-enlarge-src
            zy_src = img.get("zy-enlarge-src", "").strip().lower()
            if zy_src in invalid_src_values:
                if "zy-enlarge-src" in img.attrib:
                    del img.attrib["zy-enlarge-src"]
                    changed = True

            # 处理 data-src 懒加载占位符（若 src 为空或无效）
            data_src = img.get("data-src", "").strip()
            if data_src and src in invalid_src_values:
                img.set("src", data_src)
                if "data-src" in img.attrib:
                    del img.attrib["data-src"]
                changed = True

        if changed:
            write_xhtml_doc(doc, fp)
            fixed += 1
    return fixed
