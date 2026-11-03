import unittest

from visualization.campus_diagram import build_campus_diagram


class CampusDiagramTests(unittest.TestCase):
    def test_labels_follow_reference_positions_and_focus(self):
        places = [{"name": "示例入口", "x": 120, "y": 230},
                  {"name": "示例图书馆", "x": 340, "y": 460}]
        full = build_campus_diagram(places, footprints={"blue": [[118, 228, 4]], "gray": []})
        self.assertEqual(list(full.data[0].x), [120])
        self.assertEqual(list(full.data[1].y), [460])
        self.assertEqual(list(full.data[1].text), ["示例图书馆"])
        self.assertTrue(all(shape.layer == "below" for shape in full.layout.shapes))
        self.assertEqual(full.layout.shapes[0].type, "path")
        self.assertTrue(any(trace.name == "博观路" for trace in full.data))
        road = next(trace for trace in full.data if trace.name == "学府中路")
        self.assertEqual(list(road.y), [429, 508])
        without_labels = build_campus_diagram(places, show_labels=False)
        self.assertFalse(any(annotation.text == "示例入口" for annotation in without_labels.layout.annotations))
        focused = build_campus_diagram(places, places[1])
        self.assertLess(focused.layout.xaxis.range[1] - focused.layout.xaxis.range[0],
                        full.layout.xaxis.range[1] - full.layout.xaxis.range[0])


if __name__ == "__main__":
    unittest.main()
