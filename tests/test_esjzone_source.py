from __future__ import annotations

import unittest

import lxml.html as lxml_html

from src.novel_source import NovelAsset
from src.source_registry import available_novel_sources, create_novel_source
from src.sources.esjzone import EsjzoneBuildOptions, EsjzoneSource
from src.sources.esjzone.chapter_processor import EsjzoneChapterProcessor
from src.sources.esjzone.parser import extract_chapter_html, parse_book_info, parse_search_results


def _resolve_url(value: str) -> str:
    if value.startswith("/"):
        return "https://www.esjzone.cc" + value
    return value


class DummyClient:
    def absolute_url(self, url: str) -> str:
        return _resolve_url(url)

    def get_bytes(self, url: str, *, referer: str = "") -> bytes:
        raise AssertionError(f"Unexpected network request: {url}")


class EsjzoneParserTests(unittest.TestCase):
    def test_parse_book_info_extracts_metadata_and_chapters(self) -> None:
        doc = lxml_html.fromstring(
            """
            <html><body>
              <div class="book-detail"><h2>\u6d4b\u8bd5\u4e66</h2></div>
              <ul class="book-detail">
                <li>\u4f5c\u8005\uff1a\u6d4b\u8bd5\u4f5c\u8005</li>
                <li>\u7c7b\u578b\uff1a\u5947\u5e7b</li>
              </ul>
              <div class="col-md-3"><img src="/cover.jpg" /></div>
              <section class="m-t-20"><a class="tag">\u6807\u7b7eA</a></section>
              <div class="description"><p>\u7b80\u4ecb</p></div>
              <div id="chapterList">
                <p>\u5377\u6807\u9898</p>
                <a href="/forum/1/1.html" data-title="\u7b2c\u4e00\u7ae0">x</a>
              </div>
            </body></html>
            """
        )

        info = parse_book_info(doc, "https://www.esjzone.cc/detail/1.html", _resolve_url)

        self.assertEqual(info.title, "\u6d4b\u8bd5\u4e66")
        self.assertEqual(info.author, "\u6d4b\u8bd5\u4f5c\u8005")
        self.assertEqual(info.kind, "\u5947\u5e7b")
        self.assertEqual(info.description, "\u7b80\u4ecb")
        self.assertEqual(info.tags, ("\u6807\u7b7eA",))
        self.assertEqual(info.cover_url, "https://www.esjzone.cc/cover.jpg")
        self.assertEqual(info.latest_chapter, "\u7b2c\u4e00\u7ae0")
        self.assertEqual(len(info.chapters), 1)
        self.assertEqual(info.chapters[0].url, "https://www.esjzone.cc/forum/1/1.html")

    def test_parse_search_results_deduplicates_books(self) -> None:
        doc = lxml_html.fromstring(
            """
            <html><body>
              <div class="product-item">
                <a href="/detail/1.html">\u6d4b\u8bd5\u4e66</a>
                <div class="product-title"><a href="/detail/1.html">\u6d4b\u8bd5\u4e66</a></div>
                <div class="card-author"><a>\u6d4b\u8bd5\u4f5c\u8005</a></div>
                <img data-src="/cover.jpg" />
              </div>
              <div class="product-item">
                <a href="/detail/1.html">\u91cd\u590d</a>
              </div>
            </body></html>
            """
        )

        results = parse_search_results(doc, _resolve_url)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "\u6d4b\u8bd5\u4e66")
        self.assertEqual(results[0].author, "\u6d4b\u8bd5\u4f5c\u8005")
        self.assertEqual(results[0].cover_url, "https://www.esjzone.cc/cover.jpg")

    def test_extract_chapter_html_uses_forum_content(self) -> None:
        doc = lxml_html.fromstring(
            '<html><body><div class="forum-content mt-3"><p>\u6b63\u6587</p></div></body></html>'
        )

        self.assertIn("\u6b63\u6587", extract_chapter_html(doc))


class EsjzoneChapterProcessorTests(unittest.TestCase):
    def test_prepare_embeds_data_uri_images_as_assets(self) -> None:
        doc = lxml_html.fromstring(
            '<html><body><div class="forum-content mt-3"><p>\u6b63\u6587</p></div></body></html>'
        )
        raw_html = '<p>\u6b63\u6587<img src="data:image/png;base64,iVBORw0KGgo=" /></p>'
        assets: list[NovelAsset] = []
        processor = EsjzoneChapterProcessor(DummyClient(), lambda message: None)  # type: ignore[arg-type]

        content_html, head_css = processor.prepare(
            raw_html,
            doc,
            "https://www.esjzone.cc/forum/1/1.html",
            1,
            assets,
        )

        self.assertEqual(head_css, ())
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].id, "chapter-0001-001")
        self.assertEqual(assets[0].media_type, "image/png")
        self.assertIn("asset:chapter-0001-001", content_html)


class EsjzoneRegistryTests(unittest.TestCase):
    def test_legacy_models_and_registry_remain_available(self) -> None:
        self.assertEqual(available_novel_sources(), ("esjzone", "masiro"))
        self.assertIsInstance(create_novel_source("esjzone"), EsjzoneSource)
        self.assertEqual(EsjzoneBuildOptions(book_url="u").book_url, "u")


if __name__ == "__main__":
    unittest.main()
