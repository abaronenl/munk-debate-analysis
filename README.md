# munk-debate-analysis

Transcripts of staged debates on refugees and immigration, prepared for
sentence-level frame coding (Mendelsohn et al., 2021 typology).

## Data policy

The source texts are copyrighted, so they are never committed:
`data/raw/`, `data/interim/` and `data/processed/` stay on your own
computer (see `.gitignore`). Only scripts, metadata and the coding
template are version controlled. The pipeline manifest (below) records a
SHA-256 fingerprint of the source file, so anyone who owns the same book
can check that they produced exactly the same sentences.

## Munk Debates: Global Refugee Crisis (2016)

Source: the published Munk Debates book, as an EPUB, placed at
`data/raw/global_refugee_crisis.epub`.

Run everything with one command:

    pip install -r requirements.txt
    python scripts/run_munk_pipeline.py --epub data/raw/global_refugee_crisis.epub

| Step | Script | What it does | Output (in `data/processed/`) |
|---|---|---|---|
| 1 | `parse_munk_epub.py` | Reads the transcript chapter of the EPUB and splits it into speaker turns. A paragraph with a speaker name starts a turn; unlabelled paragraphs continue it. Each turn gets its phase (preliminary, opening, rebuttal, moderated discussion, closing) from the moderator's transition lines. Checks there are exactly four opening statements. | `munk_refugee_all_turns.jsonl/.csv`, `munk_refugee_openings.jsonl/.csv`, `munk_refugee_parsing_report.csv` |
| 2 | `split_munk_sentences.py` | Splits every turn into sentences with pysbd, paragraph by paragraph, without editing the text. Gives each sentence an ID (M0001, M0002, … in reading order) and a row type (Sentence, Moderator, Transcript note, Other). Stops if the sentences of a turn do not give back every character of the turn. | `munk_refugee_sentences.jsonl/.csv` |
| 3 | `build_munk_workbook.py` | Puts the sentences into the coding workbook, one row per sentence, nothing ticked. | `munk_frame_coding.xlsx` |
| – | `run_munk_pipeline.py` | Runs steps 1 to 3 and writes the manifest: fingerprints of the EPUB, scripts, template and outputs, library versions, counts. | `munk_pipeline_manifest.json` |

How a sentence can be traced back to the book: `sentence_id` →
`turn_id` (step 1) → `start_paragraph`/`end_paragraph` of that turn in the
EPUB chapter; inside the turn, `paragraph_in_turn` and
`char_start`/`char_end` give the exact position
(`turn_text[char_start:char_end]` is the sentence).

### Coding workbook

`data/metadata/munk_coding_template.xlsx` holds the three sheets of the
workbook before any sentences are added:

- **Frames**: the 25 frames plus NONE, Episodic and Thematic, copied from the Oxford workbook.
- **Codebook rules**: the rules agreed while coding the Oxford debate. Sentence IDs starting with S refer to Oxford sentences.
- **Coding**: the header (ID, Turn, Phase, Speaker, Side, Row type, Sentence, the 28 tick columns, # frames, Check, Coder notes).

The template was made once from the Oxford workbook with
`scripts/make_munk_template.py --oxford <path>`; re-run it only if the
frames or the rules change.

By default every sentence goes into the Coding sheet, including the
moderator's sentences and transcript notes (their Row type shows what
they are). `--analysis-only` keeps only the debaters' sentences after the
preliminary phase.

## Oxford Union: refugee crisis debate

`data/metadata/oxford_refugee_videos.csv` lists the six speeches.
`scripts/download_oxford_refugee_captions.py` downloads their YouTube
captions and `scripts/clean_oxford_refugee_captions.py` turns them into a
draft transcript.
