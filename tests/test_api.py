import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from app import create_server


ROOT = Path(__file__).resolve().parents[1]


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.server = create_server(
            host="127.0.0.1",
            port=0,
            db_path=Path(cls.temp.name) / "api.db",
        )
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def request(self, path, payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, headers=headers
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_state_and_route(self):
        status, state = self.request("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(state["stats"]["walkable"], 2211)
        self.assertEqual(len(state["places"]), 95)
        places = {place["name"]: place for place in state["places"]}
        status, result = self.request(
            "/api/route",
            {
                "start": {"place_id": places["图书馆（东）"]["id"]},
                "goal": {"place_id": places["明德楼（东）"]["id"]},
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["found"])
        self.assertGreater(result["cost"], 0)
        self.assertGreater(result["expanded"], 0)
        self.assertEqual(result["path"][0], [result["start"]["row"], result["start"]["col"]])
        self.assertEqual(result["path"][-1], [result["goal"]["row"], result["goal"]["col"]])

    def test_edit_and_undo(self):
        _, state = self.request("/api/state")
        before = state["stats"]["blocked"]
        status, result = self.request(
            "/api/edit", {"changes": [[120, 25, 1]]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["stats"]["blocked"], before + 1)
        self.request("/api/edit", {"changes": [[120, 25, 0]]})
        _, state = self.request("/api/state")
        self.assertEqual(state["map"]["grid"][120][25], 0)

    def test_export(self):
        status, bundle = self.request("/api/map/export")
        self.assertEqual(status, 200)
        self.assertEqual(bundle["format"], "campuspath-map")
        self.assertEqual(bundle["rows"], 180)
        self.assertEqual(len(bundle["places"]), 95)

    def test_bad_request(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request("/api/route", {"start": {}, "goal": {}})
        self.assertEqual(context.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
