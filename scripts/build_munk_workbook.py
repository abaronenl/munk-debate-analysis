"""
Step 3 of the Munk pipeline: put the sentences into the coding workbook.

Inputs:  data/processed/munk_refugee_sentences.csv   (step 2)
         data/metadata/munk_coding_template.xlsx    (Frames, Codebook rules,
                                                     Coding header)
Output:  data/processed/munk_frame_coding.xlsx

The Coding sheet gets one row per sentence, in reading order, with the same
tick columns, checks and colours as the Oxford Coding sheet. Nothing is
ticked: every row is left for the coders, including moderator sentences and
transcript notes (their Row type tells the coder what they are).

By default every sentence is included. --analysis-only keeps only the
sentences step 1 marked include_for_analysis (debaters, after the
preliminary phase).
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import openpyxl
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SENTENCES = PROJECT_ROOT / "data" / "processed" / "munk_refugee_sentences.csv"
DEFAULT_TEMPLATE = PROJECT_ROOT / "data" / "metadata" / "munk_coding_template.xlsx"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "munk_frame_coding.xlsx"

FIRST_ROW = 4
TICK_FIRST, TICK_LAST = 8, 35          # H to AI: 25 frames, NONE, IN1, IN2
FRAME_LAST = 32                         # AF: last of the 25 frames
NONE_COL = 33                           # AG
COUNT_COL, CHECK_COL, NOTES_COL = 36, 37, 38   # AJ, AK, AL

# Colour of a ticked cell, by group (same as the Oxford Coding sheet)
GROUP_FILLS = [
    (8, 10, "2F5597"),    # Material   GM1-GM3
    (11, 12, "548235"),   # Normative  GN1-GN2
    (13, 16, "C55A11"),   # Order      GO1-GO4
    (17, 21, "7030A0"),   # Society    GS1-GS5
    (22, 25, "1F4E79"),   # Victim     IV1-IV4
    (26, 28, "375623"),   # Hero       IH1-IH3
    (29, 32, "C00000"),   # Threat     IT1-IT4
    (33, 33, "404040"),   # NONE
    (34, 35, "BF8F00"),   # Narrative  IN1-IN2
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Munk coding workbook from the sentences file.")
    parser.add_argument("--sentences", type=Path, default=DEFAULT_SENTENCES)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--analysis-only", action="store_true")
    return parser.parse_args()


def read_sentences(path: Path, analysis_only: bool) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    if analysis_only:
        rows = [row for row in rows if row["include_for_analysis"] == "True"]
    return rows


def letter(column: int) -> str:
    return get_column_letter(column)


def fill_coding(sheet, sentences: list[dict[str, str]]) -> None:
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    font = Font(name="Arial", size=9)
    last = FIRST_ROW + len(sentences) - 1

    for offset, sentence in enumerate(sentences):
        row = FIRST_ROW + offset
        values = [
            sentence["sentence_id"],
            int(sentence["turn_id"]),
            sentence["phase"],
            sentence["speaker"],
            sentence["side"],
            sentence["row_type"],
            sentence["text"],
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row, column, value)
            cell.font = font
            cell.alignment = Alignment(vertical="top", wrap_text=(column == 7))
        for column in range(TICK_FIRST, TICK_LAST + 1):
            cell = sheet.cell(row, column)
            cell.border = border
            cell.font = font
            cell.alignment = Alignment(horizontal="center", vertical="top")
        frames = f"{letter(TICK_FIRST)}{row}:{letter(FRAME_LAST)}{row}"
        sheet.cell(row, COUNT_COL, f'=COUNTIF({frames},"x")')
        sheet.cell(
            row, CHECK_COL,
            f'=IF(AND({letter(COUNT_COL)}{row}=0,{letter(NONE_COL)}{row}<>"x"),"not coded",'
            f'IF(AND({letter(COUNT_COL)}{row}>0,{letter(NONE_COL)}{row}="x"),"NONE + frame",""))',
        )
        for column in (COUNT_COL, CHECK_COL, NOTES_COL):
            cell = sheet.cell(row, column)
            cell.font = font
            cell.alignment = Alignment(vertical="top", wrap_text=(column == NOTES_COL))

    ticks = f"{letter(TICK_FIRST)}{FIRST_ROW}:{letter(TICK_LAST)}{last}"
    validation = DataValidation(
        type="list", formula1='"x"', allow_blank=True, showErrorMessage=True,
        errorTitle="Tick with x", error="Type a lowercase x, or leave the cell empty.",
    )
    sheet.add_data_validation(validation)
    validation.add(ticks)

    rules = sheet.conditional_formatting
    rules.add(
        f"A{FIRST_ROW}:{letter(TICK_FIRST - 1)}{last}",
        FormulaRule(formula=[f"ISODD($B{FIRST_ROW})"], fill=PatternFill(bgColor="F2F2F2", fill_type="solid")),
    )
    rules.add(
        f"G{FIRST_ROW}:G{last}",
        FormulaRule(formula=[f'$F{FIRST_ROW}<>"Sentence"'], font=Font(color="808080")),
    )
    for first, last_column, colour in GROUP_FILLS:
        rules.add(
            f"{letter(first)}{FIRST_ROW}:{letter(last_column)}{last}",
            CellIsRule(operator="equal", formula=['"x"'],
                       fill=PatternFill(bgColor=colour, fill_type="solid"),
                       font=Font(color="FFFFFF", bold=True)),
        )
    check = f"{letter(CHECK_COL)}{FIRST_ROW}"
    rules.add(
        f"{check}:{letter(CHECK_COL)}{last}",
        FormulaRule(formula=[f'{check}="NONE + frame"'],
                    fill=PatternFill(bgColor="FFC7CE", fill_type="solid"), font=Font(color="9C0006")),
    )

    sheet["A1"] = (
        f"Coding: Munk Debates, Global Refugee Crisis (2016). {len(sentences)} sentences. Tick with x."
    )


def main() -> None:
    args = parse_args()
    sentences = read_sentences(args.sentences.resolve(), args.analysis_only)
    workbook = openpyxl.load_workbook(args.template.resolve())
    fill_coding(workbook["Coding"], sentences)
    workbook.calculation.fullCalcOnLoad = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(args.output)
    print(f"Wrote {len(sentences)} sentences to {args.output}")


if __name__ == "__main__":
    main()
