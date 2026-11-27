# munk-debate-analysis

Transcripts of staged debates on refugees and immigration, prepared for
sentence-level frame coding (Mendelsohn et al., 2021 typology). The Munk
Debate on the global refugee crisis (Toronto, 2016) is coded with the rules
agreed while coding the Oxford Union debate.

## Data policy

The book is copyrighted, so it is never shared or committed:
`data/raw/`, `data/interim/` and `data/processed/` stay on your own
computer (see `.gitignore`). Only the scripts, this README, the
requirements and the coding template can go online. The manifest (below)
records a SHA-256 fingerprint of the book and of every output, so anyone
who owns the same edition can check they got exactly the same sentences
without the book being shared.

Source: *How Should We Respond to the Global Refugee Crisis?* (The Munk
Debates, House of Anansi, 2017, ISBN 9781487002121), EPUB edition, saved
as `data/raw/global_refugee_crisis.epub`.
SHA-256 of that file:
`552ea9ca4a619c90eefa937a60a5bee11899c4d29a6dab5b61e3fce3727bab0c`

## Setup (Windows)

    cd munk-debate-analysis
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

## Run

    python scripts\run_munk_pipeline.py --epub data\raw\global_refugee_crisis.epub

| Step | Script | What it does | Output (in `data/processed/`) |
|---|---|---|---|
| 1 | `parse_munk_epub.py` | Reads the transcript chapter of the EPUB (`GlobalRefugeeCrisis_epub-6.xhtml`) and splits it into speaker turns. A paragraph that starts with a speaker name starts a turn; paragraphs without a name continue it. Each turn gets its phase (preliminary, opening, rebuttal, moderated discussion, closing) from the moderator's transition lines. Checks there are exactly four opening statements. | `munk_refugee_all_turns.jsonl/.csv`, `munk_refugee_openings.jsonl/.csv`, `munk_refugee_parsing_report.csv` |
| 2 | `split_munk_sentences.py` | Splits every turn into sentences with pysbd, paragraph by paragraph, without editing the text. Applies the manual splits listed in the script (one so far). Gives each sentence an ID (M0001, M0002, … in reading order) and a row type (Sentence, Moderator, Transcript note, Other). Stops if the sentences of a turn do not give back every character of the turn. | `munk_refugee_sentences.jsonl/.csv` |
| 3 | `build_munk_workbook.py` | Puts the sentences into the coding workbook, one row per sentence, nothing ticked. | `munk_frame_coding.xlsx` |
| – | `run_munk_pipeline.py` | Runs steps 1 to 3 and writes the manifest: fingerprints of the EPUB, scripts, template and outputs, library versions, counts. | `munk_pipeline_manifest.json` |

Result with the EPUB above: 89 turns and 673 sentences: 559 from the four
debaters (Steyn 168, Farage 143, Schama 129, Arbour 119) and 114 from the
moderator. The book has no stage notes such as
[Applause], so no row has the type Transcript note.

## Tracing a sentence back to the book

`sentence_id` → `turn_id` → `start_paragraph`/`end_paragraph` of that
turn in the transcript chapter. Inside the turn, `paragraph_in_turn` and
`char_start`/`char_end` give the exact position:
`turn_text[char_start:char_end]` is the sentence.

## Manual splits

pysbd keeps a quotation together with the words around it. That is right
when a quoted sentence sits inside a sentence (M0128, M0187, M0547,
M0621 stay whole), but once it joined two sentences. That place is listed
in `MANUAL_SPLITS` in `split_munk_sentences.py`:

| Turn | Split after | Result |
|---|---|---|
| 5 (Schama, opening) | “Well, in those days …” | M0159 and M0160 |

Any further split found during coding should be added to that list and the
pipeline run again, so every change to the sentences is written down.

## Coding workbook

`data/metadata/munk_coding_template.xlsx` holds the three sheets before
any sentences are added:

- **Frames**: the 25 frames plus NONE, Episodic and Thematic, copied from the Oxford workbook.
- **Codebook rules**: the rules agreed while coding the Oxford debate. Sentence IDs starting with S refer to Oxford sentences.
- **Coding**: the header (ID, Turn, Phase, Speaker, Side, Row type, Sentence, the 28 tick columns, # frames, Check, Coder notes).

The template was made from the Oxford workbook with
`scripts/make_munk_template.py --oxford <path>`; run it again only if the
frames or the rules change.

By default every sentence goes into the Coding sheet, including the
moderator's sentences (their Row type shows what they are).
`--analysis-only` keeps only the debaters' sentences after the
preliminary phase.

## Check against the earlier run

The turns file from the first project (July 2026) gives the same 89 turns,
field by field. Its fingerprint differed only because Windows had written
it with different line endings; both scripts now write the `.jsonl` files
with the same line endings on every computer.

## Oxford Union: refugee crisis debate

`data/metadata/oxford_refugee_videos.csv` lists the six speeches.
`scripts/download_oxford_refugee_captions.py` downloads their YouTube
captions (needs yt-dlp, in `requirements.txt`) and
`scripts/clean_oxford_refugee_captions.py` turns them into a draft
transcript.
