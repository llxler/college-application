from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from admission_recommender import (
    CandidateFilters,
    RecommendRequest,
    RecommendThresholds,
    filter_candidates,
    load_rank_data,
    load_workbook_data,
    rank_for_score,
    recommend,
)
from admission_recommender.exporter import (
    EXCEL_MIME,
    JPG_MIME,
    PDF_MIME,
    build_export_stem,
    to_excel_bytes,
    to_jpg_bytes,
    to_pdf_bytes,
)

DATA_PATH = Path(__file__).with_name("table.xlsx")
RANK_PATH = Path(__file__).with_name("rank.xlsx")
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
EXPORT_FORMATS = {
    "Excel": ("xlsx", EXCEL_MIME),
    "PDF": ("pdf", PDF_MIME),
    "JPG": ("jpg", JPG_MIME),
}


@st.cache_data(show_spinner=False)
def load_data(data_path: str, file_mtime_ns: int) -> pd.DataFrame:
    return load_workbook_data(data_path)


@st.cache_data(show_spinner=False)
def load_ranks() -> pd.DataFrame:
    if not RANK_PATH.exists():
        return pd.DataFrame(columns=["首选科目", "分数", "位次值"])
    return load_rank_data(RANK_PATH)


@st.cache_data(show_spinner=False)
def create_export(result: pd.DataFrame, export_format: str) -> bytes:
    if export_format == "PDF":
        return to_pdf_bytes(result)
    if export_format == "JPG":
        return to_jpg_bytes(result)
    return to_excel_bytes(result)


def main() -> None:
    st.set_page_config(
        page_title="志愿推荐筛选程序",
        page_icon=":material/school:",
        layout="wide",
    )
    st.title("志愿推荐筛选程序")
    st.warning(
        "本系统仅基于往年投档线进行辅助筛选，不能替代官方招生计划和最终录取结果。",
        icon=":material/info:",
    )

    if not DATA_PATH.exists():
        st.error(f"未找到数据文件：{DATA_PATH}")
        return

    data = load_data(str(DATA_PATH), DATA_PATH.stat().st_mtime_ns)
    if data.empty:
        st.error("Excel 数据为空或读取失败。")
        return

    filters, request, thresholds = render_controls(data, load_ranks())
    filtered = filter_candidates(data, filters)
    incomplete_count = int((filtered["数据状态"] == "数据不完整").sum())

    result = recommend(filtered, request, thresholds)
    render_result(result, len(filtered), incomplete_count, filters, request)


def render_controls(
    data: pd.DataFrame,
    rank_data: pd.DataFrame,
) -> tuple[CandidateFilters, RecommendRequest, RecommendThresholds]:
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

        location_data = batch_data
        if first_choice:
            location_data = location_data[location_data["首选科目"] == first_choice]
        if skill_category:
            location_data = location_data[location_data["类别"] == skill_category]
        if art_category:
            location_data = location_data[location_data["类别"] == art_category]

        province_options = available_values(location_data, "学校所在省份")
        provinces = st.multiselect(
            "学校所在省份",
            province_options,
            placeholder="搜索或选择省份" if province_options else "当前批次暂无省份数据",
            disabled=not province_options,
        )
        city_data = location_data
        if provinces:
            city_data = city_data[city_data["学校所在省份"].isin(provinces)]
        city_options = available_values(city_data, "学校所在城市")
        cities = st.multiselect(
            "学校所在城市",
            city_options,
            placeholder="搜索或选择城市" if city_options else "当前批次暂无城市数据",
            disabled=not city_options,
        )
        input_mode = st.segmented_control(
            "成绩录入方式",
            options=["分数", "位次"],
            default="分数",
            selection_mode="single",
        )
        user_score = None
        user_rank = None
        if input_mode == "位次":
            user_rank = parse_optional_number(st.text_input("用户位次值"))
        else:
            entered_score = parse_optional_number(st.text_input("用户总分"))
            if entered_score is not None and first_choice:
                converted_rank = rank_for_score(rank_data, first_choice, entered_score)
                if converted_rank is None:
                    st.error(f"rank.xlsx 暂无 {first_choice} {entered_score:g} 分对应的位次。")
                else:
                    user_score = entered_score
                    user_rank = float(converted_rank)
                    st.metric(
                        "自动换算位次",
                        f"{converted_rank:,}",
                        help="根据 rank.xlsx 中对应科目的一分一段表换算。",
                        border=True,
                    )
            else:
                user_score = entered_score
        major_keyword = st.text_input(
            "专业关键词（可选）",
            placeholder="如：电子信息 人工智能（匹配任意一个）",
            help="多个关键词可用空格、逗号、顿号、分号、竖线或斜杠分隔；匹配任意一个，英文不区分大小写。",
        ).strip()
        school_natures = st.multiselect(
            "学校性质筛选",
            sorted(value for value in batch_data["学校性质"].dropna().unique() if value),
        )
        exclude_remark_keywords = st.multiselect("备注排除", REMARK_EXCLUDE_OPTIONS)
        per_level_limit = int(st.number_input("每档推荐数量", min_value=1, max_value=100, value=10, step=1))
        thresholds = render_rank_threshold_controls()

    filters = CandidateFilters(
        batch=batch,
        first_choice=first_choice,
        selected_subjects=selected_subjects,
        skill_category=skill_category,
        art_category=art_category,
        provinces=provinces,
        cities=cities,
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


def render_rank_threshold_controls() -> RecommendThresholds:
    with st.expander("位次推荐阈值"):
        rank_rush_min = st.number_input("位次冲下限", value=-0.10, step=0.01, format="%.2f")
        rank_rush_max = st.number_input("位次冲上限", value=0.05, step=0.01, format="%.2f")
        rank_stable_min = st.number_input("位次稳下限", value=0.05, step=0.01, format="%.2f")
        rank_stable_max = st.number_input("位次稳上限", value=0.25, step=0.01, format="%.2f")
        rank_safe_min = st.number_input("位次保下限", value=0.25, step=0.01, format="%.2f")
        st.divider()
        with st.popover("查看位次阈值说明", icon=":material/help:"):
            st.markdown(
                """
                位次值越小，排名越靠前。系统按下面的比例判断“冲、稳、保”：

                `位次差比例 =（往年投档位次 - 你的位次）/ 你的位次`

                - 比例为正：你的位次优于往年投档位次。
                - 比例为负：你的位次低于往年投档位次。
                - 阈值使用小数填写，例如 `0.05` 代表 `5%`。

                例如你的位次是 `10000`，某专业组往年投档位次是 `12000`，
                位次差比例就是 `(12000 - 10000) / 10000 = 0.20`，即 `20%`。

                默认规则：`-10%～5%` 为冲，`>5%～25%` 为稳，`>25%` 为保。
                """
            )
    return RecommendThresholds(
        rank_rush_min=rank_rush_min,
        rank_rush_max=rank_rush_max,
        rank_stable_min=rank_stable_min,
        rank_stable_max=rank_stable_max,
        rank_safe_min=rank_safe_min,
    )


def render_result(
    result: pd.DataFrame,
    filtered_count: int,
    incomplete_count: int,
    filters: CandidateFilters,
    request: RecommendRequest,
) -> None:
    visible_result, row_ids, signature = result_after_deletions(result)

    st.subheader("推荐结果")
    col1, col2, col3 = st.columns(3)
    col1.metric("筛选后数据", filtered_count, border=True)
    col2.metric("数据不完整", incomplete_count, border=True)
    col3.metric("推荐结果", len(visible_result), border=True)

    if result.empty:
        st.info("暂无符合当前条件的结果。")
        return
    if visible_result.empty:
        st.info("推荐结果已全部删除。")
        return

    editor_result = visible_result.copy()
    editor_result.insert(0, "_志愿标识", row_ids)
    editor_result.insert(0, "删除", False)
    editor_key = f"result_editor_{signature}_{st.session_state.result_delete_version}"
    edited_result = st.data_editor(
        editor_result,
        width="stretch",
        height=520,
        hide_index=True,
        disabled=[column for column in editor_result.columns if column != "删除"],
        column_config={
            "删除": st.column_config.CheckboxColumn("删除", help="勾选不需要的志愿"),
            "_志愿标识": None,
        },
        key=editor_key,
    )

    selected_ids = edited_result.loc[edited_result["删除"], "_志愿标识"].tolist()
    delete_column, _ = st.columns([1, 5])
    if delete_column.button(
        "删除选中志愿",
        icon=":material/delete:",
        disabled=not selected_ids,
        width="stretch",
    ):
        st.session_state.deleted_result_ids = list(
            set(st.session_state.deleted_result_ids).union(selected_ids)
        )
        st.session_state.result_delete_version += 1
        st.rerun()

    export_format = st.segmented_control(
        "导出格式",
        options=list(EXPORT_FORMATS),
        default="Excel",
        selection_mode="single",
    )
    export_format = export_format or "Excel"
    extension, mime = EXPORT_FORMATS[export_format]
    category = filters.skill_category or filters.art_category
    export_stem = build_export_stem(
        filters.first_choice,
        category,
        request.user_score,
        request.user_rank,
    )
    file_name = f"{export_stem}.{extension}"
    export_data = create_export(visible_result, export_format)

    download_column, _ = st.columns([1, 5])
    download_column.download_button(
        f"导出 {export_format}",
        data=export_data,
        file_name=file_name,
        mime=mime,
        icon=":material/download:",
        width="stretch",
    )


def result_after_deletions(result: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, str]:
    signature = result_signature(result)
    if st.session_state.get("result_signature") != signature:
        st.session_state.result_signature = signature
        st.session_state.deleted_result_ids = []
        st.session_state.result_delete_version = 0

    all_row_ids = result_row_ids(result)
    deleted_ids = set(st.session_state.deleted_result_ids)
    visible_mask = ~all_row_ids.isin(deleted_ids)
    return (
        result.loc[visible_mask].reset_index(drop=True),
        all_row_ids.loc[visible_mask].reset_index(drop=True),
        signature,
    )


def result_signature(result: pd.DataFrame) -> str:
    hashes = pd.util.hash_pandas_object(result.astype(str), index=True)
    return hashlib.sha256(hashes.values.tobytes()).hexdigest()[:16]


def result_row_ids(result: pd.DataFrame) -> pd.Series:
    hashes = pd.util.hash_pandas_object(result.astype(str), index=False)
    return hashes.map(lambda value: f"{int(value):016x}")


def available_batches(data: pd.DataFrame) -> list[str]:
    existing = set(data["批次"].dropna().unique())
    ordered = [batch for batch in BATCH_ORDER if batch in existing]
    remaining = sorted(existing - set(ordered))
    return ordered + remaining


def available_values(data: pd.DataFrame, column: str) -> list[str]:
    if column not in data.columns:
        return []
    return sorted(
        {
            str(value).strip()
            for value in data[column].dropna()
            if str(value).strip()
        }
    )


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
