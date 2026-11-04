from collections import deque
import unittest

from algorithms.layered_astar import CampusMap, layered_astar


class AStarTests(unittest.TestCase):
    def test_shortest_route_matches_independent_bfs(self):
        grids = [[[0, 0, 1], [0, 1, 0], [0, 0, 0]],
                 [[1, 0, 0], [0, 0, 0], [0, 1, 0]]]
        portal = ((0, 0, 1), (1, 0, 1))
        start, goal = (0, 0, 0), (1, 2, 2)
        queue, seen = deque([(start, 0)]), {start}
        expected = None
        while queue:
            p, cost = queue.popleft()
            if p == goal:
                expected = cost
                break
            layer, row, col = p
            candidates = [(layer, row-1, col), (layer, row+1, col),
                          (layer, row, col-1), (layer, row, col+1)]
            if p in portal:
                candidates.append(portal[1] if p == portal[0] else portal[0])
            for q in candidates:
                if 0 <= q[1] < 3 and 0 <= q[2] < 3 and grids[q[0]][q[1]][q[2]] == 0 and q not in seen:
                    seen.add(q)
                    queue.append((q, cost+1))
        result = layered_astar(grids, start, goal, [portal])
        self.assertEqual(result.path_length, expected)
        for a, b in zip(result.path, result.path[1:]):
            self.assertTrue(a in portal and b in portal or
                            a[0] == b[0] and abs(a[1]-b[1]) + abs(a[2]-b[2]) == 1)

    def test_same_cell_unreachable_and_invalid_endpoint(self):
        grid = [[[0, 1, 0]]]
        self.assertEqual(layered_astar(grid, (0, 0, 0), (0, 0, 0)).path_length, 0)
        self.assertFalse(layered_astar(grid, (0, 0, 0), (0, 0, 2)).found)
        with self.assertRaises(ValueError):
            layered_astar(grid, (0, 0, 1), (0, 0, 2))
        with self.assertRaises(ValueError):
            layered_astar(grid, (0, -1, 0), (0, 0, 2))
        with self.assertRaises(ValueError):
            CampusMap([[[0], [0, 1]]])

    def test_overlapping_layers_do_not_connect_implicitly(self):
        grids = [[[0]], [[0]]]
        self.assertFalse(layered_astar(grids, (0, 0, 0), (1, 0, 0)).found)
        result = layered_astar(grids, (0, 0, 0), (1, 0, 0), [((0, 0, 0), (1, 0, 0))])
        self.assertEqual(result.path_length, 1)


if __name__ == "__main__":
    unittest.main()
