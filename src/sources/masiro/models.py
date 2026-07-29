"""Masiro-specific data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MasiroChapterRef:
    title: str
    url: str
    cost: int = 0
    is_volume: bool = False


@dataclass(frozen=True)
class MasiroBookInfo:
    title: str
    author: str
    translators: tuple[str, ...]
    url: str
    cover_url: str
    intro_html: str
    description: str
    tags: tuple[str, ...]
    status: str
    kind: str
    word_count: str
    latest_chapter: str
    chapters: list[MasiroChapterRef]
    account_balance: Optional[int] = None

    @property
    def translator(self) -> str:
        return "、".join(self.translators)


@dataclass(frozen=True)
class MasiroPurchasePlan:
    chapter_count: int
    total_cost: int
    account_balance: Optional[int] = None


@dataclass(frozen=True)
class MasiroPaymentInfo:
    cost: int
    payment_type: int
    object_id: int
    csrf_token: str


@dataclass(frozen=True)
class MasiroBuildOptions:
    book_url: str
    output_path: Optional[str] = None
    output_dir: Optional[str] = None
    cookie: Optional[str] = None
    cookie_file: Optional[str] = None
    user_agent: Optional[str] = None
    auto_purchase: bool = False
    max_purchase_cost: Optional[int] = None
    max_chapters: Optional[int] = None
    chapter_start: Optional[int] = None
    chapter_end: Optional[int] = None
    chapter_workers: int = 2
    slow_chapter_workers: int = 1
    chapter_timeout_seconds: float = 12.0
    slow_chapter_timeout_seconds: float = 60.0
    chapter_retries: int = 2
