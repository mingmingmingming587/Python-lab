from collections import Counter
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

from algorithms.astar import astar
from database.pdf_map import (PDF_PATH, ROWS, COLS, EXPECTED_COUNTS, load_pdf_map,
                              initial_pdf_state, open_pdf_project, road_components,
                              set_building_marker,
                              set_place_entrance, import_map_json, MAP_JSON_FORMAT)
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
    def test_classification_changes_use_one_consistent_color_layer(self):
        layout = pdf_fixture()
        state = initial_pdf_state(layout)
        original = pdf_map_figure(layout, state, show_background=True)
        state["classes"][2][2:4] = [1, 3]
        state["grid"][2][2:4] = [1, 1]
        fig = pdf_map_figure(layout, state, show_background=True,
                             selected=[2, 2], selection_bounds=(2, 2, 2, 3))
        self.assertEqual(len(fig.data), 1)
        base = fig.data[0]
        self.assertEqual(base.colorscale, original.data[0].colorscale)
        self.assertEqual(base.opacity, original.data[0].opacity)
        self.assertEqual(base.opacity, .55)
        self.assertEqual(base.colorscale[0][1], "rgba(0,0,0,0)")
        self.assertEqual(base.colorscale[1][1], "rgba(0,0,0,0)")
        self.assertEqual(tuple(base.z[2][2:5]), (1, 3, 2))
        self.assertEqual(layout["classes"][2][2:4], [2, 2])
        self.assertEqual(fig.layout.shapes[0].fillcolor, "rgba(0,0,0,0)")

    def test_review_highlights_and_focuses_without_changing_classification(self):
        layout = pdf_fixture()
        state = initial_pdf_state(layout)
        reviewed = [(2, 2), (2, 3)]
        fig = pdf_map_figure(layout, state, review_cells=reviewed)
        self.assertEqual(fig.data[1].name, "核查道路区域")
        self.assertEqual(tuple(fig.data[1].z[2][2:5]), (1, 1, None))
        self.assertEqual(list(fig.layout.xaxis.range), [0, 12])
        self.assertEqual(state["classes"], layout["classes"])

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
    def test_initial_grid_and_building_points_stay_inside_buildings(self):
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

    def test_initial_markers_and_entrances_only_seed_new_database(self):
        layout = pdf_fixture()
        with TemporaryDirectory() as tmp, patch("database.pdf_map.load_pdf_map", return_value=layout):
            db = Path(tmp) / "existing.db"
            _, service, revision, state = open_pdf_project(db_path=db)
            self.assertEqual(state["places"], {})
            layout["building_markers"] = [{"name": "示例建筑", "row": 5, "col": 5, "note": "入口未设置"}]
            layout["place_entrances"] = [{"place": "示例建筑", "name": "候选入口", "point": [2, 2],
                                          "enabled": True}]
            _, _, updated_revision, updated = open_pdf_project(db_path=db)
            self.assertEqual((updated_revision, updated), (revision, state))
            _, _, _, seeded = open_pdf_project(db_path=Path(tmp) / "new.db")
            self.assertEqual(seeded["places"]["示例建筑"], [5, 5])
            self.assertEqual(seeded["entrances"]["示例建筑"][0]["source"], "map_inferred")

    @unittest.skipUnless(PDF_PATH.exists(), "需要校园地图资料")
    def test_seed_entries_are_pending_and_cover_all_places(self):
        layout = load_pdf_map()
        state = initial_pdf_state(layout)
        entries = [entry for place in state["entrances"].values() for entry in place]
        self.assertEqual(set(state["entrances"]), set(state["places"]))
        self.assertEqual(len(entries), 89)
        self.assertEqual(sum(not entry["enabled"] for entry in entries), 0)
        for entry in entries:
            self.assertEqual(entry["source"], "map_inferred")
            self.assertEqual(state["grid"][entry["point"][0]][entry["point"][1]], 0)
        self.assertTrue(all(len(entries) == 1 for entries in state["entrances"].values()))

    def test_import_and_manual_edit_keep_entrance_sources_explicit(self):
        layout = pdf_fixture()
        state = initial_pdf_state(layout)
        state["places"] = {"图书馆": [5, 5]}
        set_place_entrance(state, "图书馆", "候选门", 2, 2, source="map_inferred")
        imported = import_map_json(json.dumps({"format": MAP_JSON_FORMAT, "state": state}), layout)
        self.assertEqual(imported["entrances"], state["entrances"])
        self.assertNotIn("map_version", imported)
        with self.assertRaisesRegex(ValueError, "网格来源"):
            import_map_json(json.dumps({"format": MAP_JSON_FORMAT, "state": state}),
                            {**layout, "source_hash": "different"})
        set_place_entrance(state, "图书馆", "手工门", 2, 3)
        self.assertEqual(len(state["entrances"]["图书馆"]), 1)
        self.assertNotIn("source", state["entrances"]["图书馆"][0])
        state["entrances"]["图书馆"][0]["source"] = "unknown"
        with self.assertRaisesRegex(ValueError, "入口"):
            import_map_json(json.dumps({"format": MAP_JSON_FORMAT, "state": state}), layout)

    def test_map_json_rejects_multiple_entrances(self):
        layout = pdf_fixture()
        state = initial_pdf_state(layout)
        state["places"] = {"图书馆": [5, 5]}
        state["entrances"] = {"图书馆": [
            {"name": "停用", "point": [2, 2], "enabled": False},
            {"name": "受阻", "point": [5, 5], "enabled": True},
            {"name": "保留", "point": [2, 3], "enabled": True},
        ]}
        with self.assertRaisesRegex(ValueError, "每个地点最多设置一个入口"):
            import_map_json(json.dumps({"format": MAP_JSON_FORMAT, "state": state}), layout)

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
            self.assertEqual(service.save(state), revision+1)
            self.assertFalse(astar(state["grid"], (2, 2), (2, 8)).found)
            self.assertEqual(service.history()[0]["snapshot"]["grid"][2][5], 0)
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
        self.assertEqual(list(trace.marker.symbol), ["square", "square-open", "diamond"])
        goal = pdf_map_figure(layout, state, goal=[2, 3])
        goal_trace = next(t for t in goal.data if t.name == "终点")
        self.assertEqual(goal_trace.colorscale[0][1], "#7c3aed")
        self.assertEqual(trace.marker.color[2], "#ea580c")
        self.assertEqual(state["grid"], before)
        del state["entrances"]
        self.assertNotIn("已录入入口", [trace.name for trace in pdf_map_figure(layout, state).data])


if __name__ == "__main__":
    unittest.main()
