"""ESJZone chapter content preparation."""

from __future__ import annotations

from urllib.parse import urljoin

import lxml.etree as etree
import lxml.html as lxml_html

from ...esjzone_font import chapter_font_css, extract_esjzone_font, rewrite_chapter_font_family
from ...novel_source import NovelAsset
from ...utils import LogCallback
from .assets import _decode_data_image, _guess_image_type, _image_source
from .client import EsjzoneClient
from .html_utils import _inner_html, _normalise_blank_blocks


class EsjzoneChapterProcessor:
    def __init__(self, client: EsjzoneClient, log: LogCallback) -> None:
        self.client = client
        self.log = log
        self._font_asset_ids: set[str] = set()

    def prepare(
        self,
        raw_html: str,
        page_doc: etree._Element,
        chapter_url: str,
        chapter_index: int,
        assets: list[NovelAsset],
    ) -> tuple[str, tuple[str, ...]]:
        wrapper = lxml_html.fragment_fromstring(f"<div>{raw_html}</div>", create_parent=False)
        self._remove_unsafe_nodes(wrapper)

        head_css = self._apply_scrambled_font(wrapper, page_doc, assets)
        self._collect_images(wrapper, chapter_url, chapter_index, assets)

        _normalise_blank_blocks(wrapper)
        return _inner_html(wrapper), head_css

    def _remove_unsafe_nodes(self, wrapper: etree._Element) -> None:
        for bad in wrapper.xpath(".//script|.//style|.//iframe|.//form|.//link[starts-with(translate(@href, 'DATA', 'data'), 'data:text/css')]"):
            parent = bad.getparent()
            if parent is not None:
                parent.remove(bad)

    def _apply_scrambled_font(
        self,
        wrapper: etree._Element,
        page_doc: etree._Element,
        assets: list[NovelAsset],
    ) -> tuple[str, ...]:
        embedded_font = extract_esjzone_font(page_doc)
        if embedded_font is None:
            return ()

        if embedded_font.asset_id not in self._font_asset_ids:
            assets.append(
                NovelAsset(
                    id=embedded_font.asset_id,
                    filename=embedded_font.filename,
                    data=embedded_font.data,
                    media_type=embedded_font.media_type,
                    kind="font",
                )
            )
            self._font_asset_ids.add(embedded_font.asset_id)
            self.log(
                "Embedded ESJZone scrambled font "
                f"{embedded_font.family!r} -> {embedded_font.filename}"
            )

        rewrite_chapter_font_family(wrapper, embedded_font)
        return (chapter_font_css(embedded_font),)

    def _collect_images(
        self,
        wrapper: etree._Element,
        chapter_url: str,
        chapter_index: int,
        assets: list[NovelAsset],
    ) -> None:
        image_counter = 0
        for img in wrapper.xpath(".//img[@src or @data-src or @data-original or @data-lazy-src or @srcset or @data-srcset]"):
            src = _image_source(img)
            if not src:
                continue
            decoded = _decode_data_image(src) if src.startswith("data:") else None
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
                suffix, media_type = _guess_image_type(image_url, data)
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
            img.attrib.pop("data-src", None)
            img.attrib.pop("data-original", None)
            img.attrib.pop("data-lazy-src", None)
            img.attrib.pop("srcset", None)
            img.attrib.pop("data-srcset", None)
