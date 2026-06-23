"""HTML helpers used by the ESJZone source adapter."""

from __future__ import annotations

import html as html_lib
import re

import lxml.etree as etree


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


def _clean_labeled_value(value: str, *labels: str) -> str:
    text = _text(value)
    for label in labels:
        text = re.sub(rf"^\s*{re.escape(label)}\s*[:：]?\s*", "", text)
    return text.strip(" :：")


def _detail_value(doc: etree._Element, *labels: str) -> str:
    items = doc.xpath("//ul[contains(concat(' ', normalize-space(@class), ' '), ' book-detail ')]//li")
    for item in items:
        text = _text(item.text_content())
        if not any(label in text for label in labels):
            continue
        link_value = _first_text(item, ".//a[1]/text()")
        if link_value and not any(link_value.strip(" :：") == label for label in labels):
            return link_value
        value = _clean_labeled_value(text, *labels)
        if value:
            return value
    return ""


def _is_empty_block(element: etree._Element) -> bool:
    if not isinstance(element.tag, str) or element.tag.lower() not in {"p", "div"}:
        return False
    if element.xpath(".//img|.//svg|.//hr|.//table|.//video|.//audio"):
        return False
    return not _text(element.text_content())


def _normalise_blank_blocks(wrapper: etree._Element) -> None:
    children = list(wrapper)
    index = 0
    while index < len(children):
        child = children[index]
        if not _is_empty_block(child):
            index += 1
            continue

        run: list[etree._Element] = []
        while index < len(children) and _is_empty_block(children[index]):
            run.append(children[index])
            index += 1

        if len(run) >= 2:
            keeper = run[0]
            keeper.clear()
            keeper.tag = "p"
            keeper.set("class", "scene-break")
            keeper.text = "\u00a0"
            for extra in run[1:]:
                parent = extra.getparent()
                if parent is not None:
                    parent.remove(extra)
        else:
            parent = run[0].getparent()
            if parent is not None:
                parent.remove(run[0])
