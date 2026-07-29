"""HTML parsers for ESJZone pages."""

from __future__ import annotations

import html as html_lib
from collections.abc import Callable

import lxml.etree as etree

from .html_utils import _detail_value, _first_attr, _first_text, _has_class, _inner_html, _text
from .models import EsjzoneBookInfo, EsjzoneChapterRef, EsjzoneSearchResult


def parse_search_results(
    doc: etree._Element,
    resolve_url: Callable[[str], str],
) -> list[EsjzoneSearchResult]:
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
        url = resolve_url(href)
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
                cover_url=resolve_url(cover) if cover else "",
                latest_chapter=latest,
                summary=summary,
            )
        )
    return results


def parse_book_info(
    doc: etree._Element,
    book_url: str,
    resolve_url: Callable[[str], str],
) -> EsjzoneBookInfo:
    title = _first_text(
        doc,
        "//div[contains(concat(' ', normalize-space(@class), ' '), ' book-detail ')]/h2/text()"
        "|//h2/text()",
    )
    author = _detail_value(doc, "作者")
    cover = _first_attr(doc, "//div[contains(@class, 'col-md-3')]//img[1]/@src")
    if "empty" in cover:
        cover = ""

    tags = [
        _text(item.text_content())
        for item in doc.xpath("//section[contains(@class, 'm-t-20')]//a[contains(@class, 'tag')]")
        if _text(item.text_content())
    ]
    desc = doc.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' description ')]")
    description = _text(desc[0].text_content()) if desc else ""
    intro_parts: list[str] = []
    if tags:
        intro_parts.append("<p>" + html_lib.escape("🏷️" + " / ".join(tags)) + "</p>")
    if desc:
        intro_parts.append(_inner_html(desc[0]))

    kind = _detail_value(doc, "类型", "類型")
    word_count = _first_text(doc, "//*[contains(concat(' ', normalize-space(@class), ' '), ' icon-file-text ')]/parent::*//text()")

    chapters = parse_chapters(doc, resolve_url)
    latest = next((chapter.title for chapter in reversed(chapters) if not chapter.is_volume), "")
    if not latest:
        latest = _first_text(doc, "//*[@id='chapterList']//a[last()]/text()")

    return EsjzoneBookInfo(
        title=title or "ESJZone Book",
        author=author or "未知作者",
        url=book_url,
        cover_url=resolve_url(cover) if cover else "",
        intro_html="\n".join(part for part in intro_parts if part),
        description=description,
        tags=tuple(tags),
        kind=kind,
        word_count=word_count,
        latest_chapter=latest,
        chapters=chapters,
    )


def parse_chapters(
    doc: etree._Element,
    resolve_url: Callable[[str], str],
) -> list[EsjzoneChapterRef]:
    nodes = doc.xpath("//*[@id='chapterList']//*[self::a or self::p or self::summary]")
    chapters: list[EsjzoneChapterRef] = []
    seen_urls: set[str] = set()
    for node in nodes:
        tag = node.tag.lower() if isinstance(node.tag, str) else ""
        class_attr = node.get("class") or ""
        is_volume = tag in {"p", "summary"} or _has_class(class_attr, "non")
        title = _text(node.get("data-title") or node.text_content())
        href = node.get("href") or ""
        url = resolve_url(href) if href else ""

        if is_volume:
            continue
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        chapters.append(EsjzoneChapterRef(title=title, url=url, is_volume=False))

    if chapters:
        return chapters

    for link in doc.xpath("//a[contains(@href, '.html') and contains(@href, '/forum/')]"):
        title = _text(link.text_content())
        url = resolve_url(link.get("href") or "")
        if title and url and url not in seen_urls:
            seen_urls.add(url)
            chapters.append(EsjzoneChapterRef(title=title, url=url, is_volume=False))
    return chapters


def extract_chapter_html(doc: etree._Element) -> str:
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
