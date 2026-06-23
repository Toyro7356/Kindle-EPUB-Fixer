"""ESJZone source adapter."""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

import lxml.etree as etree

from ...novel_build import NovelBuildOptions, build_novel_epub, read_novel_chapters, select_readable_chapters
from ...novel_source import NovelAsset, NovelBook, NovelReadOptions, NovelSearchResult
from ...utils import LogCallback, _default_log
from .assets import _guess_image_type
from .chapter_processor import EsjzoneChapterProcessor
from .client import ESJZONE_BASE_URL, EsjzoneClient, _read_cookie
from .models import EsjzoneBookInfo, EsjzoneBuildOptions, EsjzoneChapterRef, EsjzoneSearchResult
from .parser import (
    extract_chapter_html,
    parse_book_info,
    parse_search_results,
)


class EsjzoneReader:
    def __init__(self, client: EsjzoneClient, log: LogCallback = _default_log) -> None:
        self.client = client
        self.log = log
        self.chapter_processor = EsjzoneChapterProcessor(client, log)

    def search(self, keyword: str, page: int = 1) -> list[EsjzoneSearchResult]:
        path = f"/tags/{quote(keyword.strip())}/{page}.html"
        doc = self.client.get_document(path)
        return parse_search_results(doc, self.client.absolute_url)

    def read(
        self,
        book_url: str,
        options: NovelReadOptions,
    ) -> NovelBook:
        info = self.fetch_book_info(book_url)
        if not info.chapters:
            raise RuntimeError("No chapters found on ESJZone detail page")

        assets: list[NovelAsset] = []
        cover = self._download_cover(info)
        selected = select_readable_chapters(info.chapters, options)

        novel_chapters = read_novel_chapters(
            selected,
            assets,
            self.fetch_chapter_html,
            self._prepare_chapter_content,
            self.log,
            options,
        )

        return NovelBook(
            title=info.title,
            author=info.author,
            source_url=info.url,
            language="zh-CN",
            intro_html=info.intro_html,
            kind=info.kind,
            word_count=info.word_count,
            latest_chapter=info.latest_chapter,
            cover=cover,
            assets=assets,
            chapters=novel_chapters,
        )

    def fetch_book_info(self, book_url: str) -> EsjzoneBookInfo:
        doc = self.client.get_document(book_url)
        url = self.client.absolute_url(book_url)
        return parse_book_info(doc, url, self.client.absolute_url)

    def fetch_chapter_html(self, chapter: EsjzoneChapterRef, timeout: float) -> tuple[str, etree._Element]:
        doc = self.client.get_document(chapter.url, timeout=timeout, retries=0)
        return extract_chapter_html(doc), doc

    def _download_cover(self, info: EsjzoneBookInfo) -> Optional[NovelAsset]:
        if not info.cover_url:
            return None
        try:
            data = self.client.get_bytes(info.cover_url, referer=info.url)
        except Exception as exc:
            self.log(f"[Warning] Cover download failed: {exc}")
            return None
        suffix, media_type = _guess_image_type(info.cover_url, data)
        return NovelAsset(
            id="cover",
            filename=f"cover{suffix}",
            data=data,
            media_type=media_type,
        )

    def _prepare_chapter_content(
        self,
        raw_html: str,
        page_doc: etree._Element,
        chapter: EsjzoneChapterRef,
        chapter_index: int,
        assets: list[NovelAsset],
    ) -> tuple[str, tuple[str, ...]]:
        return self.chapter_processor.prepare(raw_html, page_doc, chapter.url, chapter_index, assets)


class EsjzoneSource:
    source_id = "esjzone"
    display_name = "ESJZone"

    def __init__(self, client: EsjzoneClient, log: LogCallback = _default_log) -> None:
        self.reader = EsjzoneReader(client, log)

    def search(self, keyword: str, page: int = 1) -> list[NovelSearchResult]:
        return [
            NovelSearchResult(
                source_id=self.source_id,
                title=result.title,
                author=result.author,
                url=result.url,
                cover_url=result.cover_url,
                latest_chapter=result.latest_chapter,
                summary=result.summary,
            )
            for result in self.reader.search(keyword, page=page)
        ]

    def search_esjzone(self, keyword: str, page: int = 1) -> list[EsjzoneSearchResult]:
        return self.reader.search(keyword, page=page)

    def read(self, book_url: str, options: NovelReadOptions) -> NovelBook:
        return self.reader.read(book_url, options)


def build_esjzone_epub(options: EsjzoneBuildOptions, log: LogCallback = _default_log) -> str:
    cookie = _read_cookie(options.cookie, options.cookie_file)
    source = EsjzoneSource(EsjzoneClient(cookie=cookie), log)
    return build_novel_epub(
        source,
        NovelBuildOptions(
            book_url=options.book_url,
            output_path=options.output_path,
            output_dir=options.output_dir,
            max_chapters=options.max_chapters,
            chapter_start=options.chapter_start,
            chapter_end=options.chapter_end,
            validate_output=True,
            chapter_workers=options.chapter_workers,
            slow_chapter_workers=options.slow_chapter_workers,
            chapter_timeout_seconds=options.chapter_timeout_seconds,
            slow_chapter_timeout_seconds=options.slow_chapter_timeout_seconds,
            chapter_retries=options.chapter_retries,
        ),
        log,
    )


def search_esjzone(keyword: str, page: int = 1, cookie: str = "", cookie_file: Optional[str] = None) -> list[EsjzoneSearchResult]:
    source = EsjzoneSource(EsjzoneClient(cookie=_read_cookie(cookie, cookie_file)))
    return source.search_esjzone(keyword, page=page)
