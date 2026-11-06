from collections import deque
import unittest

from algorithms.astar import CampusMap, astar


class AStarTests(unittest.TestCase):
    def test_shortest_route_matches_independent_bfs(self):
        grid = [[0, 0, 1], [0, 1, 0], [0, 0, 0]]
        start, goal = (0, 0), (2, 2)
        queue, seen = deque([(start, 0)]), {start}
        expected = None
        while queue:
            p, cost = queue.popleft()
            if p == goal:
                expected = cost
                break
            row, col = p
            candidates = [(row-1, col), (row+1, col), (row, col-1), (row, col+1)]
            for q in candidates:
                if 0 <= q[0] < 3 and 0 <= q[1] < 3 and grid[q[0]][q[1]] == 0 and q not in seen:
                    seen.add(q)
                    queue.append((q, cost+1))
        result = astar(grid, start, goal)
        self.assertEqual(result.path_length, expected)
        for a, b in zip(result.path, result.path[1:]):
            self.assertEqual(abs(a[0]-b[0]) + abs(a[1]-b[1]), 1)

    def test_same_cell_unreachable_and_invalid_endpoint(self):
        grid = [[0, 1, 0]]
        self.assertEqual(astar(grid, (0, 0), (0, 0)).path_length, 0)
        self.assertFalse(astar(grid, (0, 0), (0, 2)).found)
        with self.assertRaises(ValueError):
            astar(grid, (0, 1), (0, 2))
        with self.assertRaises(ValueError):
            astar(grid, (-1, 0), (0, 2))
        with self.assertRaises(ValueError):
            CampusMap([[0], [0, 1]])


if __name__ == "__main__":
    unittest.main()
