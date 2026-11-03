import tempfile
import unittest
from pathlib import Path

from algorithms.astar import astar_search
from database.survey import delete_survey, init_survey, list_survey, save_survey, verified_grid
from visualization.user_markings import blocked_grid_cells, image_point, add_markings
from visualization.campus_diagram import build_campus_diagram


class CampusSurveyTests(unittest.TestCase):
    def test_user_fences_override_roads_and_bridge_is_only_visual(self):
        blocked = blocked_grid_cells()
        self.assertTrue(blocked)
        row, col = next(iter(blocked))
        record = {"kind": "道路", "status": "已核实可通行", "row1": row, "col1": col, "row2": row, "col2": col}
        self.assertEqual(verified_grid([record])[row][col], 0)
        self.assertEqual(verified_grid([record], blocked)[row][col], 1)
        # 用户标注的绿线和天桥不会在没有已核实记录时打开任何网格。
        self.assertTrue(all(cell == 1 for line in verified_grid([], blocked) for cell in line))
        fig = add_markings(build_campus_diagram([]))
        self.assertTrue(any(trace.name == "天桥 · 行人跨街" for trace in fig.data))
        self.assertTrue(any("非全天开放" in trace.name for trace in fig.data))
        self.assertAlmostEqual(image_point((92, 156))[0], 86)

    def test_persistence_and_safe_astar_grid(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "survey.db"
            init_survey(db)
            save_survey("道路", "待核实", (2, 1), (2, 4), "待核实", "参考图", db_path=db)
            self.assertEqual(verified_grid(list_survey(db))[2][2], 1)
            save_survey("道路", "已确认", (2, 1), (2, 4), "已核实可通行", "现场", db_path=db)
            save_survey("入口", "图书馆入口", (2, 1), (2, 1), "已核实可通行", "现场", db_path=db)
            save_survey("入口", "食堂入口", (2, 4), (2, 4), "已核实可通行", "现场", db_path=db)
            records = list_survey(db)
            self.assertEqual(astar_search(verified_grid(records), (2, 1), (2, 4)).path_length, 3)
            save_survey("道路", "临时封闭", (2, 3), (2, 3), "已核实不可通行", "现场", db_path=db)
            self.assertFalse(astar_search(verified_grid(list_survey(db)), (2, 1), (2, 4)).found)
            delete_survey(list_survey(db)[-1]["id"], db)
            self.assertTrue(astar_search(verified_grid(list_survey(db)), (2, 1), (2, 4)).found)
            with self.assertRaises(ValueError):
                save_survey("道路", "斜线", (0, 0), (1, 1), "待核实", "参考图", db_path=db)
            with self.assertRaises(ValueError):
                save_survey("入口", "入口", (0, 0), (0, 0), "已核实可通行", "", db_path=db)
            self.assertEqual(len(list_survey(db)), 4)


if __name__ == "__main__":
    unittest.main()
