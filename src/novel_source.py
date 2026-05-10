"""Shared source-reader data model for web novels."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class NovelAsset:
    id: str
    filename: str
    data: bytes
    media_type: str


@dataclass(frozen=True)
class NovelChapter:
    title: str
    content_html: str = ""
    source_url: str = ""
    is_volume: bool = False


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
