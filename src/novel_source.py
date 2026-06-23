"""Shared source-reader data model for web novels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass(frozen=True)
class NovelAsset:
    id: str
    filename: str
    data: bytes
    media_type: str
    kind: str = "image"


@dataclass(frozen=True)
class NovelChapter:
    title: str
    content_html: str = ""
    source_url: str = ""
    is_volume: bool = False
    head_css: tuple[str, ...] = ()


@dataclass(frozen=True)
class NovelBook:
    title: str
    author: str
    source_url: str
    language: str = "zh-CN"
    intro_html: str = ""
    kind: str = ""
    word_count: str = ""
    latest_chapter: str = ""
    cover: Optional[NovelAsset] = None
    assets: list[NovelAsset] = field(default_factory=list)
    chapters: list[NovelChapter] = field(default_factory=list)


@dataclass(frozen=True)
class NovelReadOptions:
    max_chapters: Optional[int] = None
    chapter_start: Optional[int] = None
    chapter_end: Optional[int] = None
    chapter_workers: int = 4
    slow_chapter_workers: int = 2
    chapter_timeout_seconds: float = 12.0
    slow_chapter_timeout_seconds: float = 60.0
    chapter_retries: int = 2


@dataclass(frozen=True)
class NovelSearchResult:
    source_id: str
    title: str
    author: str
    url: str
    cover_url: str = ""
    latest_chapter: str = ""
    summary: str = ""


class NovelSource(Protocol):
    source_id: str
    display_name: str

    def search(self, keyword: str, page: int = 1) -> list[NovelSearchResult]:
        ...

    def read(self, book_url: str, options: NovelReadOptions) -> NovelBook:
        ...
