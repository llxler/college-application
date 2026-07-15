from __future__ import annotations

import unittest

from streamlit.testing.v1 import AppTest


class AppTests(unittest.TestCase):
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

        province_filter = next(
            item for item in app.sidebar.multiselect if item.label == "省份"
        )
        self.assertEqual(province_filter.options, ["湖北省", "其他"])

        score_input = next(item for item in app.sidebar.text_input if item.label == "用户总分")
        score_input.set_value("476")
        app.run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.sidebar.metric[0].label, "自动换算位次")
        self.assertEqual(app.sidebar.metric[0].value, "40,690")

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
