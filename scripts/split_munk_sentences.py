"""
Step 2 of the Munk pipeline: split speaker turns into sentences.

Input:  data/processed/munk_refugee_all_turns.jsonl
        (written by step 1, scripts/parse_munk_epub.py)

Output: data/processed/munk_refugee_sentences.csv
        data/processed/munk_refugee_sentences.jsonl

Every sentence keeps a link back to its source:
- turn_id and speaker, phase, side and role of the turn (from step 1)
- paragraph_in_turn: which paragraph of the turn the sentence comes from
- char_start, char_end: exact position of the sentence in the turn text,
  so turn_text[char_start:char_end] gives the sentence back

Splitting rules (one rule per line, nothing else is changed):
1. A turn is split into paragraphs at the blank lines step 1 inserted
   between the original EPUB paragraphs.
2. Each paragraph is split into sentences with pysbd (rule-based, no
   randomness, so the same input always gives the same sentences).
   pysbd keeps a quotation together with the words around it. That is
   right for a quoted sentence inside a sentence, but in one place it
   also joins two sentences. Those places are listed in MANUAL_SPLITS
   below and split there, so every manual change is written down.
3. Sentence text is never edited. Only leading and trailing spaces are
   removed.
4. Row type:
   - "Transcript note"  the whole sentence is inside brackets or
                        parentheses, e.g. [Applause] or (Laughter)
   - "Moderator"        the turn belongs to the moderator
   - "Other"            the speaker is not a debater or the moderator
   - "Sentence"         everything else
5. Sentence IDs run in reading order over the whole debate: M0001, M0002, ...

The script stops with an error if the sentences of a turn, put back
together, do not give back every character of that turn (spaces aside).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

import pysbd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "munk_refugee_all_turns.jsonl"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

ID_PREFIX = "M"
ID_WIDTH = 4

# Places where pysbd joined two sentences, found by reading its output.
# Each entry is (turn_id, the text that ends the first sentence); the turn is
# split right after that text. The script stops if the text is not found
# exactly once in the turn, or if it does not fall inside one sentence.
MANUAL_SPLITS = [
    # Simon Schama, opening statement: a quoted phrase, then a new sentence
    # starting with "And as some of you know".
    (5, "“Well, in those days …”"),
]

# A sentence made only of a bracketed note, e.g. "[Applause]" or "(LAUGHTER)".
TRANSCRIPT_NOTE = re.compile(r"^\s*[\[(][^\[\]()]*[\])]\s*[.!?]?\s*$")

FIELDNAMES = [
    "sentence_id",
    "debate_id",
    "turn_id",
    "paragraph_in_turn",
    "sentence_in_turn",
    "speaker",
    "role",
    "side",
    "phase",
    "include_for_analysis",
    "row_type",
    "char_start",
    "char_end",
    "text",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split Munk speaker turns into sentences.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def read_turns(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Turns file not found: {path}. Run scripts/parse_munk_epub.py first.")
    with path.open(encoding="utf-8") as file:
        turns = [json.loads(line) for line in file if line.strip()]
    turns.sort(key=lambda turn: turn["turn_id"])
    return turns


def paragraph_spans(text: str) -> list[tuple[int, int]]:
    """Start and end offsets of each paragraph (separated by blank lines)."""
    spans = []
    position = 0
    for part in text.split("\n\n"):
        start = position
        end = start + len(part)
        if part.strip():
            spans.append((start, end))
        position = end + 2
    return spans


def split_paragraph(
    segmenter: pysbd.Segmenter,
    text: str,
    offset: int,
) -> list[tuple[int, int, str]]:
    """
    Split one paragraph into sentences and return (start, end, text) with
    offsets in the turn text. Offsets are found by searching each sentence
    in the paragraph from the end of the previous one, so a sentence that
    occurs twice is still placed correctly.
    """
    sentences = []
    cursor = 0
    for raw in segmenter.segment(text):
        sentence = raw.strip()
        if not sentence:
            continue
        start = text.find(sentence, cursor)
        if start < 0:
            raise RuntimeError(f"Sentence not found in its paragraph: {sentence!r}")
        end = start + len(sentence)
        sentences.append((offset + start, offset + end, sentence))
        cursor = end
    return sentences


def apply_manual_splits(
    turn: dict[str, Any],
    turn_spans: list[tuple[int, tuple[int, int, str]]],
) -> list[tuple[int, tuple[int, int, str]]]:
    """Split the sentences listed in MANUAL_SPLITS for this turn."""
    text = turn["text"]
    for turn_id, marker in MANUAL_SPLITS:
        if turn_id != turn["turn_id"]:
            continue
        if text.count(marker) != 1:
            raise RuntimeError(f"Manual split {marker!r} found {text.count(marker)} times in turn {turn_id}.")
        cut = text.find(marker) + len(marker)
        for index, (paragraph, (start, end, _)) in enumerate(turn_spans):
            if start < cut < end:
                first_end = start + len(text[start:cut].rstrip())
                second_start = cut + (len(text[cut:end]) - len(text[cut:end].lstrip()))
                turn_spans[index:index + 1] = [
                    (paragraph, (start, first_end, text[start:first_end])),
                    (paragraph, (second_start, end, text[second_start:end])),
                ]
                break
        else:
            raise RuntimeError(f"Manual split {marker!r} is not inside a sentence of turn {turn_id}.")
    return turn_spans


def row_type(turn: dict[str, Any], sentence: str) -> str:
    if TRANSCRIPT_NOTE.match(sentence):
        return "Transcript note"
    if turn["role"] == "moderator":
        return "Moderator"
    if turn["role"] != "debater":
        return "Other"
    return "Sentence"


def check_turn_is_complete(turn: dict[str, Any], spans: list[tuple[int, int, str]]) -> None:
    """Every non-space character of the turn must be inside exactly one sentence."""
    text = turn["text"]
    covered = [False] * len(text)
    for start, end, sentence in spans:
        if text[start:end] != sentence:
            raise RuntimeError(f"Offsets do not match the text in turn {turn['turn_id']}.")
        for index in range(start, end):
            if covered[index]:
                raise RuntimeError(f"Overlapping sentences in turn {turn['turn_id']}.")
            covered[index] = True
    missing = [
        character
        for character, is_covered in zip(text, covered)
        if not is_covered and not character.isspace()
    ]
    if missing:
        raise RuntimeError(
            f"Turn {turn['turn_id']}: {len(missing)} characters are not in any sentence: "
            f"{''.join(missing)[:80]!r}"
        )


def build_sentences(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segmenter = pysbd.Segmenter(language="en", clean=False)
    records = []
    for turn in turns:
        turn_spans = []
        for paragraph_number, (p_start, p_end) in enumerate(paragraph_spans(turn["text"]), start=1):
            for span in split_paragraph(segmenter, turn["text"][p_start:p_end], p_start):
                turn_spans.append((paragraph_number, span))
        turn_spans = apply_manual_splits(turn, turn_spans)
        check_turn_is_complete(turn, [span for _, span in turn_spans])

        for sentence_number, (paragraph_number, (start, end, sentence)) in enumerate(turn_spans, start=1):
            records.append(
                {
                    "sentence_id": "",
                    "debate_id": turn["debate_id"],
                    "turn_id": turn["turn_id"],
                    "paragraph_in_turn": paragraph_number,
                    "sentence_in_turn": sentence_number,
                    "speaker": turn["speaker"],
                    "role": turn["role"],
                    "side": turn["side"] or "",
                    "phase": turn["phase"],
                    "include_for_analysis": turn["include_for_analysis"],
                    "row_type": row_type(turn, sentence),
                    "char_start": start,
                    "char_end": end,
                    "text": sentence,
                }
            )

    for number, record in enumerate(records, start=1):
        record["sentence_id"] = f"{ID_PREFIX}{number:0{ID_WIDTH}d}"
    return records


def write_outputs(records: list[dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "munk_refugee_sentences.csv"
    jsonl_path = output_dir / "munk_refugee_sentences.jsonl"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)

    # newline="\n": same line endings, and so the same fingerprint, on every computer
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    return csv_path, jsonl_path


def main() -> None:
    args = parse_args()
    turns = read_turns(args.input.resolve())
    records = build_sentences(turns)
    csv_path, jsonl_path = write_outputs(records, args.output_dir.resolve())

    counts: dict[str, int] = {}
    for record in records:
        counts[record["row_type"]] = counts.get(record["row_type"], 0) + 1

    print(f"Read {len(turns)} turns, wrote {len(records)} sentences.")
    for name, count in sorted(counts.items()):
        print(f"  {name}: {count}")
    print("Created files:")
    print(f"  - {csv_path}")
    print(f"  - {jsonl_path}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
