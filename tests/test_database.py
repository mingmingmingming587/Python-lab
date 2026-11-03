import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path

from algorithms.astar import astar_search
from database import store


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "data" / "test.db"
        store.init_database(self.db)

    def test_initialization_and_persistence(self):
        initial = store.load_map(self.db)
        self.assertEqual(initial["name"], "模拟校园地图")
        grid = initial["grid"]
        grid[3][4] = 1
        store.save_grid(grid, self.db)
        store.add_place("测试入口", 1, 2, self.db)
        store.init_database(self.db)
        loaded = store.load_map(self.db)
        self.assertEqual(loaded["grid"][3][4], 1)
        self.assertEqual(loaded["places"]["测试入口"], (1, 2))

    def test_places_and_grid_validation(self):
        data = store.load_map(self.db)
        with self.assertRaises(ValueError):
            store.add_place("模拟教学楼入口", 1, 2, self.db)
        with self.assertRaises(ValueError):
            store.add_place("无效", 0, 0, self.db)
        with self.assertRaises(ValueError):
            store.add_place("越界", 99, 0, self.db)
        grid = data["grid"]
        grid[1][1] = 1
        with self.assertRaises(ValueError):
            store.save_grid(grid, self.db)
        self.assertEqual(store.load_map(self.db)["grid"][1][1], 0)
        store.add_place("测试", 1, 2, self.db)
        store.update_place("测试", "更名", 1, 3, self.db)
        self.assertEqual(store.load_map(self.db)["places"]["更名"], (1, 3))
        store.delete_place("更名", self.db)
        self.assertNotIn("更名", store.load_map(self.db)["places"])

    def test_stale_grid_cannot_overwrite_new_edits(self):
        older = store.load_map(self.db)["grid"]
        newer = [row[:] for row in older]
        newer[3][4] = 1
        store.save_grid(newer, self.db, expected_grid=older)
        stale = [row[:] for row in older]
        stale[1][2] = 1
        with self.assertRaisesRegex(ValueError, "其他会话修改"):
            store.save_grid(stale, self.db, expected_grid=older)
        self.assertEqual(store.load_map(self.db)["grid"], newer)

    def test_stale_places_block_grid_save(self):
        data = store.load_map(self.db)
        store.add_place("新地点", 1, 2, self.db)
        with self.assertRaisesRegex(ValueError, "地点已被其他会话修改"):
            store.save_grid(data["grid"], self.db, expected_grid=data["grid"], expected_places=data["places"])

    def test_history_snapshot_survives_map_and_place_changes(self):
        data = store.load_map(self.db)
        start = "模拟教学楼入口"
        goal = "模拟图书馆入口"
        result = astar_search(data["grid"], data["places"][start], data["places"][goal])
        record_id = store.save_route(start, goal, data["grid"], result, self.db)
        changed = data["grid"]
        changed[3][4] = 1
        store.save_grid(changed, self.db)
        store.delete_place(goal, self.db)
        record = store.list_routes(self.db)[0]
        self.assertEqual(record["id"], record_id)
        self.assertEqual(record["goal_name"], goal)
        self.assertEqual(record["grid_snapshot"][3][4], 0)
        self.assertEqual(record["path_length"], result.path_length)
        self.assertEqual(record["path_snapshot"], [list(p) for p in result.path])

    def test_stale_place_is_rejected_even_for_unreachable_result(self):
        data = store.load_map(self.db)
        start, goal = "模拟教学楼入口", "模拟图书馆入口"
        old_start, old_goal = data["places"][start], data["places"][goal]
        data["grid"][3][4] = 1
        result = astar_search(data["grid"], old_start, old_goal)
        self.assertFalse(result.found)
        store.update_place(goal, goal, 2, 5, self.db)
        with self.assertRaisesRegex(ValueError, "坐标已变化"):
            store.save_route(start, goal, data["grid"], result, self.db,
                             expected_start=old_start, expected_goal=old_goal)
        self.assertEqual(store.list_routes(self.db), [])

    def test_replace_map_preserves_history(self):
        before = store.load_map(self.db)
        start, goal = "模拟教学楼入口", "模拟图书馆入口"
        result = astar_search(before["grid"], before["places"][start], before["places"][goal])
        store.save_route(start, goal, before["grid"], result, self.db)
        store.replace_map("另一张模拟地图", [[0, 1, 0], [0, 0, 0]],
                          {"入口一": [0, 0], "入口二": (1, 2)},
                          expected_name=before["name"], expected_grid=before["grid"], expected_places=before["places"], db_path=self.db)
        after = store.load_map(self.db)
        self.assertEqual(after["name"], "另一张模拟地图")
        self.assertEqual(after["grid"], [[0, 1, 0], [0, 0, 0]])
        self.assertEqual(after["places"], {"入口一": (0, 0), "入口二": (1, 2)})
        history = store.list_routes(self.db)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["grid_snapshot"], before["grid"])
        self.assertEqual(history[0]["start_name"], start)

    def test_replace_map_rejects_invalid_and_stale_without_modification(self):
        before = store.load_map(self.db)
        invalid = [
            ("", [[0]], {"入口": [0, 0]}),
            ("地图", [[0], [0, 0]], {}),
            ("地图", [[0, 1]], {"入口": [0, 1]}),
            ("地图", [[0]], {"入口": [True, 0]}),
            ("地图", [[0]], {"入口": [0, 1]}),
            ("地图", [[0]], {"入口": [0, 0, 0]}),
            ("地图", [[0]], {"入口": [0, 0], " 入口 ": [0, 0]}),
            ("地图", [[0]], [("入口", [0, 0])]),
        ]
        for name, grid, places in invalid:
            with self.subTest(name=name, grid=grid, places=places):
                with self.assertRaises(ValueError):
                    store.replace_map(name, grid, places, expected_name=before["name"], expected_grid=before["grid"],
                                      expected_places=before["places"], db_path=self.db)
                self.assertEqual(store.load_map(self.db), before)
        store.add_place("新地点", 1, 2, self.db)
        latest = store.load_map(self.db)
        with self.assertRaisesRegex(ValueError, "其他会话修改"):
            store.replace_map("地图", [[0]], {"入口": [0, 0]}, expected_name=before["name"], expected_grid=before["grid"],
                              expected_places=before["places"], db_path=self.db)
        self.assertEqual(store.load_map(self.db), latest)

    def test_replace_map_rolls_back_failed_write(self):
        before = store.load_map(self.db)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("CREATE TRIGGER reject_import BEFORE INSERT ON places WHEN NEW.name = '触发失败' "
                         "BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            store.replace_map("模拟导入", [[0]], {"触发失败": [0, 0]}, expected_name=before["name"], expected_grid=before["grid"],
                              expected_places=before["places"], db_path=self.db)
        self.assertEqual(store.load_map(self.db), before)

    def test_replace_map_rejects_stale_name_only(self):
        before = store.load_map(self.db)
        store.replace_map("新的地图名", before["grid"], before["places"], expected_name=before["name"],
                          expected_grid=before["grid"], expected_places=before["places"], db_path=self.db)
        after = store.load_map(self.db)
        with self.assertRaisesRegex(ValueError, "其他会话修改"):
            store.replace_map("旧会话覆盖", before["grid"], before["places"], expected_name=before["name"],
                              expected_grid=before["grid"], expected_places=before["places"], db_path=self.db)
        self.assertEqual(store.load_map(self.db), after)


if __name__ == "__main__":
    unittest.main()
