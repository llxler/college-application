from __future__ import annotations

import unittest
import zipfile
from io import BytesIO

import pandas as pd
from PIL import Image

from admission_recommender import (
    CandidateFilters,
    RecommendRequest,
    filter_candidates,
    load_rank_data,
    load_workbook_data,
    rank_for_score,
    recommend,
    subject_requirement_matches,
)
from admission_recommender.exporter import (
    build_export_stem,
    to_excel_bytes,
    to_jpg_bytes,
    to_pdf_bytes,
)


class RecommenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = load_workbook_data("table.xlsx")

    def test_loads_all_sheets_and_cleans_columns(self) -> None:
        self.assertEqual(len(set(self.data["原始工作表"])), 10)
        self.assertIn("专业信息", self.data.columns)
        self.assertIn("院校专业组代号", self.data.columns)
        self.assertIn("省份", self.data.columns)
        self.assertNotIn("专业", self.data.columns)
        self.assertNotIn("具体专业", self.data.columns)

    def test_province_cleanup_and_filter(self) -> None:
        junior = self.data[self.data["批次"] == "高职高专普通批"]
        self.assertEqual(set(junior["省份"]), {"湖北省", "其他"})
        self.assertEqual(int((junior["省份"] == "湖北省").sum()), 447)

        hubei = filter_candidates(
            self.data,
            CandidateFilters(
                batch="高职高专普通批",
                selected_subjects=["化", "生", "地", "政"],
                provinces=["湖北省"],
            ),
        )
        other = filter_candidates(
            self.data,
            CandidateFilters(
                batch="高职高专普通批",
                selected_subjects=["化", "生", "地", "政"],
                provinces=["其他"],
            ),
        )
        self.assertEqual(len(hubei), 447)
        self.assertEqual(len(other), 1520)
        self.assertTrue((hubei["省份"] == "湖北省").all())
        self.assertTrue((other["省份"] == "其他").all())

    def test_province_filter_handles_legacy_data_without_column(self) -> None:
        legacy_data = pd.DataFrame([{"批次": "体育本科"}, {"批次": "体育本科"}])

        hubei = filter_candidates(
            legacy_data,
            CandidateFilters(batch="体育本科", provinces=["湖北省"]),
        )
        other = filter_candidates(
            legacy_data,
            CandidateFilters(batch="体育本科", provinces=["其他"]),
        )

        self.assertTrue(hubei.empty)
        self.assertEqual(len(other), 2)
        self.assertTrue((other["省份"] == "其他").all())

    def test_ignores_empty_art_columns(self) -> None:
        art = self.data[self.data["原始工作表"] == "艺术（本科）"]
        self.assertTrue(all(isinstance(column, str) for column in art.columns))
        self.assertTrue(art["专业信息"].isna().all())

    def test_subject_matching(self) -> None:
        self.assertTrue(subject_requirement_matches("不限", []))
        self.assertTrue(subject_requirement_matches("化", ["化", "生"]))
        self.assertTrue(subject_requirement_matches("化和生", ["化", "生"]))
        self.assertFalse(subject_requirement_matches("化和生", ["化", "地"]))

    def test_skill_category_cleanup(self) -> None:
        skill = self.data[self.data["批次"] == "技能高考高职高专批"]
        self.assertIn("计算机类", set(skill["类别"].dropna()))
        self.assertNotIn("组计算机类", set(skill["类别"].dropna()))

    def test_rank_recommendation_prefers_rank(self) -> None:
        sample = pd.DataFrame(
            [
                {
                    "院校专业组代号": "A",
                    "院校专业组名称": "冲学校",
                    "批次": "本科普通批",
                    "首选科目或类别": "物理",
                    "再选科目要求": "不限",
                    "投档最低分": 600,
                    "位次值": 9500,
                    "专业成绩": pd.NA,
                    "专业信息": "计算机",
                    "学校性质": "公办",
                    "备注": pd.NA,
                    "数据状态": "正常",
                },
                {
                    "院校专业组代号": "B",
                    "院校专业组名称": "稳学校",
                    "批次": "本科普通批",
                    "首选科目或类别": "物理",
                    "再选科目要求": "不限",
                    "投档最低分": 580,
                    "位次值": 11500,
                    "专业成绩": pd.NA,
                    "专业信息": "计算机",
                    "学校性质": "公办",
                    "备注": pd.NA,
                    "数据状态": "正常",
                },
                {
                    "院校专业组代号": "C",
                    "院校专业组名称": "保学校",
                    "批次": "本科普通批",
                    "首选科目或类别": "物理",
                    "再选科目要求": "不限",
                    "投档最低分": 560,
                    "位次值": 13000,
                    "专业成绩": pd.NA,
                    "专业信息": "计算机",
                    "学校性质": "公办",
                    "备注": pd.NA,
                    "数据状态": "正常",
                },
            ]
        )
        result = recommend(sample, RecommendRequest(user_score=610, user_rank=10000, per_level_limit=3))
        self.assertEqual(list(result["推荐档位"]), ["冲", "稳", "保"])
        self.assertTrue(pd.to_numeric(result["位次差"], errors="coerce").notna().all())

    def test_filters_and_exports(self) -> None:
        filters = CandidateFilters(
            batch="本科普通批",
            first_choice="物理",
            selected_subjects=["化", "生"],
            major_keyword="计算机",
            school_natures=["公办"],
        )
        filtered = filter_candidates(self.data, filters)
        result = recommend(filtered, RecommendRequest(user_score=600, user_rank=30000, per_level_limit=2))
        exported = to_excel_bytes(result)
        self.assertGreater(len(exported), 1000)
        with zipfile.ZipFile(BytesIO(exported)) as archive:
            self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())
            sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("学校性质", sheet_xml)
        for removed_column in ["备注", "分差", "位次差", "推荐理由"]:
            self.assertNotIn(f">{removed_column}<", sheet_xml)

    def test_rank_data_score_lookup(self) -> None:
        rank_data = load_rank_data("rank.xlsx")
        self.assertEqual(set(rank_data["首选科目"]), {"物理", "历史"})
        self.assertEqual(rank_for_score(rank_data, "物理", 476), 123707)
        self.assertEqual(rank_for_score(rank_data, "历史", 476), 40690)
        self.assertEqual(rank_for_score(rank_data, "物理", 708), 21)
        self.assertEqual(rank_for_score(rank_data, "历史", 679), 12)
        self.assertIsNone(rank_for_score(rank_data, "物理", 149))

    def test_jpg_and_pdf_exports(self) -> None:
        result = recommend(
            pd.DataFrame([_sample_row("A", "测试学校", 590, 10500)]),
            RecommendRequest(user_rank=10000, per_level_limit=1),
        )
        jpg = to_jpg_bytes(result)
        pdf = to_pdf_bytes(result)

        self.assertTrue(jpg.startswith(b"\xff\xd8"))
        self.assertEqual(Image.open(BytesIO(jpg)).format, "JPEG")
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)

    def test_export_filename_uses_subject_and_score(self) -> None:
        self.assertEqual(
            build_export_stem("物理", None, 476, 30000),
            "志愿生成结果（首选物理476分）",
        )
        self.assertEqual(
            build_export_stem(None, "计算机类", None, 1200),
            "志愿生成结果（计算机类1200位）",
        )

    def test_real_batch_counts_match_workbook(self) -> None:
        counts = self.data.groupby(["原始工作表"]).size().to_dict()
        self.assertEqual(counts["本科普通批（首选物理）"], 3176)
        self.assertEqual(counts["本科普通批（首选历史）"], 1384)
        self.assertEqual(counts["高职高专普通批（首选物理）"], 1059)
        self.assertEqual(counts["高职高专普通批（首选历史）"], 908)
        self.assertEqual(counts["艺术（本科）"], 889)

    def test_common_batch_filter_dimensions(self) -> None:
        filters = CandidateFilters(
            batch="高职高专普通批",
            first_choice="历史",
            selected_subjects=[],
            major_keyword="口腔医学",
            school_natures=["公办"],
        )
        filtered = filter_candidates(self.data, filters)
        self.assertGreater(len(filtered), 0)
        self.assertTrue((filtered["首选科目"] == "历史").all())
        self.assertTrue((filtered["再选科目要求"] == "不限").all())
        self.assertTrue(filtered["专业信息"].str.contains("口腔医学", regex=False).all())
        self.assertTrue((filtered["学校性质"] == "公办").all())

    def test_skill_and_art_category_filters(self) -> None:
        skill = filter_candidates(
            self.data,
            CandidateFilters(batch="技能高考本科批", skill_category="计算机类"),
        )
        art = filter_candidates(
            self.data,
            CandidateFilters(batch="艺术本科", art_category="设计类"),
        )
        self.assertGreater(len(skill), 0)
        self.assertGreater(len(art), 0)
        self.assertTrue((skill["类别"] == "计算机类").all())
        self.assertTrue((art["类别"] == "设计类").all())

    def test_major_keyword_is_ignored_when_batch_has_no_major_column_data(self) -> None:
        without_keyword = filter_candidates(self.data, CandidateFilters(batch="体育本科"))
        with_keyword = filter_candidates(
            self.data,
            CandidateFilters(batch="体育本科", major_keyword="计算机"),
        )
        self.assertEqual(len(with_keyword), len(without_keyword))

    def test_multiple_major_keywords_match_any_term(self) -> None:
        data = pd.DataFrame(
            [
                {"批次": "本科普通批", "专业信息": "电子信息工程技术"},
                {"批次": "本科普通批", "专业信息": "人工智能技术应用"},
                {"批次": "本科普通批", "专业信息": "护理"},
            ]
        )

        for keywords in [
            "电子信息 人工智能",
            "电子信息，人工智能",
            "电子信息、人工智能",
            "电子信息/人工智能",
        ]:
            with self.subTest(keywords=keywords):
                filtered = filter_candidates(
                    data,
                    CandidateFilters(batch="本科普通批", major_keyword=keywords),
                )
                self.assertEqual(
                    list(filtered["专业信息"]),
                    ["电子信息工程技术", "人工智能技术应用"],
                )

    def test_major_keywords_ignore_case_and_character_width(self) -> None:
        data = pd.DataFrame(
            [
                {"批次": "本科普通批", "专业信息": "Artificial Intelligence"},
                {"批次": "本科普通批", "专业信息": "ＣＯＭＰＵＴＥＲ科学"},
                {"批次": "本科普通批", "专业信息": "护理"},
            ]
        )

        filtered = filter_candidates(
            data,
            CandidateFilters(
                batch="本科普通批",
                major_keyword="artificial；computer；ＡＲＴＩＦＩＣＩＡＬ",
            ),
        )

        self.assertEqual(
            list(filtered["专业信息"]),
            ["Artificial Intelligence", "ＣＯＭＰＵＴＥＲ科学"],
        )

        separator_only = filter_candidates(
            data,
            CandidateFilters(batch="本科普通批", major_keyword=" ，、； | / "),
        )
        self.assertEqual(len(separator_only), len(data))

    def test_remark_exclusion_uses_remark_and_school_nature(self) -> None:
        mini = pd.DataFrame(
            [
                {"批次": "本科普通批", "学校性质": "公办", "备注": "国家专项计划"},
                {"批次": "本科普通批", "学校性质": "中外合作", "备注": ""},
                {"批次": "本科普通批", "学校性质": "公办", "备注": ""},
            ]
        )
        filtered = filter_candidates(
            mini,
            CandidateFilters(
                batch="本科普通批",
                exclude_remark_keywords=["国家专项计划", "中外合作"],
            ),
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.iloc[0]["学校性质"], "公办")

    def test_score_only_recommendation(self) -> None:
        sample = pd.DataFrame(
            [
                _sample_row("A", "冲学校", 602, 1000),
                _sample_row("B", "稳学校", 590, 2000),
                _sample_row("C", "保学校", 570, 3000),
            ]
        )
        result = recommend(sample, RecommendRequest(user_score=600, user_rank=None, per_level_limit=3))
        self.assertEqual(list(result["推荐档位"]), ["冲", "稳", "保"])
        self.assertEqual(list(result["分差"]), [-2, 10, 30])
        self.assertTrue((result["位次差"] == "").all())

    def test_incomplete_rows_are_not_recommended(self) -> None:
        sample = pd.DataFrame(
            [
                _sample_row("A", "完整学校", 590, 10500, status="正常"),
                _sample_row("B", "缺位次学校", 580, pd.NA, status="数据不完整"),
            ]
        )
        result = recommend(sample, RecommendRequest(user_rank=10000, per_level_limit=10))
        self.assertEqual(list(result["院校专业组代号"]), ["A"])

    def test_rank_threshold_boundaries(self) -> None:
        sample = pd.DataFrame(
            [
                _sample_row("A", "负十边界", 590, 9000),
                _sample_row("B", "五边界", 590, 10500),
                _sample_row("C", "二十五边界", 590, 12500),
                _sample_row("D", "保边界外", 590, 12501),
            ]
        )
        result = recommend(sample, RecommendRequest(user_rank=10000, per_level_limit=10))
        levels = dict(zip(result["院校专业组代号"], result["推荐档位"]))
        self.assertEqual(levels["A"], "冲")
        self.assertEqual(levels["B"], "冲")
        self.assertEqual(levels["C"], "稳")
        self.assertEqual(levels["D"], "保")


def _sample_row(code: str, name: str, score: object, rank: object, status: str = "正常") -> dict[str, object]:
    return {
        "院校专业组代号": code,
        "院校专业组名称": name,
        "批次": "本科普通批",
        "首选科目或类别": "物理",
        "再选科目要求": "不限",
        "投档最低分": score,
        "位次值": rank,
        "专业成绩": pd.NA,
        "专业信息": "计算机",
        "学校性质": "公办",
        "备注": pd.NA,
        "数据状态": status,
    }


if __name__ == "__main__":
    unittest.main()
