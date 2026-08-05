from __future__ import annotations

import csv
import html
import re
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MANIFEST_FILE = PROJECT_ROOT / "data" / "metadata" / "oxford_refugee_videos.csv"

RAW_CAPTION_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "oxford"
    / "refugee_crisis"
    / "captions"
    / "automatic"
)

INTERIM_ROOT = (
    PROJECT_ROOT
    / "data"
    / "interim"
    / "oxford"
    / "refugee_crisis"
)

SEGMENT_DIR = INTERIM_ROOT / "segments"
TRANSCRIPT_DIR = INTERIM_ROOT / "transcripts"

COMBINED_SEGMENTS_FILE = INTERIM_ROOT / "oxford_refugee_segments.csv"
COMBINED_TRANSCRIPT_FILE = INTERIM_ROOT / "oxford_refugee_draft_transcript.txt"
QUALITY_REPORT_FILE = INTERIM_ROOT / "oxford_refugee_caption_quality_report.csv"


# ---------------------------------------------------------------------
# Speech order for this Oxford debate
# ---------------------------------------------------------------------

SPEECH_STRUCTURE: dict[str, dict[str, str | int]] = {
    "G8rprHmFXoQ": {
        "speech_order": 1,
        "original_phase": "opening proposition speech",
    },
    "9TaReFVlxZc": {
        "speech_order": 2,
        "original_phase": "opening opposition speech",
    },
    "oeRMU0WHZDE": {
        "speech_order": 3,
        "original_phase": "second proposition speech",
    },
    "R2yI8NbPfEs": {
        "speech_order": 4,
        "original_phase": "second opposition speech",
    },
    "zYJGWkpooR0": {
        "speech_order": 5,
        "original_phase": "closing proposition speech",
    },
    "gwTVVvWASdI": {
        "speech_order": 6,
        "original_phase": "closing opposition speech",
    },
}


# ---------------------------------------------------------------------
# VTT parsing
# ---------------------------------------------------------------------

TIMESTAMP_RE = re.compile(
    r"(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2}\.\d{3})"
)
INLINE_TIMESTAMP_RE = re.compile(r"<\d{2}:\d{2}:\d{2}\.\d{3}>")
C_TAG_RE = re.compile(r"</?c(?:\.[^>]*)?>")
ANY_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class CaptionCue:
    start_seconds: float
    end_seconds: float
    visible_text: str


@dataclass
class NewTextEvent:
    start_seconds: float
    end_seconds: float
    text: str
    word_count: int


@dataclass
class TranscriptSegment:
    start_seconds: float
    end_seconds: float
    text: str


def timestamp_to_seconds(value: str) -> float:
    match = TIMESTAMP_RE.fullmatch(value)
    if not match:
        raise ValueError(f"Invalid VTT timestamp: {value}")

    return (
        int(match["hours"]) * 3600
        + int(match["minutes"]) * 60
        + float(match["seconds"])
    )


def seconds_to_timestamp(value: float) -> str:
    total_ms = round(value * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)

    return (
        f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    )


def remove_vtt_markup(text: str) -> str:
    """Remove VTT tags without correcting the caption wording."""

    text = INLINE_TIMESTAMP_RE.sub(" ", text)
    text = C_TAG_RE.sub(" ", text)
    text = ANY_TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\u200b", "")
    return re.sub(r"\s+", " ", text).strip()


def parse_vtt(path: Path) -> list[CaptionCue]:
    content = path.read_text(encoding="utf-8-sig")
    blocks = re.split(r"\n\s*\n", content.strip())
    cues: list[CaptionCue] = []

    for block in blocks:
        lines = block.splitlines()
        timing_index = next(
            (index for index, line in enumerate(lines) if "-->" in line),
            None,
        )

        if timing_index is None:
            continue

        start_text, end_and_settings = lines[timing_index].split("-->", 1)
        end_text = end_and_settings.strip().split()[0]
        payload = "\n".join(lines[timing_index + 1 :])

        cues.append(
            CaptionCue(
                start_seconds=timestamp_to_seconds(start_text.strip()),
                end_seconds=timestamp_to_seconds(end_text),
                visible_text=remove_vtt_markup(payload),
            )
        )

    return cues


# ---------------------------------------------------------------------
# Remove YouTube's rolling-caption repetition
# ---------------------------------------------------------------------

def normalize_token(token: str) -> str:
    return re.sub(
        r"^\W+|\W+$",
        "",
        token,
        flags=re.UNICODE,
    ).casefold()


def find_longest_overlap(
    existing_tokens: list[str],
    incoming_tokens: list[str],
    maximum_tokens: int = 120,
) -> int:
    if not existing_tokens or not incoming_tokens:
        return 0

    existing = [
        normalize_token(token)
        for token in existing_tokens[-maximum_tokens:]
    ]
    incoming = [
        normalize_token(token)
        for token in incoming_tokens[:maximum_tokens]
    ]

    for size in range(min(len(existing), len(incoming)), 0, -1):
        if existing[-size:] == incoming[:size]:
            return size

    return 0


def cue_already_seen(
    incoming_tokens: list[str],
    recent_normalized_tokens: list[str],
) -> bool:
    incoming = [normalize_token(token) for token in incoming_tokens]
    recent = recent_normalized_tokens[-160:]

    if not incoming or len(incoming) > len(recent):
        return False

    for start in range(len(recent) - len(incoming) + 1):
        if recent[start : start + len(incoming)] == incoming:
            return True

    return False


def deduplicate_rolling_captions(
    cues: list[CaptionCue],
) -> list[NewTextEvent]:
    transcript_tokens: list[str] = []
    normalized_tokens: list[str] = []
    events: list[NewTextEvent] = []

    for cue in cues:
        cue_tokens = cue.visible_text.split()
        if not cue_tokens:
            continue

        overlap = find_longest_overlap(transcript_tokens, cue_tokens)
        new_tokens = cue_tokens[overlap:]

        if overlap == 0 and cue_already_seen(cue_tokens, normalized_tokens):
            new_tokens = []

        if not new_tokens:
            continue

        transcript_tokens.extend(new_tokens)
        normalized_tokens.extend(normalize_token(token) for token in new_tokens)

        events.append(
            NewTextEvent(
                start_seconds=cue.start_seconds,
                end_seconds=cue.end_seconds,
                text=" ".join(new_tokens),
                word_count=sum(
                    1 for token in new_tokens if normalize_token(token)
                ),
            )
        )

    return events


# ---------------------------------------------------------------------
# Create manageable review blocks
# ---------------------------------------------------------------------

def group_events_into_segments(
    events: list[NewTextEvent],
    maximum_seconds: float = 30.0,
    maximum_words: int = 90,
    gap_seconds: float = 2.5,
) -> list[TranscriptSegment]:
    """
    Build timestamped review blocks.

    These are not argument units or grammatical sentences. They are
    manageable chunks for checking the automatic transcript.
    """

    segments: list[TranscriptSegment] = []
    parts: list[str] = []
    word_count = 0
    start: float | None = None
    end: float | None = None
    previous_end: float | None = None

    def flush() -> None:
        nonlocal parts, word_count, start, end
        if parts and start is not None and end is not None:
            segments.append(
                TranscriptSegment(
                    start_seconds=start,
                    end_seconds=end,
                    text=" ".join(parts).strip(),
                )
            )
        parts = []
        word_count = 0
        start = None
        end = None

    for event in events:
        if not event.text:
            continue

        if parts:
            large_pause = (
                previous_end is not None
                and event.start_seconds - previous_end > gap_seconds
            )
            long_duration = (
                start is not None
                and event.end_seconds - start > maximum_seconds
                and word_count >= 30
            )
            too_many_words = (
                word_count + event.word_count > maximum_words
                and word_count >= 30
            )

            if large_pause or long_duration or too_many_words:
                flush()

        if start is None:
            start = event.start_seconds

        parts.append(event.text)
        word_count += event.word_count
        end = event.end_seconds
        previous_end = event.end_seconds

    flush()
    return segments


# ---------------------------------------------------------------------
# Manifest and files
# ---------------------------------------------------------------------

def load_manifest() -> list[dict[str, str]]:
    if not MANIFEST_FILE.exists():
        raise FileNotFoundError(f"Manifest not found:\n{MANIFEST_FILE}")

    with MANIFEST_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        rows = list(csv.DictReader(file))

    required = {"video_id", "speaker", "side", "url"}

    if not rows:
        raise ValueError("The manifest is empty.")

    missing = required - set(rows[0].keys())
    if missing:
        raise ValueError(
            "The manifest is missing columns: "
            + ", ".join(sorted(missing))
        )

    return rows


def select_caption_file(video_id: str) -> tuple[Path, bool]:
    original = RAW_CAPTION_DIR / f"{video_id}.en-orig.vtt"
    english = RAW_CAPTION_DIR / f"{video_id}.en.vtt"

    identical = (
        original.exists()
        and english.exists()
        and original.read_bytes() == english.read_bytes()
    )

    if original.exists():
        return original, identical

    if english.exists():
        return english, identical

    raise FileNotFoundError(
        f"No English VTT found for {video_id} in:\n{RAW_CAPTION_DIR}"
    )


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    headers: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def initial_segment_type(segment_number: int, text: str) -> str:
    if segment_number == 1:
        return "introduction_or_speech_start_needs_check"

    if re.fullmatch(r"(?:\[[^\]]+\]\s*)+", text.strip()):
        return "audience_or_sound_marker"

    return "main_speech_or_interruption_unchecked"


SEGMENT_HEADERS = [
    "segment_id",
    "debate_id",
    "venue",
    "video_id",
    "source_url",
    "expected_main_speaker",
    "side",
    "speech_order",
    "original_phase",
    "harmonized_phase",
    "start_time",
    "end_time",
    "segment_type",
    "raw_asr_text",
    "cleaned_text",
    "speaker_check_status",
    "text_check_status",
    "audio_checked",
    "needs_audio_check",
    "correction_notes",
    "source_caption_file",
]


def main() -> None:
    SEGMENT_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    manifest_rows = load_manifest()
    all_rows: list[dict[str, object]] = []
    quality_rows: list[dict[str, object]] = []

    for manifest_row in manifest_rows:
        video_id = manifest_row["video_id"].strip()
        speaker = manifest_row["speaker"].strip()
        side = manifest_row["side"].strip()
        source_url = manifest_row["url"].strip()

        structure = SPEECH_STRUCTURE.get(video_id)
        if structure is None:
            raise ValueError(
                f"No speech order has been defined for video {video_id}."
            )

        caption_file, duplicate_tracks = select_caption_file(video_id)
        cues = parse_vtt(caption_file)
        events = deduplicate_rolling_captions(cues)
        segments = group_events_into_segments(events)

        video_rows: list[dict[str, object]] = []

        for number, segment in enumerate(segments, start=1):
            row: dict[str, object] = {
                "segment_id": f"{video_id}_{number:03d}",
                "debate_id": "oxford_refugee_crisis",
                "venue": "Oxford Union",
                "video_id": video_id,
                "source_url": source_url,
                "expected_main_speaker": speaker,
                "side": side,
                "speech_order": int(structure["speech_order"]),
                "original_phase": str(structure["original_phase"]),
                "harmonized_phase": "prepared main speech",
                "start_time": seconds_to_timestamp(segment.start_seconds),
                "end_time": seconds_to_timestamp(segment.end_seconds),
                "segment_type": initial_segment_type(number, segment.text),
                "raw_asr_text": segment.text,
                "cleaned_text": segment.text,
                "speaker_check_status": "unverified",
                "text_check_status": "unreviewed",
                "audio_checked": "no",
                "needs_audio_check": "",
                "correction_notes": "",
                "source_caption_file": caption_file.name,
            }

            video_rows.append(row)
            all_rows.append(row)

        write_csv(
            SEGMENT_DIR / f"{video_id}_segments.csv",
            video_rows,
            SEGMENT_HEADERS,
        )

        transcript_lines = [
            f"{speaker} — {side} — {structure['original_phase']}",
            f"Video: {source_url}",
            "",
        ]

        for row in video_rows:
            transcript_lines.extend(
                [
                    f"[{row['start_time']} --> {row['end_time']}]",
                    str(row["cleaned_text"]),
                    "",
                ]
            )

        (
            TRANSCRIPT_DIR / f"{video_id}_draft.txt"
        ).write_text(
            "\n".join(transcript_lines),
            encoding="utf-8",
        )

        duration = cues[-1].end_seconds if cues else 0.0
        quality_rows.append(
            {
                "video_id": video_id,
                "speaker": speaker,
                "side": side,
                "speech_order": int(structure["speech_order"]),
                "caption_file_used": caption_file.name,
                "en_and_en_orig_identical": (
                    "yes" if duplicate_tracks else "no"
                ),
                "raw_cue_count": len(cues),
                "deduplicated_event_count": len(events),
                "review_segment_count": len(segments),
                "draft_word_count": sum(
                    len(segment.text.split()) for segment in segments
                ),
                "duration_seconds": round(duration, 3),
                "caption_source": "YouTube automatic captions",
                "manual_caption_available": "no",
                "quality_status": "requires text and speaker review",
            }
        )

        print(
            f"Processed {speaker}: "
            f"{len(cues)} cues -> {len(segments)} review segments."
        )

    all_rows.sort(
        key=lambda row: (
            int(row["speech_order"]),
            str(row["start_time"]),
        )
    )

    write_csv(
        COMBINED_SEGMENTS_FILE,
        all_rows,
        SEGMENT_HEADERS,
    )

    combined_lines: list[str] = []
    current_video: str | None = None

    for row in all_rows:
        video_id = str(row["video_id"])

        if video_id != current_video:
            if combined_lines:
                combined_lines.extend(["", "=" * 72, ""])

            combined_lines.extend(
                [
                    (
                        f"{row['expected_main_speaker']} — "
                        f"{row['side']} — {row['original_phase']}"
                    ),
                    f"Video: {row['source_url']}",
                    "",
                ]
            )
            current_video = video_id

        combined_lines.extend(
            [
                f"[{row['start_time']} --> {row['end_time']}]",
                str(row["cleaned_text"]),
                "",
            ]
        )

    COMBINED_TRANSCRIPT_FILE.write_text(
        "\n".join(combined_lines),
        encoding="utf-8",
    )

    quality_headers = [
        "video_id",
        "speaker",
        "side",
        "speech_order",
        "caption_file_used",
        "en_and_en_orig_identical",
        "raw_cue_count",
        "deduplicated_event_count",
        "review_segment_count",
        "draft_word_count",
        "duration_seconds",
        "caption_source",
        "manual_caption_available",
        "quality_status",
    ]

    write_csv(
        QUALITY_REPORT_FILE,
        quality_rows,
        quality_headers,
    )

    print("\nFinished.")
    print(f"Combined segments: {COMBINED_SEGMENTS_FILE}")
    print(f"Combined transcript: {COMBINED_TRANSCRIPT_FILE}")
    print(f"Quality report: {QUALITY_REPORT_FILE}")


if __name__ == "__main__":
    main()
