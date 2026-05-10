"""ESJZone source reader.

This module only knows how to read ESJZone pages and produce the shared web
novel model. EPUB generation is handled by ``novel_epub`` so future sites can
share the same conversion pipeline.
"""

from __future__ import annotations

import html as html_lib
import http.client
import re
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, build_opener

import lxml.etree as etree
import lxml.html as lxml_html

from .novel_epub import EpubConversionOptions, KindleNovelEpubConverter
from .novel_source import NovelAsset, NovelBook, NovelChapter
from .utils import LogCallback, _default_log


ESJZONE_BASE_URL = "https://www.esjzone.one"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


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


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _slug(value: str, default: str = "item") -> str:
    sanitized = re.sub(r"[^0-9A-Za-z._-]+", "-", value).strip("-._")
    return sanitized[:80] or default


def _inner_html(element: etree._Element) -> str:
    chunks: list[str] = []
    if element.text:
        chunks.append(html_lib.escape(element.text))
    for child in element:
        chunks.append(etree.tostring(child, encoding="unicode", method="xml"))
    return "".join(chunks).strip()


def _first_text(root: etree._Element, xpath: str) -> str:
    values = root.xpath(xpath)
    for value in values:
        if isinstance(value, etree._Element):
            text = _text(value.text_content())
        else:
            text = _text(value)
        if text:
            return text
    return ""


def _first_attr(root: etree._Element, xpath: str) -> str:
    values = root.xpath(xpath)
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _has_class(class_attr: str, class_name: str) -> bool:
    return class_name in (class_attr or "").split()


def _read_cookie(cookie: Optional[str], cookie_file: Optional[str]) -> str:
    if cookie:
        return cookie.strip()
    if cookie_file:
        return Path(cookie_file).read_text(encoding="utf-8").strip()
    return ""


class EsjzoneClient:
    def __init__(
        self,
        base_url: str = ESJZONE_BASE_URL,
        cookie: str = "",
        timeout: int = 30,
        throttle_seconds: float = 0.25,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie = cookie.strip()
        self.timeout = timeout
        self.throttle_seconds = throttle_seconds
        self._opener = build_opener()
        self._last_request = 0.0

    def absolute_url(self, url: str) -> str:
        if not url:
            return ""
        return urljoin(self.base_url + "/", url)

    def get_bytes(self, url: str, *, referer: str = "") -> bytes:
        absolute = self.absolute_url(url)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8,en;q=0.7",
            "Connection": "close",
        }
        if referer:
            headers["Referer"] = self.absolute_url(referer)
        if self.cookie:
            headers["Cookie"] = self.cookie

        last_error: Exception | None = None
        for attempt in range(3):
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self.throttle_seconds:
                time.sleep(self.throttle_seconds - elapsed)
            self._last_request = time.monotonic()

            request = Request(absolute, headers=headers)
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    return response.read()
            except HTTPError as exc:
                raise RuntimeError(f"ESJZone request failed: HTTP {exc.code} {absolute}") from exc
            except (URLError, ssl.SSLError, http.client.RemoteDisconnected, ConnectionError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                break

        raise RuntimeError(f"ESJZone request failed: {absolute}: {last_error}") from last_error

    def get_text(self, url: str, *, referer: str = "") -> str:
        data = self.get_bytes(url, referer=referer)
        for encoding in ("utf-8", "utf-8-sig", "big5", "gb18030"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def get_document(self, url: str, *, referer: str = "") -> etree._Element:
        return lxml_html.fromstring(self.get_text(url, referer=referer))

    def is_logged_in(self) -> bool:
        doc = self.get_document("/my/profile.html")
        body_text = _text(doc.text_content()).lower()
        if "login" in body_text or "登入" in body_text or "登录" in body_text:
            return False
        return bool(doc.xpath("//a[contains(@href, '/my/logout') or contains(@href, 'logout')]")) or "/my/profile" in body_text


class EsjzoneReader:
    def __init__(self, client: EsjzoneClient, log: LogCallback = _default_log) -> None:
        self.client = client
        self.log = log

    def search(self, keyword: str, page: int = 1) -> list[EsjzoneSearchResult]:
        path = f"/tags/{quote(keyword.strip())}/{page}.html"
        doc = self.client.get_document(path)
        cards = doc.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' product-item ')]"
            "|//div[contains(concat(' ', normalize-space(@class), ' '), ' card ')]"
            "[.//a[contains(@href, '/detail/')]]"
        )
        results: list[EsjzoneSearchResult] = []
        seen: set[str] = set()
        for card in cards:
            href = _first_attr(card, ".//a[contains(@href, '/detail/')][1]/@href")
            if not href:
                continue
            url = self.client.absolute_url(href)
            if url in seen:
                continue
            seen.add(url)

            title = _first_text(card, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' product-title ')]//a/text()")
            if not title:
                title = _first_text(card, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' card-title ')]//a/text()")
            if not title:
                title = _first_text(card, ".//a[contains(@href, '/detail/')][1]/text()")

            author = _first_text(card, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' card-author ')]//a/text()")
            latest = _first_text(card, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' card-ep ')]//text()")
            if not latest:
                latest = _first_text(card, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' book-ep ')]//a/text()")
            summary = _first_text(card, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' book-ep ')]//text()")
            cover = _first_attr(card, ".//img/@data-src") or _first_attr(card, ".//img/@src")
            if "empty" in cover:
                cover = ""
            results.append(
                EsjzoneSearchResult(
                    title=title,
                    author=author,
                    url=url,
                    cover_url=self.client.absolute_url(cover) if cover else "",
                    latest_chapter=latest,
                    summary=summary,
                )
            )
        return results

    def read(self, book_url: str, max_chapters: Optional[int] = None) -> NovelBook:
        info = self.fetch_book_info(book_url)
        if not info.chapters:
            raise RuntimeError("No chapters found on ESJZone detail page")

        assets: list[NovelAsset] = []
        cover = self._download_cover(info)
        selected = [chapter for chapter in info.chapters if not chapter.is_volume]
        if max_chapters is not None:
            selected = selected[: max(0, max_chapters)]
        selected_urls = {chapter.url for chapter in selected}

        novel_chapters: list[NovelChapter] = []
        content_index = 0
        for entry in info.chapters:
            if entry.is_volume:
                novel_chapters.append(NovelChapter(title=entry.title, is_volume=True))
                continue
            if entry.url not in selected_urls:
                continue

            content_index += 1
            self.log(f"Reading chapter {content_index}/{len(selected)}: {entry.title}")
            raw_html = self.fetch_chapter_html(entry)
            content_html = self._prepare_chapter_content(raw_html, entry.url, content_index, assets)
            novel_chapters.append(
                NovelChapter(
                    title=entry.title,
                    content_html=content_html,
                    source_url=entry.url,
                    is_volume=False,
                )
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

        title = _first_text(
            doc,
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' book-detail ')]/h2/text()"
            "|//h2/text()",
        )
        author = _first_text(
            doc,
            "(//ul[contains(concat(' ', normalize-space(@class), ' '), ' book-detail ')]//li)[2]//a/text()"
            "|(//ul[contains(concat(' ', normalize-space(@class), ' '), ' book-detail ')]//li)[2]//text()",
        )
        cover = _first_attr(doc, "//div[contains(@class, 'col-md-3')]//img[1]/@src")
        if "empty" in cover:
            cover = ""

        tags = [
            _text(item.text_content())
            for item in doc.xpath("//section[contains(@class, 'm-t-20')]//a[contains(@class, 'tag')]")
            if _text(item.text_content())
        ]
        desc = doc.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' description ')]")
        intro_parts: list[str] = []
        if tags:
            intro_parts.append("<p>" + html_lib.escape("🏷️" + " / ".join(tags)) + "</p>")
        if desc:
            intro_parts.append(_inner_html(desc[0]))

        kind_items = [
            _text(item.text_content())
            for item in doc.xpath("//ul[contains(concat(' ', normalize-space(@class), ' '), ' book-detail ')]//li")
            if _text(item.text_content())
        ]
        kind = "；".join(kind_items[-2:]) if len(kind_items) >= 2 else ""
        word_count = _first_text(doc, "//*[contains(concat(' ', normalize-space(@class), ' '), ' icon-file-text ')]/parent::*//text()")

        chapters = self._parse_chapters(doc)
        latest = next((chapter.title for chapter in reversed(chapters) if not chapter.is_volume), "")
        if not latest:
            latest = _first_text(doc, "//*[@id='chapterList']//a[last()]/text()")

        return EsjzoneBookInfo(
            title=title or "ESJZone Book",
            author=author or "未知作者",
            url=url,
            cover_url=self.client.absolute_url(cover) if cover else "",
            intro_html="\n".join(part for part in intro_parts if part),
            kind=kind,
            word_count=word_count,
            latest_chapter=latest,
            chapters=chapters,
        )

    def _parse_chapters(self, doc: etree._Element) -> list[EsjzoneChapterRef]:
        nodes = doc.xpath("//*[@id='chapterList']//*[self::a or self::p or self::summary]")
        chapters: list[EsjzoneChapterRef] = []
        seen_urls: set[str] = set()
        for node in nodes:
            tag = node.tag.lower() if isinstance(node.tag, str) else ""
            class_attr = node.get("class") or ""
            is_volume = tag in {"p", "summary"} or _has_class(class_attr, "non")
            title = _text(node.get("data-title") or node.text_content())
            href = node.get("href") or ""
            url = self.client.absolute_url(href) if href else ""

            if is_volume:
                if title:
                    chapters.append(EsjzoneChapterRef(title=title, url="", is_volume=True))
                continue
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            chapters.append(EsjzoneChapterRef(title=title, url=url, is_volume=False))

        if chapters:
            return chapters

        for link in doc.xpath("//a[contains(@href, '.html') and contains(@href, '/forum/')]"):
            title = _text(link.text_content())
            url = self.client.absolute_url(link.get("href") or "")
            if title and url and url not in seen_urls:
                seen_urls.add(url)
                chapters.append(EsjzoneChapterRef(title=title, url=url, is_volume=False))
        return chapters

    def fetch_chapter_html(self, chapter: EsjzoneChapterRef) -> str:
        doc = self.client.get_document(chapter.url)
        content_nodes = doc.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' forum-content ') "
            "and contains(concat(' ', normalize-space(@class), ' '), ' mt-3 ')]"
            "|//div[contains(concat(' ', normalize-space(@class), ' '), ' d_post_content ') "
            "and contains(concat(' ', normalize-space(@class), ' '), ' j_d_post_content ')]"
        )
        if not content_nodes:
            content_nodes = doc.xpath("//article|//main")
        if not content_nodes:
            return "<p></p>"
        return _inner_html(content_nodes[0])

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
        chapter_url: str,
        chapter_index: int,
        assets: list[NovelAsset],
    ) -> str:
        wrapper = lxml_html.fragment_fromstring(f"<div>{raw_html}</div>", create_parent=False)
        for bad in wrapper.xpath(".//script|.//style|.//iframe|.//form"):
            parent = bad.getparent()
            if parent is not None:
                parent.remove(bad)

        image_counter = 0
        for img in wrapper.xpath(".//img[@src]"):
            src = img.get("src") or ""
            if src.startswith("data:"):
                continue
            image_url = self.client.absolute_url(urljoin(chapter_url, src))
            try:
                data = self.client.get_bytes(image_url, referer=chapter_url)
            except Exception as exc:
                self.log(f"[Warning] Image download failed: {image_url}: {exc}")
                continue
            image_counter += 1
            suffix, media_type = _guess_image_type(image_url, data)
            asset_id = f"chapter-{chapter_index:04d}-{image_counter:03d}"
            assets.append(
                NovelAsset(
                    id=asset_id,
                    filename=f"{asset_id}{suffix}",
                    data=data,
                    media_type=media_type,
                )
            )
            img.set("src", f"asset:{asset_id}")
            img.attrib.pop("data-src", None)

        return _inner_html(wrapper)


def build_esjzone_epub(options: EsjzoneBuildOptions, log: LogCallback = _default_log) -> str:
    cookie = _read_cookie(options.cookie, options.cookie_file)
    reader = EsjzoneReader(EsjzoneClient(cookie=cookie), log)
    log("Reading ESJZone source data")
    book = reader.read(options.book_url, max_chapters=options.max_chapters)
    log("Converting source data to Kindle EPUB")
    converter = KindleNovelEpubConverter(log)
    return converter.convert(
        book,
        EpubConversionOptions(
            output_path=options.output_path,
            output_dir=options.output_dir,
            validate_output=True,
        ),
    )


def search_esjzone(keyword: str, page: int = 1, cookie: str = "", cookie_file: Optional[str] = None) -> list[EsjzoneSearchResult]:
    reader = EsjzoneReader(EsjzoneClient(cookie=_read_cookie(cookie, cookie_file)))
    return reader.search(keyword, page=page)


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
