from __future__ import annotations

import re
from typing import Any

import pandas as pd


STANDARD_COLUMNS = [
    "院校专业组代号",
    "院校专业组名称",
    "学校名称",
    "批次",
    "首选科目",
    "首选科目或类别",
    "再选科目要求",
    "类别",
    "投档最低分",
    "专业成绩",
    "位次值",
    "专业信息",
    "学校所在省份",
    "学校所在城市",
    "学校性质",
    "备注",
    "数据状态",
    "批次类型",
    "原始工作表",
]


def clean_header(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = re.sub(r"[\s\u3000]+", "", text)
    if not text:
        return None
    if text in {"专业", "具体专业"}:
        return "专业信息"
    if text == "院校专业组":
        return "院校专业组代号"
    if text == "省份":
        return "学校所在省份"
    return text


def clean_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text if text else None
    return value


def identify_sheet(sheet_name: str) -> dict[str, str | None]:
    if "本科普通批" in sheet_name:
        return {
            "批次": "本科普通批",
            "批次类型": "普通批",
            "首选科目": _first_choice_from_name(sheet_name),
        }
    if "高职高专普通批" in sheet_name:
        return {
            "批次": "高职高专普通批",
            "批次类型": "普通批",
            "首选科目": _first_choice_from_name(sheet_name),
        }
    if "技能高考本科批" in sheet_name:
        return {"批次": "技能高考本科批", "批次类型": "技能高考", "首选科目": None}
    if "技能高考高职高专批" in sheet_name:
        return {"批次": "技能高考高职高专批", "批次类型": "技能高考", "首选科目": None}
    if "体育" in sheet_name and "本科" in sheet_name:
        return {"批次": "体育本科", "批次类型": "体育", "首选科目": None}
    if "体育" in sheet_name and "专科" in sheet_name:
        return {"批次": "体育专科", "批次类型": "体育", "首选科目": None}
    if "艺术" in sheet_name and "本科" in sheet_name:
        return {"批次": "艺术本科", "批次类型": "艺术", "首选科目": None}
    if "艺术" in sheet_name and "专科" in sheet_name:
        return {"批次": "艺术专科", "批次类型": "艺术", "首选科目": None}
    return {"批次": sheet_name, "批次类型": "其他", "首选科目": None}


def clean_sheet_rows(rows: list[list[Any]], sheet_name: str) -> pd.DataFrame:
    if len(rows) < 2:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    headers = [clean_header(value) for value in rows[1]]
    effective_columns = [(index, header) for index, header in enumerate(headers) if header]
    records: list[dict[str, Any]] = []

    for row in rows[2:]:
        record = {
            header: clean_cell(row[index]) if index < len(row) else None
            for index, header in effective_columns
        }
        if any(value is not None for value in record.values()):
            records.append(record)

    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    meta = identify_sheet(sheet_name)
    df["原始工作表"] = sheet_name
    df["批次"] = meta["批次"]
    df["批次类型"] = meta["批次类型"]
    df["首选科目"] = meta["首选科目"]

    for column in [
        "再选科目要求",
        "类别",
        "学校名称",
        "学校所在省份",
        "学校所在城市",
        "学校性质",
        "备注",
        "专业信息",
    ]:
        if column in df.columns:
            df[column] = df[column].map(clean_cell)

    if "类别" in df.columns:
        df["类别"] = df["类别"].replace({"组计算机类": "计算机类"})

    for column in ["投档最低分", "位次值", "专业成绩"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    for column in STANDARD_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA

    df["首选科目或类别"] = _display_track(df)
    df["数据状态"] = df.apply(_data_status, axis=1)
    return df[STANDARD_COLUMNS]


def _first_choice_from_name(sheet_name: str) -> str | None:
    if "物理" in sheet_name:
        return "物理"
    if "历史" in sheet_name:
        return "历史"
    return None


def _display_track(df: pd.DataFrame) -> pd.Series:
    batch_type = df["批次类型"].iloc[0]
    if batch_type == "普通批":
        return df["首选科目"]
    if batch_type in {"技能高考", "艺术"}:
        return df["类别"]
    return pd.Series([""] * len(df), index=df.index)


def _data_status(row: pd.Series) -> str:
    if pd.isna(row.get("投档最低分")) or pd.isna(row.get("位次值")):
        return "数据不完整"
    return "正常"
