import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())

from tools.previewer_compare import DEFAULT_PREVIEWER, compare_one


def collect_epubs(base_dir: Path) -> list[Path]:
    return sorted(p for p in base_dir.rglob("*.epub") if p.is_file())


def _read_summary_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _summary_row(result: dict) -> dict:
    rows = result.get("summary") or []
    return rows[0] if rows else {}


def _int_field(row: dict, key: str) -> int:
    try:
        return int((row.get(key) or "0").strip())
    except Exception:
        return 0


def _et_rank(value: str) -> int:
    normalized = (value or "").strip().lower()
    if normalized == "supported":
        return 2
    if normalized == "not supported":
        return 1
    return 0


def summarize_case(case: dict) -> dict:
    original = _summary_row(case["original"])
    processed = _summary_row(case["processed_result"])

    original_status = {
        "enhanced_typesetting": original.get("Enhanced Typesetting Status", ""),
        "conversion": original.get("Conversion Status", ""),
        "error_count": _int_field(original, "Error Count"),
        "quality_issue_count": _int_field(original, "Quality Issue Count"),
    }
    processed_status = {
        "enhanced_typesetting": processed.get("Enhanced Typesetting Status", ""),
        "conversion": processed.get("Conversion Status", ""),
        "error_count": _int_field(processed, "Error Count"),
        "quality_issue_count": _int_field(processed, "Quality Issue Count"),
    }

    original_success = original_status["conversion"] == "Success"
    processed_success = processed_status["conversion"] == "Success"
    original_et = _et_rank(original_status["enhanced_typesetting"])
    processed_et = _et_rank(processed_status["enhanced_typesetting"])
    improved = (not original_success and processed_success) or (
        processed_success
        and processed_status["quality_issue_count"] < original_status["quality_issue_count"]
    ) or (
        original_success
        and processed_success
        and processed_et > original_et
    )
    regressed = (original_success and not processed_success) or (
        processed_success
        and original_success
        and processed_status["quality_issue_count"] > original_status["quality_issue_count"]
    ) or (
        original_success
        and processed_success
        and processed_et < original_et
    )

    return {
        "input": case["input"],
        "processed": case["processed"],
        "original_status": original_status,
        "processed_status": processed_status,
        "improved": improved,
        "regressed": regressed,
        "same_success_state": original_success == processed_success,
    }


def build_overview(results: list[dict]) -> dict:
    summaries = [summarize_case(case) for case in results]
    total = len(summaries)
    original_success = sum(1 for item in summaries if item["original_status"]["conversion"] == "Success")
    processed_success = sum(1 for item in summaries if item["processed_status"]["conversion"] == "Success")
    improved = sum(1 for item in summaries if item["improved"])
    regressed = sum(1 for item in summaries if item["regressed"])
    processed_with_quality_issues = sum(
        1 for item in summaries if item["processed_status"]["quality_issue_count"] > 0
    )
    processed_with_errors = sum(
        1
        for item in summaries
        if item["processed_status"]["conversion"] != "Success"
        or item["processed_status"]["error_count"] > 0
    )

    return {
        "summary": {
            "total": total,
            "original_success": original_success,
            "processed_success": processed_success,
            "improved": improved,
            "regressed": regressed,
            "processed_with_quality_issues": processed_with_quality_issues,
            "processed_with_errors": processed_with_errors,
        },
        "results": summaries,
    }


def _save_report(report_path: Path, results: list[dict]) -> None:
    overview = build_overview(results)
    overview["raw_results"] = results
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_existing_case(epub_path: Path, case_dir: Path) -> dict | None:
    processed_path = case_dir / "processed" / epub_path.name
    original_summary = _read_summary_csv(case_dir / "preview-original" / "Summary_Log.csv")
    processed_summary = _read_summary_csv(case_dir / "preview-processed" / "Summary_Log.csv")
    if not original_summary or not processed_summary or not processed_path.exists():
        return None

    return {
        "input": str(epub_path.resolve()),
        "processed": str(processed_path.resolve()),
        "original": {
            "summary": original_summary,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        },
        "processed_result": {
            "summary": processed_summary,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
        },
        "resumed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Kindle Previewer against all sample EPUBs and compare original vs processed outputs.")
    parser.add_argument("base_dir", nargs="?", default="测试文件", help="Directory containing EPUB samples")
    parser.add_argument("--previewer", default=str(DEFAULT_PREVIEWER), help="Path to Kindle Previewer executable")
    parser.add_argument("--report", default="build/previewer-audit.json", help="Path to write JSON report")
    parser.add_argument("--workdir", default="build/previewer-audit", help="Directory to keep per-book work products")
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N EPUBs")
    parser.add_argument("--resume", action="store_true", help="Reuse completed case directories when present")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Per Previewer invocation timeout in seconds",
    )
    args = parser.parse_args()

    previewer = Path(args.previewer)
    if not previewer.exists():
        raise SystemExit(f"Kindle Previewer not found: {previewer}")

    epubs = collect_epubs(Path(args.base_dir))
    if args.limit > 0:
        epubs = epubs[: args.limit]

    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    report_path = Path(args.report).resolve()

    results = []
    total = len(epubs)
    for index, epub_path in enumerate(epubs, start=1):
        case_dir = workdir / f"case-{index:03d}-{epub_path.stem}"
        case_dir.mkdir(parents=True, exist_ok=True)
        if args.resume:
            resumed = _load_existing_case(epub_path, case_dir)
            if resumed is not None:
                print(f"[{index}/{total}] {epub_path.name} (resume)")
                results.append(resumed)
                _save_report(report_path, results)
                continue
        print(f"[{index}/{total}] {epub_path.name}")
        try:
            results.append(
                compare_one(
                    previewer,
                    epub_path.resolve(),
                    case_dir,
                    timeout_seconds=args.timeout_seconds,
                )
            )
        except Exception as exc:
            results.append(
                {
                    "input": str(epub_path.resolve()),
                    "processed": "",
                    "original": {"summary": [], "returncode": 1, "stdout": "", "stderr": ""},
                    "processed_result": {
                        "summary": [
                            {
                                "Enhanced Typesetting Status": "Not Supported",
                                "Conversion Status": "Error",
                                "Error Count": "1",
                                "Quality Issue Count": "0",
                            }
                        ],
                        "returncode": 1,
                        "stdout": "",
                        "stderr": f"exception: {exc}",
                    },
                    "exception": str(exc),
                }
            )
        _save_report(report_path, results)

    overview = build_overview(results)
    overview["raw_results"] = results
    print(json.dumps(overview["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote report to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
