"""Resource helpers for ESJZone chapter content."""

from __future__ import annotations

import base64
import re
from pathlib import Path
from urllib.parse import unquote, unquote_to_bytes, urlparse

import lxml.etree as etree


def _decode_data_image(value: str) -> tuple[bytes, str, str] | None:
    match = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);?(base64)?,(.*)$", value, re.DOTALL)
    if not match:
        return None
    media_type = match.group(1).lower()
    payload = match.group(3)
    try:
        data = base64.b64decode(payload, validate=False) if match.group(2) else unquote_to_bytes(payload)
    except Exception:
        return None
    suffix = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
    }.get(media_type, ".jpg")
    return data, suffix, "image/jpeg" if media_type == "image/jpg" else media_type


def _image_source(img: etree._Element) -> str:
    for attr in ("data-src", "data-original", "data-lazy-src", "src"):
        value = (img.get(attr) or "").strip()
        if value and "empty" not in value.lower() and "blank" not in value.lower():
            return value
    for attr in ("data-srcset", "srcset"):
        value = _srcset_source(img.get(attr) or "")
        if value and "empty" not in value.lower() and "blank" not in value.lower():
            return value
    return ""


def _srcset_source(value: str) -> str:
    candidates = [part.strip() for part in value.split(",") if part.strip()]
    for candidate in reversed(candidates):
        pieces = candidate.split()
        if pieces:
            return pieces[0]
    return ""


def _guess_image_type(url: str, data: bytes) -> tuple[str, str]:
    parsed_suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    if parsed_suffix == ".jpeg":
        return ".jpg", "image/jpeg"
    if parsed_suffix in {".jpg", ".png", ".gif", ".svg", ".webp"}:
        return parsed_suffix, {
            ".jpg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".webp": "image/webp",
        }[parsed_suffix]
    if data.startswith(b"\xff\xd8"):
        return ".jpg", "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return ".png", "image/png"
    if data.startswith(b"GIF"):
        return ".gif", "image/gif"
    if data[:20].lstrip().startswith(b"<svg"):
        return ".svg", "image/svg+xml"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return ".webp", "image/webp"
    return ".jpg", "image/jpeg"
