"""Masiro chapter content preparation."""

from __future__ import annotations

import re
from urllib.parse import urljoin

import lxml.etree as etree
import lxml.html as lxml_html

from ...novel_source import NovelAsset
from ...utils import LogCallback
from .assets import decode_data_image, guess_image_type, image_source
from .client import MasiroClient
from .parser import _inner_html, _text


class MasiroChapterProcessor:
    def __init__(self, client: MasiroClient, log: LogCallback) -> None:
        self.client = client
        self.log = log

    def prepare(
        self,
        raw_html: str,
        page_doc: etree._Element,
        chapter_url: str,
        chapter_index: int,
        assets: list[NovelAsset],
    ) -> tuple[str, tuple[str, ...]]:
        del page_doc
        wrapper = lxml_html.fragment_fromstring(f"<div>{raw_html}</div>", create_parent=False)
        self._remove_unsafe_nodes(wrapper)
        self._collect_images(wrapper, chapter_url, chapter_index, assets)
        self._normalise_blank_blocks(wrapper)
        return _inner_html(wrapper), ()

    def _remove_unsafe_nodes(self, wrapper: etree._Element) -> None:
        for bad in wrapper.xpath(".//script|.//style|.//iframe|.//form|.//button"):
            parent = bad.getparent()
            if parent is not None:
                parent.remove(bad)
        for element in wrapper.iter():
            if not isinstance(element.tag, str):
                continue
            for attr in list(element.attrib):
                if attr.lower().startswith("on") or attr.lower() in {"contenteditable", "data-id"}:
                    element.attrib.pop(attr, None)
            style = element.get("style")
            if style:
                cleaned = re.sub(r"(?:position|z-index|display)\s*:[^;]+;?", "", style, flags=re.IGNORECASE).strip()
                if cleaned:
                    element.set("style", cleaned)
                else:
                    element.attrib.pop("style", None)

    def _collect_images(
        self,
        wrapper: etree._Element,
        chapter_url: str,
        chapter_index: int,
        assets: list[NovelAsset],
    ) -> None:
        image_counter = 0
        for img in wrapper.xpath(".//img[@src or @data-src or @data-original or @data-lazy-src or @srcset or @data-srcset]"):
            src = image_source(img)
            if not src:
                continue
            decoded = decode_data_image(src) if src.startswith("data:") else None
            if decoded:
                data, suffix, media_type = decoded
            else:
                image_url = self.client.absolute_url(urljoin(chapter_url, src))
                try:
                    data = self.client.get_bytes(image_url, referer=chapter_url)
                except Exception as exc:
                    self.log(f"[Warning] Image download failed: {image_url}: {exc}")
                    parent = img.getparent()
                    if parent is not None:
                        parent.remove(img)
                    continue
                suffix, media_type = guess_image_type(image_url, data)
            image_counter += 1
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
            for attr in ("data-src", "data-original", "data-lazy-src", "srcset", "data-srcset"):
                img.attrib.pop(attr, None)

    def _normalise_blank_blocks(self, wrapper: etree._Element) -> None:
        children = list(wrapper)
        index = 0
        while index < len(children):
            child = children[index]
            if not self._is_empty_block(child):
                index += 1
                continue

            run: list[etree._Element] = []
            while index < len(children) and self._is_empty_block(children[index]):
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

    @staticmethod
    def _is_empty_block(element: etree._Element) -> bool:
        if not isinstance(element.tag, str) or element.tag.lower() not in {"p", "div"}:
            return False
        if element.xpath(".//img|.//svg|.//hr|.//table|.//video|.//audio"):
            return False
        return not _text(element.text_content().replace("\u00a0", ""))
