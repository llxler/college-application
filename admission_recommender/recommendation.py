from __future__ import annotations

import math

import pandas as pd

from .models import RecommendRequest, RecommendThresholds

RESULT_COLUMNS = [
    "推荐档位",
    "院校专业组代号",
    "院校专业组名称",
    "批次",
    "首选科目或类别",
    "再选科目要求",
    "投档最低分",
    "位次值",
    "专业成绩",
    "专业信息",
    "学校性质",
    "备注",
    "分差",
    "位次差",
    "推荐理由",
]

LEVELS = ("冲", "稳", "保")


def recommend(
    data: pd.DataFrame,
    request: RecommendRequest,
    thresholds: RecommendThresholds | None = None,
) -> pd.DataFrame:
    thresholds = thresholds or RecommendThresholds()
    if data.empty or (not request.user_rank and request.user_score is None):
        return pd.DataFrame(columns=RESULT_COLUMNS)

    df = data[data["数据状态"] == "正常"].copy()
    if df.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    if request.user_rank and request.user_rank > 0:
        df = _recommend_by_rank(df, request, thresholds)
    elif request.user_score is not None:
        df = _recommend_by_score(df, request, thresholds)
    else:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    df = df[df["推荐档位"].notna()].copy()
    if df.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    result = _dedupe_sort_limit(df, request.per_level_limit)[RESULT_COLUMNS]
    return result.astype(object).where(pd.notna(result), "")


def _recommend_by_rank(
    df: pd.DataFrame,
    request: RecommendRequest,
    thresholds: RecommendThresholds,
) -> pd.DataFrame:
    df["位次差"] = df["位次值"] - request.user_rank
    df["位次差比例"] = df["位次差"] / request.user_rank
    df["推荐档位"] = df["位次差比例"].map(lambda ratio: _rank_level(ratio, thresholds))
    if request.user_score is not None:
        df["分差"] = request.user_score - df["投档最低分"]
    else:
        df["分差"] = pd.NA
    df["排序值"] = df.apply(_rank_sort_value, axis=1)
    df["推荐理由"] = df.apply(lambda row: _rank_reason(row, request.user_rank), axis=1)
    return df


def _recommend_by_score(
    df: pd.DataFrame,
    request: RecommendRequest,
    thresholds: RecommendThresholds,
) -> pd.DataFrame:
    df["分差"] = request.user_score - df["投档最低分"]
    df["位次差"] = pd.NA
    df["推荐档位"] = df["分差"].map(lambda diff: _score_level(diff, thresholds))
    df["排序值"] = df["分差"].abs()
    df.loc[df["推荐档位"].isin(["稳", "保"]), "排序值"] = df["分差"]
    df["推荐理由"] = df.apply(lambda row: _score_reason(row, request.user_score), axis=1)
    return df


def _rank_level(ratio: float, thresholds: RecommendThresholds) -> str | None:
    if pd.isna(ratio):
        return None
    if thresholds.rank_rush_min <= ratio <= thresholds.rank_rush_max:
        return "冲"
    if thresholds.rank_stable_min < ratio <= thresholds.rank_stable_max:
        return "稳"
    if ratio > thresholds.rank_safe_min:
        return "保"
    return None


def _score_level(diff: float, thresholds: RecommendThresholds) -> str | None:
    if pd.isna(diff):
        return None
    if thresholds.score_rush_min <= diff <= thresholds.score_rush_max:
        return "冲"
    if thresholds.score_stable_min < diff <= thresholds.score_stable_max:
        return "稳"
    if diff > thresholds.score_safe_min:
        return "保"
    return None


def _rank_sort_value(row: pd.Series) -> float:
    ratio = row["位次差比例"]
    if row["推荐档位"] == "冲":
        return abs(ratio)
    return ratio


def _dedupe_sort_limit(df: pd.DataFrame, per_level_limit: int) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    dedupe_columns = ["批次", "首选科目或类别", "院校专业组代号"]
    per_level_limit = max(int(per_level_limit), 1)
    for level in LEVELS:
        subset = df[df["推荐档位"] == level].sort_values("排序值", kind="mergesort")
        subset = subset.drop_duplicates(subset=dedupe_columns, keep="first")
        pieces.append(subset.head(per_level_limit))
    if not pieces:
        return pd.DataFrame(columns=df.columns)
    result = pd.concat(pieces, ignore_index=True)
    result["推荐档位"] = pd.Categorical(result["推荐档位"], categories=list(LEVELS), ordered=True)
    return result.sort_values(["推荐档位", "排序值"], kind="mergesort").reset_index(drop=True)


def _rank_reason(row: pd.Series, user_rank: float) -> str:
    score = _format_number(row["投档最低分"])
    line_rank = _format_number(row["位次值"])
    diff = row["位次差"]
    if diff >= 0:
        comparison = f"你的位次优于往年投档线约 {_format_number(diff)} 名"
    else:
        comparison = f"你的位次低于往年投档线约 {_format_number(abs(diff))} 名"
    return (
        f"该院校专业组 2025 年投档最低分为 {score} 分，位次值为 {line_rank}。"
        f"你的位次为 {_format_number(user_rank)}，{comparison}，属于{_level_name(row['推荐档位'])}。"
    )


def _score_reason(row: pd.Series, user_score: float) -> str:
    score = _format_number(row["投档最低分"])
    line_rank = _format_number(row["位次值"])
    diff = row["分差"]
    if diff >= 0:
        comparison = f"你的分数高于往年投档线约 {_format_number(diff)} 分"
    else:
        comparison = f"你的分数低于往年投档线约 {_format_number(abs(diff))} 分"
    return (
        f"该院校专业组 2025 年投档最低分为 {score} 分，位次值为 {line_rank}。"
        f"你的总分为 {_format_number(user_score)}，{comparison}，属于{_level_name(row['推荐档位'])}。"
    )


def _level_name(level: str) -> str:
    return {"冲": "冲刺推荐", "稳": "稳妥推荐", "保": "保底推荐"}.get(level, "推荐")


def _format_number(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    numeric = float(value)
    if math.isclose(numeric, round(numeric)):
        return str(int(round(numeric)))
    return f"{numeric:.3f}".rstrip("0").rstrip(".")
