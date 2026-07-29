from __future__ import annotations

import unittest
from urllib.error import HTTPError

import lxml.html as lxml_html

from src.novel_source import NovelAsset, NovelReadOptions
from src.source_registry import create_novel_source
from src.sources.masiro import MasiroReader, MasiroSource
from src.sources.masiro.chapter_processor import MasiroChapterProcessor
from src.sources.masiro.client import MasiroClient, MasiroRateLimitError
from src.sources.masiro.parser import extract_chapter_html, parse_book_info, parse_payment_info


def _resolve_url(value: str) -> str:
    if value.startswith("/"):
        return "https://masiro.me" + value
    return value


class DummyClient:
    def absolute_url(self, url: str) -> str:
        return _resolve_url(url)

    def get_bytes(self, url: str, *, referer: str = "") -> bytes:
        raise AssertionError(f"Unexpected network request: {url}")


class FakeResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.data


class FakeOpener:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def open(self, request, timeout=None):
        del request, timeout
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _rate_limit_error() -> HTTPError:
    return HTTPError(
        "https://masiro.me/test",
        429,
        "Too Many Requests",
        {"Retry-After": "0"},
        None,
    )


class ReaderClient(DummyClient):
    def __init__(self) -> None:
        self.requested: list[str] = []

    def get_document(self, url: str, **kwargs):
        del kwargs
        self.requested.append(url)
        if "novelView" in url:
            return lxml_html.fromstring(
                """
                <html><body><div class="box n-h">
                  <div class="novel-title">测试书</div>
                  <div class="n-detail"><div class="author"><a>作者</a></div></div>
                </div>
                <ul class="episode-ul">
                  <a href="/admin/novelReading?cid=1"><li class="episode-box"><span>免费章</span><small></small></li></a>
                  <a href="/admin/novelReading?cid=2"><li class="episode-box"><span>收费章</span><small>1G</small></li></a>
                </ul></body></html>
                """
            )
        if "cid=1" in url:
            return lxml_html.fromstring(
                '<html><body><div class="box-body nvl-content"><p>正文</p></div></body></html>'
            )
        raise AssertionError(f"Priced chapter was requested: {url}")


class PurchaseClient(ReaderClient):
    def __init__(self) -> None:
        super().__init__()
        self.purchased = False
        self.posts: list[tuple[str, dict[str, object], str]] = []

    def get_document(self, url: str, **kwargs):
        del kwargs
        self.requested.append(url)
        if "novelView" in url:
            return lxml_html.fromstring(
                """
                <html><body><p>金币:5 粉丝:0</p><div class="box n-h">
                  <div class="novel-title">收费测试书</div>
                  <div class="n-detail"><div class="author"><a>作者</a></div></div>
                </div>
                <ul class="episode-ul">
                  <a href="/admin/novelReading?cid=2"><li class="episode-box"><span>收费章</span><small>1G</small></li></a>
                </ul></body></html>
                """
            )
        if "cid=2" in url and self.purchased:
            return lxml_html.fromstring(
                '<html><body><div class="box-body nvl-content"><p>已购买正文</p></div></body></html>'
            )
        if "cid=2" in url:
            return lxml_html.fromstring(
                """
                <html><head><meta name="csrf-token" content="token-2" /></head><body>
                  <input class="cost" value="1" />
                  <input class="type" value="2" />
                  <input class="object_id" value="2" />
                  <input class="csrf" value="token-2" />
                  <p>立即打钱</p>
                </body></html>
                """
            )
        raise AssertionError(f"Unexpected request: {url}")

    def post_form_json(self, url: str, data: dict[str, object], *, csrf_token: str, **kwargs) -> dict:
        del kwargs
        self.posts.append((url, data, csrf_token))
        self.purchased = True
        return {"code": 1, "msg": "支付成功"}


class UncertainPurchaseClient(PurchaseClient):
    def post_form_json(self, url: str, data: dict[str, object], *, csrf_token: str, **kwargs) -> dict:
        super().post_form_json(url, data, csrf_token=csrf_token, **kwargs)
        raise RuntimeError("connection closed after payment")


class ChangedPriceClient(PurchaseClient):
    def get_document(self, url: str, **kwargs):
        doc = super().get_document(url, **kwargs)
        if "cid=2" in url and not self.purchased:
            cost = doc.xpath("//input[contains(concat(' ', normalize-space(@class), ' '), ' cost ')]")
            if cost:
                cost[0].set("value", "2")
        return doc


class LostPurchaseResponseClient(PurchaseClient):
    def post_form_json(self, url: str, data: dict[str, object], *, csrf_token: str, **kwargs) -> dict:
        del kwargs
        self.posts.append((url, data, csrf_token))
        raise RuntimeError("connection closed before result")


class MasiroParserTests(unittest.TestCase):
    def test_parse_book_info_extracts_metadata_and_chapters(self) -> None:
        doc = lxml_html.fromstring(
            """
            <html><body>
              <div class="box n-h">
                <div class="novel-title">测试书</div>
                <img class="img-thumbnail" src="/cover.webp?quality=60" />
                <div class="n-detail">
                  <div class="author">作者：<a>测试作者</a></div>
                  <div class="n-translator">翻译：<a>测试译者</a><a>协力译者</a></div>
                  <div class="n-status">状态：连载中</div>
                  <div class="tags"><span class="label">异世界</span></div>
                  <div class="n-update"><a href="/admin/novelReading?cid=2">第二话</a></div>
                  <div class="n-chapters">字数：1000字共2话</div>
                </div>
                <div class="brief"><p>简介正文</p></div>
              </div>
              <ul class="episode-ul">
                <a href="/admin/novelReading?cid=1"><li class="episode-box"><span>第一话</span><small></small></li></a>
                <a href="/admin/novelReading?cid=2"><li class="episode-box"><span>第二话</span><small>1G</small></li></a>
              </ul>
            </body></html>
            """
        )

        info = parse_book_info(doc, "https://masiro.me/admin/novelView?novel_id=1", _resolve_url)

        self.assertEqual(info.title, "测试书")
        self.assertEqual(info.author, "测试作者")
        self.assertEqual(info.translator, "测试译者、协力译者")
        self.assertEqual(info.translators, ("测试译者", "协力译者"))
        self.assertEqual(info.description, "简介正文")
        self.assertEqual(info.tags, ("异世界",))
        self.assertEqual(info.status, "连载中")
        self.assertEqual(info.cover_url, "https://masiro.me/cover.webp?quality=60")
        self.assertEqual(info.kind, "连载中 / 异世界")
        self.assertEqual(info.word_count, "1000字共2话")
        self.assertEqual(info.latest_chapter, "第二话")
        self.assertEqual([chapter.title for chapter in info.chapters], ["第一话", "第二话"])
        self.assertEqual(info.chapters[1].cost, 1)

    def test_parse_book_info_reports_login_page(self) -> None:
        doc = lxml_html.fromstring(
            '<html><head><title>登录</title></head><body><form action="/admin/auth/login"><input type="password" /></form></body></html>'
        )

        with self.assertRaisesRegex(RuntimeError, "login is required"):
            parse_book_info(doc, "https://masiro.me/admin/novelView?novel_id=1", _resolve_url)

    def test_parse_book_info_falls_back_to_interleaved_chapter_json(self) -> None:
        doc = lxml_html.fromstring(
            """
            <html><body>
              <div class="box n-h"><div class="novel-title">旧书</div></div>
              <script id="f-chapters-json" type="application/json">
                [{"id": 10, "title": "第一卷"}, {"id": 20, "title": "第二卷"}]
              </script>
              <script id="chapters-json" type="application/json">
                [
                  {"id": 1, "parent_id": 10, "title": "第一话", "cost": 0},
                  {"id": 3, "parent_id": 20, "title": "第三话", "cost": 1},
                  {"id": 2, "parent_id": 10, "title": "第二话", "cost": 0},
                  {"id": 4, "parent_id": 20, "title": "第四话", "cost": 0}
                ]
              </script>
            </body></html>
            """
        )

        info = parse_book_info(doc, "https://masiro.me/admin/novelView?novel_id=10", _resolve_url)

        self.assertEqual([chapter.title for chapter in info.chapters], ["第一话", "第二话", "第三话", "第四话"])
        self.assertEqual(info.chapters[2].cost, 1)
        self.assertEqual(info.chapters[3].url, "https://masiro.me/admin/novelReading?cid=4")

    def test_parse_payment_info_extracts_official_pay_fields(self) -> None:
        doc = lxml_html.fromstring(
            """
            <html><head><meta name="csrf-token" content="token" /></head><body>
              <input class="cost" value="3" />
              <input class="type" value="2" />
              <input class="object_id" value="99" />
              <input class="csrf" value="token" />
            </body></html>
            """
        )

        payment = parse_payment_info(doc)

        self.assertIsNotNone(payment)
        self.assertEqual(payment.cost, 3)  # type: ignore[union-attr]
        self.assertEqual(payment.payment_type, 2)  # type: ignore[union-attr]
        self.assertEqual(payment.object_id, 99)  # type: ignore[union-attr]
        self.assertEqual(payment.csrf_token, "token")  # type: ignore[union-attr]


class MasiroClientTests(unittest.TestCase):
    def test_get_retries_rate_limits_after_shared_cooldown(self) -> None:
        opener = FakeOpener([_rate_limit_error(), _rate_limit_error(), FakeResponse(b"ok")])
        client = MasiroClient(throttle_seconds=0)
        client._opener = opener  # type: ignore[attr-defined]

        result = client.get_bytes("/test", retries=0)

        self.assertEqual(result, b"ok")
        self.assertEqual(opener.calls, 3)

    def test_get_stops_after_bounded_rate_limit_retries(self) -> None:
        opener = FakeOpener([_rate_limit_error(), _rate_limit_error(), _rate_limit_error()])
        client = MasiroClient(throttle_seconds=0)
        client._opener = opener  # type: ignore[attr-defined]

        with self.assertRaises(MasiroRateLimitError):
            client.get_bytes("/test", retries=0)

        self.assertEqual(opener.calls, 3)

    def test_extract_chapter_html_uses_nvl_content(self) -> None:
        doc = lxml_html.fromstring(
            '<html><body><div class="box-body nvl-content"><p>正文</p></div></body></html>'
        )

        self.assertIn("正文", extract_chapter_html(doc))


class MasiroChapterProcessorTests(unittest.TestCase):
    def test_prepare_embeds_data_images_and_removes_blank_paragraphs(self) -> None:
        doc = lxml_html.fromstring(
            '<html><body><div class="box-body nvl-content"><p>正文</p></div></body></html>'
        )
        raw_html = '<p>正文</p><p>&nbsp;</p><p>下一段<img src="data:image/png;base64,iVBORw0KGgo=" /></p>'
        assets: list[NovelAsset] = []
        processor = MasiroChapterProcessor(DummyClient(), lambda message: None)  # type: ignore[arg-type]

        content_html, head_css = processor.prepare(
            raw_html,
            doc,
            "https://masiro.me/admin/novelReading?cid=1",
            1,
            assets,
        )

        self.assertEqual(head_css, ())
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].id, "chapter-0001-001")
        self.assertIn("asset:chapter-0001-001", content_html)
        self.assertNotIn("&nbsp;", content_html)


class MasiroRegistryTests(unittest.TestCase):
    def test_registry_creates_masiro_source(self) -> None:
        self.assertIsInstance(create_novel_source("masiro"), MasiroSource)

    def test_reader_does_not_request_chapters_that_still_show_a_price(self) -> None:
        client = ReaderClient()
        logs: list[str] = []
        reader = MasiroReader(client, logs.append)  # type: ignore[arg-type]

        book = reader.read(
            "https://masiro.me/admin/novelView?novel_id=1",
            NovelReadOptions(chapter_workers=1, slow_chapter_workers=1),
        )

        self.assertEqual([chapter.title for chapter in book.chapters], ["免费章"])
        self.assertFalse(any("cid=2" in url for url in client.requested))
        self.assertTrue(any("purchase price" in message for message in logs))

    def test_reader_auto_purchases_within_approved_budget(self) -> None:
        client = PurchaseClient()
        reader = MasiroReader(
            client,
            lambda message: None,
            auto_purchase=True,
            max_purchase_cost=1,
        )  # type: ignore[arg-type]

        book = reader.read(
            "https://masiro.me/admin/novelView?novel_id=1",
            NovelReadOptions(chapter_workers=1, slow_chapter_workers=1, chapter_retries=0),
        )

        self.assertEqual([chapter.title for chapter in book.chapters], ["收费章"])
        self.assertEqual(len(client.posts), 1)
        self.assertEqual(client.posts[0][0], "/admin/pay")
        self.assertEqual(client.posts[0][1], {"type": 2, "object_id": 2, "cost": 1})
        self.assertEqual(client.posts[0][2], "token-2")

    def test_reader_rejects_purchase_plan_over_budget_before_posting(self) -> None:
        client = PurchaseClient()
        reader = MasiroReader(
            client,
            lambda message: None,
            auto_purchase=True,
            max_purchase_cost=0,
        )  # type: ignore[arg-type]

        with self.assertRaisesRegex(RuntimeError, "exceeding the approved budget"):
            reader.read(
                "https://masiro.me/admin/novelView?novel_id=1",
                NovelReadOptions(chapter_workers=1, slow_chapter_workers=1),
            )

        self.assertEqual(client.posts, [])

    def test_reader_verifies_access_without_repeating_an_uncertain_purchase(self) -> None:
        client = UncertainPurchaseClient()
        reader = MasiroReader(
            client,
            lambda message: None,
            auto_purchase=True,
            max_purchase_cost=1,
        )  # type: ignore[arg-type]

        book = reader.read(
            "https://masiro.me/admin/novelView?novel_id=1",
            NovelReadOptions(chapter_workers=1, slow_chapter_workers=1, chapter_retries=0),
        )

        self.assertEqual([chapter.title for chapter in book.chapters], ["收费章"])
        self.assertEqual(len(client.posts), 1)

    def test_reader_does_not_post_when_server_price_changed(self) -> None:
        client = ChangedPriceClient()
        logs: list[str] = []
        reader = MasiroReader(
            client,
            logs.append,
            auto_purchase=True,
            max_purchase_cost=1,
        )  # type: ignore[arg-type]

        with self.assertRaisesRegex(RuntimeError, "No chapters were fetched successfully"):
            reader.read(
                "https://masiro.me/admin/novelView?novel_id=1",
                NovelReadOptions(chapter_workers=1, slow_chapter_workers=1, chapter_retries=0),
            )

        self.assertEqual(client.posts, [])
        self.assertTrue(any("price changed" in message for message in logs))

    def test_reader_never_repeats_an_unverified_purchase_post(self) -> None:
        client = LostPurchaseResponseClient()
        reader = MasiroReader(
            client,
            lambda message: None,
            auto_purchase=True,
            max_purchase_cost=1,
        )  # type: ignore[arg-type]

        with self.assertRaisesRegex(RuntimeError, "No chapters were fetched successfully"):
            reader.read(
                "https://masiro.me/admin/novelView?novel_id=1",
                NovelReadOptions(chapter_workers=1, slow_chapter_workers=1, chapter_retries=2),
            )

        self.assertEqual(len(client.posts), 1)


if __name__ == "__main__":
    unittest.main()
