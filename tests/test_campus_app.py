import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from database.campus_project import CampusMapService
from database.pdf_map import MAP_JSON_FORMAT, initial_pdf_state
from tests.test_pdf_map import pdf_fixture
from visualization.pdf_map import pdf_map_figure


class CampusAppTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        self.layout = pdf_fixture()
        state = initial_pdf_state(self.layout)
        state["places"] = {"示例起点": [5, 5], "示例终点": [2, 8]}
        state["entrances"] = {
            "示例起点": [{"name":"西门","point":[2, 2],"enabled":True}],
            "示例终点": [{"name":"入口","point":[2, 8],"enabled":True}],
        }
        self.service = CampusMapService(state, Path(temporary) / "pdf.db")
        self.enterContext(patch("visualization.workspace.open_pdf_project", side_effect=lambda: (self.layout, self.service, *self.service.load())))

    def page(self, filename):
        root = Path(__file__).resolve().parents[1]
        return AppTest.from_file(str(root / "pages" / filename), default_timeout=40).run()

    def test_unsaved_draft_is_marked_and_navigation_uses_saved_map(self):
        before = self.service.load()
        with patch("visualization.workspace.pdf_map_figure", wraps=pdf_map_figure) as render:
            edit = self.page("road_review.py")
            next(b for b in edit.button if b.label == "设为边界").click().run()
            self.assertTrue(any("有未保存修改" in item.value for item in edit.info))
            next(g for g in edit.get("button_group") if g.label == "操作台").set_value("导航").run()
            self.assertTrue(any("导航使用已保存地图" in item.value for item in edit.warning))
            self.assertEqual(render.call_args.args[1]["classes"][0][0], 0)
            next(g for g in edit.get("button_group") if g.label == "操作台").set_value("维护").run()
            self.assertEqual(render.call_args.args[1]["classes"][0][0], 3)
            self.assertEqual(edit.session_state["map_draft"]["state"]["classes"][0][0], 3)
        self.assertFalse(edit.exception)
        self.assertEqual(self.service.load(), before)

    def test_review_region_highlights_without_saving(self):
        _, state = self.service.load()
        state["classes"][10][10], state["grid"][10][10] = 2, 0
        self.service.save(state)
        before = self.service.load()
        with patch("visualization.workspace.pdf_map_figure", wraps=pdf_map_figure) as render:
            edit = self.page("road_review.py")
            self.assertIsNone(render.call_args.kwargs["review_cells"])
            region = next(s for s in edit.selectbox if s.label == "在地图上查看道路区域")
            region.select(1).run()
            self.assertEqual(render.call_args.kwargs["review_cells"], [(10, 10)])
        self.assertFalse(edit.exception)
        self.assertEqual(self.service.load(), before)
        self.assertNotIn("map_draft", edit.session_state)

    def test_name_navigation_edit_and_history(self):
        nav = self.page("navigation.py")
        self.assertFalse(nav.exception)
        self.assertTrue(any("起点" == t.label for t in nav.selectbox))
        next(b for b in nav.button if b.label == "开始 A* 搜索").click().run()
        self.assertFalse(nav.exception)
        history = self.service.history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["path_length"], 6)
        self.assertEqual(history[0]["start_name"], "示例起点")
        self.assertFalse(history[0]["snapshot"]["route_query"]["start_access"]["temporary"])
        nav.slider[0].set_value(0).run()
        next(c for c in nav.checkbox if c.label=="显示细网格与坐标").check().run()
        next(c for c in nav.checkbox if c.label=="聚焦当前路线或地点").check().run()
        self.assertFalse(nav.exception)
        self.assertEqual(len(self.service.history()),1)
        record_page = self.page("route_history.py")
        self.assertFalse(record_page.exception)
        self.assertEqual(len(record_page.get("plotly_chart")), 1)

        edit = self.page("road_review.py")
        next(n for n in edit.number_input if n.label == "行").set_value(2)
        next(n for n in edit.number_input if n.label == "列").set_value(5)
        next(b for b in edit.button if b.label == "设为边界").click().run()
        next(b for b in edit.button if b.label == "保存地图").click().run()
        self.assertFalse(edit.exception)
        self.assertEqual(self.service.load()[1]["grid"][2][5], 1)
        self.assertEqual(self.service.history()[0]["snapshot"]["grid"][2][5], 0)
        next(b for b in nav.button if b.label == "开始 A* 搜索").click().run()
        self.assertFalse(nav.exception)
        self.assertFalse(self.service.history()[0]["found"])

    def test_save_failure_retains_draft(self):
        edit = self.page("road_review.py")
        before = self.service.load()
        next(b for b in edit.button if b.label == "设为边界").click().run()
        edit.session_state["map_draft"]["state"]["grid"][0][0] = 0
        next(b for b in edit.button if b.label == "保存地图").click().run()
        self.assertTrue(any("分类网格与通行网格不一致" in e.value for e in edit.error))
        self.assertTrue(edit.session_state["map_draft"]["undo"])
        self.assertEqual(self.service.load(), before)
        audit = self.page("road_review.py")
        self.assertFalse(audit.exception)
        self.assertEqual(len(audit.get("plotly_chart")), 1)
        self.assertEqual(len(self.service.load()[1]["places"]), 2)

    def test_unavailable_named_entrance_does_not_save_invalid_route(self):
        _, state = self.service.load()
        state["classes"][2][2] = 3
        state["grid"][2][2] = 1
        self.service.save(state)
        nav = self.page("navigation.py")
        self.assertTrue(any("没有当前可用的已指定入口" in e.value for e in nav.error))
        self.assertTrue(next(b for b in nav.button if b.label == "开始 A* 搜索").disabled)
        self.assertEqual(self.service.history(), [])

    def test_inferred_entrance_keeps_pending_status_in_route_history(self):
        _, state = self.service.load()
        state["entrances"]["示例起点"][0]["source"] = "map_inferred"
        self.service.save(state)
        nav = self.page("navigation.py")
        self.assertTrue(any("图面推定" in warning.value for warning in nav.warning))
        next(b for b in nav.button if b.label == "开始 A* 搜索").click().run()
        self.assertFalse(nav.exception)
        query = self.service.history()[0]["snapshot"]["route_query"]
        self.assertTrue(query["start_access"]["temporary"])
        self.assertEqual(query["start_access"]["source"], "map_inferred")
        self.assertFalse(query["goal_access"]["temporary"])

    def test_manual_building_marker_can_be_inside_building(self):
        edit = self.page("map_management.py")
        next(t for t in edit.text_input if t.label == "地点名称").set_value("示例建筑")
        next(n for n in edit.number_input if n.label == "地点标记行").set_value(5)
        next(n for n in edit.number_input if n.label == "地点标记列").set_value(5)
        next(b for b in edit.button if b.label == "应用地点标记").click().run()
        self.assertNotIn("示例建筑", self.service.load()[1]["places"])
        next(b for b in edit.button if b.label == "保存地图").click().run()
        self.assertFalse(edit.exception)
        state = self.service.load()[1]
        self.assertEqual(state["places"]["示例建筑"], [5, 5])
        self.assertEqual(state["grid"][5][5], 1)
        refreshed = self.page("map_management.py")
        self.assertFalse(refreshed.exception)

    def test_existing_building_search_loads_its_coordinates(self):
        from database.pdf_map import set_building_marker
        _, state = self.service.load()
        set_building_marker(state, "示例图书馆", 5, 5)
        self.service.save(state)
        edit = self.page("map_management.py")
        next(s for s in edit.selectbox if s.label == "选择地点标记").select("示例图书馆").run()
        selected = next(s for s in edit.selectbox if s.label == "选择地点标记")
        self.assertEqual(selected.value, "示例图书馆")
        self.assertEqual(next(n for n in edit.number_input if n.label == "地点标记行").value, 5)
        self.assertEqual(next(n for n in edit.number_input if n.label == "地点标记列").value, 5)

    def test_named_selection_keeps_map_visible(self):
        nav = self.page("navigation.py")
        next(s for s in nav.selectbox if s.label == "起点").select("示例终点").run()
        self.assertFalse(nav.exception)
        self.assertEqual(len(nav.get("plotly_chart")),1)
        self.assertEqual(nav.session_state["nav_start"], "示例终点")

    def test_swap_and_workspace_switch_keep_navigation_and_view(self):
        nav = self.page("navigation.py")
        next(b for b in nav.button if b.label=="交换起点与终点").click().run()
        self.assertEqual(next(s for s in nav.selectbox if s.label=="起点").value,"示例终点")
        next(b for b in nav.button if b.label=="开始 A* 搜索").click().run()
        next(c for c in nav.checkbox if c.label=="显示细网格与坐标").check().run()
        group = next(g for g in nav.get("button_group") if g.label=="操作台")
        group.set_value("地点").run()
        self.assertFalse(nav.exception)
        self.assertEqual(len(nav.get("plotly_chart")),1)
        next(g for g in nav.get("button_group") if g.label=="操作台").set_value("导航").run()
        self.assertFalse(nav.exception)
        self.assertEqual(next(s for s in nav.selectbox if s.label=="起点").value,"示例终点")
        self.assertTrue(next(c for c in nav.checkbox if c.label=="显示细网格与坐标").value)
        self.assertEqual(len(self.service.history()),1)
        self.assertTrue(any("示例终点" in s.value for s in nav.success))

    def test_region_undo_redo_and_history_snapshot(self):
        nav = self.page("navigation.py")
        next(b for b in nav.button if b.label=="开始 A* 搜索").click().run()
        edit = self.page("road_review.py")
        edit.session_state["edit_bounds"] = (2,4,2,6)
        edit.session_state["_edit_row"] = 2
        edit.session_state["_edit_col"] = 4
        edit.run()
        initial = self.service.load()
        next(b for b in edit.button if b.label=="设为边界").click().run()
        self.assertFalse(edit.exception)
        draft = edit.session_state["map_draft"]
        self.assertEqual(draft["state"]["classes"][2][4:7],[3,3,3])
        self.assertEqual(draft["state"]["grid"][2][4:7],[1,1,1])
        self.assertEqual(self.service.history()[0]["snapshot"]["grid"][2][4:7],[0, 0, 0])
        next(b for b in edit.button if b.label=="设为建筑").click().run()
        next(b for b in edit.button if b.label=="后退").click().run()
        self.assertEqual(draft["state"]["classes"][2][4:7],[3,3,3])
        next(b for b in edit.button if b.label=="后退").click().run()
        self.assertFalse(edit.exception)
        self.assertEqual(draft["state"]["grid"][2][4:7],[0, 0, 0])
        self.assertTrue(next(b for b in edit.button if b.label=="后退").disabled)
        next(g for g in edit.get("button_group") if g.label=="操作台").set_value("地点").run()
        next(b for b in edit.button if b.label=="前进").click().run()
        self.assertEqual(draft["state"]["classes"][2][4:7],[3,3,3])
        next(b for b in edit.button if b.label=="前进").click().run()
        self.assertEqual(draft["state"]["classes"][2][4:7],[1,1,1])
        self.assertTrue(next(b for b in edit.button if b.label=="前进").disabled)

        next(b for b in edit.button if b.label=="后退").click().run()
        next(g for g in edit.get("button_group") if g.label=="操作台").set_value("维护").run()
        next(n for n in edit.number_input if n.label=="行").set_value(2)
        next(n for n in edit.number_input if n.label=="列").set_value(4)
        next(b for b in edit.button if b.label=="设为未标注").click().run()
        self.assertFalse(edit.exception)
        self.assertTrue(next(b for b in edit.button if b.label=="前进").disabled)
        self.assertEqual(self.service.load(), initial)
        next(b for b in edit.button if b.label=="保存地图").click().run()
        revision, saved = self.service.load()
        self.assertEqual(revision, initial[0]+1)
        self.assertEqual(saved["classes"][2][4:7],[0,0,0])
        self.assertTrue(next(b for b in edit.button if b.label=="后退").disabled)
        self.assertEqual(self.service.history()[0]["snapshot"]["grid"][2][4:7],[0,0,0])

    def test_last_saved_draft_replaces_the_current_map(self):
        edit = self.page("road_review.py")
        next(b for b in edit.button if b.label=="设为边界").click().run()
        draft = edit.session_state["map_draft"]["state"]
        _, state = self.service.load()
        state["classes"][1][1] = 2
        state["grid"][1][1] = 0
        other_revision = self.service.save(state)
        edit.run()
        next(b for b in edit.button if b.label=="保存地图").click().run()
        self.assertFalse(edit.exception)
        self.assertFalse(edit.error)
        self.assertEqual(self.service.load(), (other_revision+1, draft))
        self.assertNotIn("map_draft", edit.session_state)

    def test_import_and_restore_are_undoable_draft_edits(self):
        nav = self.page("navigation.py")
        next(b for b in nav.button if b.label == "开始 A* 搜索").click().run()
        history = self.service.history()
        before = self.service.load()
        edited = self.service.load()[1]
        edited["classes"][2][2] = 3
        # A blocked entrance stays recorded. The imported grid comes from classes.
        edit = self.page("road_review.py")
        edit.file_uploader[0].set_value(("broken.json", b"{}", "application/json")).run()
        next(b for b in edit.button if b.label == "导入 JSON 地图").click().run()
        self.assertTrue(edit.error)
        self.assertNotIn("map_draft", edit.session_state)

        content = json.dumps({"format": MAP_JSON_FORMAT, "state": edited}).encode("utf-8")
        edit.file_uploader[0].set_value(("campus-map.json", content, "application/json")).run()
        next(b for b in edit.button if b.label == "导入 JSON 地图").click().run()
        self.assertFalse(edit.error)
        draft = edit.session_state["map_draft"]
        self.assertEqual(draft["state"]["grid"][2][2], 1)
        self.assertEqual(draft["state"]["entrances"], edited["entrances"])
        next(b for b in edit.button if b.label == "后退").click().run()
        self.assertEqual(draft["state"], before[1])
        next(b for b in edit.button if b.label == "前进").click().run()
        self.assertEqual(draft["state"]["grid"][2][2], 1)

        next(b for b in edit.button if b.label == "恢复初始地图").click().run()
        self.assertEqual(draft["state"]["grid"][2][2], 1)
        next(b for b in edit.button if b.label == "取消").click().run()
        self.assertEqual(draft["state"]["grid"][2][2], 1)
        next(b for b in edit.button if b.label == "恢复初始地图").click().run()
        next(b for b in edit.button if b.label == "确认恢复").click().run()
        initial = initial_pdf_state(self.layout)
        self.assertEqual(draft["state"], initial)
        next(b for b in edit.button if b.label == "后退").click().run()
        self.assertEqual(draft["state"]["grid"][2][2], 1)
        next(b for b in edit.button if b.label == "前进").click().run()
        self.assertEqual(self.service.load(), before)
        next(b for b in edit.button if b.label == "保存地图").click().run()
        self.assertEqual(self.service.load(), (before[0]+1, initial))
        self.assertEqual(self.service.history(), history)

    def test_search_playback_does_not_repeat_query(self):
        nav = self.page("navigation.py")
        next(b for b in nav.button if b.label=="开始 A* 搜索").click().run()
        next(b for b in nav.button if b.label=="播放搜索过程").click().run()
        self.assertFalse(nav.exception)
        self.assertEqual(len(self.service.history()),1)
        self.assertTrue(nav.session_state["show_visited"])

    def test_default_map_text_and_scale_survive_mode_switch(self):
        nav = self.page("navigation.py")
        self.assertTrue(next(c for c in nav.checkbox if c.label=="显示 PDF 对照底图").value)
        self.assertTrue(next(c for c in nav.checkbox if c.label=="显示全部地点名称").value)
        self.assertEqual(next(r for r in nav.radio if r.label=="地图尺度").value,"清晰浏览")
        next(r for r in nav.radio if r.label=="地图尺度").set_value("全校总览").run()
        next(c for c in nav.checkbox if c.label=="显示 PDF 对照底图").uncheck().run()
        next(g for g in nav.get("button_group") if g.label=="操作台").set_value("地点").run()
        self.assertFalse(nav.exception)
        self.assertEqual(next(r for r in nav.radio if r.label=="地图尺度").value,"全校总览")
        self.assertFalse(next(c for c in nav.checkbox if c.label=="显示 PDF 对照底图").value)
        self.assertTrue(next(c for c in nav.checkbox if c.label=="显示全部地点名称").value)


if __name__ == "__main__":
    unittest.main()
