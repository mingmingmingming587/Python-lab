import json
import tempfile
import unittest
from pathlib import Path

from campus.database import MapService


ROOT = Path(__file__).resolve().parents[1]


class MapServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "test.db"
        self.service = MapService(
            self.db_path,
            ROOT / "data" / "base_map.json",
            ROOT / "data" / "places.json",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_seed_data(self):
        campus_map = self.service.get_map()
        self.assertEqual((campus_map.rows, campus_map.cols), (180, 90))
        self.assertEqual(campus_map.counts()["walkable"], 2211)
        self.assertEqual(len(self.service.list_places()), 95)
        with self.service.connect() as connection:
            cell_count = connection.execute(
                "SELECT COUNT(*) AS count FROM cells WHERE map_id = 1"
            ).fetchone()["count"]
        self.assertEqual(cell_count, 180 * 90)

    def test_save_and_reset_map(self):
        campus_map = self.service.get_map()
        campus_map.set_cell(120, 25, 1)
        self.service.update_cells([[120, 25, 1]])
        self.service.save_map(campus_map)
        self.assertEqual(self.service.get_map().grid[120][25], 1)
        with self.service.connect() as connection:
            blocked = connection.execute(
                "SELECT blocked FROM cells WHERE map_id = 1 AND row = 120 AND col = 25"
            ).fetchone()["blocked"]
        self.assertEqual(blocked, 1)
        self.service.reset_map()
        self.assertEqual(self.service.get_map().grid[120][25], 0)

    def test_place_crud(self):
        place = self.service.add_place(
            "测试地点", "building", 120, 25, access_row=121, access_col=25, aliases="测试"
        )
        self.assertEqual(place.name, "测试地点")
        self.assertEqual(self.service.get_place(place.id).aliases, "测试")
        updated = self.service.update_place(
            place.id, "测试地点2", "park", 120, 25, 121, 25, "别名"
        )
        self.assertEqual(updated.name, "测试地点2")
        self.service.delete_place(place.id)
        self.assertIsNone(self.service.get_place(place.id))

    def test_duplicate_place_name(self):
        self.service.add_place("重复点", "building", 120, 25, 121, 25)
        with self.assertRaises(ValueError):
            self.service.add_place("重复点", "building", 121, 25, 121, 25)

    def test_query_history(self):
        campus_map = self.service.get_map()
        start = (104, 67)
        goal = (170, 80)
        from campus.astar import AStarFinder

        result = AStarFinder(campus_map).search(start, goal)
        query_id = self.service.save_query(
            campus_map, start, goal, "图书馆（东）", "明德楼（东）", result
        )
        self.assertTrue(result.found)
        self.assertGreater(result.cost, 0)
        summary = self.service.list_queries()[0]
        self.assertEqual(summary["id"], query_id)
        self.assertTrue(summary["found"])
        detail = self.service.get_query(query_id)
        self.assertEqual(detail["cost"], result.cost)
        self.assertEqual(detail["path"][0], list(start))

    def test_export_import_round_trip(self):
        bundle = self.service.export_bundle()
        self.assertEqual(bundle["rows"], 180)
        self.assertEqual(len(bundle["places"]), 95)
        bundle["places"] = bundle["places"][:3]
        campus_map = self.service.import_bundle(bundle)
        self.assertEqual(campus_map.rows, 180)
        self.assertEqual(len(self.service.list_places()), 3)


if __name__ == "__main__":
    unittest.main()
