import tempfile
import unittest
from collections import deque
from pathlib import Path

from algorithms.layered_astar import CampusMap, layered_astar
from database.campus_project import (active_portals, campus_history, initial_campus, init_campus,
                                     load_campus, save_campus, save_campus_route)
from visualization.user_markings import blocked_grid_cells, image_point


def layout_fixture():
    points = [("北区路线", (640, 960)), ("南区路线", (646, 1044)), ("校内路线", (600, 1355))]
    return {"places": [{"name": name, "x": image_point(p)[0], "y": image_point(p)[1]} for name, p in points]}


class LayeredCampusTests(unittest.TestCase):
    def test_crossing_does_not_create_implicit_intersection(self):
        ground = [[1, 0, 1], [1, 0, 1], [1, 0, 1]]
        bridge = [[1, 1, 1], [0, 0, 0], [1, 1, 1]]
        # 投影位置 (1,1) 相同也不能自动从地面切换到天桥。
        self.assertFalse(layered_astar([ground, bridge], (0, 0, 1), (1, 1, 2)).found)
        portals = [((0, 1, 1), (1, 1, 1))]
        result = layered_astar([ground, bridge], (0, 0, 1), (1, 1, 2), portals)
        self.assertTrue(result.found)
        self.assertEqual(result.path_length, 3)
        self.assertIn((0, 1, 1), result.path)
        self.assertIn((1, 1, 1), result.path)

    def test_astar_matches_bfs_and_handles_closed_endpoint(self):
        grids = [[[0, 0, 1], [0, 1, 0], [0, 0, 0]], [[1, 0, 0], [0, 0, 0], [0, 1, 0]]]
        portal = ((0, 0, 1), (1, 0, 1))
        start, goal = (0, 0, 0), (1, 2, 2)
        queue, seen = deque([(start, 0)]), {start}
        expected = None
        while queue:
            p, cost = queue.popleft()
            if p == goal:
                expected = cost
                break
            l, r, c = p
            candidates = [(l, r-1, c), (l, r+1, c), (l, r, c-1), (l, r, c+1)]
            if p in portal:
                candidates.append(portal[1] if p == portal[0] else portal[0])
            for q in candidates:
                if 0 <= q[1] < 3 and 0 <= q[2] < 3 and grids[q[0]][q[1]][q[2]] == 0 and q not in seen:
                    seen.add(q); queue.append((q, cost + 1))
        result = layered_astar(grids, start, goal, [portal])
        self.assertEqual(result.path_length, expected)
        grids[1][0][1] = 1
        self.assertFalse(layered_astar(grids, start, goal, [portal]).found)

    def test_map_persistence_history_and_gate(self):
        layout = layout_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "campus.db"
            init_campus(layout, db)
            revision, state = load_campus(db)
            start, goal = tuple(state["places"]["北区路线"]), tuple(state["places"]["南区路线"])
            result = layered_astar(state["grids"], start, goal, active_portals(state))
            self.assertTrue(result.found)
            self.assertIn(2, {point[0] for point in result.path})
            north_gate = next(p for p in state["portals"] if p[4] == "北侧限时门")
            gate_pair = ((north_gate[0], north_gate[2], north_gate[3]), (north_gate[1], north_gate[2], north_gate[3]))
            self.assertNotIn(gate_pair, active_portals(state))
            south_gate = next(p for p in state["portals"] if p[4] == "南侧门")
            south_pair = ((south_gate[0], south_gate[2], south_gate[3]), (south_gate[1], south_gate[2], south_gate[3]))
            self.assertIn(south_pair, active_portals(state))
            legacy_state = dict(state)
            legacy_state["south_gate_open"] = False
            self.assertIn(south_pair, active_portals(legacy_state))
            self.assertFalse(layered_astar(state["grids"], *gate_pair, []).found)
            # 天桥与海油大街在图面交叉，也没有从桥直接切换到地面的连接。
            crossing = (north_gate[2], north_gate[3])
            self.assertEqual(state["grids"][2][crossing[0]][crossing[1]], 0)
            self.assertEqual(state["grids"][1][crossing[0]][crossing[1]], 0)
            self.assertNotIn((1, *crossing), CampusMap(state["grids"], active_portals(state)).neighbors((2, *crossing)))
            save_campus_route("北区路线", "南区路线", state, result, db)
            state["north_gate_open"] = True
            self.assertIn(gate_pair, active_portals(state))
            self.assertEqual(layered_astar(state["grids"], *gate_pair, [gate_pair]).path_length, 1)
            for row, col in blocked_grid_cells(include_north_gate=False):
                self.assertEqual(state["grids"][0][row][col], 1)
                self.assertEqual(state["grids"][1][row][col], 1)
            self.assertEqual(save_campus(state, revision, db), 1)
            with self.assertRaises(ValueError):
                save_campus(state, revision, db)
            self.assertTrue(load_campus(db)[1]["north_gate_open"])
            history = campus_history(db)
            self.assertEqual(len(history), 1)
            self.assertFalse(history[0]["snapshot"]["north_gate_open"])
            self.assertEqual(history[0]["path_length"], result.path_length)


if __name__ == "__main__":
    unittest.main()
