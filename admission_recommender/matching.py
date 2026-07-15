from __future__ import annotations

import re
from typing import Iterable

import pandas as pd

from .models import CandidateFilters

SUBJECTS = ("化", "生", "地", "政")


def subject_requirement_matches(requirement: object, selected_subjects: Iterable[str]) -> bool:
    required = required_subjects(requirement)
    if not required:
        return True
    return required.issubset(set(selected_subjects))


def required_subjects(requirement: object) -> set[str]:
    if requirement is None or pd.isna(requirement):
        return set()
    text = str(requirement).strip()
    if not text or text == "不限":
        return set()
    return set(re.findall("|".join(SUBJECTS), text))


def filter_candidates(data: pd.DataFrame, filters: CandidateFilters) -> pd.DataFrame:
    df = data.copy()
    df = df[df["批次"] == filters.batch]

    if filters.first_choice:
        df = df[df["首选科目"] == filters.first_choice]

    if filters.selected_subjects and "再选科目要求" in df.columns:
        mask = df["再选科目要求"].map(
            lambda requirement: subject_requirement_matches(
                requirement,
                filters.selected_subjects,
            )
        )
        df = df[mask]
    elif _is_common_batch(df):
        df = df[df["再选科目要求"].map(lambda requirement: not required_subjects(requirement))]

    if filters.skill_category:
        df = df[df["类别"] == filters.skill_category]

    if filters.art_category:
        df = df[df["类别"] == filters.art_category]

    if filters.provinces:
        df = df[df["省份"].isin(filters.provinces)]

    keyword = (filters.major_keyword or "").strip()
    if keyword and "专业信息" in df.columns and df["专业信息"].notna().any():
        df = df[df["专业信息"].fillna("").str.contains(keyword, regex=False)]

    if filters.school_natures:
        df = df[df["学校性质"].isin(filters.school_natures)]

    for keyword in filters.exclude_remark_keywords:
        keyword = keyword.strip()
        if not keyword:
            continue
        text = (
            df["备注"].fillna("").astype(str)
            + " "
            + df["学校性质"].fillna("").astype(str)
        )
        df = df[~text.str.contains(keyword, regex=False)]

    return df.reset_index(drop=True)


def _is_common_batch(df: pd.DataFrame) -> bool:
    if df.empty or "批次类型" not in df.columns:
        return False
    return bool((df["批次类型"] == "普通批").any())
