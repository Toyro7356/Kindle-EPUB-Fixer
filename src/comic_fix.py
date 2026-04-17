import os
import re
from pathlib import Path
from typing import Optional, Tuple

from lxml import etree
from PIL import Image

from .constants import NS_OPF, NS_XHTML
from .epub_io import opf_dir
from .text_io import read_text_file, write_text_file


def _detect_resolution_from_viewport(opf_path: str) -> Optional[Tuple[int, int]]:
    """从第一个包含 viewport 的 XHTML 页面中解析分辨率。"""
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces={"opf": NS_OPF},
    )
    for item in items:
        href = item.get("href")
        if not href:
            continue
        fp = base_dir / href.replace("/", os.sep)
        if not fp.exists():
            continue
        try:
            content = read_text_file(fp)
        except Exception:
            continue
        # 匹配 <meta name="viewport" content="width=1066, height=1600" />
        m = re.search(
            r'<meta[^>]+name=["\']viewport["\'][^>]+content=["\']width=(\d+),\s*height=(\d+)["\']',
            content,
            re.IGNORECASE,
        )
        if m:
            return int(m.group(1)), int(m.group(2))
        # 反向匹配 content 在前 name 在后
        m2 = re.search(
            r'<meta[^>]+content=["\']width=(\d+),\s*height=(\d+)["\'][^>]+name=["\']viewport["\']',
            content,
            re.IGNORECASE,
        )
        if m2:
            return int(m2.group(1)), int(m2.group(2))
    return None


def _detect_resolution_from_images(opf_path: str) -> Optional[Tuple[int, int]]:
    """从 manifest 中第一个图片文件解析分辨率。"""
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    items = tree.xpath(
        "//opf:manifest/opf:item[starts-with(@media-type,'image/')]",
        namespaces={"opf": NS_OPF},
    )
    for item in items:
        href = item.get("href")
        if not href:
            continue
        fp = base_dir / href.replace("/", os.sep)
        if not fp.exists():
            continue
        try:
            with Image.open(str(fp)) as img:
                return img.size
        except Exception:
            continue
    return None


def _get_spine_ppd(opf_path: str) -> str:
    """获取 spine 的 page-progression-direction，默认为 ltr。"""
    tree = etree.parse(opf_path)
    spine = tree.getroot().find(f"{{{NS_OPF}}}spine")
    if spine is not None:
        return spine.get("page-progression-direction") or "ltr"
    return "ltr"


def ensure_comic_rendition(opf_path: str) -> bool:
    """
    确保漫画 OPF 中包含 rendition:layout=pre-paginated。
    若缺失，则同时添加 rendition:spread=landscape。
    """
    tree = etree.parse(opf_path)
    root = tree.getroot()
    metadata = root.find(f"{{{NS_OPF}}}metadata")
    if metadata is None:
        return False

    has_layout = False
    has_spread = False
    for meta in metadata.findall(f"{{{NS_OPF}}}meta"):
        prop = meta.get("property") or ""
        if prop == "rendition:layout":
            has_layout = True
            if (meta.text or "").strip().lower() != "pre-paginated":
                meta.text = "pre-paginated"
        if prop == "rendition:spread":
            has_spread = True

    modified = False
    if not has_layout:
        m = etree.SubElement(metadata, f"{{{NS_OPF}}}meta")
        m.set("property", "rendition:layout")
        m.text = "pre-paginated"
        modified = True
    if not has_spread:
        m = etree.SubElement(metadata, f"{{{NS_OPF}}}meta")
        m.set("property", "rendition:spread")
        m.text = "landscape"
        modified = True

    if modified:
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)
    return modified


def add_kindle_comic_meta(opf_path: str) -> bool:
    """
    为 Kindle 漫画兼容性注入 Amazon 专属 meta 标签：
    fixed-layout, original-resolution, book-type, primary-writing-mode,
    zero-gutter, zero-margin, orientation-lock, region-mag
    """
    resolution = _detect_resolution_from_viewport(opf_path)
    if resolution is None:
        resolution = _detect_resolution_from_images(opf_path)
    if resolution is None:
        resolution = (1200, 1600)

    ppd = _get_spine_ppd(opf_path)
    writing_mode = "horizontal-rl" if ppd == "rtl" else "horizontal-lr"

    tree = etree.parse(opf_path)
    root = tree.getroot()
    metadata = root.find(f"{{{NS_OPF}}}metadata")
    if metadata is None:
        return False

    # 收集已有的 name meta
    existing_names = set()
    for meta in metadata.findall(f"{{{NS_OPF}}}meta"):
        name = meta.get("name")
        if name:
            existing_names.add(name.lower())

    required_metas = [
        ("fixed-layout", "true"),
        ("original-resolution", f"{resolution[0]}x{resolution[1]}"),
        ("book-type", "comic"),
        ("primary-writing-mode", writing_mode),
        ("zero-gutter", "true"),
        ("zero-margin", "true"),
        ("orientation-lock", "none"),
        ("region-mag", "true"),
    ]

    modified = False
    for name, content in required_metas:
        if name.lower() in existing_names:
            continue
        m = etree.SubElement(metadata, f"{{{NS_OPF}}}meta")
        m.set("name", name)
        m.set("content", content)
        modified = True

    if modified:
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)
    return modified


def ensure_comic_viewport(opf_path: str) -> int:
    """
    确保所有漫画页面的 XHTML 都包含 viewport meta 标签。
    若页面缺失，则尝试从第一张有 viewport 的页面复制尺寸，
    或从该页面引用的图片推断尺寸。
    """
    base_dir = Path(opf_dir(opf_path))
    tree = etree.parse(opf_path)
    items = tree.xpath(
        "//opf:manifest/opf:item[@media-type='application/xhtml+xml']",
        namespaces={"opf": NS_OPF},
    )

    # 先找一个参考分辨率
    ref_viewport = None
    for item in items:
        href = item.get("href")
        if not href:
            continue
        fp = base_dir / href.replace("/", os.sep)
        if not fp.exists():
            continue
        try:
            content = read_text_file(fp)
        except Exception:
            continue
        m = re.search(
            r'<meta[^>]+name=["\']viewport["\'][^>]+content=["\']width=(\d+),\s*height=(\d+)["\']',
            content,
            re.IGNORECASE,
        )
        if m:
            ref_viewport = f"width={m.group(1)}, height={m.group(2)}"
            break
        m2 = re.search(
            r'<meta[^>]+content=["\']width=(\d+),\s*height=(\d+)["\'][^>]+name=["\']viewport["\']',
            content,
            re.IGNORECASE,
        )
        if m2:
            ref_viewport = f"width={m2.group(1)}, height={m2.group(2)}"
            break

    if ref_viewport is None:
        return 0

    fixed = 0
    viewport_meta = f'<meta name="viewport" content="{ref_viewport}"/>'
    for item in items:
        href = item.get("href")
        if not href:
            continue
        fp = base_dir / href.replace("/", os.sep)
        if not fp.exists():
            continue
        try:
            content = read_text_file(fp)
        except Exception:
            continue
        if "viewport" in content.lower():
            continue
        # 没有 viewport，尝试插入到 </head> 前
        if "</head>" in content.lower():
            content = re.sub(
                r"(</head>)",
                f"  {viewport_meta}\n\\1",
                content,
                flags=re.IGNORECASE,
            )
        else:
            # 如果连 head 都没有，在 <html> 后插入一个极简 head
            content = re.sub(
                r"(<html[^>]*>)",
                f"\\1\n<head>\n  {viewport_meta}\n</head>",
                content,
                flags=re.IGNORECASE,
            )
        write_text_file(fp, content)
        fixed += 1

    return fixed


def sanitize_comic_for_kindle(opf_path: str) -> int:
    """对漫画执行全套 Kindle 兼容性修复，返回修改标志数。"""
    changes = 0
    if ensure_comic_rendition(opf_path):
        changes += 1
    if add_kindle_comic_meta(opf_path):
        changes += 1
    vp_fixed = ensure_comic_viewport(opf_path)
    if vp_fixed:
        changes += 1
    return changes
