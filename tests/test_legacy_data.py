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
        self.assertEqual(state["entrances"]["图书馆"][0]["point"], [0, 0])
        self.assertEqual(len(state["entrances"]["图书馆"]), 1)
        history = service.history()[0]
        self.assertEqual((history["id"], history["created_at"]), (7, "2026-11-06T12:00:00Z"))
        self.assertEqual(history["path"], [[0, 0], [0, 1]])
        self.assertEqual((history["path_length"], history["expanded_count"]), (1, 1))
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

    def _old_relational_db(self, version):
        db = Path(self.directory) / f"relational-{version}.db"
        with closing(sqlite3.connect(db)) as conn, conn:
            conn.executescript("""
                PRAGMA foreign_keys=ON;
                CREATE TABLE maps (id INTEGER PRIMARY KEY, name TEXT, rows INTEGER, cols INTEGER,
                    revision INTEGER, source TEXT, source_hash TEXT, map_version TEXT,
                    building_markers_version TEXT, metadata TEXT);
                CREATE TABLE map_cells (map_id INTEGER REFERENCES maps(id) ON DELETE CASCADE,
                    row INTEGER, col INTEGER, cell_type INTEGER, PRIMARY KEY (map_id,row,col));
                CREATE TABLE places (id INTEGER PRIMARY KEY,
                    map_id INTEGER REFERENCES maps(id) ON DELETE CASCADE,
                    name TEXT, kind TEXT, row INTEGER, col INTEGER, status TEXT);
                CREATE TABLE place_entrances (id INTEGER PRIMARY KEY,
                    place_id INTEGER REFERENCES places(id) ON DELETE CASCADE,
                    name TEXT, row INTEGER, col INTEGER, enabled INTEGER);
                CREATE TABLE campus_route_history (id INTEGER PRIMARY KEY, map_id INTEGER REFERENCES maps(id),
                    created_at TEXT, start_name TEXT, goal_name TEXT, snapshot TEXT, found INTEGER,
                    path TEXT, visited TEXT, path_length INTEGER, expanded_count INTEGER);
                INSERT INTO maps VALUES (1,'校园地图',1,2,3,'旧说明','pdf','旧版本','旧标记','{}');
                INSERT INTO map_cells VALUES (1,0,0,2),(1,0,1,2);
                INSERT INTO places VALUES (11,1,'图书馆','建筑',0,1,'手动校对');
                INSERT INTO place_entrances VALUES (1,11,'可用入口',0,1,1);
            """)
            conn.execute("""INSERT INTO campus_route_history VALUES
                (7,1,'2026-11-06T12:00:00Z','西门','图书馆',?,1,'[[0,0],[0,1]]','[[0,0]]',1,1)""",
                         (json.dumps(self.snapshot),))
            if version >= 2:
                conn.execute("ALTER TABLE place_entrances ADD COLUMN source TEXT DEFAULT 'manual'")
                conn.execute("UPDATE place_entrances SET source='map_inferred'")
            conn.execute(f"PRAGMA user_version={version}")
        return db

    def test_five_table_database_migrates_to_single_map_columns(self):
        for version in (0, 1, 3):
            with self.subTest(version=version):
                db = self._old_relational_db(version)
                reopened = CampusMapService(self.initial, db)
                revision, state = reopened.load()
                self.assertEqual(revision, 3)
                self.assertEqual(state["grid"], [[0, 0]])
                self.assertEqual(state["places"], {"图书馆": [0, 1]})
                self.assertEqual(state["place_status"], {"图书馆": "手动校对"})
                entry = state["entrances"]["图书馆"][0]
                self.assertEqual(entry.get("source", "manual"), "map_inferred" if version == 3 else "manual")
                self.assertEqual(reopened.history()[0]["expanded_count"], 1)
                with closing(sqlite3.connect(db)) as conn:
                    self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 4)
                    self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
                    for table, size in (("maps", 6), ("map_cells", 3), ("places", 6),
                                        ("place_entrances", 6), ("campus_route_history", 8)):
                        self.assertEqual(len(conn.execute(f"PRAGMA table_info({table})").fetchall()), size)
                    self.assertEqual(conn.execute("SELECT place_id FROM place_entrances").fetchone()[0], 11)
                    raw = conn.execute("SELECT snapshot FROM campus_route_history WHERE id=7").fetchone()[0]
                    self.assertEqual(raw, json.dumps(self.snapshot))

    def test_multiple_entry_migration_keeps_available_entry_and_history(self):
        db = self._old_relational_db(2)
        with closing(sqlite3.connect(db)) as conn, conn:
            conn.execute("UPDATE place_entrances SET id=2")
            conn.execute("""INSERT INTO place_entrances (id,place_id,name,row,col,enabled)
                VALUES (1,11,'已停用',0,0,0)""")
        reopened = CampusMapService(self.initial, db)
        updated_revision, state = reopened.load()
        self.assertEqual(updated_revision, 4)
        self.assertEqual([entry["name"] for entry in state["entrances"]["图书馆"]], ["可用入口"])
        self.assertEqual(reopened.history()[0]["id"], 7)
        self.assertEqual(CampusMapService(self.initial, db).load(), (updated_revision, state))
        with closing(sqlite3.connect(db)) as conn, conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("""INSERT INTO place_entrances (place_id,name,row,col,enabled)
                    SELECT id,'重复入口',0,0,1 FROM places WHERE name='图书馆'""")

    def test_inferred_entry_source_survives_save_and_reopen(self):
        service = CampusMapService(self.initial, self.db)
        _, state = service.load()
        state["entrances"]["图书馆"][0]["source"] = "map_inferred"
        service.save(state)
        loaded = CampusMapService(self.initial, self.db).load()[1]
        self.assertEqual(loaded["entrances"], state["entrances"])
        self.assertEqual(len(loaded["entrances"]["图书馆"]), 1)

    def test_migration_rolls_back_if_a_late_insert_fails(self):
        self.legacy["entrances"]["图书馆"][0]["source"] = "invalid-source"
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
