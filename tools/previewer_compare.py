import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.getcwd())

from src.core import process_epub


DEFAULT_PREVIEWER = Path.home() / "AppData" / "Local" / "Amazon" / "Kindle Previewer 3" / "Kindle Previewer 3.exe"


def run_previewer(previewer: Path, input_path: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(previewer),
        str(input_path),
        "-log",
        "-qualitychecks",
        "-output",
        str(output_dir),
        "-locale",
        "en",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    summary_path = output_dir / "Summary_Log.csv"
    summary_rows = []
    if summary_path.exists():
        with summary_path.open("r", encoding="utf-8-sig", newline="") as fh:
            summary_rows = list(csv.DictReader(fh))

    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "summary": summary_rows,
    }


def compare_one(previewer: Path, epub_path: Path, work_dir: Path) -> dict:
    processed_dir = work_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    processed_path = Path(process_epub(str(epub_path), str(processed_dir / epub_path.name), log=lambda _msg: None))

    original_result = run_previewer(previewer, epub_path, work_dir / "preview-original")
    processed_result = run_previewer(previewer, processed_path, work_dir / "preview-processed")

    return {
        "input": str(epub_path),
        "processed": str(processed_path),
        "original": original_result,
        "processed_result": processed_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Kindle Previewer results for original vs processed EPUB files.")
    parser.add_argument("files", nargs="+", help="EPUB files to compare")
    parser.add_argument("--previewer", default=str(DEFAULT_PREVIEWER), help="Path to Kindle Previewer executable")
    parser.add_argument("--report", default="build/previewer-compare.json", help="JSON report path")
    parser.add_argument(
        "--keep-workdir",
        default="",
        help="Keep per-book working directories under this path instead of using a temporary directory",
    )
    args = parser.parse_args()

    previewer = Path(args.previewer)
    if not previewer.exists():
        raise SystemExit(f"Kindle Previewer not found: {previewer}")

    results = []
    keep_root = Path(args.keep_workdir).resolve() if args.keep_workdir else None
    if keep_root is not None:
        keep_root.mkdir(parents=True, exist_ok=True)
        root = keep_root
        for index, file_name in enumerate(args.files, start=1):
            epub_path = Path(file_name).resolve()
            case_dir = root / f"case-{index}-{epub_path.stem}"
            case_dir.mkdir(parents=True, exist_ok=True)
            print(f"[{index}/{len(args.files)}] {epub_path.name}")
            results.append(compare_one(previewer, epub_path, case_dir))
    else:
        with tempfile.TemporaryDirectory() as temp_root:
            root = Path(temp_root)
            for index, file_name in enumerate(args.files, start=1):
                epub_path = Path(file_name).resolve()
                case_dir = root / f"case-{index}"
                case_dir.mkdir(parents=True, exist_ok=True)
                print(f"[{index}/{len(args.files)}] {epub_path.name}")
                results.append(compare_one(previewer, epub_path, case_dir))

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote report to {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
