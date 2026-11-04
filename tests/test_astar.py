import unittest

from campus.astar import AStarFinder
from campus.map import CampusMap


class AStarTests(unittest.TestCase):
    def test_open_grid_shortest_path(self):
        campus_map = CampusMap(5, 5)
        result = AStarFinder(campus_map).search((0, 0), (4, 4))
        self.assertTrue(result.found)
        self.assertEqual(result.cost, 8)
        self.assertEqual(len(result.path), 9)
        self.assertEqual(result.path[0], (0, 0))
        self.assertEqual(result.path[-1], (4, 4))
        self.assertGreater(result.expanded, 0)

    def test_detour_around_wall(self):
        grid = [[0, 0, 1, 0, 0] for _ in range(5)]
        grid[2][2] = 0
        campus_map = CampusMap(5, 5, grid)
        result = AStarFinder(campus_map).search((0, 0), (4, 4))
        self.assertTrue(result.found)
        self.assertEqual(result.cost, len(result.path) - 1)
        self.assertNotIn((2, 2), result.path[:1])
        self.assertIn((2, 2), result.path)

    def test_unreachable(self):
        grid = [[0, 0, 1, 0, 0] for _ in range(5)]
        campus_map = CampusMap(5, 5, grid)
        result = AStarFinder(campus_map).search((0, 0), (4, 4))
        self.assertFalse(result.found)
        self.assertEqual(result.path, [])
        self.assertIn("不可达", result.message)
        self.assertGreater(result.expanded, 0)

    def test_blocked_start_and_goal(self):
        campus_map = CampusMap(3, 3, [[1, 0, 0], [0, 0, 0], [0, 0, 1]])
        finder = AStarFinder(campus_map)
        self.assertFalse(finder.search((0, 0), (2, 2)).found)
        self.assertFalse(finder.search((0, 1), (2, 2)).found)

    def test_same_start_and_goal(self):
        campus_map = CampusMap(3, 3)
        result = AStarFinder(campus_map).search((1, 1), (1, 1))
        self.assertTrue(result.found)
        self.assertEqual(result.cost, 0)
        self.assertEqual(result.path, [(1, 1)])

    def test_manhattan_is_admissible(self):
        self.assertEqual(AStarFinder.manhattan((0, 0), (3, 4)), 7)


if __name__ == "__main__":
    unittest.main()
