from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import app as streamlit_app


class AppTests(unittest.TestCase):
    def test_data_cache_includes_workbook_mtime(self) -> None:
        streamlit_app.load_data.clear()
        with patch.object(
            streamlit_app,
            "load_workbook_data",
            return_value=pd.DataFrame([{"批次": "测试批次"}]),
        ) as loader:
            streamlit_app.load_data("table.xlsx", 1)
            streamlit_app.load_data("table.xlsx", 1)
            streamlit_app.load_data("table.xlsx", 2)

        self.assertEqual(loader.call_count, 2)
        streamlit_app.load_data.clear()

    def test_location_filters_disable_without_location_data(self) -> None:
        app = AppTest.from_file("app.py").run(timeout=30)
        batch = next(item for item in app.sidebar.selectbox if item.label == "报考批次")
        batch.set_value("技能高考本科批")
        app.run(timeout=30)

        province_filter = next(
            item for item in app.sidebar.multiselect if item.label == "学校所在省份"
        )
        city_filter = next(
            item for item in app.sidebar.multiselect if item.label == "学校所在城市"
        )
        self.assertTrue(province_filter.disabled)
        self.assertTrue(city_filter.disabled)
        self.assertEqual(province_filter.options, [])
        self.assertEqual(city_filter.options, [])

    def test_rank_help_and_export_only_result_actions(self) -> None:
        app = AppTest.from_file("app.py").run(timeout=30)
        self.assertFalse(app.exception)

        threshold_expander = next(
            item for item in app.sidebar.expander if item.label == "位次推荐阈值"
        )
        threshold_children = list(threshold_expander.children.values())
        self.assertEqual(threshold_children[-1].type, "popover")
        self.assertEqual(len(threshold_expander.number_input), 5)

        popover = app.get("popover")[0].proto.popover
        self.assertEqual(popover.label, "查看位次阈值说明")
        self.assertIn("位次差比例", app.markdown[0].value)
        self.assertIn("0.05", app.markdown[0].value)

        display_expander = next(
            item for item in app.sidebar.expander if item.label == "显示设置"
        )
        self.assertFalse(display_expander.proto.expanded)
        display_selector = next(
            item
            for item in display_expander.multiselect
            if item.label == "结果显示列"
        )
        self.assertEqual(
            display_selector.value,
            [
                "推荐档位",
                "院校专业组代号",
                "院校专业组名称",
                "首选科目或类别",
                "再选科目要求",
                "位次值",
                "专业信息",
                "学校性质",
            ],
        )

        province_filter = next(
            item for item in app.sidebar.multiselect if item.label == "学校所在省份"
        )
        self.assertIn("湖北省", province_filter.options)
        self.assertIn("北京市", province_filter.options)

        city_filter = next(
            item for item in app.sidebar.multiselect if item.label == "学校所在城市"
        )
        self.assertIn("武汉市", city_filter.options)
        self.assertIn("北京市", city_filter.options)

        city_filter.set_value(["北京市"])
        app.run(timeout=30)
        province_filter = next(
            item for item in app.sidebar.multiselect if item.label == "学校所在省份"
        )
        province_filter.set_value(["湖北省"])
        app.run(timeout=30)
        self.assertFalse(app.exception)
        city_filter = next(
            item for item in app.sidebar.multiselect if item.label == "学校所在城市"
        )
        self.assertEqual(city_filter.value, [])
        self.assertIn("武汉市", city_filter.options)
        self.assertNotIn("北京市", city_filter.options)

        major_input = next(
            item for item in app.sidebar.text_input if item.label == "专业关键词（可选）"
        )
        self.assertIn("匹配任意一个", major_input.proto.placeholder)
        self.assertIn("英文不区分大小写", major_input.proto.help)

        score_input = next(item for item in app.sidebar.text_input if item.label == "用户总分")
        score_input.set_value("476")
        app.run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.sidebar.metric[0].label, "自动换算位次")
        self.assertEqual(app.sidebar.metric[0].value, "40,690")

        displayed_columns = [
            column
            for column in app.dataframe[0].value.columns
            if column != "_志愿标识"
        ]
        self.assertEqual(
            displayed_columns,
            [
                "删除",
                "推荐档位",
                "院校专业组",
                "院校专业组名称",
                "首选科目",
                "再选科目",
                "位次值",
                "专业信息",
                "学校性质",
            ],
        )

        display_expander = next(
            item for item in app.sidebar.expander if item.label == "显示设置"
        )
        display_selector = next(
            item
            for item in display_expander.multiselect
            if item.label == "结果显示列"
        )
        display_selector.set_value(["推荐档位", "投档最低分", "备注"])
        app.run(timeout=30)
        self.assertFalse(app.exception)
        displayed_columns = [
            column
            for column in app.dataframe[0].value.columns
            if column != "_志愿标识"
        ]
        self.assertEqual(displayed_columns, ["删除", "推荐档位", "投档最低分", "备注"])

        display_expander = next(
            item for item in app.sidebar.expander if item.label == "显示设置"
        )
        display_selector = next(
            item
            for item in display_expander.multiselect
            if item.label == "结果显示列"
        )
        display_selector.set_value([])
        app.run(timeout=30)
        self.assertFalse(app.exception)
        displayed_columns = [
            column
            for column in app.dataframe[0].value.columns
            if column != "_志愿标识"
        ]
        self.assertEqual(displayed_columns, ["删除"])

        self.assertFalse(app.get("html"))
        self.assertEqual([item.label for item in app.button], ["删除选中志愿"])
        self.assertEqual(
            [item.label for item in app.get("download_button")],
            ["导出 Excel"],
        )

        input_mode = next(
            item for item in app.sidebar.segmented_control if item.label == "成绩录入方式"
        )
        input_mode.set_value("位次")
        app.run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(
            [item.label for item in app.sidebar.text_input],
            ["用户位次值", "专业关键词（可选）"],
        )


if __name__ == "__main__":
    unittest.main()
