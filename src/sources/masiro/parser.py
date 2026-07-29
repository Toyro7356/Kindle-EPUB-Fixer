"""HTML parsers for authenticated Masiro pages."""

from __future__ import annotations

import html as html_lib
import json
import re
from collections.abc import Callable

import lxml.etree as etree

from .models import MasiroBookInfo, MasiroChapterRef, MasiroPaymentInfo


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _inner_html(element: etree._Element) -> str:
    chunks: list[str] = []
    if element.text:
        chunks.append(html_lib.escape(element.text))
    for child in element:
        chunks.append(etree.tostring(child, encoding="unicode", method="xml"))
    return "".join(chunks).strip()


def _first_text(root: etree._Element, xpath: str) -> str:
    for value in root.xpath(xpath):
        text = _text(value.text_content() if isinstance(value, etree._Element) else value)
        if text:
            return text
    return ""


def _first_attr(root: etree._Element, xpath: str) -> str:
    for value in root.xpath(xpath):
        text = _text(value)
        if text:
            return text
    return ""


def _clean_labeled_value(value: str, *labels: str) -> str:
    text = _text(value)
    for label in labels:
        text = re.sub(rf"^\s*{re.escape(label)}\s*[:：]?\s*", "", text)
    return text.strip(" :：")


def _cost_value(value: object) -> int:
    match = re.search(r"\d+", _text(value))
    return int(match.group(0)) if match else 0


def _looks_like_login(doc: etree._Element) -> bool:
    return bool(
        doc.xpath("//form[contains(@action, '/auth/login') or contains(@action, '/login')]")
        or doc.xpath("//input[@type='password']")
        or "登录" in _first_text(doc, "//title/text()")
    )


def parse_book_info(
    doc: etree._Element,
    book_url: str,
    resolve_url: Callable[[str], str],
) -> MasiroBookInfo:
    title = _first_text(doc, "//*[contains(concat(' ', normalize-space(@class), ' '), ' n-h ')]//*[contains(concat(' ', normalize-space(@class), ' '), ' novel-title ')][1]")
    if not title:
        if _looks_like_login(doc):
            raise RuntimeError("Masiro login is required. Refresh the Cookie from the web login window.")
        raise RuntimeError("Masiro book details were not found; the page may be blocked or unavailable")

    author = _first_text(doc, "//*[contains(concat(' ', normalize-space(@class), ' '), ' n-detail ')]//*[contains(concat(' ', normalize-space(@class), ' '), ' author ')]//a[1]")
    translators = tuple(
        dict.fromkeys(
            text
            for item in doc.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' n-translator ')]//a")
            if (text := _text(item.text_content()))
        )
    )
    cover = _first_attr(doc, "//*[contains(concat(' ', normalize-space(@class), ' '), ' n-h ')]//img[contains(concat(' ', normalize-space(@class), ' '), ' img-thumbnail ')][1]/@src")
    tags = [
        _text(item.text_content())
        for item in doc.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' tags ')]//*[contains(concat(' ', normalize-space(@class), ' '), ' label ')]")
        if _text(item.text_content())
    ]
    status = _clean_labeled_value(
        _first_text(doc, "//*[contains(concat(' ', normalize-space(@class), ' '), ' n-status ')]"),
        "状态",
    )
    brief = doc.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' n-h ')]//*[contains(concat(' ', normalize-space(@class), ' '), ' brief ')][1]")
    intro_html = _inner_html(brief[0]) if brief else ""
    description = _text(brief[0].text_content()) if brief else ""
    word_count = _clean_labeled_value(
        _first_text(doc, "//*[contains(concat(' ', normalize-space(@class), ' '), ' n-chapters ')]"),
        "字数",
    )
    latest = _first_text(doc, "//*[contains(concat(' ', normalize-space(@class), ' '), ' n-update ')]//a[contains(@href, 'novelReading')][1]")
    chapters = parse_chapters(doc, resolve_url)
    balance_match = re.search(r"金币\s*[:：]\s*(\d+)", _text(doc.text_content()))

    return MasiroBookInfo(
        title=title,
        author=author or "未知作者",
        translators=translators,
        url=book_url,
        cover_url=resolve_url(cover) if cover else "",
        intro_html=intro_html,
        description=description,
        tags=tuple(tags),
        status=status,
        kind=" / ".join([item for item in [status, *tags] if item]),
        word_count=word_count,
        latest_chapter=latest or (chapters[-1].title if chapters else ""),
        chapters=chapters,
        account_balance=int(balance_match.group(1)) if balance_match else None,
    )


def parse_chapters(
    doc: etree._Element,
    resolve_url: Callable[[str], str],
) -> list[MasiroChapterRef]:
    chapters: list[MasiroChapterRef] = []
    seen_urls: set[str] = set()
    links = doc.xpath("//ul[contains(concat(' ', normalize-space(@class), ' '), ' episode-ul ')]/a[contains(@href, 'novelReading?cid=')]")
    for link in links:
        href = link.get("href") or ""
        url = resolve_url(href)
        if not url or url in seen_urls:
            continue
        title = _first_text(link, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' episode-box ')]/span[1]")
        if not title:
            title = _first_text(link, ".//li[1]")
        if not title:
            continue
        cost = _cost_value(_first_text(link, ".//*[contains(concat(' ', normalize-space(@class), ' '), ' episode-box ')]/small[1]"))
        seen_urls.add(url)
        chapters.append(MasiroChapterRef(title=title, url=url, cost=cost))
    if chapters:
        return chapters

    return _parse_chapter_json(doc, resolve_url)


def _parse_chapter_json(
    doc: etree._Element,
    resolve_url: Callable[[str], str],
) -> list[MasiroChapterRef]:
    folders = _read_json_script(doc, "f-chapters-json")
    entries = _read_json_script(doc, "chapters-json")
    if not isinstance(entries, list):
        return []

    folder_ids = [folder.get("id") for folder in folders if isinstance(folder, dict)] if isinstance(folders, list) else []
    ordered_entries: list[dict] = []
    seen_entry_ids: set[object] = set()
    for folder_id in folder_ids:
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("parent_id") != folder_id:
                continue
            entry_id = entry.get("id")
            if entry_id in seen_entry_ids:
                continue
            seen_entry_ids.add(entry_id)
            ordered_entries.append(entry)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        if entry_id in seen_entry_ids:
            continue
        seen_entry_ids.add(entry_id)
        ordered_entries.append(entry)

    chapters: list[MasiroChapterRef] = []
    for entry in ordered_entries:
        chapter_id = entry.get("id")
        title = _text(entry.get("title"))
        if chapter_id is None or not title:
            continue
        cost = _cost_value(entry.get("cost"))
        chapters.append(
            MasiroChapterRef(
                title=title,
                url=resolve_url(f"/admin/novelReading?cid={chapter_id}"),
                cost=cost,
            )
        )
    return chapters


def _read_json_script(doc: etree._Element, script_id: str):
    nodes = doc.xpath(f"//script[@id='{script_id}']")
    if not nodes:
        return []
    payload = nodes[0].text or ""
    try:
        return json.loads(payload)
    except (TypeError, ValueError):
        return []


def parse_payment_info(doc: etree._Element) -> MasiroPaymentInfo | None:
    cost = _cost_value(_first_attr(doc, "//input[contains(concat(' ', normalize-space(@class), ' '), ' cost ')]/@value"))
    payment_type = _cost_value(_first_attr(doc, "//input[contains(concat(' ', normalize-space(@class), ' '), ' type ')]/@value"))
    object_id = _cost_value(_first_attr(doc, "//input[contains(concat(' ', normalize-space(@class), ' '), ' object_id ')]/@value"))
    csrf_token = _first_attr(
        doc,
        "//input[contains(concat(' ', normalize-space(@class), ' '), ' csrf ')]/@value"
        "|//meta[@name='csrf-token']/@content",
    )
    if cost <= 0 or payment_type <= 0 or object_id <= 0 or not csrf_token:
        return None
    return MasiroPaymentInfo(
        cost=cost,
        payment_type=payment_type,
        object_id=object_id,
        csrf_token=csrf_token,
    )


def extract_chapter_html(doc: etree._Element) -> str:
    content = doc.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' nvl-content ')][1]")
    if content:
        return _inner_html(content[0])
    if _looks_like_login(doc):
        raise RuntimeError("Masiro login expired while reading a chapter")
    page_text = _text(doc.text_content())
    if any(marker in page_text for marker in ("购买", "金币不足", "权限不足", "等级不足", "无法阅读")):
        raise RuntimeError("Masiro chapter is not accessible to the current account")
    raise RuntimeError("Masiro chapter content was not found")
