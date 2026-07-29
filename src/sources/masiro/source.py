"""Masiro source adapter."""

from __future__ import annotations

import threading
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import lxml.etree as etree

from ...novel_build import NovelBuildOptions, build_novel_epub, read_novel_chapters, select_readable_chapters
from ...novel_source import NovelAsset, NovelBook, NovelReadOptions, NovelSearchResult
from ...utils import LogCallback, _default_log
from .assets import guess_image_type
from .chapter_processor import MasiroChapterProcessor
from .client import MASIRO_BASE_URL, MasiroClient, _read_cookie
from .models import MasiroBookInfo, MasiroBuildOptions, MasiroChapterRef, MasiroPurchasePlan
from .parser import extract_chapter_html, parse_book_info, parse_payment_info


class MasiroReader:
    def __init__(
        self,
        client: MasiroClient,
        log: LogCallback = _default_log,
        *,
        auto_purchase: bool = False,
        max_purchase_cost: int | None = None,
    ) -> None:
        self.client = client
        self.log = log
        self.auto_purchase = auto_purchase
        self.max_purchase_cost = max_purchase_cost
        self.chapter_processor = MasiroChapterProcessor(client, log)
        self._purchase_lock = threading.Lock()
        self._purchase_attempted_ids: set[int] = set()
        self._purchased_chapter_ids: set[int] = set()
        self._purchase_spent = 0

    def read(self, book_url: str, options: NovelReadOptions) -> NovelBook:
        info = self.fetch_book_info(book_url)
        if not info.chapters:
            raise RuntimeError("No chapters found on the Masiro detail page")

        assets: list[NovelAsset] = []
        cover = self._download_cover(info)
        selected = select_readable_chapters(info.chapters, options)
        purchase_plan = self.purchase_plan(selected, info.account_balance)
        if self.auto_purchase:
            self._validate_purchase_plan(purchase_plan)
            if purchase_plan.chapter_count:
                self.log(
                    f"Auto-purchase approved for {purchase_plan.chapter_count} chapter(s), "
                    f"maximum {purchase_plan.total_cost} coin(s)"
                )
        else:
            selected = [chapter for chapter in selected if chapter.cost <= 0]
            if purchase_plan.chapter_count:
                self.log(
                    f"Skipped {purchase_plan.chapter_count} Masiro chapter(s) that still show a purchase price"
                )
            if not selected:
                raise RuntimeError("No accessible Masiro chapters matched the requested range")
        fetch_options = replace(
            options,
            chapter_workers=min(max(1, options.chapter_workers), 2),
            slow_chapter_workers=1,
        )
        if fetch_options.chapter_workers != options.chapter_workers or fetch_options.slow_chapter_workers != options.slow_chapter_workers:
            self.log(
                "Masiro request concurrency limited to "
                f"{fetch_options.chapter_workers} normal worker(s) and 1 slow worker"
            )
        chapters = read_novel_chapters(
            selected,
            assets,
            self.fetch_chapter_html,
            self._prepare_chapter_content,
            self.log,
            fetch_options,
        )

        return NovelBook(
            title=info.title,
            author=info.author,
            source_url=info.url,
            language="zh-CN",
            intro_html=info.intro_html,
            description=info.description,
            subjects=info.tags,
            translators=info.translators,
            publisher="Masiro",
            status=info.status,
            kind=info.kind,
            word_count=info.word_count,
            latest_chapter=info.latest_chapter,
            cover=cover,
            assets=assets,
            chapters=chapters,
        )

    def fetch_book_info(self, book_url: str) -> MasiroBookInfo:
        doc = self.client.get_document(book_url)
        url = self.client.absolute_url(book_url)
        return parse_book_info(doc, url, self.client.absolute_url)

    def fetch_chapter_html(self, chapter: MasiroChapterRef, timeout: float) -> tuple[str, etree._Element]:
        if chapter.cost > 0:
            doc = self._ensure_chapter_access(chapter, timeout)
        else:
            doc = self.client.get_document(chapter.url, timeout=timeout, retries=0)
        return extract_chapter_html(doc), doc

    @staticmethod
    def purchase_plan(
        chapters: list[MasiroChapterRef],
        account_balance: int | None = None,
    ) -> MasiroPurchasePlan:
        priced = [chapter for chapter in chapters if chapter.cost > 0]
        return MasiroPurchasePlan(
            chapter_count=len(priced),
            total_cost=sum(chapter.cost for chapter in priced),
            account_balance=account_balance,
        )

    def _validate_purchase_plan(self, plan: MasiroPurchasePlan) -> None:
        if plan.chapter_count == 0:
            return
        if self.max_purchase_cost is None or self.max_purchase_cost < 0:
            raise RuntimeError("Auto-purchase requires an explicit non-negative purchase budget")
        if plan.total_cost > self.max_purchase_cost:
            raise RuntimeError(
                f"Masiro purchase plan costs {plan.total_cost} coin(s), exceeding the approved budget "
                f"of {self.max_purchase_cost}"
            )
        if plan.account_balance is not None and plan.total_cost > plan.account_balance:
            raise RuntimeError(
                f"Masiro purchase plan costs {plan.total_cost} coin(s), but the account balance is "
                f"{plan.account_balance}"
            )

    def _ensure_chapter_access(self, chapter: MasiroChapterRef, timeout: float) -> etree._Element:
        chapter_id = self._chapter_id(chapter.url)
        with self._purchase_lock:
            doc = self.client.get_document(chapter.url, timeout=timeout, retries=0)
            try:
                extract_chapter_html(doc)
                self._purchased_chapter_ids.add(chapter_id)
                return doc
            except RuntimeError:
                pass

            if chapter_id in self._purchased_chapter_ids:
                raise RuntimeError("Masiro chapter is still unavailable after purchase")
            if chapter_id in self._purchase_attempted_ids:
                raise RuntimeError("Refusing to repeat an unverified Masiro purchase attempt")
            if not self.auto_purchase:
                raise RuntimeError("Masiro chapter requires purchase and auto-purchase is disabled")

            payment = parse_payment_info(doc)
            if payment is None:
                raise RuntimeError("Masiro purchase details were not found on the chapter page")
            if payment.payment_type != 2 or payment.object_id != chapter_id:
                raise RuntimeError("Masiro purchase details do not match the requested chapter")
            if payment.cost != chapter.cost:
                raise RuntimeError(
                    f"Masiro chapter price changed from {chapter.cost} to {payment.cost} coin(s); "
                    "refresh the purchase preview"
                )
            if self.max_purchase_cost is None or self._purchase_spent + payment.cost > self.max_purchase_cost:
                raise RuntimeError("Masiro purchase would exceed the approved budget")

            self.log(f"Purchasing Masiro chapter for {payment.cost} coin(s): {chapter.title}")
            self._purchase_attempted_ids.add(chapter_id)
            try:
                result = self.client.post_form_json(
                    "/admin/pay",
                    {
                        "type": payment.payment_type,
                        "object_id": payment.object_id,
                        "cost": payment.cost,
                    },
                    csrf_token=payment.csrf_token,
                    referer=chapter.url,
                    timeout=timeout,
                )
            except RuntimeError as purchase_error:
                verification_doc = self.client.get_document(chapter.url, timeout=timeout, retries=0)
                try:
                    extract_chapter_html(verification_doc)
                except RuntimeError:
                    raise purchase_error
                self._purchase_spent += payment.cost
                self._purchased_chapter_ids.add(chapter_id)
                self.log(f"Purchase verified after an uncertain response: {chapter.title}")
                return verification_doc

            if str(result.get("code")) != "1":
                raise RuntimeError(f"Masiro purchase failed: {result.get('msg') or 'unknown error'}")

            self._purchase_spent += payment.cost
            self._purchased_chapter_ids.add(chapter_id)
            purchased_doc = self.client.get_document(chapter.url, timeout=timeout, retries=0)
            extract_chapter_html(purchased_doc)
            self.log(f"Purchased Masiro chapter: {chapter.title}")
            return purchased_doc

    @staticmethod
    def _chapter_id(url: str) -> int:
        values = parse_qs(urlsplit(url).query).get("cid", [])
        if not values or not values[0].isdigit():
            raise RuntimeError(f"Invalid Masiro chapter URL: {url}")
        return int(values[0])

    def _download_cover(self, info: MasiroBookInfo) -> NovelAsset | None:
        if not info.cover_url:
            return None
        try:
            data = self.client.get_bytes(info.cover_url, referer=info.url)
        except Exception as exc:
            self.log(f"[Warning] Cover download failed: {exc}")
            return None
        suffix, media_type = guess_image_type(info.cover_url, data)
        return NovelAsset(id="cover", filename=f"cover{suffix}", data=data, media_type=media_type)

    def _prepare_chapter_content(
        self,
        raw_html: str,
        page_doc: etree._Element,
        chapter: MasiroChapterRef,
        chapter_index: int,
        assets: list[NovelAsset],
    ) -> tuple[str, tuple[str, ...]]:
        return self.chapter_processor.prepare(raw_html, page_doc, chapter.url, chapter_index, assets)


class MasiroSource:
    source_id = "masiro"
    display_name = "Masiro"

    def __init__(
        self,
        client: MasiroClient,
        log: LogCallback = _default_log,
        *,
        auto_purchase: bool = False,
        max_purchase_cost: int | None = None,
    ) -> None:
        self.reader = MasiroReader(
            client,
            log,
            auto_purchase=auto_purchase,
            max_purchase_cost=max_purchase_cost,
        )

    def search(self, keyword: str, page: int = 1) -> list[NovelSearchResult]:
        del keyword, page
        raise RuntimeError("Masiro search is not supported yet; use a novel detail URL")

    def read(self, book_url: str, options: NovelReadOptions) -> NovelBook:
        return self.reader.read(book_url, options)


def build_masiro_epub(options: MasiroBuildOptions, log: LogCallback = _default_log) -> str:
    cookie = _read_cookie(options.cookie, options.cookie_file)
    source = MasiroSource(
        MasiroClient(
            cookie=cookie,
            user_agent=options.user_agent or "",
            rate_limit_callback=lambda seconds: log(
                f"[Rate Limit] Masiro cooling down for {seconds:g} second(s)"
            ),
        ),
        log,
        auto_purchase=options.auto_purchase,
        max_purchase_cost=options.max_purchase_cost,
    )
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


def preview_masiro_purchase(options: MasiroBuildOptions) -> MasiroPurchasePlan:
    cookie = _read_cookie(options.cookie, options.cookie_file)
    reader = MasiroReader(MasiroClient(cookie=cookie, user_agent=options.user_agent or ""))
    info = reader.fetch_book_info(options.book_url)
    selected = select_readable_chapters(
        info.chapters,
        NovelReadOptions(
            max_chapters=options.max_chapters,
            chapter_start=options.chapter_start,
            chapter_end=options.chapter_end,
        ),
    )
    return reader.purchase_plan(selected, info.account_balance)
