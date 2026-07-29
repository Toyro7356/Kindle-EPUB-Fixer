"""Machine-readable backend used by the native WinUI frontend."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .core import process_epub
from .esjzone import EsjzoneBuildOptions, build_esjzone_epub, search_esjzone
from .masiro import MasiroBuildOptions, build_masiro_epub, preview_masiro_purchase
from .novel_build import NovelBuildOptions, build_novel_epub
from .source_registry import create_novel_source


def _emit(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=True), flush=True)


def _parse_chapter_range(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    text = value.strip()
    if not text:
        return None, None
    match = re.match(r"^(\d+)\s*(?:-|~|～|—|–|至|到)\s*(\d+)\s*(?:话|話|章|章节|章節)?$", text)
    if not match:
        raise ValueError("Chapter range must look like 1-10")
    start = int(match.group(1))
    end = int(match.group(2))
    if start <= 0 or end < start:
        raise ValueError("Chapter range must be positive and ascending")
    return start, end


def _read_optional_text(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8-sig")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kindle EPUB Fixer backend")
    parser.add_argument("--input", help="Input EPUB path")
    parser.add_argument("--output", help="Output EPUB path or output directory")
    parser.add_argument("--output-dir", help="Output directory")
    parser.add_argument("--version", action="store_true", help="Print backend version event")
    parser.add_argument("--novel-source", help="Website novel source id, for example esjzone or masiro")
    parser.add_argument("--novel-url", help="Book detail URL to fetch and convert with --novel-source")
    parser.add_argument("--novel-search", help="Search a website novel source by keyword")
    parser.add_argument("--novel-page", type=int, default=1, help="Website novel source search page")
    parser.add_argument("--novel-cookie", help="Raw Cookie header value for the website novel source")
    parser.add_argument("--novel-cookie-file", help="Path to a text file containing the website novel source Cookie header")
    parser.add_argument("--novel-user-agent", help="Browser User-Agent paired with the website login Cookie")
    parser.add_argument("--novel-auto-purchase", action="store_true", help="Allow supported sources to purchase selected chapters")
    parser.add_argument("--novel-max-purchase-cost", type=int, help="Hard coin budget for automatic chapter purchases")
    parser.add_argument("--esjzone-url", help="ESJZone book detail URL to fetch and convert")
    parser.add_argument("--esjzone-search", help="Search ESJZone by keyword and print result events")
    parser.add_argument("--esjzone-page", type=int, default=1, help="ESJZone search page")
    parser.add_argument("--esjzone-cookie", help="Raw ESJZone Cookie header value")
    parser.add_argument("--esjzone-cookie-file", help="Path to a text file containing ESJZone Cookie header value")
    parser.add_argument("--masiro-url", help="Masiro novel detail URL to fetch and convert")
    parser.add_argument("--masiro-cookie", help="Raw Masiro Cookie header value")
    parser.add_argument("--masiro-cookie-file", help="Path to a text file containing Masiro Cookie header value")
    parser.add_argument("--masiro-user-agent", help="Browser User-Agent paired with the Masiro login Cookie")
    parser.add_argument("--masiro-preview", action="store_true", help="Preview selected Masiro chapter purchase cost without buying")
    parser.add_argument("--masiro-auto-purchase", action="store_true", help="Automatically purchase selected Masiro chapters")
    parser.add_argument("--masiro-max-purchase-cost", type=int, help="Hard coin budget for automatic Masiro purchases")
    parser.add_argument("--max-chapters", type=int, help="Limit chapter count for web-novel conversion")
    parser.add_argument("--chapter-range", help="Fetch an inclusive 1-based chapter range, for example 1-10")
    parser.add_argument("--chapter-start", type=int, help="Fetch chapters starting at this 1-based index")
    parser.add_argument("--chapter-end", type=int, help="Fetch chapters through this 1-based index")
    parser.add_argument("--chapter-workers", type=int, default=4, help="Normal website novel chapter worker count")
    parser.add_argument("--slow-chapter-workers", type=int, default=2, help="Slow website novel chapter worker count")
    parser.add_argument("--chapter-timeout", type=float, default=12.0, help="Normal chapter fetch timeout in seconds")
    parser.add_argument("--slow-chapter-timeout", type=float, default=60.0, help="Slow queue chapter fetch timeout in seconds")
    parser.add_argument("--chapter-retries", type=int, default=2, help="Retries before skipping a failed chapter")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.version:
        _emit("version", version=__version__)
        return

    if args.novel_search:
        try:
            if not args.novel_source:
                raise ValueError("Missing required argument: --novel-source")
            source = create_novel_source(
                args.novel_source,
                cookie=args.novel_cookie or _read_optional_text(args.novel_cookie_file),
                user_agent=args.novel_user_agent or "",
                auto_purchase=args.novel_auto_purchase,
                max_purchase_cost=args.novel_max_purchase_cost,
            )
            results = source.search(args.novel_search, page=args.novel_page)
            _emit(
                "search_results",
                source=source.source_id,
                count=len(results),
                results=[result.__dict__ for result in results],
            )
            return
        except Exception as exc:
            _emit("error", message=str(exc))
            sys.exit(1)

    if args.novel_url:
        try:
            if not args.novel_source:
                raise ValueError("Missing required argument: --novel-source")
            range_start, range_end = _parse_chapter_range(args.chapter_range)
            chapter_start = args.chapter_start or range_start
            chapter_end = args.chapter_end or range_end
            _emit("progress", status="Reading novel source", progress=5)

            def log(message: str) -> None:
                _emit("log", message=message)

            source = create_novel_source(
                args.novel_source,
                cookie=args.novel_cookie or _read_optional_text(args.novel_cookie_file),
                user_agent=args.novel_user_agent or "",
                auto_purchase=args.novel_auto_purchase,
                max_purchase_cost=args.novel_max_purchase_cost,
                log=log,
            )
            output_path = build_novel_epub(
                source,
                NovelBuildOptions(
                    book_url=args.novel_url,
                    output_path=args.output,
                    output_dir=args.output_dir,
                    max_chapters=args.max_chapters,
                    chapter_start=chapter_start,
                    chapter_end=chapter_end,
                    validate_output=True,
                    chapter_workers=args.chapter_workers,
                    slow_chapter_workers=args.slow_chapter_workers,
                    chapter_timeout_seconds=args.chapter_timeout,
                    slow_chapter_timeout_seconds=args.slow_chapter_timeout,
                    chapter_retries=args.chapter_retries,
                ),
                log=log,
            )
            _emit("progress", status="Done", progress=100, output=output_path)
            _emit("done", output=output_path)
            return
        except Exception as exc:
            _emit("error", message=str(exc))
            sys.exit(1)

    if args.masiro_url:
        try:
            range_start, range_end = _parse_chapter_range(args.chapter_range)
            chapter_start = args.chapter_start or range_start
            chapter_end = args.chapter_end or range_end
            _emit("progress", status="抓取书籍信息", progress=5)

            def log(message: str) -> None:
                _emit("log", message=message)

            options = MasiroBuildOptions(
                book_url=args.masiro_url,
                output_path=args.output,
                output_dir=args.output_dir,
                cookie=args.masiro_cookie,
                cookie_file=args.masiro_cookie_file,
                user_agent=args.masiro_user_agent,
                auto_purchase=args.masiro_auto_purchase,
                max_purchase_cost=args.masiro_max_purchase_cost,
                max_chapters=args.max_chapters,
                chapter_start=chapter_start,
                chapter_end=chapter_end,
                chapter_workers=args.chapter_workers,
                slow_chapter_workers=args.slow_chapter_workers,
                chapter_timeout_seconds=args.chapter_timeout,
                slow_chapter_timeout_seconds=args.slow_chapter_timeout,
                chapter_retries=args.chapter_retries,
            )
            if args.masiro_preview:
                plan = preview_masiro_purchase(options)
                _emit(
                    "purchase_plan",
                    chapter_count=plan.chapter_count,
                    total_cost=plan.total_cost,
                    account_balance=plan.account_balance,
                )
                return

            output_path = build_masiro_epub(options, log=log)
            _emit("progress", status="完成", progress=100, output=output_path)
            _emit("done", output=output_path)
            return
        except Exception as exc:
            _emit("error", message=str(exc))
            sys.exit(1)

    if args.esjzone_search:
        try:
            results = search_esjzone(
                args.esjzone_search,
                page=args.esjzone_page,
                cookie=args.esjzone_cookie or "",
                cookie_file=args.esjzone_cookie_file,
            )
            _emit(
                "search_results",
                source="esjzone",
                count=len(results),
                results=[result.__dict__ for result in results],
            )
            return
        except Exception as exc:
            _emit("error", message=str(exc))
            sys.exit(1)

    if args.esjzone_url:
        try:
            range_start, range_end = _parse_chapter_range(args.chapter_range)
            chapter_start = args.chapter_start or range_start
            chapter_end = args.chapter_end or range_end
            _emit("progress", status="抓取书籍信息", progress=5)

            def log(message: str) -> None:
                _emit("log", message=message)

            output_path = build_esjzone_epub(
                EsjzoneBuildOptions(
                    book_url=args.esjzone_url,
                    output_path=args.output,
                    output_dir=args.output_dir,
                    cookie=args.esjzone_cookie,
                    cookie_file=args.esjzone_cookie_file,
                    max_chapters=args.max_chapters,
                    chapter_start=chapter_start,
                    chapter_end=chapter_end,
                    chapter_workers=args.chapter_workers,
                    slow_chapter_workers=args.slow_chapter_workers,
                    chapter_timeout_seconds=args.chapter_timeout,
                    slow_chapter_timeout_seconds=args.slow_chapter_timeout,
                    chapter_retries=args.chapter_retries,
                ),
                log=log,
            )
            _emit("progress", status="完成", progress=100, output=output_path)
            _emit("done", output=output_path)
            return
        except Exception as exc:
            _emit("error", message=str(exc))
            sys.exit(1)

    if not args.input:
        _emit("error", message="Missing required argument: --input")
        sys.exit(2)

    input_path = Path(args.input).resolve()
    output_target = args.output or args.output_dir
    if args.output_dir:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        _emit("error", message=f"Input file does not exist: {input_path}")
        sys.exit(2)

    try:
        _emit("progress", status="分析中", progress=8)

        def log(message: str) -> None:
            _emit("log", message=message)

        output_path = process_epub(str(input_path), output_target, log=log)
        _emit("progress", status="完成", progress=100, output=output_path)
        _emit("done", output=output_path)
    except Exception as exc:
        _emit("error", message=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
