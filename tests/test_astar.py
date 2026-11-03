import unittest
from collections import deque

from algorithms.astar import astar_search


class AStarTests(unittest.TestCase):
    def test_all_three_by_three_maps_against_bfs(self):
        # 对所有 3×3 地图的合法起终点，用独立 BFS 对照最短步数。
        for mask in range(1 << 9):
            grid = [[(mask >> (r * 3 + c)) & 1 for c in range(3)] for r in range(3)]
            open_cells = [(r, c) for r in range(3) for c in range(3) if grid[r][c] == 0]
            for start in open_cells:
                queue = deque([(start, 0)])
                distances = {start: 0}
                while queue:
                    (r, c), distance = queue.popleft()
                    for point in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                        nr, nc = point
                        if 0 <= nr < 3 and 0 <= nc < 3 and grid[nr][nc] == 0 and point not in distances:
                            distances[point] = distance + 1
                            queue.append((point, distance + 1))
                for goal in open_cells:
                    result = astar_search(grid, start, goal)
                    self.assertEqual(result.path_length, distances.get(goal), (grid, start, goal))
                    self.assertEqual(result.found, goal in distances, (grid, start, goal))

    def test_detour_finds_shortest_valid_path(self):
        grid = [[0, 1, 0], [0, 1, 0], [0, 0, 0]]
        result = astar_search(grid, (0, 0), (0, 2))
        self.assertTrue(result.found)
        self.assertEqual(result.path_length, 6)
        self.assertEqual((result.path[0], result.path[-1]), ((0, 0), (0, 2)))
        self.assertTrue(all(grid[r][c] == 0 for r, c in result.path))
        self.assertTrue(all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(result.path, result.path[1:])))
        self.assertEqual(result.expanded_count, len(result.visited_order))
        self.assertEqual(result.expanded_count, len(set(result.visited_order)))

    def test_same_point_and_unreachable(self):
        same = astar_search([[0]], (0, 0), (0, 0))
        self.assertEqual((same.path, same.path_length), ([(0, 0)], 0))
        blocked = astar_search([[0, 1, 0]], (0, 0), (0, 2))
        self.assertEqual((blocked.found, blocked.path, blocked.path_length), (False, [], None))

    def test_invalid_input(self):
        for grid, start, goal in [([], (0, 0), (0, 0)), ([[0], [0, 0]], (0, 0), (0, 0)), ([[0, 1]], (0, 0), (0, 1)), ([[0]], (-1, 0), (0, 0)), ([[True]], (0, 0), (0, 0))]:
            with self.subTest(grid=grid, start=start, goal=goal):
                with self.assertRaises(ValueError):
                    astar_search(grid, start, goal)


if __name__ == "__main__":
    unittest.main()
