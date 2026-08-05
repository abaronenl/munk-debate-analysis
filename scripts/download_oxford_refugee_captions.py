from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------

# This resolves to the root folder:
# C:\...\munk-debate-analysis
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# This is the CSV file you already created.
MANIFEST_FILE = (
    PROJECT_ROOT
    / "data"
    / "metadata"
    / "oxford_refugee_videos.csv"
)

# Raw Oxford refugee data will be stored here.
RAW_ROOT = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "oxford"
    / "refugee_crisis"
)

MANUAL_CAPTION_DIR = RAW_ROOT / "captions" / "manual"
AUTOMATIC_CAPTION_DIR = RAW_ROOT / "captions" / "automatic"
YOUTUBE_METADATA_DIR = RAW_ROOT / "metadata"


def create_output_folders() -> None:
    """
    Create the folders used for downloaded captions and metadata.

    parents=True creates all missing parent folders.
    exist_ok=True prevents an error if the folders already exist.
    """

    MANUAL_CAPTION_DIR.mkdir(parents=True, exist_ok=True)
    AUTOMATIC_CAPTION_DIR.mkdir(parents=True, exist_ok=True)
    YOUTUBE_METADATA_DIR.mkdir(parents=True, exist_ok=True)


def load_manifest() -> list[dict[str, str]]:
    """
    Read the Oxford refugee video manifest.

    Returns one dictionary per video.
    """

    if not MANIFEST_FILE.exists():
        raise FileNotFoundError(
            "Could not find the video manifest:\n"
            f"{MANIFEST_FILE}"
        )

    with MANIFEST_FILE.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        videos = list(csv.DictReader(file))

    if not videos:
        raise ValueError(
            f"The manifest is empty: {MANIFEST_FILE}"
        )

    required_columns = {
        "video_id",
        "url",
        "speaker",
        "side",
    }

    available_columns = set(videos[0].keys())
    missing_columns = required_columns - available_columns

    if missing_columns:
        raise ValueError(
            "The manifest is missing these columns: "
            + ", ".join(sorted(missing_columns))
        )

    return videos


def run_command(
    command: list[str],
    *,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    """
    Run a command and display it in the terminal.

    check=False allows the script to continue when one subtitle
    type is unavailable for a particular video.
    """

    print("\nRunning command:")
    print(" ".join(command))

    result = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=capture_output,
    )

    if not capture_output and result.returncode != 0:
        print(
            f"Command finished with exit code "
            f"{result.returncode}."
        )

    return result


def save_subtitle_availability(
    video_id: str,
    url: str,
) -> None:
    """
    Ask yt-dlp which subtitle tracks exist and save the result.
    """

    result = run_command(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "--skip-download",
            "--no-playlist",
            "--list-subs",
            url,
        ],
        capture_output=True,
    )

    output_file = (
        YOUTUBE_METADATA_DIR
        / f"{video_id}_subtitle_availability.txt"
    )

    text = ""

    if result.stdout:
        text += result.stdout

    if result.stderr:
        text += "\nERROR OUTPUT:\n"
        text += result.stderr

    output_file.write_text(
        text,
        encoding="utf-8",
    )

    print(f"Saved subtitle information: {output_file}")


def download_youtube_metadata(
    url: str,
) -> None:
    """
    Download technical YouTube metadata without downloading the video.
    """

    output_template = str(
        YOUTUBE_METADATA_DIR
        / "%(id)s.%(ext)s"
    )

    run_command(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "--skip-download",
            "--no-playlist",
            "--write-info-json",
            "-o",
            output_template,
            url,
        ]
    )


def download_manual_captions(
    url: str,
) -> None:
    """
    Attempt to download human-uploaded English captions.
    """

    output_template = str(
        MANUAL_CAPTION_DIR
        / "%(id)s.%(ext)s"
    )

    run_command(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "--skip-download",
            "--no-playlist",
            "--write-subs",
            "--sub-langs",
            "en.*,en",
            "--sub-format",
            "vtt",
            "-o",
            output_template,
            url,
        ]
    )


def download_automatic_captions(
    url: str,
) -> None:
    """
    Attempt to download automatically generated English captions.
    """

    output_template = str(
        AUTOMATIC_CAPTION_DIR
        / "%(id)s.%(ext)s"
    )

    run_command(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "--skip-download",
            "--no-playlist",
            "--write-auto-subs",
            "--sub-langs",
            "en.*,en",
            "--sub-format",
            "vtt",
            "-o",
            output_template,
            url,
        ]
    )


def main() -> None:
    """
    Process every Oxford refugee video in the manifest.
    """

    create_output_folders()
    videos = load_manifest()

    print(f"Found {len(videos)} videos in the manifest.")

    for number, video in enumerate(videos, start=1):
        video_id = video["video_id"].strip()
        url = video["url"].strip()
        speaker = video["speaker"].strip()
        side = video["side"].strip()

        if not video_id or not url:
            print(
                f"Skipping manifest row {number}: "
                "missing video_id or URL."
            )
            continue

        print("\n" + "=" * 70)
        print(
            f"Video {number}/{len(videos)}: "
            f"{speaker} — {side}"
        )
        print(f"Video ID: {video_id}")
        print(f"URL: {url}")
        print("=" * 70)

        save_subtitle_availability(
            video_id=video_id,
            url=url,
        )

        download_youtube_metadata(url)
        download_manual_captions(url)
        download_automatic_captions(url)

    print("\n" + "=" * 70)
    print("Finished.")
    print("=" * 70)

    print("\nDownloaded files are stored in:")

    print(
        "\nManual captions:\n"
        f"{MANUAL_CAPTION_DIR}"
    )

    print(
        "\nAutomatic captions:\n"
        f"{AUTOMATIC_CAPTION_DIR}"
    )

    print(
        "\nYouTube metadata:\n"
        f"{YOUTUBE_METADATA_DIR}"
    )


if __name__ == "__main__":
    main()