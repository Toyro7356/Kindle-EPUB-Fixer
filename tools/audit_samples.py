import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.getcwd())

from src.book_profile import detect_book_profile
from src.book_type import detect_book_type
from src.core import process_epub
from src.epub_io import find_opf, unpack_epub
from src.epub_validator import validate_epub


def collect_epubs(base_dir: Path) -> list[Path]:
    return sorted(p for p in base_dir.rglob("*.epub") if p.is_file())


def analyze_input(epub_path: Path) -> dict:
    with tempfile.TemporaryDirectory() as temp_dir:
        unpack_epub(str(epub_path), temp_dir)
        opf_path = find_opf(temp_dir)
        profile = detect_book_profile(opf_path)
        book_type = detect_book_type(opf_path)
        return {
            "book_type": book_type,
            "layout_mode": profile.layout_mode,
            "preserve_layout": profile.preserve_layout,
            "has_kobo_markers": profile.has_kobo_adobe_markers,
            "has_viewport_pages": profile.has_viewport_pages,
            "has_svg_pages": profile.has_svg_pages,
            "has_javascript": profile.has_javascript,
            "has_vertical_writing": profile.has_vertical_writing,
            "has_rtl_progression": profile.has_rtl_progression,
            "page_count": profile.page_count,
            "notes": profile.notes,
        }


def audit_one(epub_path: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / epub_path.name
    started = time.perf_counter()
    logs: list[str] = []

    meta = analyze_input(epub_path)

    result = {
        "input": str(epub_path),
        "output": str(output_path),
        "meta": meta,
        "ok": False,
        "seconds": 0.0,
        "issues": [],
        "log_tail": [],
    }

    try:
        process_epub(str(epub_path), str(output_path), log=logs.append)
        issues = validate_epub(str(output_path), meta["book_type"])
        result["ok"] = True
        result["issues"] = issues
    except Exception as exc:
        result["issues"] = [f"exception: {exc}"]
    finally:
        result["seconds"] = round(time.perf_counter() - started, 3)
        result["log_tail"] = logs[-20:]

    return result


def summarize(results: list[dict]) -> dict:
    total = len(results)
    success = sum(1 for item in results if item["ok"])
    with_issues = sum(1 for item in results if item["issues"])
    preserve_layout = sum(1 for item in results if item["meta"]["preserve_layout"])
    avg_seconds = round(sum(item["seconds"] for item in results) / total, 3) if total else 0.0
    return {
        "total": total,
        "success": success,
        "with_issues": with_issues,
        "preserve_layout_count": preserve_layout,
        "average_seconds": avg_seconds,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit sample EPUB processing results.")
    parser.add_argument("base_dir", nargs="?", default="测试文件", help="Base directory containing sample EPUB files")
    parser.add_argument("--limit", type=int, default=0, help="Only audit the first N EPUBs")
    parser.add_argument(
        "--output-dir",
        default="build/audit-output",
        help="Directory to place processed output files",
    )
    parser.add_argument(
        "--report",
        default="build/audit-report.json",
        help="Path to write the JSON report",
    )
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Delete the output directory before auditing",
    )
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    output_dir = Path(args.output_dir)
    report_path = Path(args.report)

    if args.clean_output and output_dir.exists():
        shutil.rmtree(output_dir)

    epubs = collect_epubs(base_dir)
    if args.limit > 0:
        epubs = epubs[: args.limit]

    results = []
    for idx, epub in enumerate(epubs, start=1):
        print(f"[{idx}/{len(epubs)}] {epub.name}")
        result = audit_one(epub, output_dir)
        results.append(result)
        status = "OK" if result["ok"] and not result["issues"] else "WARN"
        print(f"  -> {status} in {result['seconds']}s")
        if result["issues"]:
            for issue in result["issues"][:5]:
                print(f"     - {issue}")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summarize(results),
        "results": results,
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"Report written to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
