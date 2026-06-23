"""ESJZone-specific data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EsjzoneSearchResult:
    title: str
    author: str
    url: str
    cover_url: str
    latest_chapter: str
    summary: str


@dataclass(frozen=True)
class EsjzoneChapterRef:
    title: str
    url: str
    is_volume: bool = False


@dataclass(frozen=True)
class EsjzoneBookInfo:
    title: str
    author: str
    url: str
    cover_url: str
    intro_html: str
    kind: str
    word_count: str
    latest_chapter: str
    chapters: list[EsjzoneChapterRef]


@dataclass(frozen=True)
class EsjzoneBuildOptions:
    book_url: str
    output_path: Optional[str] = None
    output_dir: Optional[str] = None
    cookie: Optional[str] = None
    cookie_file: Optional[str] = None
    max_chapters: Optional[int] = None
    chapter_start: Optional[int] = None
    chapter_end: Optional[int] = None
    chapter_workers: int = 4
    slow_chapter_workers: int = 2
    chapter_timeout_seconds: float = 12.0
    slow_chapter_timeout_seconds: float = 60.0
    chapter_retries: int = 2
