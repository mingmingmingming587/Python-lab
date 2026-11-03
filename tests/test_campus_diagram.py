import unittest

from visualization.campus_diagram import build_campus_diagram
from visualization.campus_navigation import navigation_figure
from algorithms.path_result import PathResult
from database.campus_project import initial_campus
from tests.test_campus_project import layout_fixture


class CampusDiagramTests(unittest.TestCase):
    def test_routes_and_statuses_are_grid_cells(self):
        layout = layout_fixture()
        state = initial_campus(layout)
        row, col = next((r, c) for r, line in enumerate(state["grids"][0])
                        for c, cell in enumerate(line) if cell == 0)
        result = PathResult(True, [(0, row, col)], [(0, row, col)], 1, 0.0, 0)
        fig = navigation_figure(layout, state, result=result)
        traces = {trace.name: trace for trace in fig.data}
        self.assertEqual(traces["校内路线"].type, "heatmap")
        self.assertEqual(traces["校内路线"].z[row][col], 1)
        self.assertIn("校内 · 可通行", traces)
        self.assertTrue(all("lines" not in (trace.mode or "") for trace in fig.data if trace.type == "scatter"))

    def test_labels_follow_reference_positions_and_focus(self):
        places = [{"name": "示例入口", "x": 120, "y": 230},
                  {"name": "示例图书馆", "x": 340, "y": 460}]
        full = build_campus_diagram(places, footprints={"blue": [[118, 228, 4]], "gray": []})
        self.assertEqual(list(full.data[0].x), [120])
        self.assertEqual(list(full.data[1].y), [460])
        self.assertEqual(list(full.data[1].text), ["示例图书馆"])
        self.assertTrue(all(shape.layer == "below" for shape in full.layout.shapes))
        self.assertEqual(full.layout.shapes[0].type, "path")
        self.assertTrue(all("lines" not in (trace.mode or "") for trace in full.data))
        without_labels = build_campus_diagram(places, show_labels=False)
        self.assertFalse(any(annotation.text == "示例入口" for annotation in without_labels.layout.annotations))
        focused = build_campus_diagram(places, places[1])
        self.assertLess(focused.layout.xaxis.range[1] - focused.layout.xaxis.range[0],
                        full.layout.xaxis.range[1] - full.layout.xaxis.range[0])


if __name__ == "__main__":
    unittest.main()
