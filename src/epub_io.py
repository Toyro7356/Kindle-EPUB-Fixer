import os
import posixpath
import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import quote

import lxml.etree as etree

from .constants import NSMAP
from .text_io import read_text_file, write_text_file


_INVALID_ZIP_PATH_CHARS = re.compile(r'[<>:"\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_REFERENCE_TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".htm",
    ".ncx",
    ".opf",
    ".svg",
    ".xhtml",
    ".xml",
}


def _quote_zip_path(path: str) -> str:
    return "/".join(quote(segment, safe="-._~") for segment in path.split("/"))


def _sanitize_zip_segment(segment: str) -> str:
    if segment in {"", ".", ".."}:
        return "_"

    sanitized = _INVALID_ZIP_PATH_CHARS.sub("_", segment).rstrip(" .")
    if not sanitized:
        sanitized = "_"

    stem = sanitized.split(".", 1)[0]
    if stem.upper() in _RESERVED_WINDOWS_NAMES:
        sanitized = f"_{sanitized}"
    return sanitized


def _sanitize_zip_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    is_dir = normalized.endswith("/")
    parts = [
        _sanitize_zip_segment(part)
        for part in normalized.split("/")
        if part not in {"", "."}
    ]
    if not parts:
        return normalized

    sanitized = "/".join(parts)
    if is_dir:
        sanitized += "/"
    return sanitized


def _dedupe_zip_name(name: str, used_names: set[str]) -> str:
    if name.endswith("/"):
        used_names.add(name.rstrip("/").lower())
        return name

    parent, filename = posixpath.split(name)
    stem, ext = posixpath.splitext(filename)
    candidate = name
    counter = 2
    while candidate.lower() in used_names:
        candidate_name = f"{stem}_{counter}{ext}"
        candidate = f"{parent}/{candidate_name}" if parent else candidate_name
        counter += 1

    used_names.add(candidate.lower())
    return candidate


def _build_safe_name_mapping(infos: list[zipfile.ZipInfo]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used_names: set[str] = set()

    for info in infos:
        original = info.filename.replace("\\", "/")
        candidate = _sanitize_zip_name(original)
        safe_name = _dedupe_zip_name(candidate, used_names)
        mapping[original] = safe_name

    return mapping


def _reference_variants(original: str) -> set[str]:
    variants = {original, _quote_zip_path(original)}
    if not original.startswith("."):
        variants.add(f"./{original}")
        variants.add(f"./{_quote_zip_path(original)}")
    return variants


def _rewrite_mapped_references(temp_dir: str, mapping: dict[str, str]) -> None:
    changed_targets = {
        original: safe
        for original, safe in mapping.items()
        if original != safe and not original.endswith("/")
    }
    if not changed_targets:
        return

    text_entries = [
        (original, safe)
        for original, safe in mapping.items()
        if not safe.endswith("/") and Path(safe).suffix.lower() in _REFERENCE_TEXT_SUFFIXES
    ]
    temp_root = Path(temp_dir)

    for current_original, current_safe in text_entries:
        file_path = temp_root / current_safe.replace("/", os.sep)
        if not file_path.exists():
            continue

        current_original_dir = posixpath.dirname(current_original) or "."
        current_safe_dir = posixpath.dirname(current_safe) or "."
        replacements: set[tuple[str, str]] = set()

        for target_original, target_safe in changed_targets.items():
            original_rel = posixpath.relpath(target_original, current_original_dir)
            safe_rel = posixpath.relpath(target_safe, current_safe_dir)
            safe_ref = _quote_zip_path(safe_rel)
            for variant in _reference_variants(original_rel):
                replacements.add((variant, safe_ref))

        content = read_text_file(file_path)
        updated = content
        for old, new in sorted(replacements, key=lambda pair: len(pair[0]), reverse=True):
            if old != new:
                updated = updated.replace(old, new)

        if updated != content:
            write_text_file(file_path, updated)


def unpack_epub(epub_path: str, temp_dir: str) -> None:
    with zipfile.ZipFile(epub_path, "r") as zf:
        infos = zf.infolist()
        mapping = _build_safe_name_mapping(infos)
        temp_root = Path(temp_dir)

        for info in infos:
            original = info.filename.replace("\\", "/")
            safe_name = mapping[original]
            target_path = temp_root / safe_name.replace("/", os.sep)
            if info.is_dir() or safe_name.endswith("/"):
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as source, target_path.open("wb") as target:
                shutil.copyfileobj(source, target)

        _rewrite_mapped_references(temp_dir, mapping)


def repack_epub(temp_dir: str, output_path: str) -> None:
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        mimetype_path = Path(temp_dir) / "mimetype"
        if mimetype_path.exists():
            zf.write(str(mimetype_path), "mimetype", compress_type=zipfile.ZIP_STORED)
        for root, dirs, files in os.walk(temp_dir):
            dirs[:] = [d for d in dirs if d != "__MACOSX"]
            for file in files:
                abs_path = Path(root) / file
                arcname = str(abs_path.relative_to(temp_dir)).replace(os.sep, "/")
                if arcname == "mimetype":
                    continue
                zf.write(str(abs_path), arcname)


def find_opf(temp_dir: str) -> str:
    container_path = Path(temp_dir) / "META-INF" / "container.xml"
    if not container_path.exists():
        raise FileNotFoundError("META-INF/container.xml does not exist")
    tree = etree.parse(str(container_path))
    for rf in tree.xpath("//container:rootfiles/container:rootfile", namespaces=NSMAP):
        full_path = rf.get("full-path")
        if full_path:
            return str(Path(temp_dir) / full_path.replace("/", os.sep))
    raise FileNotFoundError("No rootfile entry found in container.xml")


def opf_dir(opf_path: str) -> str:
    return str(Path(opf_path).parent)
