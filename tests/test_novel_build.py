from __future__ import annotations

import unittest
from dataclasses import dataclass

from src.novel_build import SlowChapterError, read_novel_chapters, select_readable_chapters
from src.novel_source import NovelAsset, NovelReadOptions


@dataclass(frozen=True)
class Chapter:
    title: str
    is_volume: bool = False
    url: str = ""


class SelectReadableChaptersTests(unittest.TestCase):
    def test_filters_volume_entries(self) -> None:
        chapters = [
            Chapter("volume", is_volume=True),
            Chapter("one"),
            Chapter("two"),
        ]

        selected = select_readable_chapters(chapters, NovelReadOptions())

        self.assertEqual([chapter.title for chapter in selected], ["one", "two"])

    def test_applies_inclusive_one_based_range_after_filtering_volumes(self) -> None:
        chapters = [
            Chapter("volume", is_volume=True),
            Chapter("one"),
            Chapter("two"),
            Chapter("three"),
        ]

        selected = select_readable_chapters(
            chapters,
            NovelReadOptions(chapter_start=2, chapter_end=3),
        )

        self.assertEqual([chapter.title for chapter in selected], ["two", "three"])

    def test_max_chapters_is_ignored_when_explicit_range_is_present(self) -> None:
        chapters = [Chapter("one"), Chapter("two"), Chapter("three")]

        selected = select_readable_chapters(
            chapters,
            NovelReadOptions(max_chapters=1, chapter_start=2, chapter_end=3),
        )

        self.assertEqual([chapter.title for chapter in selected], ["two", "three"])

    def test_invalid_range_raises(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Invalid chapter range"):
            select_readable_chapters(
                [Chapter("one")],
                NovelReadOptions(chapter_start=3, chapter_end=2),
            )

    def test_empty_selection_raises(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "No readable chapters"):
            select_readable_chapters(
                [Chapter("volume", is_volume=True)],
                NovelReadOptions(),
            )


class ReadNovelChaptersTests(unittest.TestCase):
    def test_builds_novel_chapters_with_progress_logs(self) -> None:
        chapters = [Chapter("one", url="https://example.test/one"), Chapter("two", url="https://example.test/two")]
        assets: list[NovelAsset] = []
        logs: list[str] = []

        def fetch(chapter: Chapter, timeout: float) -> tuple[str, str]:
            return f"<p>{chapter.title}</p>", f"page:{chapter.title}"

        def prepare(
            raw_html: str,
            page: str,
            chapter: Chapter,
            chapter_index: int,
            chapter_assets: list[NovelAsset],
        ) -> tuple[str, tuple[str, ...]]:
            chapter_assets.append(
                NovelAsset(
                    id=f"asset-{chapter_index}",
                    filename=f"asset-{chapter_index}.txt",
                    data=page.encode("utf-8"),
                    media_type="text/plain",
                )
            )
            return raw_html, (f".chapter-{chapter_index} {{}}",)

        novel_chapters = read_novel_chapters(chapters, assets, fetch, prepare, logs.append)

        self.assertEqual([chapter.title for chapter in novel_chapters], ["one", "two"])
        self.assertEqual(
            [chapter.source_url for chapter in novel_chapters],
            ["https://example.test/one", "https://example.test/two"],
        )
        self.assertEqual(novel_chapters[0].head_css, (".chapter-1 {}",))
        self.assertEqual([asset.id for asset in assets], ["asset-1", "asset-2"])
        self.assertEqual(
            logs,
            [
                "Reading chapter 1/2 (normal, attempt 1): one",
                "Reading chapter 2/2 (normal, attempt 1): two",
                "Preparing chapter 1/2: one",
                "Preparing chapter 2/2: two",
            ],
        )

    def test_slow_chapter_moves_to_slow_queue_without_blocking_other_chapters(self) -> None:
        chapters = [Chapter("slow", url="https://example.test/slow"), Chapter("fast", url="https://example.test/fast")]
        fetch_order: list[tuple[str, float]] = []
        logs: list[str] = []

        def fetch(chapter: Chapter, timeout: float) -> tuple[str, str]:
            fetch_order.append((chapter.title, timeout))
            if chapter.title == "slow" and timeout == 1:
                raise SlowChapterError(chapter.title, timeout)
            return f"<p>{chapter.title}</p>", chapter.title

        def prepare(
            raw_html: str,
            page: str,
            chapter: Chapter,
            chapter_index: int,
            chapter_assets: list[NovelAsset],
        ) -> tuple[str, tuple[str, ...]]:
            return raw_html, ()

        novel_chapters = read_novel_chapters(
            chapters,
            [],
            fetch,
            prepare,
            logs.append,
            NovelReadOptions(
                chapter_workers=1,
                slow_chapter_workers=1,
                chapter_timeout_seconds=1,
                slow_chapter_timeout_seconds=9,
                chapter_retries=0,
            ),
        )

        self.assertEqual([chapter.title for chapter in novel_chapters], ["slow", "fast"])
        self.assertIn(("fast", 1), fetch_order)
        self.assertIn(("slow", 9), fetch_order)
        self.assertTrue(any("moved to slow queue" in message for message in logs))

    def test_failed_chapter_is_skipped_after_retries(self) -> None:
        chapters = [Chapter("bad", url="https://example.test/bad"), Chapter("good", url="https://example.test/good")]
        attempts: dict[str, int] = {}
        logs: list[str] = []

        def fetch(chapter: Chapter, timeout: float) -> tuple[str, str]:
            attempts[chapter.title] = attempts.get(chapter.title, 0) + 1
            if chapter.title == "bad":
                raise RuntimeError("boom")
            return f"<p>{chapter.title}</p>", chapter.title

        def prepare(
            raw_html: str,
            page: str,
            chapter: Chapter,
            chapter_index: int,
            chapter_assets: list[NovelAsset],
        ) -> tuple[str, tuple[str, ...]]:
            return raw_html, ()

        novel_chapters = read_novel_chapters(
            chapters,
            [],
            fetch,
            prepare,
            logs.append,
            NovelReadOptions(chapter_workers=1, slow_chapter_workers=1, chapter_retries=2),
        )

        self.assertEqual([chapter.title for chapter in novel_chapters], ["good"])
        self.assertEqual(attempts["bad"], 3)
        self.assertTrue(any("skipped after retries" in message for message in logs))


if __name__ == "__main__":
    unittest.main()
