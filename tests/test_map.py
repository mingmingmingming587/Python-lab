import unittest

from campus.map import CampusMap


class CampusMapTests(unittest.TestCase):
    def test_zero_is_walkable_and_one_is_blocked(self):
        campus_map = CampusMap(2, 3, [[0, 1, 0], [1, 0, 1]])
        self.assertTrue(campus_map.is_walkable(0, 0))
        self.assertFalse(campus_map.is_walkable(0, 1))
        self.assertEqual(campus_map.neighbors(0, 0), [])
        self.assertEqual(campus_map.neighbors(1, 1), [])

    def test_set_cell_and_counts(self):
        campus_map = CampusMap(2, 2)
        self.assertEqual(campus_map.counts()["walkable"], 4)
        campus_map.set_cell(0, 0, 1)
        self.assertEqual(campus_map.counts(), {"walkable": 3, "blocked": 1, "total": 4})
        campus_map.apply_changes([[1, 1, 1]])
        self.assertEqual(campus_map.counts()["walkable"], 2)

    def test_snapshot_round_trip(self):
        campus_map = CampusMap(2, 2, [[0, 1], [1, 0]])
        snapshot = campus_map.snapshot()
        self.assertEqual(snapshot, "0110")
        other = CampusMap(2, 2)
        other.load_snapshot(snapshot)
        self.assertEqual(other.grid, [[0, 1], [1, 0]])

    def test_nearest_walkable(self):
        campus_map = CampusMap(3, 3, [[1, 1, 1], [1, 1, 1], [0, 1, 1]])
        self.assertEqual(campus_map.nearest_walkable(0, 0, 5), (2, 0, 2))
        self.assertIsNone(campus_map.nearest_walkable(0, 0, 1))

    def test_components(self):
        campus_map = CampusMap(3, 4, [[0, 0, 1, 0], [1, 0, 0, 1], [1, 1, 0, 1]])
        self.assertEqual(campus_map.components(), [5, 1])

    def test_validation(self):
        with self.assertRaises(ValueError):
            CampusMap(2, 2, [[0, 0]])
        with self.assertRaises(ValueError):
            CampusMap(2, 2, [[0, 0], [0, 2, 0]])


if __name__ == "__main__":
    unittest.main()
