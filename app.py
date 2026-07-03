from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from admission_recommender import (
    CandidateFilters,
    RecommendRequest,
    RecommendThresholds,
    filter_candidates,
    load_workbook_data,
    recommend,
)
from admission_recommender.exporter import EXCEL_MIME, to_excel_bytes

DATA_PATH = Path(__file__).with_name("table.xlsx")
BATCH_ORDER = [
    "本科普通批",
    "高职高专普通批",
    "技能高考本科批",
    "技能高考高职高专批",
    "体育本科",
    "体育专科",
    "艺术本科",
    "艺术专科",
]
REMARK_EXCLUDE_OPTIONS = [
    "中外合作办学",
    "乡村振兴",
    "专本联合培养",
    "国家专项计划",
    "护理类",
]


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    return load_workbook_data(DATA_PATH)


def main() -> None:
    st.set_page_config(page_title="志愿推荐筛选程序", layout="wide")
    st.title("志愿推荐筛选程序")
    st.warning("本系统仅基于往年投档线进行辅助筛选，不能替代官方招生计划和最终录取结果。")

    if not DATA_PATH.exists():
        st.error(f"未找到数据文件：{DATA_PATH}")
        return

    data = load_data()
    if data.empty:
        st.error("Excel 数据为空或读取失败。")
        return

    filters, request, thresholds = render_controls(data)
    filtered = filter_candidates(data, filters)
    incomplete_count = int((filtered["数据状态"] == "数据不完整").sum())

    result = recommend(filtered, request, thresholds)
    render_result(result, len(filtered), incomplete_count)


def render_controls(data: pd.DataFrame) -> tuple[CandidateFilters, RecommendRequest, RecommendThresholds]:
    with st.sidebar:
        st.header("筛选条件")
        batch = st.selectbox("报考批次", available_batches(data))
        batch_data = data[data["批次"] == batch]
        batch_type = str(batch_data["批次类型"].dropna().iloc[0])

        first_choice = None
        selected_subjects: list[str] = []
        skill_category = None
        art_category = None

        if batch_type == "普通批":
            first_choice = st.selectbox("首选科目", sorted(batch_data["首选科目"].dropna().unique()))
            selected_subjects = st.multiselect("再选科目", ["化", "生", "地", "政"])
        elif batch_type == "技能高考":
            skill_category = st.selectbox("技能高考类别", sorted(batch_data["类别"].dropna().unique()))
        elif batch_type == "艺术":
            art_category = st.selectbox("艺术类别", sorted(batch_data["类别"].dropna().unique()))

        user_score = parse_optional_number(st.text_input("用户总分（可选）"))
        user_rank = parse_optional_number(st.text_input("用户位次值（可选）"))
        major_keyword = st.text_input("专业关键词（可选）").strip()
        school_natures = st.multiselect(
            "学校性质筛选",
            sorted(value for value in batch_data["学校性质"].dropna().unique() if value),
        )
        exclude_remark_keywords = st.multiselect("备注排除", REMARK_EXCLUDE_OPTIONS)
        per_level_limit = int(st.number_input("每档推荐数量", min_value=1, max_value=100, value=10, step=1))
        thresholds = render_threshold_controls()

    filters = CandidateFilters(
        batch=batch,
        first_choice=first_choice,
        selected_subjects=selected_subjects,
        skill_category=skill_category,
        art_category=art_category,
        major_keyword=major_keyword,
        school_natures=school_natures,
        exclude_remark_keywords=exclude_remark_keywords,
    )
    request = RecommendRequest(
        user_score=user_score,
        user_rank=user_rank,
        per_level_limit=per_level_limit,
    )
    return filters, request, thresholds


def render_threshold_controls() -> RecommendThresholds:
    with st.expander("推荐阈值"):
        rank_rush_min = st.number_input("位次冲下限", value=-0.10, step=0.01, format="%.2f")
        rank_rush_max = st.number_input("位次冲上限", value=0.05, step=0.01, format="%.2f")
        rank_stable_min = st.number_input("位次稳下限", value=0.05, step=0.01, format="%.2f")
        rank_stable_max = st.number_input("位次稳上限", value=0.25, step=0.01, format="%.2f")
        rank_safe_min = st.number_input("位次保下限", value=0.25, step=0.01, format="%.2f")
        score_rush_min = st.number_input("分数冲下限", value=-10.0, step=1.0)
        score_rush_max = st.number_input("分数冲上限", value=5.0, step=1.0)
        score_stable_min = st.number_input("分数稳下限", value=5.0, step=1.0)
        score_stable_max = st.number_input("分数稳上限", value=20.0, step=1.0)
        score_safe_min = st.number_input("分数保下限", value=20.0, step=1.0)
    return RecommendThresholds(
        rank_rush_min=rank_rush_min,
        rank_rush_max=rank_rush_max,
        rank_stable_min=rank_stable_min,
        rank_stable_max=rank_stable_max,
        rank_safe_min=rank_safe_min,
        score_rush_min=score_rush_min,
        score_rush_max=score_rush_max,
        score_stable_min=score_stable_min,
        score_stable_max=score_stable_max,
        score_safe_min=score_safe_min,
    )


def render_result(result: pd.DataFrame, filtered_count: int, incomplete_count: int) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric("筛选后数据", filtered_count)
    col2.metric("数据不完整", incomplete_count)
    col3.metric("推荐结果", len(result))

    if result.empty:
        st.info("暂无符合当前条件和推荐阈值的结果。")
        return

    st.dataframe(result, use_container_width=True, hide_index=True)
    st.download_button(
        "导出 Excel",
        data=to_excel_bytes(result),
        file_name="志愿推荐结果.xlsx",
        mime=EXCEL_MIME,
    )


def available_batches(data: pd.DataFrame) -> list[str]:
    existing = set(data["批次"].dropna().unique())
    ordered = [batch for batch in BATCH_ORDER if batch in existing]
    remaining = sorted(existing - set(ordered))
    return ordered + remaining


def parse_optional_number(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        st.sidebar.error(f"无法识别数字：{text}")
        return None
    if number <= 0:
        st.sidebar.error(f"请输入大于 0 的数字：{text}")
        return None
    return number


if __name__ == "__main__":
    main()
