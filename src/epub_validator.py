"""
Standalone EPUB validation for processed output.
"""

import os
import re
import zipfile
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import unquote
from xml.etree import ElementTree as ET


def _parse_xml_safe(data: bytes) -> ET.Element:
    return ET.fromstring(data)


def _find_opf_path(zf: zipfile.ZipFile) -> str:
    container = zf.read("META-INF/container.xml")
    root = _parse_xml_safe(container)
    for rf in root.iter():
        if rf.tag.endswith("rootfile"):
            full_path = rf.get("full-path")
            if full_path:
                return full_path
    raise ValueError("container.xml did not contain a rootfile")


def _zip_path_exists(zf: zipfile.ZipFile, path: str) -> bool:
    candidates = {
        path,
        path.lstrip("/"),
        unquote(path),
        unquote(path).lstrip("/"),
    }
    return any(candidate in zf.namelist() for candidate in candidates)


class EpubValidationError(Exception):
    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def validate_epub(epub_path: str, book_type: str = "") -> List[str]:
    errors: List[str] = []
    warnings: List[str] = []

    try:
        with zipfile.ZipFile(epub_path, "r") as zf:
            if "META-INF/container.xml" not in zf.namelist():
                errors.append("Missing META-INF/container.xml")
                return errors

            try:
                opf_path = _find_opf_path(zf)
            except ValueError as exc:
                errors.append(str(exc))
                return errors

            if opf_path not in zf.namelist():
                errors.append(f"Missing OPF file: {opf_path}")
                return errors

            try:
                opf_root = _parse_xml_safe(zf.read(opf_path))
            except ET.ParseError as exc:
                errors.append(f"Failed to parse OPF: {exc}")
                return errors

            manifest: Dict[str, Dict[str, str]] = {}
            manifest_ids: Set[str] = set()
            xhtml_items: List[Tuple[str, str]] = []
            script_items: List[str] = []

            rendition_layout = ""
            amazon_meta: Dict[str, str] = {}

            for elem in opf_root.iter():
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag

                if tag == "item":
                    item_id = elem.get("id")
                    href = elem.get("href")
                    media_type = elem.get("media-type") or ""
                    if not item_id:
                        errors.append("Manifest item missing id")
                        continue
                    if item_id in manifest_ids:
                        errors.append(f"Duplicate manifest id: {item_id}")
                    manifest_ids.add(item_id)
                    if href and media_type == "application/xhtml+xml":
                        xhtml_items.append((item_id, href))
                    elif href and ("javascript" in media_type or href.lower().endswith(".js")):
                        script_items.append(href)
                    manifest[item_id] = {"href": href or "", "media-type": media_type}

                elif tag == "meta":
                    prop = elem.get("property") or ""
                    name = elem.get("name") or ""
                    if prop == "rendition:layout":
                        rendition_layout = (elem.text or "").strip().lower()
                    if name:
                        amazon_meta[name] = elem.get("content") or ""

            opf_dir = Path(opf_path).parent.as_posix()
            for item_id, info in manifest.items():
                href = info["href"]
                if not href:
                    continue
                resolved = (Path(opf_dir) / href).as_posix() if opf_dir and opf_dir != "." else href
                if not _zip_path_exists(zf, resolved):
                    errors.append(f"Manifest target missing: {href} (id={item_id})")

            spine = None
            for elem in opf_root.iter():
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag == "spine":
                    spine = elem
                    break

            if spine is None:
                errors.append("OPF is missing a spine element")
            else:
                for itemref in spine:
                    tag = itemref.tag.split("}")[-1] if "}" in itemref.tag else itemref.tag
                    if tag != "itemref":
                        continue
                    idref = itemref.get("idref")
                    if not idref:
                        errors.append("Spine itemref missing idref")
                        continue
                    if idref not in manifest:
                        errors.append(f"Spine references missing manifest id: {idref}")

            broken_img_refs: List[str] = []
            xhtml_without_viewport: List[str] = []
            xhtml_with_script: List[str] = []
            webp_in_zip: List[str] = []

            for _, href in xhtml_items:
                resolved = (Path(opf_dir) / href).as_posix() if opf_dir and opf_dir != "." else href
                if not _zip_path_exists(zf, resolved):
                    continue
                try:
                    raw_bytes = zf.read(unquote(resolved) if unquote(resolved) in zf.namelist() else resolved)
                    content = raw_bytes.decode("utf-8")
                except Exception:
                    continue

                try:
                    _parse_xml_safe(raw_bytes)
                except ET.ParseError as exc:
                    errors.append(f"Failed to parse XHTML {href}: {exc}")
                    continue

                if "viewport" not in content.lower():
                    xhtml_without_viewport.append(href)

                if "<script" in content.lower():
                    xhtml_with_script.append(href)

                imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE)
                for img in imgs:
                    raw = (Path(resolved).parent / img).as_posix()
                    img_resolved = os.path.normpath(raw).replace(os.sep, "/")
                    if img_resolved.startswith("../"):
                        img_resolved = img_resolved[3:]
                    if not _zip_path_exists(zf, img_resolved):
                        broken_img_refs.append(f"{href} -> {img}")

            for name in zf.namelist():
                lowered = name.lower()
                if lowered.endswith(".webp"):
                    webp_in_zip.append(name)
                if lowered.endswith(".js") and name not in script_items:
                    script_items.append(name)

            broken_img_refs = [
                ref
                for ref in broken_img_refs
                if not any(token in ref.split(" -> ", 1)[-1].lower() for token in ["self", "none", "null", "#"])
            ]

            if webp_in_zip:
                errors.append(f"Found {len(webp_in_zip)} WebP files in ZIP: {webp_in_zip[:3]}")
            if broken_img_refs:
                errors.append(f"Found {len(broken_img_refs)} broken image references: {broken_img_refs[:3]}")
            if xhtml_with_script:
                errors.append(f"Found {len(xhtml_with_script)} XHTML files still containing scripts: {xhtml_with_script[:3]}")
            if script_items:
                errors.append(f"Found {len(script_items)} JavaScript files: {script_items[:3]}")

            if book_type == "comic":
                explicit_layout_metas = ["fixed-layout", "book-type"]
                has_explicit_comic_layout = rendition_layout == "pre-paginated" or any(
                    name in amazon_meta for name in explicit_layout_metas
                )
                meaningful_missing_viewport = [
                    href
                    for href in xhtml_without_viewport
                    if Path(href).name.lower()
                    not in {"navigation-documents.xhtml", "navigation-toc.xhtml", "toc.xhtml", "toc.html", "toc.htm", "titlepage.xhtml"}
                ]

                if has_explicit_comic_layout and rendition_layout != "pre-paginated":
                    errors.append(
                        f"Comic metadata is inconsistent: rendition:layout should be pre-paginated (current={rendition_layout or 'missing'})"
                    )

                if has_explicit_comic_layout:
                    if meaningful_missing_viewport:
                        errors.append(
                            f"Comic has {len(meaningful_missing_viewport)} pages without viewport: {meaningful_missing_viewport[:3]}"
                        )

            if "mimetype" in zf.namelist():
                mimetype_info = zf.getinfo("mimetype")
                if mimetype_info.compress_type != zipfile.ZIP_STORED:
                    warnings.append("mimetype should be stored without compression")
            else:
                warnings.append("Missing mimetype file")

    except zipfile.BadZipFile:
        errors.append("File is not a valid ZIP/EPUB")
    except Exception as exc:
        errors.append(f"Validation raised an exception: {exc}")

    return errors + warnings


def validate_and_raise(epub_path: str, book_type: str = "") -> None:
    issues = validate_epub(epub_path, book_type)
    if issues:
        raise EpubValidationError(issues)
