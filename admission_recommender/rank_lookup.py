from __future__ import annotations

from pathlib import Path

import pandas as pd

from .excel_loader import read_xlsx_rows

RANK_COLUMNS = ["首选科目", "分数", "位次值"]


def load_rank_data(path: str | Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for sheet_name, rows in read_xlsx_rows(path).items():
        first_choice = _first_choice_from_name(sheet_name)
        header_index = _header_index(rows)
        if first_choice is None or header_index is None:
            continue

        headers = rows[header_index]
        score_index = headers.index("分数")
        rank_index = headers.index("累计人数")
        records = [
            {
                "首选科目": first_choice,
                "分数": row[score_index] if score_index < len(row) else None,
                "位次值": row[rank_index] if rank_index < len(row) else None,
            }
            for row in rows[header_index + 1 :]
        ]
        frames.append(pd.DataFrame(records))

    if not frames:
        return pd.DataFrame(columns=RANK_COLUMNS)

    result = pd.concat(frames, ignore_index=True)
    result["分数"] = pd.to_numeric(result["分数"], errors="coerce")
    result["位次值"] = pd.to_numeric(result["位次值"], errors="coerce")
    result = result.dropna(subset=["分数", "位次值"])
    result = result.drop_duplicates(subset=["首选科目", "分数"], keep="last")
    return result[RANK_COLUMNS].sort_values(
        ["首选科目", "分数"],
        ascending=[True, False],
        ignore_index=True,
    )


def rank_for_score(
    rank_data: pd.DataFrame,
    first_choice: str,
    score: float,
) -> int | None:
    rows = rank_data[rank_data["首选科目"] == first_choice]
    if rows.empty or score < rows["分数"].min():
        return None

    eligible = rows[rows["分数"] >= score]
    if eligible.empty:
        matched = rows.loc[rows["分数"].idxmax()]
    else:
        matched = eligible.loc[eligible["分数"].idxmin()]
    return int(matched["位次值"])


def _header_index(rows: list[list[object]]) -> int | None:
    for index, row in enumerate(rows):
        if "分数" in row and "累计人数" in row:
            return index
    return None


def _first_choice_from_name(sheet_name: str) -> str | None:
    if "物理" in sheet_name:
        return "物理"
    if "历史" in sheet_name:
        return "历史"
    return None
