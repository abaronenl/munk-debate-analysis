"""
Run the whole Munk pipeline, from the book to the coding workbook, and
record what was used so the result can be traced and repeated.

Steps:
  1. scripts/parse_munk_epub.py       EPUB -> speaker turns
  2. scripts/split_munk_sentences.py  speaker turns -> sentences
  3. scripts/build_munk_workbook.py   sentences -> coding workbook

Afterwards it writes data/processed/munk_pipeline_manifest.json with:
- the SHA-256 fingerprint of the EPUB, of every script, of the template
  and of every file produced. The same EPUB and scripts always give the
  same turns and sentences files, and so the same fingerprints for them.
  Anyone with the book can check they got the same sentences without the
  book being shared. (The workbook's fingerprint changes on every run,
  because an Excel file stores the time it was saved.)
- the Python and library versions
- the number of turns and sentences

Usage:
    python scripts/run_munk_pipeline.py --epub data/raw/global_refugee_crisis.epub
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
PROCESSED = PROJECT_ROOT / "data" / "processed"
TEMPLATE = PROJECT_ROOT / "data" / "metadata" / "munk_coding_template.xlsx"
DEFAULT_EPUB = PROJECT_ROOT / "data" / "raw" / "global_refugee_crisis.epub"

STEP_SCRIPTS = [
    "parse_munk_epub.py",
    "split_munk_sentences.py",
    "build_munk_workbook.py",
    "run_munk_pipeline.py",
    "make_munk_template.py",
]
OUTPUTS = [
    "munk_refugee_all_turns.jsonl",
    "munk_refugee_all_turns.csv",
    "munk_refugee_openings.jsonl",
    "munk_refugee_openings.csv",
    "munk_refugee_parsing_report.csv",
    "munk_refugee_sentences.jsonl",
    "munk_refugee_sentences.csv",
    "munk_frame_coding.xlsx",
]
LIBRARIES = ["beautifulsoup4", "lxml", "pysbd", "openpyxl"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def run(arguments: list[str]) -> None:
    print("\n$ python " + " ".join(arguments))
    subprocess.run([sys.executable, *arguments], check=True, cwd=PROJECT_ROOT)


def count_lines(path: Path) -> int:
    with path.open(encoding="utf-8") as file:
        return sum(1 for line in file if line.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Munk pipeline from EPUB to coding workbook.")
    parser.add_argument("--epub", type=Path, default=DEFAULT_EPUB)
    parser.add_argument("--analysis-only", action="store_true")
    args = parser.parse_args()
    epub = args.epub.resolve()

    run([str(SCRIPTS / "parse_munk_epub.py"), "--input", str(epub), "--output-dir", str(PROCESSED)])
    run([str(SCRIPTS / "split_munk_sentences.py")])
    run([str(SCRIPTS / "build_munk_workbook.py")] + (["--analysis-only"] if args.analysis_only else []))

    manifest = {
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "analysis_only": args.analysis_only,
        "source_epub": {"file_name": epub.name, "sha256": sha256(epub)},
        "scripts": {name: sha256(SCRIPTS / name) for name in STEP_SCRIPTS if (SCRIPTS / name).exists()},
        "template": {"file_name": TEMPLATE.name, "sha256": sha256(TEMPLATE)},
        "outputs": {name: sha256(PROCESSED / name) for name in OUTPUTS if (PROCESSED / name).exists()},
        "counts": {
            "turns": count_lines(PROCESSED / "munk_refugee_all_turns.jsonl"),
            "sentences": count_lines(PROCESSED / "munk_refugee_sentences.jsonl"),
        },
        "python": platform.python_version(),
        "libraries": {name: importlib.metadata.version(name) for name in LIBRARIES},
    }
    manifest_path = PROCESSED / "munk_pipeline_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nWrote {manifest_path}")


if __name__ == "__main__":
    main()
