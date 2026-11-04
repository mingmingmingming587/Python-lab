import unittest

from algorithms.place_navigation import access_points, plan_named_route
from database.pdf_map import initial_pdf_state, set_place_entrance, set_building_marker
from tests.test_pdf_map import pdf_fixture


class PlaceNavigationTests(unittest.TestCase):
    def setUp(self):
        self.state = initial_pdf_state(pdf_fixture())
        self.state["places"] = {"起点建筑":[0,5,5], "终点建筑":[0,2,8]}

    def test_temporary_access_is_explicit_and_does_not_open_building(self):
        original = [line[:] for line in self.state["grids"][0]]
        accesses = access_points(self.state,"起点建筑")
        self.assertTrue(accesses[0]["temporary"])
        self.assertEqual(accesses[0]["point"],[0,2,5])
        result,start,goal = plan_named_route(self.state,"起点建筑","终点建筑")
        self.assertTrue(result.found)
        self.assertEqual(result.path_length,3)
        self.assertNotIn((0,5,5),result.path)
        self.assertEqual(self.state["grids"][0],original)

    def test_multiple_entrances_choose_shortest_or_honor_selection(self):
        set_place_entrance(self.state,"起点建筑","西门",2,2)
        set_place_entrance(self.state,"起点建筑","东门",2,7)
        set_place_entrance(self.state,"终点建筑","入口",2,8)
        result,start,goal = plan_named_route(self.state,"起点建筑","终点建筑")
        self.assertEqual(result.path_length,1)
        self.assertEqual(start["name"],"东门")
        self.assertFalse(start["temporary"])
        self.assertEqual(plan_named_route(self.state,"起点建筑","终点建筑",start_gate="西门")[0].path_length,6)
        set_place_entrance(self.state,"起点建筑","东门",2,7,old_name="东门",enabled=False)
        self.assertEqual(plan_named_route(self.state,"起点建筑","终点建筑")[0].path_length,6)

    def test_disabled_or_blocked_entries_do_not_silently_use_temporary_access(self):
        set_place_entrance(self.state,"起点建筑","门",2,2,enabled=False)
        with self.assertRaises(ValueError):
            access_points(self.state,"起点建筑")
        with self.assertRaises(ValueError):
            set_place_entrance(self.state,"起点建筑","建筑内部不是门",5,5)

    def test_field_marker_does_not_make_the_field_walkable(self):
        set_building_marker(self.state,"运动场",10,10,kind="场地")
        self.assertEqual(self.state["places"]["运动场"],[0,10,10])
        self.assertEqual(self.state["place_kinds"]["运动场"],"场地")
        self.assertEqual(self.state["grids"][0][10][10],1)
        set_building_marker(self.state,"分类图涂黄的网球场",5,5,kind="场地")
        self.assertEqual(self.state["classes"][5][5],1)
        self.assertEqual(self.state["grids"][0][5][5],1)


if __name__=="__main__":
    unittest.main()
