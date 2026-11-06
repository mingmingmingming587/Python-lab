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
        self.service = CampusMapService({"grid": [[0, 0]], "places": {}}, self.db)
        self.legacy = {
            "grids": [[[0, 0]]], "places": {"图书馆": [0, 0, 1]},
            "entrances": {"图书馆": [{"name": "西门", "point": [0, 0, 0], "enabled": True}]},
            "portals": [],
            "route_query": {"start_access": {"point": [0, 0, 0], "temporary": False}},
        }
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE campus_project SET revision=3, data=? WHERE id=1", (json.dumps(self.legacy),))
            conn.execute("""INSERT INTO campus_route_history
                (start_name, goal_name, snapshot, found, path, visited, path_length, expanded_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("西门", "图书馆", json.dumps(self.legacy), 1,
                 json.dumps([[0, 0, 0], [0, 0, 1]]), json.dumps([[0, 0, 0]]), 1, 1))

    def test_old_map_and_history_load_as_two_dimensions_without_rewriting(self):
        revision, state = self.service.load()
        self.assertEqual(revision, 3)
        self.assertEqual(state["grid"], [[0, 0]])
        self.assertEqual(state["places"]["图书馆"], [0, 1])
        self.assertEqual(state["entrances"]["图书馆"][0]["point"], [0, 0])
        history = self.service.history()[0]
        self.assertEqual(history["path"], [[0, 0], [0, 1]])
        self.assertEqual(history["snapshot"]["route_query"]["start_access"]["point"], [0, 0])
        with closing(sqlite3.connect(self.db)) as conn, conn:
            raw = json.loads(conn.execute("SELECT data FROM campus_project WHERE id=1").fetchone()[0])
            self.assertEqual(raw, self.legacy)
        self.service.save(state, revision)
        with closing(sqlite3.connect(self.db)) as conn, conn:
            saved = json.loads(conn.execute("SELECT data FROM campus_project WHERE id=1").fetchone()[0])
            self.assertIn("grid", saved)
            self.assertNotIn("grids", saved)
        self.assertEqual(self.service.history()[0]["path"], [[0, 0], [0, 1]])

    def test_multilayer_data_is_not_silently_discarded(self):
        self.legacy["grids"].append([[0, 0]])
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE campus_project SET data=? WHERE id=1", (json.dumps(self.legacy),))
        with self.assertRaisesRegex(ValueError, "多层"):
            self.service.load()
        with closing(sqlite3.connect(self.db)) as conn, conn:
            raw = json.loads(conn.execute("SELECT data FROM campus_project WHERE id=1").fetchone()[0])
        self.assertEqual(raw, self.legacy)


if __name__ == "__main__":
    unittest.main()
