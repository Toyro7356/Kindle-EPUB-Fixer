"""ESJZone web novel importer.

The importer uses the user's existing ESJZone login cookie when a book requires
an authenticated session. It does not store account credentials.
"""

from __future__ import annotations

import html as html_lib
import http.client
import os
import re
import ssl
import shutil
import tempfile
import time
import uuid
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, build_opener

import lxml.etree as etree
import lxml.html as lxml_html

from .core import process_epub
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
class EsjzoneChapter:
    title: str
    url: str
    is_volume: bool = False


@dataclass(frozen=True)
class EsjzoneBook:
    title: str
    author: str
    url: str
    cover_url: str
    intro_html: str
    kind: str
    word_count: str
    latest_chapter: str
    chapters: list[EsjzoneChapter]


@dataclass(frozen=True)
class EsjzoneBuildOptions:
    book_url: str
    output_path: Optional[str] = None
    output_dir: Optional[str] = None
    cookie: Optional[str] = None
    cookie_file: Optional[str] = None
    max_chapters: Optional[int] = None
    keep_raw: bool = False


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _safe_filename(value: str, default: str = "book") -> str:
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" .")
    return sanitized[:120] or default


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


@contextmanager
def _temporary_work_dir():
    temp_root = Path(os.environ.get("KINDLE_EPUB_FIXER_TEMP_DIR") or tempfile.gettempdir())
    temp_root.mkdir(parents=True, exist_ok=True)
    temp_dir = temp_root / f"esjzone-epub-{uuid.uuid4().hex}"
    temp_dir.mkdir()
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


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

    def search(self, keyword: str, page: int = 1) -> list[EsjzoneSearchResult]:
        path = f"/tags/{quote(keyword.strip())}/{page}.html"
        doc = self.get_document(path)
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
            url = self.absolute_url(href)
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
            cover = _first_attr(card, ".//img/@data-src")
            if not cover:
                cover = _first_attr(card, ".//img/@src")
            if "empty" in cover:
                cover = ""
            results.append(
                EsjzoneSearchResult(
                    title=title,
                    author=author,
                    url=url,
                    cover_url=self.absolute_url(cover) if cover else "",
                    latest_chapter=latest,
                    summary=summary,
                )
            )
        return results

    def fetch_book(self, book_url: str) -> EsjzoneBook:
        doc = self.get_document(book_url)
        url = self.absolute_url(book_url)

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

        chapters = self._parse_chapters(doc, url)
        latest = next((chapter.title for chapter in reversed(chapters) if not chapter.is_volume), "")
        if not latest:
            latest = _first_text(doc, "//*[@id='chapterList']//a[last()]/text()")

        return EsjzoneBook(
            title=title or "ESJZone Book",
            author=author or "未知作者",
            url=url,
            cover_url=self.absolute_url(cover) if cover else "",
            intro_html="\n".join(part for part in intro_parts if part),
            kind=kind,
            word_count=word_count,
            latest_chapter=latest,
            chapters=chapters,
        )

    def _parse_chapters(self, doc: etree._Element, book_url: str) -> list[EsjzoneChapter]:
        nodes = doc.xpath("//*[@id='chapterList']//*[self::a or self::p or self::summary]")
        chapters: list[EsjzoneChapter] = []
        seen_urls: set[str] = set()
        for node in nodes:
            tag = node.tag.lower() if isinstance(node.tag, str) else ""
            class_attr = node.get("class") or ""
            is_volume = tag in {"p", "summary"} or _has_class(class_attr, "non")
            title = _text(node.get("data-title") or node.text_content())
            href = node.get("href") or ""
            url = self.absolute_url(href) if href else ""

            if is_volume:
                if title:
                    chapters.append(EsjzoneChapter(title=title, url="", is_volume=True))
                continue
            if not title or not url or url in seen_urls:
                continue
            seen_urls.add(url)
            chapters.append(EsjzoneChapter(title=title, url=url, is_volume=False))

        if chapters:
            return chapters

        for link in doc.xpath("//a[contains(@href, '.html') and contains(@href, '/forum/')]"):
            title = _text(link.text_content())
            url = self.absolute_url(link.get("href") or "")
            if title and url and url not in seen_urls:
                seen_urls.add(url)
                chapters.append(EsjzoneChapter(title=title, url=url, is_volume=False))
        return chapters

    def fetch_chapter_html(self, chapter: EsjzoneChapter) -> str:
        doc = self.get_document(chapter.url)
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


class EsjzoneEpubBuilder:
    def __init__(self, client: EsjzoneClient, log: LogCallback = _default_log) -> None:
        self.client = client
        self.log = log

    def build(self, options: EsjzoneBuildOptions) -> str:
        self.log("Fetching ESJZone book metadata")
        book = self.client.fetch_book(options.book_url)
        if not book.chapters:
            raise RuntimeError("No chapters found on ESJZone detail page")

        output_path = self._resolve_output_path(book, options)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with _temporary_work_dir() as temp_dir:
            raw_epub = temp_dir / "raw.esjzone.epub"
            self._write_raw_epub(book, raw_epub, temp_dir, options)
            if options.keep_raw:
                shutil.copy2(raw_epub, output_path)
                return str(output_path)

            self.log("Running Kindle EPUB compatibility repair")
            process_epub(str(raw_epub), str(output_path), log=self.log)
            return str(output_path)

    def _resolve_output_path(self, book: EsjzoneBook, options: EsjzoneBuildOptions) -> Path:
        if options.output_path:
            path = Path(options.output_path)
            if path.exists() and path.is_dir():
                return path / f"{_safe_filename(book.title)}.epub"
            if path.suffix.lower() != ".epub":
                return path / f"{_safe_filename(book.title)}.epub"
            return path
        if options.output_dir:
            return Path(options.output_dir) / f"{_safe_filename(book.title)}.epub"
        return Path.cwd() / "转换后" / f"{_safe_filename(book.title)}.epub"

    def _write_raw_epub(
        self,
        book: EsjzoneBook,
        epub_path: Path,
        temp_dir: Path,
        options: EsjzoneBuildOptions,
    ) -> None:
        root = temp_dir / "epub"
        oebps = root / "OEBPS"
        text_dir = oebps / "Text"
        style_dir = oebps / "Styles"
        image_dir = oebps / "Images"
        meta_dir = root / "META-INF"
        for directory in (text_dir, style_dir, image_dir, meta_dir):
            directory.mkdir(parents=True, exist_ok=True)

        (root / "mimetype").write_text("application/epub+zip", encoding="ascii")
        (meta_dir / "container.xml").write_text(CONTAINER_XML, encoding="utf-8")
        (style_dir / "style.css").write_text(STYLE_CSS, encoding="utf-8")

        manifest_items: list[tuple[str, str, str, str]] = [
            ("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
            ("ncx", "toc.ncx", "application/x-dtbncx+xml", ""),
            ("style", "Styles/style.css", "text/css", ""),
        ]
        spine_ids: list[str] = []
        nav_points: list[tuple[int, str, str]] = []
        nav_items: list[tuple[str, str, bool]] = []

        cover_href = self._download_cover(book, image_dir)
        if cover_href:
            manifest_items.append(("cover-image", cover_href, _media_type_for_path(cover_href), "cover-image"))

        intro_href = "Text/intro.xhtml"
        (oebps / intro_href).write_text(self._chapter_document("书籍信息", book.intro_html or "<p></p>"), encoding="utf-8")
        manifest_items.append(("intro", intro_href, "application/xhtml+xml", ""))
        spine_ids.append("intro")
        nav_points.append((1, "书籍信息", intro_href))
        nav_items.append(("书籍信息", intro_href, False))

        chapters = [chapter for chapter in book.chapters if not chapter.is_volume]
        if options.max_chapters is not None:
            chapters = chapters[: max(0, options.max_chapters)]

        volume_index = 0
        chapter_index = 0
        chapter_lookup = {chapter.url: chapter for chapter in chapters}
        for entry in book.chapters:
            if entry.is_volume:
                volume_index += 1
                nav_items.append((entry.title, "", True))
                continue
            if entry.url not in chapter_lookup:
                continue
            chapter_index += 1
            self.log(f"Fetching chapter {chapter_index}/{len(chapters)}: {entry.title}")
            raw_html = self.client.fetch_chapter_html(entry)
            content_html = self._prepare_chapter_content(raw_html, entry.url, image_dir, chapter_index)
            item_id = f"chapter-{chapter_index:04d}"
            href = f"Text/chapter-{chapter_index:04d}-{_slug(entry.title, 'chapter')}.xhtml"
            (oebps / href).write_text(self._chapter_document(entry.title, content_html), encoding="utf-8")
            manifest_items.append((item_id, href, "application/xhtml+xml", ""))
            spine_ids.append(item_id)
            nav_points.append((len(nav_points) + 1, entry.title, href))
            nav_items.append((entry.title, href, False))

        known_assets = {cover_href} if cover_href else set()
        for image_path in sorted(image_dir.glob("*")):
            href = f"Images/{image_path.name}"
            if href in known_assets:
                continue
            manifest_items.append((f"image-{_slug(image_path.stem)}", href, _media_type_for_path(href), ""))

        self._write_nav(oebps / "nav.xhtml", book, nav_items)
        self._write_ncx(oebps / "toc.ncx", book, nav_points)
        self._write_opf(oebps / "content.opf", book, manifest_items, spine_ids, cover_href)
        self._zip_epub(root, epub_path)

    def _download_cover(self, book: EsjzoneBook, image_dir: Path) -> str:
        if not book.cover_url:
            return ""
        try:
            data = self.client.get_bytes(book.cover_url, referer=book.url)
        except Exception as exc:
            self.log(f"[Warning] Cover download failed: {exc}")
            return ""
        suffix = _guess_image_suffix(book.cover_url, data)
        path = image_dir / f"cover{suffix}"
        path.write_bytes(data)
        return f"Images/{path.name}"

    def _prepare_chapter_content(self, raw_html: str, chapter_url: str, image_dir: Path, chapter_index: int) -> str:
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
            suffix = _guess_image_suffix(image_url, data)
            image_name = f"chapter-{chapter_index:04d}-{image_counter:03d}{suffix}"
            (image_dir / image_name).write_bytes(data)
            img.set("src", f"../Images/{image_name}")
            img.attrib.pop("data-src", None)

        return _inner_html(wrapper)

    def _chapter_document(self, title: str, body_html: str) -> str:
        return XHTML_TEMPLATE.format(
            title=html_lib.escape(title),
            body=body_html,
        )

    def _write_nav(self, path: Path, book: EsjzoneBook, nav_items: list[tuple[str, str, bool]]) -> None:
        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN" xml:lang="zh-CN">',
            "<head>",
            f"<title>{html_lib.escape(book.title)} - 目录</title>",
            '<link rel="stylesheet" type="text/css" href="Styles/style.css"/>',
            "</head><body>",
            '<nav epub:type="toc" id="toc"><h1>目录</h1><ol>',
        ]
        for title, href, is_volume in nav_items:
            if is_volume or not href:
                lines.append(f'<li><span>{html_lib.escape(title)}</span></li>')
            else:
                lines.append(f'<li><a href="{html_lib.escape(href)}">{html_lib.escape(title)}</a></li>')
        lines.extend(["</ol></nav>", "</body></html>"])
        path.write_text("\n".join(lines), encoding="utf-8")

    def _write_ncx(self, path: Path, book: EsjzoneBook, nav_points: list[tuple[int, str, str]]) -> None:
        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">',
            "<head>",
            f'<meta name="dtb:uid" content="{html_lib.escape(_book_uuid(book.url))}"/>',
            "</head>",
            f"<docTitle><text>{html_lib.escape(book.title)}</text></docTitle>",
            "<navMap>",
        ]
        for play_order, title, href in nav_points:
            lines.extend(
                [
                    f'<navPoint id="navPoint-{play_order}" playOrder="{play_order}">',
                    f"<navLabel><text>{html_lib.escape(title)}</text></navLabel>",
                    f'<content src="{html_lib.escape(href)}"/>',
                    "</navPoint>",
                ]
            )
        lines.extend(["</navMap>", "</ncx>"])
        path.write_text("\n".join(lines), encoding="utf-8")

    def _write_opf(
        self,
        path: Path,
        book: EsjzoneBook,
        manifest_items: list[tuple[str, str, str, str]],
        spine_ids: list[str],
        cover_href: str,
    ) -> None:
        metadata = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">',
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">',
            f'<dc:identifier id="bookid">{html_lib.escape(_book_uuid(book.url))}</dc:identifier>',
            f"<dc:title>{html_lib.escape(book.title)}</dc:title>",
            f"<dc:creator>{html_lib.escape(book.author)}</dc:creator>",
            "<dc:language>zh-CN</dc:language>",
            f'<dc:source>{html_lib.escape(book.url)}</dc:source>',
            f'<meta property="dcterms:modified">{time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}</meta>',
        ]
        if cover_href:
            metadata.append('<meta name="cover" content="cover-image"/>')
        metadata.append("</metadata>")

        manifest = ["<manifest>"]
        for item_id, href, media_type, properties in manifest_items:
            properties_attr = f' properties="{properties}"' if properties else ""
            manifest.append(
                f'<item id="{html_lib.escape(item_id)}" href="{html_lib.escape(href)}" '
                f'media-type="{html_lib.escape(media_type)}"{properties_attr}/>'
            )
        manifest.append("</manifest>")

        spine = ['<spine toc="ncx">']
        for item_id in spine_ids:
            spine.append(f'<itemref idref="{html_lib.escape(item_id)}"/>')
        spine.append("</spine>")
        path.write_text("\n".join(metadata + manifest + spine + ["</package>"]), encoding="utf-8")

    def _zip_epub(self, root: Path, epub_path: Path) -> None:
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.write(root / "mimetype", "mimetype", compress_type=zipfile.ZIP_STORED)
            for path in sorted(root.rglob("*")):
                if path.name == "mimetype" or path.is_dir():
                    continue
                arcname = path.relative_to(root).as_posix()
                zf.write(path, arcname, compress_type=zipfile.ZIP_DEFLATED)


def build_esjzone_epub(options: EsjzoneBuildOptions, log: LogCallback = _default_log) -> str:
    cookie = _read_cookie(options.cookie, options.cookie_file)
    client = EsjzoneClient(cookie=cookie)
    builder = EsjzoneEpubBuilder(client, log)
    return builder.build(options)


def search_esjzone(keyword: str, page: int = 1, cookie: str = "", cookie_file: Optional[str] = None) -> list[EsjzoneSearchResult]:
    client = EsjzoneClient(cookie=_read_cookie(cookie, cookie_file))
    return client.search(keyword, page=page)


def _book_uuid(url: str) -> str:
    return "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, url))


def _media_type_for_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")


def _guess_image_suffix(url: str, data: bytes) -> str:
    parsed_suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    if parsed_suffix in {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"}:
        return ".jpg" if parsed_suffix == ".jpeg" else parsed_suffix
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data.startswith(b"GIF"):
        return ".gif"
    if data[:20].lstrip().startswith(b"<svg"):
        return ".svg"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return ".webp"
    return ".jpg"


CONTAINER_XML = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


STYLE_CSS = """@charset "utf-8";
body {
  font-family: serif;
  line-height: 1.75;
  margin: 0 5%;
}
h1 {
  font-size: 1.35em;
  line-height: 1.35;
  margin: 1.2em 0;
  text-align: center;
}
p {
  margin: 0.75em 0;
}
img {
  max-width: 100%;
  height: auto;
}
blockquote {
  border-left: 0.25em solid #aaa;
  margin: 1em 0;
  padding-left: 1em;
}
"""


XHTML_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" lang="zh-CN" xml:lang="zh-CN">
<head>
  <title>{title}</title>
  <link rel="stylesheet" type="text/css" href="../Styles/style.css"/>
</head>
<body>
  <h1>{title}</h1>
  {body}
</body>
</html>
"""
