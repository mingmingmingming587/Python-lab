import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from database.campus_project import CampusMapService


class LegacyDataTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.db = Path(self.directory) / "map.db"
        self.initial = {"classes": [[0, 0]], "grid": [[1, 1]], "places": {}, "source_hash": "pdf"}
        self.legacy = {
            "classes": [[2, 2]], "grids": [[[0, 0]]], "places": {"图书馆": [0, 0, 1]},
            "place_status": {"图书馆": "手动校对"}, "place_kinds": {"图书馆": "建筑"},
            "entrances": {"图书馆": [
                {"name": "西门", "point": [0, 0, 0], "enabled": True},
                {"name": "东门", "point": [0, 0, 1], "enabled": False},
            ]},
            "portals": [], "source_hash": "pdf", "building_markers_version": "marks-v3",
        }
        self.snapshot = {**self.legacy, "route_query": {
            "start_access": {"point": [0, 0, 0], "temporary": False},
        }}
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("CREATE TABLE campus_project (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL)")
            conn.execute("""CREATE TABLE campus_route_history (
                id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, start_name TEXT NOT NULL, goal_name TEXT NOT NULL,
                snapshot TEXT NOT NULL, found INTEGER NOT NULL, path TEXT NOT NULL, visited TEXT NOT NULL,
                path_length INTEGER, expanded_count INTEGER NOT NULL)""")
            conn.execute("INSERT INTO campus_project VALUES (1, 3, ?)", (json.dumps(self.legacy),))
            conn.execute("""INSERT INTO campus_route_history
                (id, created_at, start_name, goal_name, snapshot, found, path, visited, path_length, expanded_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (7, "2026-11-06T12:00:00Z", "西门", "图书馆", json.dumps(self.snapshot), 1,
                 json.dumps([[0, 0, 0], [0, 0, 1]]), json.dumps([[0, 0, 0]]), 1, 1))

    def test_legacy_migration_preserves_map_edits_entrances_and_history(self):
        service = CampusMapService(self.initial, self.db)
        revision, state = service.load()
        self.assertEqual(revision, 3)
        self.assertEqual(state["grid"], [[0, 0]])
        self.assertEqual(state["places"]["图书馆"], [0, 1])
        self.assertEqual(state["place_status"]["图书馆"], "手动校对")
        self.assertEqual(state["building_markers_version"], "marks-v3")
        self.assertEqual(state["entrances"]["图书馆"][0]["point"], [0, 0])
        self.assertFalse(state["entrances"]["图书馆"][1]["enabled"])
        history = service.history()[0]
        self.assertEqual((history["id"], history["created_at"]), (7, "2026-11-06T12:00:00Z"))
        self.assertEqual(history["path"], [[0, 0], [0, 1]])
        self.assertEqual(history["snapshot"]["route_query"]["start_access"]["point"], [0, 0])
        with closing(sqlite3.connect(self.db)) as conn, conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(tables, {"maps", "map_cells", "places", "place_entrances", "campus_route_history"})
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            raw = conn.execute("SELECT snapshot FROM campus_route_history WHERE id=7").fetchone()[0]
            self.assertEqual(raw, json.dumps(self.snapshot))
        state["classes"][0][0] = 3
        state["grid"][0][0] = 1
        self.assertEqual(service.save(state), revision+1)
        reopened = CampusMapService(self.initial, self.db)
        self.assertEqual(reopened.load()[1]["grid"], [[1, 0]])
        self.assertEqual(reopened.history()[0]["snapshot"]["grid"], [[0, 0]])

    def test_multilayer_data_is_not_silently_discarded(self):
        self.legacy["grids"].append([[0, 0]])
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE campus_project SET data=? WHERE id=1", (json.dumps(self.legacy),))
        with self.assertRaisesRegex(ValueError, "多层"):
            CampusMapService(self.initial, self.db)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            raw = json.loads(conn.execute("SELECT data FROM campus_project WHERE id=1").fetchone()[0])
        self.assertEqual(raw, self.legacy)

    def test_existing_five_table_database_adds_source_without_losing_entries(self):
        service = CampusMapService(self.initial, self.db)
        before = service.load()
        history = service.history()
        for old_version in (0, 1):
            with self.subTest(version=old_version):
                with closing(sqlite3.connect(self.db)) as conn, conn:
                    conn.execute("ALTER TABLE place_entrances DROP COLUMN source")
                    conn.execute(f"PRAGMA user_version = {old_version}")
                reopened = CampusMapService(self.initial, self.db)
                self.assertEqual(reopened.load(), before)
                self.assertEqual(reopened.history(), history)
                self.assertEqual(CampusMapService(self.initial, self.db).load(), before)
                with closing(sqlite3.connect(self.db)) as conn:
                    self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
                    self.assertEqual({row[0] for row in conn.execute("SELECT source FROM place_entrances")}, {"manual"})

    def test_inferred_entry_source_survives_save_and_reopen(self):
        service = CampusMapService(self.initial, self.db)
        _, state = service.load()
        state["entrances"]["图书馆"][0]["source"] = "map_inferred"
        service.save(state)
        loaded = CampusMapService(self.initial, self.db).load()[1]
        self.assertEqual(loaded["entrances"], state["entrances"])
        self.assertNotIn("source", loaded["entrances"]["图书馆"][1])

    def test_migration_rolls_back_if_a_late_insert_fails(self):
        self.legacy["entrances"]["图书馆"].append(self.legacy["entrances"]["图书馆"][0])
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE campus_project SET data=? WHERE id=1", (json.dumps(self.legacy),))
        with self.assertRaises(sqlite3.IntegrityError):
            CampusMapService(self.initial, self.db)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(tables, {"campus_project", "campus_route_history"})
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT id FROM campus_route_history").fetchall(), [(7,)])


if __name__ == "__main__":
    unittest.main()
