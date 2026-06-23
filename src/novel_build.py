"""Shared build orchestration for website novel sources."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Optional, Protocol, TypeVar

from .novel_epub import EpubConversionOptions, KindleNovelEpubConverter
from .novel_source import NovelAsset, NovelChapter, NovelReadOptions, NovelSource
from .utils import LogCallback, _default_log


class ChapterSelectable(Protocol):
    is_volume: bool


class ChapterReadable(ChapterSelectable, Protocol):
    title: str
    url: str


TSelectableChapter = TypeVar("TSelectableChapter", bound=ChapterSelectable)
TChapter = TypeVar("TChapter", bound=ChapterReadable)
TPage = TypeVar("TPage")

FetchChapter = Callable[[TChapter, float], tuple[str, TPage]]
PrepareChapter = Callable[[str, TPage, TChapter, int, list[NovelAsset]], tuple[str, tuple[str, ...]]]


@dataclass(frozen=True)
class NovelBuildOptions:
    book_url: str
    output_path: Optional[str] = None
    output_dir: Optional[str] = None
    max_chapters: Optional[int] = None
    chapter_start: Optional[int] = None
    chapter_end: Optional[int] = None
    validate_output: bool = True
    chapter_workers: int = 4
    slow_chapter_workers: int = 2
    chapter_timeout_seconds: float = 12.0
    slow_chapter_timeout_seconds: float = 60.0
    chapter_retries: int = 2


@dataclass(frozen=True)
class ChapterJob:
    index: int
    chapter: TChapter


@dataclass(frozen=True)
class ChapterFetchResult:
    job: ChapterJob[TChapter]
    raw_html: str
    page_doc: TPage
    attempt: int
    is_slow: bool


@dataclass(frozen=True)
class ChapterFetchFailure:
    job: ChapterJob[TChapter]
    error: Exception
    attempt: int
    is_slow: bool


@dataclass(frozen=True)
class SlowChapterError(Exception):
    chapter_title: str
    timeout_seconds: float

    def __str__(self) -> str:
        return f"Chapter is slower than {self.timeout_seconds:g}s: {self.chapter_title}"


def _is_timeout_error(error: Exception) -> bool:
    if isinstance(error, TimeoutError):
        return True
    text = str(error).lower()
    return "timed out" in text or "timeout" in text


def select_readable_chapters(
    chapters: list[TSelectableChapter],
    options: NovelReadOptions,
) -> list[TSelectableChapter]:
    selected = [chapter for chapter in chapters if not chapter.is_volume]
    if options.chapter_start is not None or options.chapter_end is not None:
        start = max(1, options.chapter_start or 1)
        end = options.chapter_end or len(selected)
        if end < start:
            raise RuntimeError("Invalid chapter range: end is before start")
        selected = selected[start - 1 : end]
    elif options.max_chapters is not None:
        selected = selected[: max(0, options.max_chapters)]

    if not selected:
        raise RuntimeError("No readable chapters matched the requested range")
    return selected


def read_novel_chapters(
    chapters: list[TChapter],
    assets: list[NovelAsset],
    fetch_chapter: FetchChapter[TChapter, TPage],
    prepare_chapter: PrepareChapter[TChapter, TPage],
    log: LogCallback = _default_log,
    options: NovelReadOptions | None = None,
) -> list[NovelChapter]:
    read_options = options or NovelReadOptions()
    results: dict[int, tuple[TChapter, str, TPage]] = {}
    skipped: set[int] = set()

    jobs = [ChapterJob(index, chapter) for index, chapter in enumerate(chapters, start=1)]
    pending_normal: list[ChapterJob[TChapter]] = list(jobs)
    pending_slow: list[ChapterJob[TChapter]] = []
    normal_attempts: dict[int, int] = {}
    slow_attempts: dict[int, int] = {}

    def run_fetch(job: ChapterJob[TChapter], attempt: int, is_slow: bool) -> ChapterFetchResult[TChapter, TPage] | ChapterFetchFailure[TChapter]:
        timeout = read_options.slow_chapter_timeout_seconds if is_slow else read_options.chapter_timeout_seconds
        try:
            raw_html, page_doc = fetch_chapter(job.chapter, timeout)
            return ChapterFetchResult(job, raw_html, page_doc, attempt, is_slow)
        except Exception as exc:
            return ChapterFetchFailure(job, exc, attempt, is_slow)

    def submit_pending(
        executor: ThreadPoolExecutor,
        futures: dict[Future, tuple[ChapterJob[TChapter], int, bool]],
        queue: list[ChapterJob[TChapter]],
        attempts: dict[int, int],
        limit: int,
        is_slow: bool,
    ) -> None:
        while queue and len(futures) < limit:
            job = queue.pop(0)
            attempt = attempts.get(job.index, 0) + 1
            attempts[job.index] = attempt
            lane = "slow" if is_slow else "normal"
            log(f"Reading chapter {job.index}/{len(chapters)} ({lane}, attempt {attempt}): {job.chapter.title}")
            future = executor.submit(run_fetch, job, attempt, is_slow)
            futures[future] = (job, attempt, is_slow)

    def handle_failure(failure: ChapterFetchFailure[TChapter]) -> None:
        job = failure.job
        if not failure.is_slow and isinstance(failure.error, SlowChapterError):
            log(f"[Slow] {job.chapter.title} moved to slow queue")
            pending_slow.append(job)
            return
        if not failure.is_slow and _is_timeout_error(failure.error):
            log(f"[Slow] {job.chapter.title} moved to slow queue after timeout: {failure.error}")
            pending_slow.append(job)
            return

        attempts = slow_attempts if failure.is_slow else normal_attempts
        queue = pending_slow if failure.is_slow else pending_normal
        if attempts.get(job.index, failure.attempt) <= read_options.chapter_retries:
            log(f"[Warning] Chapter failed, retrying: {job.chapter.title}: {failure.error}")
            queue.append(job)
            return

        log(f"[Warning] Chapter skipped after retries: {job.chapter.title}: {failure.error}")
        skipped.add(job.index)

    normal_workers = max(1, read_options.chapter_workers)
    slow_workers = max(1, read_options.slow_chapter_workers)
    with ThreadPoolExecutor(max_workers=normal_workers) as normal_executor, ThreadPoolExecutor(max_workers=slow_workers) as slow_executor:
        normal_futures: dict[Future, tuple[ChapterJob[TChapter], int, bool]] = {}
        slow_futures: dict[Future, tuple[ChapterJob[TChapter], int, bool]] = {}

        while (
            pending_normal
            or pending_slow
            or normal_futures
            or slow_futures
        ):
            submit_pending(normal_executor, normal_futures, pending_normal, normal_attempts, normal_workers, False)
            submit_pending(slow_executor, slow_futures, pending_slow, slow_attempts, slow_workers, True)

            active = set(normal_futures) | set(slow_futures)
            if not active:
                continue

            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                normal_futures.pop(future, None)
                slow_futures.pop(future, None)
                result = future.result()
                if isinstance(result, ChapterFetchFailure):
                    handle_failure(result)
                    continue
                results[result.job.index] = (result.job.chapter, result.raw_html, result.page_doc)

    novel_chapters: list[NovelChapter] = []
    for chapter_index in range(1, len(chapters) + 1):
        if chapter_index in skipped:
            continue
        if chapter_index not in results:
            continue
        entry, raw_html, page_doc = results[chapter_index]
        log(f"Preparing chapter {chapter_index}/{len(chapters)}: {entry.title}")
        content_html, head_css = prepare_chapter(raw_html, page_doc, entry, chapter_index, assets)
        novel_chapters.append(
            NovelChapter(
                title=entry.title,
                content_html=content_html,
                source_url=entry.url,
                is_volume=False,
                head_css=head_css,
            )
        )

    if not novel_chapters:
        raise RuntimeError("No chapters were fetched successfully")
    return novel_chapters


def build_novel_epub(
    source: NovelSource,
    options: NovelBuildOptions,
    log: LogCallback = _default_log,
) -> str:
    log(f"Reading {source.display_name} source data")
    book = source.read(
        options.book_url,
        NovelReadOptions(
            max_chapters=options.max_chapters,
            chapter_start=options.chapter_start,
            chapter_end=options.chapter_end,
            chapter_workers=options.chapter_workers,
            slow_chapter_workers=options.slow_chapter_workers,
            chapter_timeout_seconds=options.chapter_timeout_seconds,
            slow_chapter_timeout_seconds=options.slow_chapter_timeout_seconds,
            chapter_retries=options.chapter_retries,
        ),
    )

    log("Converting source data to Kindle EPUB")
    converter = KindleNovelEpubConverter(log)
    return converter.convert(
        book,
        EpubConversionOptions(
            output_path=options.output_path,
            output_dir=options.output_dir,
            validate_output=options.validate_output,
        ),
    )
