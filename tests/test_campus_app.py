import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from database.campus_project import CampusMapService
from database.pdf_map import initial_pdf_state
from tests.test_pdf_map import pdf_fixture


class CampusAppTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        self.layout = pdf_fixture()
        state = initial_pdf_state(self.layout)
        state["places"] = {"示例起点": [0,5,5], "示例终点": [0,2,8]}
        state["entrances"] = {
            "示例起点": [{"name":"西门","point":[0,2,2],"enabled":True}],
            "示例终点": [{"name":"入口","point":[0,2,8],"enabled":True}],
        }
        self.service = CampusMapService(state, Path(temporary) / "pdf.db")
        self.enterContext(patch("database.pdf_map.open_pdf_project", side_effect=lambda: (self.layout, self.service, *self.service.load())))

    def page(self, filename):
        root = Path(__file__).resolve().parents[1]
        return AppTest.from_file(str(root / "pages" / filename), default_timeout=40).run()

    def test_name_navigation_edit_and_history(self):
        nav = self.page("navigation.py")
        self.assertFalse(nav.exception)
        self.assertTrue(any("搜索起点" == t.label for t in nav.text_input))
        next(b for b in nav.button if b.label == "开始 A* 搜索").click().run()
        self.assertFalse(nav.exception)
        history = self.service.history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["path_length"], 6)
        self.assertEqual(history[0]["start_name"], "示例起点")
        self.assertFalse(history[0]["snapshot"]["route_query"]["start_access"]["temporary"])
        nav.slider[0].set_value(0).run()
        next(c for c in nav.checkbox if c.label=="显示细网格与坐标").check().run()
        next(r for r in nav.radio if r.label=="视图范围").set_value("当前路线或地点").run()
        self.assertFalse(nav.exception)
        self.assertEqual(len(self.service.history()),1)
        record_page = self.page("route_history.py")
        self.assertFalse(record_page.exception)
        self.assertEqual(len(record_page.get("plotly_chart")), 1)

        edit = self.page("map_management.py")
        next(n for n in edit.number_input if n.label == "行").set_value(2)
        next(n for n in edit.number_input if n.label == "列").set_value(5)
        next(s for s in edit.selectbox if s.label == "调整分类").select(3)
        next(b for b in edit.button if b.label == "保存网格修改").click().run()
        self.assertFalse(edit.exception)
        self.assertEqual(self.service.load()[1]["grids"][0][2][5], 1)
        self.assertEqual(self.service.history()[0]["snapshot"]["grids"][0][2][5], 0)
        next(b for b in nav.button if b.label == "开始 A* 搜索").click().run()
        self.assertFalse(nav.exception)
        self.assertFalse(self.service.history()[0]["found"])

    def test_edit_conflict_stops_and_audit_uses_new_grid(self):
        edit = self.page("map_management.py")
        with patch.object(CampusMapService, "save", side_effect=ValueError("地图已被其他会话修改")):
            next(b for b in edit.button if b.label == "保存网格修改").click().run()
        self.assertTrue(any("地图已被其他会话修改" in e.value for e in edit.error))
        self.assertEqual(self.service.load()[0], 0)
        audit = self.page("road_review.py")
        self.assertFalse(audit.exception)
        self.assertEqual(len(audit.get("plotly_chart")), 1)
        self.assertEqual(len(self.service.load()[1]["places"]), 2)

    def test_unavailable_named_entrance_does_not_save_invalid_route(self):
        revision, state = self.service.load()
        state["grids"][0][2][2] = 1
        self.service.save(state, revision)
        nav = self.page("navigation.py")
        self.assertTrue(any("没有当前可用的已指定入口" in e.value for e in nav.error))
        self.assertTrue(next(b for b in nav.button if b.label == "开始 A* 搜索").disabled)
        self.assertEqual(self.service.history(), [])

    def test_manual_building_marker_can_be_inside_building(self):
        edit = self.page("map_management.py")
        next(t for t in edit.text_input if t.label == "地点名称").set_value("示例建筑")
        next(n for n in edit.number_input if n.label == "地点标记行").set_value(5)
        next(n for n in edit.number_input if n.label == "地点标记列").set_value(5)
        next(b for b in edit.button if b.label == "保存地点标记").click().run()
        self.assertFalse(edit.exception)
        state = self.service.load()[1]
        self.assertEqual(state["places"]["示例建筑"], [0, 5, 5])
        self.assertEqual(state["grids"][0][5][5], 1)
        refreshed = self.page("map_management.py")
        self.assertFalse(refreshed.exception)

    def test_existing_building_search_loads_its_coordinates(self):
        from database.pdf_map import set_building_marker
        revision, state = self.service.load()
        set_building_marker(state, "示例图书馆", 5, 5)
        self.service.save(state, revision)
        edit = self.page("map_management.py")
        next(t for t in edit.text_input if t.label == "搜索已有地点").set_value("图书").run()
        selected = next(s for s in edit.selectbox if s.label == "选择地点标记")
        self.assertEqual(selected.value, "示例图书馆")
        self.assertEqual(next(n for n in edit.number_input if n.label == "地点标记行").value, 5)
        self.assertEqual(next(n for n in edit.number_input if n.label == "地点标记列").value, 5)

    def test_named_search_keeps_map_visible_when_no_match(self):
        nav = self.page("navigation.py")
        next(t for t in nav.text_input if t.label == "搜索起点").set_value("不存在的名字").run()
        self.assertFalse(nav.exception)
        self.assertEqual(len(nav.get("plotly_chart")),1)
        self.assertTrue(next(b for b in nav.button if b.label=="开始 A* 搜索").disabled)


if __name__ == "__main__":
    unittest.main()
