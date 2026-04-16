"""
EPUB 输出独立校验器
在 process_epub 完成后对生成的 EPUB 文件做规范性检查。
"""

import os
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from .constants import NS_OPF


def _parse_xml_safe(data: bytes) -> ET.Element:
    """安全解析 XML，忽略命名空间前缀方便遍历。"""
    return ET.fromstring(data)


def _find_opf_path(zf: zipfile.ZipFile) -> str:
    container = zf.read("META-INF/container.xml")
    root = _parse_xml_safe(container)
    for rf in root.iter():
        if rf.tag.endswith("rootfile"):
            fp = rf.get("full-path")
            if fp:
                return fp
    raise ValueError("container.xml 中未找到 rootfile")


class EpubValidationError(Exception):
    """EPUB 校验不通过时抛出的异常。"""

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def validate_epub(epub_path: str, book_type: str = "") -> List[str]:
    """
    对 EPUB 文件执行全套校验。
    返回错误列表（空列表表示校验通过）。
    """
    errors: List[str] = []
    warnings: List[str] = []

    try:
        with zipfile.ZipFile(epub_path, "r") as zf:
            # 1. 基础容器检查
            if "META-INF/container.xml" not in zf.namelist():
                errors.append("缺少 META-INF/container.xml")
                return errors

            # 2. OPF 检查
            try:
                opf_path = _find_opf_path(zf)
            except ValueError as e:
                errors.append(str(e))
                return errors

            if opf_path not in zf.namelist():
                errors.append(f"OPF 文件不存在: {opf_path}")
                return errors

            try:
                opf_data = zf.read(opf_path)
                opf_root = _parse_xml_safe(opf_data)
            except ET.ParseError as e:
                errors.append(f"OPF 解析失败: {e}")
                return errors

            # 3. 收集 manifest / spine / metadata 信息
            manifest: Dict[str, Dict[str, str]] = {}  # id -> {href, media-type}
            manifest_hrefs: Set[str] = set()
            manifest_ids: Set[str] = set()
            xhtml_items: List[Tuple[str, str]] = []  # (id, href)
            image_items: List[Tuple[str, str]] = []  # (id, href)
            script_items: List[str] = []

            rendition_layout = ""
            amazon_meta: Dict[str, str] = {}
            languages: List[str] = []

            for elem in opf_root.iter():
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

                if tag == "item":
                    iid = elem.get("id")
                    href = elem.get("href")
                    mt = elem.get("media-type") or ""
                    if not iid:
                        errors.append("manifest 中存在缺少 id 的 item")
                        continue
                    if iid in manifest_ids:
                        errors.append(f"manifest 中存在重复的 id: {iid}")
                    manifest_ids.add(iid)
                    if href:
                        manifest_hrefs.add(href)
                        if mt == "application/xhtml+xml":
                            xhtml_items.append((iid, href))
                        elif mt.startswith("image/"):
                            image_items.append((iid, href))
                        elif "javascript" in mt or (href and href.lower().endswith(".js")):
                            script_items.append(href)
                    manifest[iid] = {"href": href or "", "media-type": mt}

                elif tag == "itemref":
                    pass  # spine 在下面单独处理

                elif tag == "meta":
                    prop = elem.get("property") or ""
                    name = elem.get("name") or ""
                    if prop == "rendition:layout":
                        rendition_layout = (elem.text or "").strip().lower()
                    if name:
                        amazon_meta[name] = elem.get("content") or ""

                elif tag == "language":
                    lang = (elem.text or "").strip()
                    if lang:
                        languages.append(lang)

            # 4. manifest 文件存在性检查
            opf_dir = Path(opf_path).parent.as_posix()
            for iid, info in manifest.items():
                href = info["href"]
                if not href:
                    continue
                resolved = (Path(opf_dir) / href).as_posix() if opf_dir and opf_dir != "." else href
                if resolved not in zf.namelist():
                    errors.append(f"manifest 引用的文件不存在: {href} (id={iid})")

            # 5. spine 一致性检查
            spine_idrefs: List[str] = []
            spine = None
            for elem in opf_root.iter():
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag == "spine":
                    spine = elem
                    break

            if spine is None:
                errors.append("OPF 中缺少 spine 元素")
            else:
                for itemref in spine:
                    tag = itemref.tag.split("}")[-1] if "}" in itemref.tag else itemref.tag
                    if tag == "itemref":
                        idref = itemref.get("idref")
                        if not idref:
                            errors.append("spine 中存在缺少 idref 的 itemref")
                            continue
                        if idref not in manifest:
                            errors.append(f"spine 引用了不存在的 manifest id: {idref}")
                        else:
                            spine_idrefs.append(idref)

            # 6. XHTML 内容检查
            broken_img_refs: List[str] = []
            xhtml_without_viewport: List[str] = []
            xhtml_with_script: List[str] = []
            webp_in_zip: List[str] = []

            for iid, href in xhtml_items:
                resolved = (Path(opf_dir) / href).as_posix() if opf_dir and opf_dir != "." else href
                if resolved not in zf.namelist():
                    continue
                try:
                    content = zf.read(resolved).decode("utf-8")
                except Exception:
                    continue

                # 检查 viewport
                if "viewport" not in content.lower():
                    xhtml_without_viewport.append(href)

                # 检查脚本
                if "<script" in content.lower():
                    xhtml_with_script.append(href)

                # 检查 img src 指向的文件是否存在于 zip
                imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE)
                for img in imgs:
                    raw = (Path(resolved).parent / unquote(img)).as_posix()
                    img_resolved = os.path.normpath(raw).replace(os.sep, "/")
                    # 防止 normpath 把开头的 ../ 搞丢后变成相对路径丢失根上下文
                    if img_resolved.startswith("../"):
                        img_resolved = img_resolved[3:]
                    if img_resolved not in zf.namelist():
                        broken_img_refs.append(f"{href} -> {img}")

            # 7. 全局文件类型检查
            for name in zf.namelist():
                if name.lower().endswith(".webp"):
                    webp_in_zip.append(name)
                if name.lower().endswith(".js") and name not in script_items:
                    # 如果 zip 里有 JS 但 manifest 没声明，也报错
                    script_items.append(name)

            # 过滤掉常见的占位引用（self / none 等）
            broken_img_refs = [
                r for r in broken_img_refs
                if not any(placeholder in r.split(" -> ", 1)[-1].lower() for placeholder in ["self", "none", "null", "#"])
            ]

            # 8. 汇总错误 / 警告
            if webp_in_zip:
                errors.append(f"ZIP 中仍存在 {len(webp_in_zip)} 个 webp 文件: {webp_in_zip[:3]}")

            if broken_img_refs:
                errors.append(f"发现 {len(broken_img_refs)} 个无效图片引用: {broken_img_refs[:3]}")

            if xhtml_with_script:
                errors.append(f"发现 {len(xhtml_with_script)} 个页面仍包含脚本: {xhtml_with_script[:3]}")

            if script_items:
                errors.append(f"发现 {len(script_items)} 个脚本文件: {script_items[:3]}")

            # 9. 漫画专用检查
            if book_type == "comic":
                if rendition_layout != "pre-paginated":
                    errors.append(
                        f"漫画缺少 rendition:layout=pre-paginated (当前={rendition_layout or '缺失'})"
                    )

                required_amazon_meta = [
                    "fixed-layout",
                    "original-resolution",
                    "book-type",
                ]
                missing_amazon = [k for k in required_amazon_meta if k not in amazon_meta]
                if missing_amazon:
                    errors.append(
                        f"漫画缺少必要的 Kindle 元数据: {', '.join(missing_amazon)}"
                    )

                if xhtml_without_viewport:
                    errors.append(
                        f"漫画中存在 {len(xhtml_without_viewport)} 个页面缺少 viewport: {xhtml_without_viewport[:3]}"
                    )

            # 10. mimetype 检查
            if "mimetype" in zf.namelist():
                mimetype_info = zf.getinfo("mimetype")
                if mimetype_info.compress_type != zipfile.ZIP_STORED:
                    warnings.append("mimetype 文件应未压缩存储")
            else:
                warnings.append("缺少 mimetype 文件")

    except zipfile.BadZipFile:
        errors.append("文件不是有效的 ZIP/EPUB")
    except Exception as e:
        errors.append(f"校验过程发生异常: {e}")

    # 警告不阻止流程，但会一起返回给调用方
    return errors + warnings


def validate_and_raise(epub_path: str, book_type: str = "") -> None:
    """校验 EPUB，若不通过则抛出 EpubValidationError。"""
    issues = validate_epub(epub_path, book_type)
    if issues:
        raise EpubValidationError(issues)
