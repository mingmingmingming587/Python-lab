import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from database.campus_project import CampusMapService, campus_history, load_campus
from tests.test_campus_project import layout_fixture
from visualization.user_markings import blocked_grid_cells


def source_for(layout, page="7_校园地图导航.py"):
    source = (Path("pages") / page).read_text(encoding="utf-8")
    original = 'layout_path = Path(__file__).resolve().parents[1] / "reference" / "campus-layout.json"'
    if original not in source:
        raise AssertionError("校园导航页面的布局路径已改变，请更新测试")
    return source.replace(original, f"layout_path = Path({str(layout)!r})")


class CampusAppTests(unittest.TestCase):
    def test_cannot_block_a_saved_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db, layout = tmp_path / "campus.db", tmp_path / "layout.json"
            layout.write_text(json.dumps(layout_fixture(), ensure_ascii=False), encoding="utf-8")
            with patch("database.campus_project.CampusMapService", side_effect=lambda data: CampusMapService(data, db)):
                app = AppTest.from_string(source_for(layout, "8_地图与地点维护.py"), default_timeout=40).run()
                revision, state = load_campus(db)
                layer, row, col = next(iter(state["places"].values()))
                next(s for s in app.selectbox if s.label == "地图层").select(layer)
                next(n for n in app.number_input if n.label == "行").set_value(row)
                next(n for n in app.number_input if n.label == "列").set_value(col)
                next(b for b in app.button if b.label == "保存网格修改").click().run()
                self.assertTrue(any("该格已有地点" in e.value for e in app.error))
                self.assertEqual(load_campus(db)[0], revision)

    def test_save_conflict_stops_before_searching_with_stale_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db, layout = tmp_path / "campus.db", tmp_path / "layout.json"
            layout.write_text(json.dumps(layout_fixture(), ensure_ascii=False), encoding="utf-8")
            with patch("database.campus_project.CampusMapService", side_effect=lambda data: CampusMapService(data, db)):
                app = AppTest.from_string(source_for(layout, "8_地图与地点维护.py"), default_timeout=40).run()
                self.assertFalse(app.exception)
                with patch.object(CampusMapService, "save", side_effect=ValueError("地图已被其他会话修改")):
                    next(b for b in app.button if b.label == "保存网格修改").click().run()
                self.assertFalse(app.exception)
                self.assertTrue(any("地图已被其他会话修改" in item.value for item in app.error))
                self.assertFalse(any(b.label == "开始 A* 搜索" for b in app.button))
                self.assertEqual(load_campus(db)[0], 0)

    def test_search_edit_recompute_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            db = tmp_path / "campus.db"
            layout = tmp_path / "layout.json"
            layout.write_text(json.dumps(layout_fixture(), ensure_ascii=False), encoding="utf-8")
            with patch("database.campus_project.CampusMapService", side_effect=lambda data: CampusMapService(data, db)):
                app = AppTest.from_string(source_for(layout), default_timeout=40).run()
                self.assertFalse(app.exception)
                next(t for t in app.text_input if t.label == "搜索起点").set_value("不存在的地点").run()
                self.assertTrue(any("没有找到匹配的起点" in i.value for i in app.info))
                self.assertEqual(len(app.get("plotly_chart")), 1)
                next(t for t in app.text_input if t.label == "搜索起点").set_value("北区").run()
                next(t for t in app.text_input if t.label == "搜索终点").set_value("南区").run()
                next(s for s in app.selectbox if s.label == "起点").select("北区路线").run()
                next(s for s in app.selectbox if s.label == "终点").select("南区路线").run()
                next(b for b in app.button if b.label == "开始 A* 搜索").click().run()
                self.assertFalse(app.exception)
                history = campus_history(db)
                self.assertEqual(len(history), 1)
                self.assertTrue(history[0]["found"])
                self.assertIn(2, {p[0] for p in history[0]["path"]})
                app.slider[0].set_value(0).run()
                self.assertFalse(app.exception)
                history_app = AppTest.from_string(source_for(layout, "9_路线记录.py"), default_timeout=40).run()
                next(b for b in history_app.button if b.label == "显示这条历史路线").click().run()
                self.assertEqual(len(history_app.get("plotly_chart")), 1)

                path = history[0]["path"]
                point = next(p for p in path[1:-1] if p[0] == 0 and tuple(p[1:]) not in blocked_grid_cells())
                maintenance = AppTest.from_string(source_for(layout, "8_地图与地点维护.py"), default_timeout=40).run()
                next(n for n in maintenance.number_input if n.label == "行").set_value(point[1])
                next(n for n in maintenance.number_input if n.label == "列").set_value(point[2])
                next(b for b in maintenance.button if b.label == "保存网格修改").click().run()
                self.assertFalse(maintenance.exception)
                self.assertEqual(load_campus(db)[1]["grids"][0][point[1]][point[2]], 1)
                self.assertEqual(campus_history(db)[0]["path"], path)
                next(b for b in app.button if b.label == "开始 A* 搜索").click().run()
                self.assertFalse(app.exception)
                updated = campus_history(db)[0]
                self.assertEqual(updated["snapshot"]["grids"][0][point[1]][point[2]], 1)
                self.assertNotIn(point, updated["path"])


if __name__ == "__main__":
    unittest.main()
