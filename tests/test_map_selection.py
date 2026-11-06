"""原生 Plotly 选择事件到业务坐标的边界测试。"""

from copy import deepcopy
import unittest
from unittest.mock import patch

from database.pdf_map import initial_pdf_state, set_grid_region
from tests.test_pdf_map import pdf_fixture
from visualization.workspace import _map_selected


class Session(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class MapSelectionTests(unittest.TestCase):
    def select(self, mode, tool, selection):
        session = Session(workspace_mode=mode,map_tool=tool,
                          workspace_map={"selection":selection})
        with patch("visualization.workspace.st.session_state",session):
            _map_selected()
        return session

    def test_place_click_sets_named_endpoint(self):
        ss = self.select("导航","设终点",{"points":[{"customdata":[5,5,"建筑","示例建筑"]}]})
        self.assertEqual(ss.nav_goal,"示例建筑")
        self.assertTrue(ss.map_needs_app)

    def test_grid_click_fills_marker_or_entrance_without_opening_grid(self):
        for tool,prefix in (("标记位置","_marker"),("入口位置","_entry")):
            ss = self.select("地点",tool,{"points":[{"customdata":[5,5,"网格",""]}]})
            self.assertEqual((ss[prefix+"_row"],ss[prefix+"_col"]),(5,5))
        self.assertEqual(initial_pdf_state(pdf_fixture())["grid"][5][5],1)

    def test_box_selection_uses_cell_centers_and_clips_bounds(self):
        ss = self.select("维护","框选",{"box":[{"x":[6.9,3.1],"y":[2.9,1.1]}]})
        self.assertEqual(ss.edit_bounds,(1,3,2,6))
        clipped = self.select("维护","框选",{"box":[{"x":[-5,100],"y":[-5,200]}]})
        self.assertEqual(clipped.edit_bounds,(0,0,179,89))

    def test_invalid_region_rejected_before_any_cell_is_changed(self):
        state = initial_pdf_state(pdf_fixture())
        before = deepcopy(state)
        for bounds,kind in [((2,4,2,90),2),((5,4,2,6),2),((2,4,2,6),9)]:
            with self.assertRaises(ValueError):
                set_grid_region(state,bounds,kind)
        self.assertEqual(state,before)


if __name__ == "__main__":
    unittest.main()
