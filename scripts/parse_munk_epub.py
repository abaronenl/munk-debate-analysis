from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------

# This script is expected to be located at:
# munk-debate-analysis/scripts/parse_munk_epub.py
#
# parents[1] therefore points to:
# munk-debate-analysis/
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_EPUB_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "global_refugee_crisis.epub"
)

DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
)


# ---------------------------------------------------------------------
# Debate configuration
# ---------------------------------------------------------------------

DEBATE_ID = "MUNK_2016_REFUGEE"

# The main debate transcript is contained in this EPUB chapter.
# Using the suffix makes the parser robust to folders such as OEBPS/.
TRANSCRIPT_SUFFIX = "GlobalRefugeeCrisis_epub-6.xhtml"

SPEAKER_METADATA: dict[str, dict[str, str | None]] = {
    "Louise Arbour": {
        "role": "debater",
        "side": "pro",
    },
    "Simon Schama": {
        "role": "debater",
        "side": "pro",
    },
    "Mark Steyn": {
        "role": "debater",
        "side": "con",
    },
    "Nigel Farage": {
        "role": "debater",
        "side": "con",
    },
    "Rudyard Griffiths": {
        "role": "moderator",
        "side": None,
    },
}

EXPECTED_OPENING_SPEAKERS = {
    "Louise Arbour",
    "Simon Schama",
    "Mark Steyn",
    "Nigel Farage",
}


# ---------------------------------------------------------------------
# Command-line arguments
# ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract speaker turns and opening statements from the "
            "Munk Global Refugee Crisis EPUB."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_EPUB_PATH,
        help=(
            "Path to the source EPUB. "
            f"Default: {DEFAULT_EPUB_PATH}"
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Directory for generated files. "
            f"Default: {DEFAULT_OUTPUT_DIR}"
        ),
    )

    return parser.parse_args()


# ---------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------

def normalize_text(text: str) -> str:
    """
    Collapse repeated whitespace without changing substantive wording.
    """
    return re.sub(r"\s+", " ", text).strip()


def normalize_for_matching(text: str) -> str:
    """
    Normalize punctuation and case for detecting phase transitions.
    """
    return (
        normalize_text(text)
        .lower()
        .replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("—", "-")
        .replace("–", "-")
    )


# ---------------------------------------------------------------------
# Debate phase detection
# ---------------------------------------------------------------------

def detect_phase(
    text: str,
    current_phase: str,
) -> str:
    """
    Detect the beginning of each debate phase from explicit moderator
    transition statements.
    """
    normalized = normalize_for_matching(text)

    if "let's go to our opening statements" in normalized:
        return "opening"

    if "we're now going to go into timed rebuttal" in normalized:
        return "rebuttal"

    if "now we're going to move on to the moderated portion" in normalized:
        return "moderated_discussion"

    # Use the exact start phrase. An earlier moderator statement says
    # "before we go into closing statements", which should not trigger
    # the closing phase prematurely.
    if "it's time now for closing statements" in normalized:
        return "closing"

    return current_phase


# ---------------------------------------------------------------------
# EPUB reading
# ---------------------------------------------------------------------

def locate_transcript_member(
    epub: zipfile.ZipFile,
) -> str:
    """
    Locate the main transcript XHTML file inside the EPUB archive.
    """
    matches = [
        filename
        for filename in epub.namelist()
        if filename.endswith(TRANSCRIPT_SUFFIX)
    ]

    if not matches:
        raise FileNotFoundError(
            "Could not find a chapter ending with "
            f"{TRANSCRIPT_SUFFIX!r} inside the EPUB."
        )

    if len(matches) > 1:
        raise RuntimeError(
            "Found multiple possible transcript chapters: "
            f"{matches}"
        )

    return matches[0]


def read_transcript_xhtml(
    epub_path: Path,
) -> tuple[str, bytes]:
    """
    Read the main transcript chapter from the EPUB.
    """
    if not epub_path.exists():
        raise FileNotFoundError(
            f"EPUB not found: {epub_path}"
        )

    if epub_path.suffix.lower() != ".epub":
        raise ValueError(
            f"Expected an .epub file, received: {epub_path}"
        )

    try:
        with zipfile.ZipFile(epub_path) as epub:
            transcript_member = locate_transcript_member(epub)
            xhtml = epub.read(transcript_member)

    except zipfile.BadZipFile as error:
        raise ValueError(
            f"The file is not a valid EPUB archive: {epub_path}"
        ) from error

    return transcript_member, xhtml


# ---------------------------------------------------------------------
# Speaker extraction
# ---------------------------------------------------------------------

def remove_speaker_label(
    paragraph: Any,
) -> str:
    """
    Remove the <span class="names"> speaker label from a paragraph,
    while preserving the rest of the speech text.
    """
    paragraph_copy = BeautifulSoup(
        str(paragraph),
        "lxml-xml",
    )

    speaker_span = paragraph_copy.find(
        "span",
        class_="names",
    )

    if speaker_span is not None:
        speaker_span.decompose()

    return normalize_text(
        paragraph_copy.get_text(
            " ",
            strip=True,
        )
    )


def finalize_turn(
    turn: dict[str, Any],
    turn_id: int,
) -> dict[str, Any]:
    """
    Convert an unfinished speaker turn into a final output record.
    """
    text = "\n\n".join(
        turn.pop("paragraphs")
    ).strip()

    role = turn["role"]
    phase = turn["phase"]

    return {
        "debate_id": DEBATE_ID,
        "turn_id": turn_id,
        "speaker": turn["speaker"],
        "role": role,
        "side": turn["side"],
        "phase": phase,
        "text": text,
        "word_count": len(text.split()),
        "start_paragraph": turn["start_paragraph"],
        "end_paragraph": turn["end_paragraph"],
        "paragraph_count": (
            turn["end_paragraph"]
            - turn["start_paragraph"]
            + 1
        ),
        "source_chapter": turn["source_chapter"],
        "include_for_analysis": (
            role == "debater"
            and phase != "preliminary"
        ),
    }


def parse_speaker_turns(
    xhtml: bytes,
    source_chapter: str,
) -> list[dict[str, Any]]:
    """
    Parse the transcript into speaker turns.

    Rules:
    - A paragraph containing <span class="names"> begins a new turn.
    - Paragraphs without a speaker label continue the previous turn.
    - The preliminary material remains in the complete output.
    - Moderator turns are retained but marked as moderator material.
    """
    soup = BeautifulSoup(
        xhtml,
        "lxml-xml",
    )

    unfinished_turns: list[dict[str, Any]] = []
    current_turn: dict[str, Any] | None = None
    current_phase = "preliminary"

    paragraphs = soup.find_all("p")

    for paragraph_index, paragraph in enumerate(paragraphs):
        full_text = normalize_text(
            paragraph.get_text(
                " ",
                strip=True,
            )
        )

        if not full_text:
            continue

        current_phase = detect_phase(
            full_text,
            current_phase,
        )

        speaker_span = paragraph.find(
            "span",
            class_="names",
        )

        if speaker_span is not None:
            raw_label = normalize_text(
                speaker_span.get_text(
                    " ",
                    strip=True,
                )
            )

            speaker = raw_label.rstrip(":").strip()

            speech_text = remove_speaker_label(
                paragraph
            )

            metadata = SPEAKER_METADATA.get(
                speaker,
                {
                    "role": "other",
                    "side": None,
                },
            )

            current_turn = {
                "speaker": speaker,
                "role": metadata["role"],
                "side": metadata["side"],
                "phase": current_phase,
                "start_paragraph": paragraph_index,
                "end_paragraph": paragraph_index,
                "paragraphs": (
                    [speech_text]
                    if speech_text
                    else []
                ),
                "source_chapter": source_chapter,
            }

            unfinished_turns.append(
                current_turn
            )

        elif current_turn is not None:
            # Unlabelled paragraphs, such as text-indent paragraphs,
            # continue the most recently identified speaker turn.
            current_turn["paragraphs"].append(
                full_text
            )

            current_turn["end_paragraph"] = (
                paragraph_index
            )

    turns = [
        finalize_turn(
            turn.copy(),
            turn_id,
        )
        for turn_id, turn in enumerate(
            unfinished_turns
        )
    ]

    return turns


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

def validate_turns(
    turns: list[dict[str, Any]],
) -> None:
    """
    Run checks that help detect silent parsing errors.
    """
    if not turns:
        raise RuntimeError(
            "No speaker turns were extracted."
        )

    observed_speakers = {
        turn["speaker"]
        for turn in turns
    }

    expected_speakers = set(
        SPEAKER_METADATA
    )

    unexpected_speakers = (
        observed_speakers
        - expected_speakers
    )

    if unexpected_speakers:
        print(
            "WARNING: unexpected speaker labels: "
            f"{sorted(unexpected_speakers)}",
            file=sys.stderr,
        )

    opening_turns = [
        turn
        for turn in turns
        if turn["phase"] == "opening"
        and turn["role"] == "debater"
    ]

    opening_speakers = {
        turn["speaker"]
        for turn in opening_turns
    }

    if (
        len(opening_turns) != 4
        or opening_speakers
        != EXPECTED_OPENING_SPEAKERS
    ):
        raise RuntimeError(
            "Opening-statement validation failed.\n"
            f"Expected speakers: "
            f"{sorted(EXPECTED_OPENING_SPEAKERS)}\n"
            f"Found speakers: "
            f"{sorted(opening_speakers)}\n"
            f"Number of opening turns: "
            f"{len(opening_turns)}"
        )

    empty_turn_ids = [
        turn["turn_id"]
        for turn in turns
        if not turn["text"]
    ]

    if empty_turn_ids:
        print(
            "WARNING: empty turn texts found at IDs: "
            f"{empty_turn_ids}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------

def write_jsonl(
    records: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """
    Write records as newline-delimited JSON.
    """
    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        for record in records:
            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )


def write_csv(
    records: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """
    Write records as UTF-8 CSV.

    utf-8-sig helps Microsoft Excel recognize the encoding correctly.
    """
    if not records:
        return

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(
                records[0].keys()
            ),
        )

        writer.writeheader()
        writer.writerows(records)


# ---------------------------------------------------------------------
# Parsing report
# ---------------------------------------------------------------------

def build_parsing_report(
    turns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Summarize turns and words by speaker and debate phase.
    """
    turn_counts: Counter[
        tuple[str, str, str, str | None]
    ] = Counter()

    word_counts: Counter[
        tuple[str, str, str, str | None]
    ] = Counter()

    for turn in turns:
        key = (
            turn["speaker"],
            turn["role"],
            turn["phase"],
            turn["side"],
        )

        turn_counts[key] += 1
        word_counts[key] += turn["word_count"]

    report = []

    sorted_keys = sorted(
        turn_counts,
        key=lambda item: (
            item[0],
            item[2],
        ),
    )

    for key in sorted_keys:
        speaker, role, phase, side = key

        report.append(
            {
                "speaker": speaker,
                "role": role,
                "side": side,
                "phase": phase,
                "turn_count": turn_counts[key],
                "word_count": word_counts[key],
            }
        )

    return report


# ---------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    epub_path = args.input.resolve()
    output_dir = args.output_dir.resolve()

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(f"Reading EPUB: {epub_path}")

    source_chapter, xhtml = (
        read_transcript_xhtml(
            epub_path
        )
    )

    print(
        f"Transcript chapter: "
        f"{source_chapter}"
    )

    turns = parse_speaker_turns(
        xhtml=xhtml,
        source_chapter=source_chapter,
    )

    validate_turns(turns)

    opening_statements = [
        turn
        for turn in turns
        if turn["phase"] == "opening"
        and turn["role"] == "debater"
    ]

    parsing_report = build_parsing_report(
        turns
    )

    all_turns_jsonl = (
        output_dir
        / "munk_refugee_all_turns.jsonl"
    )

    all_turns_csv = (
        output_dir
        / "munk_refugee_all_turns.csv"
    )

    openings_jsonl = (
        output_dir
        / "munk_refugee_openings.jsonl"
    )

    openings_csv = (
        output_dir
        / "munk_refugee_openings.csv"
    )

    report_csv = (
        output_dir
        / "munk_refugee_parsing_report.csv"
    )

    write_jsonl(
        turns,
        all_turns_jsonl,
    )

    write_csv(
        turns,
        all_turns_csv,
    )

    write_jsonl(
        opening_statements,
        openings_jsonl,
    )

    write_csv(
        opening_statements,
        openings_csv,
    )

    write_csv(
        parsing_report,
        report_csv,
    )

    print(
        f"\nExtracted {len(turns)} "
        "speaker turns."
    )

    print(
        f"Extracted "
        f"{len(opening_statements)} "
        "opening statements:"
    )

    for statement in opening_statements:
        print(
            f"  - {statement['speaker']} "
            f"({statement['side']}): "
            f"{statement['word_count']} words"
        )

    print("\nCreated files:")

    created_files = [
        all_turns_jsonl,
        all_turns_csv,
        openings_jsonl,
        openings_csv,
        report_csv,
    ]

    for file_path in created_files:
        print(f"  - {file_path}")


if __name__ == "__main__":
    main()