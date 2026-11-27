"""
One-off helper: build the Munk coding template from the Oxford workbook.

Output: data/metadata/munk_coding_template.xlsx with three sheets
- Frames          copied unchanged from the Oxford workbook
- Codebook rules  the Oxford rules (dates written the same way) plus the
                  rules agreed while finishing the Oxford coding
- Coding          the Oxford header (rows 1 to 3) with no sentences yet

The Oxford workbook is not in this repository, so this script only needs
to be run again if the Frames sheet or the rules change. The template it
writes is version controlled, and step 3 (build_munk_workbook.py) only
reads the template.

Usage:
    python scripts/make_munk_template.py --oxford path/to/Oxford_workbook.xlsx
"""

from __future__ import annotations

import argparse
import datetime as dt
from copy import copy
from pathlib import Path

import openpyxl
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "metadata" / "munk_coding_template.xlsx"

# Rules agreed while finishing the Oxford coding that were not yet in the
# Oxford "Codebook rules" sheet. Sentence IDs starting with S are Oxford IDs.
NEW_RULES = [
    ("19/11/2026",
     "GS3 when a politician, party, parliament, government, head of state or vote is the subject of a claim "
     "(the Pope, Assad, \"we voted\"). A mention that is only debate rhetoric is NONE. UN agencies, NGOs and "
     "people who do not work in government are not GS3.",
     "S009, S299, S434; not S038, S116", "GS3"),
    ("26/11/2026",
     "GS4 only when the sentence names a measure of a national government (programme, commitment, law, scheme, "
     "specific spending) or evaluates one it names. A word that points to a policy described before (\"this "
     "response\", \"our approach\") also gets GS4. Vague references (\"the government has acted\", \"not doing "
     "enough\") do not. Aid gets GS4 only when a specific amount, programme or output is named.",
     "S044, S047, S451, S457; not S040, S043, S465, S466", "GS4"),
    ("23/11/2026",
     "GS5 for a relation between countries, an international body or agreement (the UN and its agencies, the EU "
     "acting as a body, the Dublin Regulation, the Geneva Convention), a policy involving other countries, or a "
     "comparison between countries. Not for a country or the EU named only as a place, origin or route, and not "
     "for private donations abroad.",
     "S037, S063, S243, S459; not S034, S064, S121", "GS5"),
    ("24/11/2026",
     "GS1 only for an item the codebook lists: numbers or demographics of immigrants, country of origin, "
     "religion, ethnicity, language learning, integration efforts or lack thereof, the nation's values or pride, "
     "history of immigration, personal immigration stories, art about immigration, notable people. What the "
     "public did (petitions, donations, \"millions of people\" supporting a policy) is GS2.",
     "S095, S097, S226, S424; not S112", "GS1, GS2"),
    ("24/11/2026",
     "Immigration-specific frames (IV, IH, IT) only when the sentence presents migrants as victims, heroes or "
     "threats. IH2 needs a positive spin on migrants adapting; failed or blocked integration is GS1.",
     "S227, S297, S376; not S226", "IV, IH, IT, GS1"),
    ("23/11/2026",
     "IV2 only when the sentence describes hardship or vulnerability of migrants: poor conditions, fear, danger "
     "or death on the journey, being unable to work, displacement when the displaced are presented as refugees. "
     "\"Humanitarian crisis\" or \"catastrophe\" alone is GN1, not IV2 (codebook general note 3a).",
     "S025, S028, S202, S448; not S029, S182", "IV2, GN1"),
    ("24/11/2026",
     "Order frames. GO3 when a threat is named (terrorism, murder, invasion, border crossings, \"terrifying\"). "
     "\"Safety\" or \"safe\" with no threat named is GO4. GO4 also for harm that happened, health, relief, the "
     "journey and missing people. GO2 when a crime or perpetrator is named (murder, smugglers, traffickers, "
     "deportation, \"not a crime\"). GO1 for asylum, law, conventions and courts, not for numbers of refugees.",
     "S025, S061, S129, S223, S447; not S039", "GO1, GO2, GO3, GO4"),
    ("26/11/2026",
     "GM1 for money, aid, donors, spending and employment (\"cannot work\"). GM2 when the sentence says there "
     "is or is not enough (\"find the resources\", \"can't absorb\"). IT3 when migrants are set against "
     "sustainability or presented as a burden on resources.",
     "S099, S341, S374, S441", "GM1, GM2, IT3"),
    ("23/11/2026",
     "GN2 for fair share, proportionality, \"not doing enough\", ranking groups of refugees, and an unequal "
     "share between countries.",
     "S027, S046, S059, S312", "GN2"),
    ("21/11/2026",
     "Context: use neighbouring sentences only to work out what a word refers to (\"them\", \"the system\", "
     "\"those profiting\"). Tick a frame only if the sentence's own words cue it once those references are "
     "resolved. Never copy a frame from a neighbouring sentence.",
     "S224, S354, S062; not S355", "all"),
    ("21/11/2026",
     "NONE for sentences that only point back, announce the next point, speak to the debate itself (thanks, "
     "jokes, the motion, the vote), rhetorical questions with no cue, and figures of speech (\"drawing your "
     "pension\").",
     "S222, S307, S350", "NONE"),
    ("23/11/2026",
     "IN1 when the sentence names specific people, places, groups, events or figures. IN2 for general claims. "
     "NONE rows get no IN code.",
     "S299, S376, S424, S321", "IN1, IN2"),
    ("23/11/2026",
     "A row holding two sentences, or an introduction plus an argument, is split before coding.",
     "S110, S361", "all"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Munk coding template from the Oxford workbook.")
    parser.add_argument("--oxford", type=Path, required=True, help="Path to the Oxford coding workbook (.xlsx)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def copy_cell(source, target) -> None:
    target.value = source.value
    if source.has_style:
        target.font = copy(source.font)
        target.fill = copy(source.fill)
        target.border = copy(source.border)
        target.alignment = copy(source.alignment)
        target.number_format = source.number_format
        target.protection = copy(source.protection)
    if source.comment is not None:
        comment = Comment(source.comment.text, source.comment.author or "")
        comment.width, comment.height = source.comment.width, source.comment.height
        target.comment = comment


def copy_sheet(source, target) -> None:
    for row in source.iter_rows():
        for cell in row:
            copy_cell(cell, target.cell(cell.row, cell.column))
    for key, dimension in source.column_dimensions.items():
        target.column_dimensions[key].width = dimension.width
    for key, dimension in source.row_dimensions.items():
        target.row_dimensions[key].height = dimension.height
    for merged in source.merged_cells.ranges:
        target.merge_cells(str(merged))
    target.freeze_panes = source.freeze_panes


def date_text(value) -> str:
    if isinstance(value, (dt.date, dt.datetime)):
        return value.strftime("%d/%m/%Y")
    return str(value or "")


def build_rules(source, target) -> None:
    copy_sheet_header = [source.cell(1, column) for column in range(1, 6)]
    for column, cell in enumerate(copy_sheet_header, start=1):
        copy_cell(cell, target.cell(1, column))
    body_style = [source.cell(2, column) for column in range(1, 6)]

    rows = []
    for row in source.iter_rows(min_row=2, max_col=5, values_only=True):
        if any(value not in (None, "") for value in row):
            rows.append([date_text(row[0])] + [value if value is not None else "" for value in row[1:]])
    for date, rule, ids, frames in NEW_RULES:
        rows.append([date, rule, ids, frames, "Angela"])

    for row_number, values in enumerate(rows, start=2):
        for column, value in enumerate(values, start=1):
            cell = target.cell(row_number, column, value)
            copy_cell(body_style[column - 1], cell)
            cell.value = value
    for key, dimension in source.column_dimensions.items():
        target.column_dimensions[key].width = dimension.width
    target.freeze_panes = "A2"


def coding_columns(source) -> list[int]:
    """
    Oxford columns to copy into the Munk Coding sheet: ID to Sentence,
    the 28 tick columns, # frames, Check and Coder notes. A second ID column
    added by hand after Sentence is skipped.
    """
    header = {source.cell(3, column).value: column for column in range(1, source.max_column + 1)}
    first = list(range(1, 8))
    second_id = 8 if source.cell(3, 8).value == "ID" else None
    tick_start = 9 if second_id else 8
    ticks = list(range(tick_start, tick_start + 28))
    tail = [header["# frames"], header["Check"], header["Coder notes"]]
    return first + ticks + tail


def build_coding_header(source, target) -> None:
    columns = coding_columns(source)
    mapping = {old: new for new, old in enumerate(columns, start=1)}
    for row in range(1, 4):
        for old, new in mapping.items():
            copy_cell(source.cell(row, old), target.cell(row, new))
        target.row_dimensions[row].height = source.row_dimensions[row].height
    for merged in source.merged_cells.ranges:
        if merged.min_row > 3:
            continue
        if merged.min_col in mapping and merged.max_col in mapping:
            target.merge_cells(
                start_row=merged.min_row, end_row=merged.max_row,
                start_column=mapping[merged.min_col], end_column=mapping[merged.max_col],
            )
    for old, new in mapping.items():
        width = source.column_dimensions[get_column_letter(old)].width
        if width:
            target.column_dimensions[get_column_letter(new)].width = width
    # Munk has turns and debate phases instead of speeches and timestamps
    for column, name in enumerate(["ID", "Turn", "Phase", "Speaker", "Side", "Row type", "Sentence"], start=1):
        target.cell(3, column).value = name
    for letter, width in {"A": 7, "B": 6, "C": 13, "D": 16, "E": 7, "F": 13}.items():
        target.column_dimensions[letter].width = width
    target.freeze_panes = "H4"


def main() -> None:
    args = parse_args()
    oxford = openpyxl.load_workbook(args.oxford)
    template = openpyxl.Workbook()
    template.remove(template.active)

    copy_sheet(oxford["Frames"], template.create_sheet("Frames"))
    build_rules(oxford["Codebook rules"], template.create_sheet("Codebook rules"))
    build_coding_header(oxford["Coding"], template.create_sheet("Coding"))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    template.save(args.output)
    print(f"Created {args.output}")


if __name__ == "__main__":
    main()
