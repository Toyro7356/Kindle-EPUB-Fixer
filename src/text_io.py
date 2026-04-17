import re
from pathlib import Path


_ENCODING_PATTERNS = (
    re.compile(r'<\?xml[^>]*encoding=["\']([A-Za-z0-9._-]+)["\']', re.IGNORECASE),
    re.compile(r'@charset\s+["\']([A-Za-z0-9._-]+)["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+charset=["\']?([A-Za-z0-9._-]+)', re.IGNORECASE),
    re.compile(
        r'<meta[^>]+content=["\'][^"\']*charset=([A-Za-z0-9._-]+)[^"\']*["\']',
        re.IGNORECASE,
    ),
)


def _detect_declared_encoding(data: bytes) -> str | None:
    head = data[:4096].decode("ascii", errors="ignore")
    for pattern in _ENCODING_PATTERNS:
        match = pattern.search(head)
        if match:
            return match.group(1)
    return None


def read_text_file(path: str | Path) -> str:
    file_path = Path(path)
    data = file_path.read_bytes()
    if not data:
        return ""

    declared = _detect_declared_encoding(data)
    encodings: list[str] = []
    if data.startswith(b"\xef\xbb\xbf"):
        encodings.append("utf-8-sig")
    if declared:
        encodings.append(declared)
    encodings.extend(
        ["utf-8", "utf-16", "utf-16-le", "utf-16-be", "gb18030", "cp932", "big5", "latin-1"]
    )

    tried: set[str] = set()
    for encoding in encodings:
        normalized = encoding.lower()
        if normalized in tried:
            continue
        tried.add(normalized)
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue

    return data.decode("utf-8", errors="ignore")


def write_text_file(path: str | Path, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8", newline="")
