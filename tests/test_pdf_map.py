from collections import Counter
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from algorithms.layered_astar import astar
from database.pdf_map import (PDF_PATH, ROWS, COLS, EXPECTED_COUNTS, load_pdf_map,
                              initial_pdf_state, open_pdf_project, road_components,
                              set_building_marker, merge_building_markers)
from visualization.pdf_map import pdf_map_figure


def pdf_fixture():
    classes = [[0] * COLS for _ in range(ROWS)]
    for col in range(2, 9):
        classes[2][col] = 2
    classes[5][5] = 1
    classes[6][6] = 3
    buffer = BytesIO()
    Image.new("RGB", (90, 180), "white").save(buffer, format="PNG")
    return {"classes": classes, "background": buffer.getvalue(),
            "source": "test PDF grid", "source_hash": "test-integrated-map"}


class PDFMapTests(unittest.TestCase):
    def test_building_marker_inside_building_does_not_open_grid(self):
        state = initial_pdf_state(pdf_fixture())
        set_building_marker(state, "示例建筑", 5, 5)
        self.assertEqual(state["places"]["示例建筑"], [5, 5])
        self.assertEqual(state["grid"][5][5], 1)
        with self.assertRaises(ValueError):
            astar(state["grid"], (5, 5), (2, 2))
        with self.assertRaises(ValueError):
            set_building_marker(state, "边界上的建筑", 6, 6)

    @unittest.skipUnless(PDF_PATH.exists(), "需要本机参考 PDF")
    def test_pdf_extraction_and_building_points_stay_inside_buildings(self):
        layout = load_pdf_map()
        self.assertEqual(Counter(v for row in layout["classes"] for v in row), EXPECTED_COUNTS)
        state = initial_pdf_state(layout)
        self.assertEqual((len(state["grid"]), len(state["grid"][0])), (180, 90))
        self.assertEqual(len(state["places"]), 89)
        self.assertIn("图书馆（东）", state["places"])
        self.assertIn("运动场（东）",state["places"])
        self.assertIn("运动场（西）",state["places"])
        for name in ("轮滑场","排球场","篮球场（东区）","篮球场（西区）",
                     "安国园","问地园","天水湖","听心园","学子林",
                     "网球场（东区）","网球场（西区）","网球场（东北）"):
            self.assertIn(name,state["places"])
        for name, (row, col) in state["places"].items():
            if state["place_kinds"][name]=="场地":
                self.assertIn(state["classes"][row][col],(0,1,2))
            else:
                self.assertEqual(state["classes"][row][col],1)
            self.assertEqual(state["grid"][row][col],0 if state["classes"][row][col]==2 else 1)
        self.assertNotIn("portals", state)
        self.assertEqual([len(c) for c in road_components(state["grid"])], [2223, 4])

    def test_marker_import_preserves_manual_coordinates_and_grid(self):
        layout = pdf_fixture()
        state = initial_pdf_state(layout)
        set_building_marker(state, "已有建筑", 2, 3)
        state["classes"][5][6] = 1
        state["classes"][5][7] = 3
        original_grid = [row[:] for row in state["grid"]]
        layout["building_markers_version"] = "markers-v1"
        layout["building_markers"] = [
            {"name": "已有建筑", "row": 5, "col": 5, "note": "入口未设置"},
            {"name": "新增建筑", "row": 5, "col": 6, "note": "入口未设置"},
            {"name": "用户修改过分类的建筑", "row": 5, "col": 7, "note": "入口未设置"},
        ]
        self.assertTrue(merge_building_markers(state, layout))
        self.assertEqual(state["places"]["已有建筑"], [2, 3])
        self.assertEqual(state["places"]["新增建筑"], [5, 6])
        self.assertNotIn("用户修改过分类的建筑", state["places"])
        self.assertEqual(state["grid"], original_grid)
        self.assertFalse(merge_building_markers(state, layout))

    def test_existing_database_receives_missing_markers_once(self):
        layout = pdf_fixture()
        with TemporaryDirectory() as tmp, patch("database.pdf_map.load_pdf_map", return_value=layout):
            db = Path(tmp) / "existing.db"
            _, service, revision, state = open_pdf_project(db_path=db)
            self.assertEqual(state["places"], {})
            layout["building_markers_version"] = "markers-v1"
            layout["building_markers"] = [{"name": "示例建筑", "row": 5, "col": 5, "note": "入口未设置"}]
            _, _, updated_revision, updated = open_pdf_project(db_path=db)
            self.assertEqual(updated_revision, revision+1)
            self.assertEqual(updated["places"]["示例建筑"], [5, 5])
            self.assertEqual(open_pdf_project(db_path=db)[2], updated_revision)

    def test_save_route_snapshot_and_source_mismatch(self):
        layout = pdf_fixture()
        with TemporaryDirectory() as tmp, patch("database.pdf_map.load_pdf_map", return_value=layout):
            db = Path(tmp) / "new-map.db"
            _, service, revision, state = open_pdf_project(db_path=db)
            result = astar(state["grid"], (2, 2), (2, 8))
            self.assertEqual(result.path_length, 6)
            service.save_route("start cell", "goal cell", state, result)
            state["classes"][2][5] = 3
            state["grid"][2][5] = 1
            service.save(state, revision)
            self.assertFalse(astar(state["grid"], (2, 2), (2, 8)).found)
            self.assertEqual(service.history()[0]["snapshot"]["grid"][2][5], 0)
            with self.assertRaises(ValueError):
                service.save(state, revision)
            with patch("database.pdf_map.load_pdf_map", return_value={**layout, "source_hash": "different"}):
                with self.assertRaises(ValueError):
                    open_pdf_project(db_path=db)

    def test_map_displays_source_classes_with_matching_axes(self):
        layout = pdf_fixture()
        state = initial_pdf_state(layout)
        fig = pdf_map_figure(layout, state, selected=(2, 5))
        self.assertEqual(fig.data[0].z[5][5], 1)
        self.assertEqual(fig.data[0].z[6][6], 3)
        self.assertEqual(list(fig.layout.xaxis.range), [0, 90])
        self.assertEqual(list(fig.layout.yaxis.range), [180, 0])
        self.assertTrue(all(t.type == "heatmap" for t in fig.data))

    def test_clean_map_focus_and_search_layer_preserve_map_data(self):
        layout=pdf_fixture()
        state=initial_pdf_state(layout)
        original=[line[:] for line in state["grid"]]
        result=astar(state["grid"],(2, 2),(2, 8))
        clean=pdf_map_figure(layout,state,start=(2, 2),goal=(2, 8),result=result,focus=True)
        names=[t.name for t in clean.data]
        self.assertIn("A* 路径",names)
        self.assertNotIn("已扩展节点",names)
        self.assertFalse(clean.layout.xaxis.visible)
        self.assertLess(clean.layout.xaxis.range[1]-clean.layout.xaxis.range[0],COLS)
        self.assertTrue(clean.layout.yaxis.range[1]<=2<clean.layout.yaxis.range[0])
        detailed=pdf_map_figure(layout,state,result=result,show_grid=True,
                                show_visited=True,show_background=True)
        self.assertIn("已扩展节点",[t.name for t in detailed.data])
        self.assertTrue(detailed.layout.xaxis.visible)
        self.assertEqual(len(detailed.layout.images),1)
        self.assertEqual(state["grid"],original)

    def test_named_map_retains_every_place_and_source_text_layer(self):
        state=initial_pdf_state(pdf_fixture())
        state["places"]={"图书馆":[5, 5],"运动场":[5, 6],"教学楼":[6, 5]}
        original=[line[:] for line in state["grid"]]
        figure=pdf_map_figure(pdf_fixture(),state,show_background=True,show_building_labels=True)
        trace=next(t for t in figure.data if t.name=="地点位置标记")
        self.assertEqual(set(trace.text),set(state["places"]))
        self.assertEqual(trace.mode,"markers+text")
        self.assertGreaterEqual(trace.textfont.size,12)
        self.assertGreater(len(set(trace.textposition)),1)
        self.assertEqual(len(figure.layout.images),1)
        self.assertEqual(state["grid"],original)

    def test_multiple_entrances_show_status_without_changing_the_grid(self):
        layout = pdf_fixture()
        state = initial_pdf_state(layout)
        state["places"] = {"图书馆": [5, 5]}
        state["entrances"] = {"图书馆": [
            {"name": "东门", "point": [2, 2], "enabled": True},
            {"name": "西门", "point": [2, 3], "enabled": False},
            {"name": "北门", "point": [5, 5], "enabled": True},
        ]}
        before = [row[:] for row in state["grid"]]
        figure = pdf_map_figure(layout, state)
        trace = next(trace for trace in figure.data if trace.name == "已录入入口")
        self.assertEqual([item[4] for item in trace.customdata], ["东门", "西门", "北门"])
        self.assertEqual([item[5] for item in trace.customdata], ["已启用", "已停用", "道路不可通行"])
        self.assertEqual(list(trace.marker.symbol), ["square", "square-open", "square"])
        self.assertEqual(state["grid"], before)
        del state["entrances"]
        self.assertNotIn("已录入入口", [trace.name for trace in pdf_map_figure(layout, state).data])


if __name__ == "__main__":
    unittest.main()
