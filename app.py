"""CampusPath web application.

Run:
    python app.py

The project intentionally uses only the Python standard library at runtime:
``http.server`` for the API, ``sqlite3`` for persistence and a vanilla
JavaScript canvas front end.  This keeps the course project easy to run.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from campus.astar import AStarFinder
from campus.database import MapService
from campus.map import CampusMap


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
MAX_BODY = 20 * 1024 * 1024


class CampusApplication:
    def __init__(self, db_path: Path):
        self.service = MapService(
            db_path=db_path,
            base_map_path=ROOT / "data" / "base_map.json",
            places_path=ROOT / "data" / "places.json",
        )
        self.map = self.service.get_map()
        self.lock = threading.RLock()

    def state(self) -> dict[str, Any]:
        with self.lock:
            self.map = self.service.get_map()
            meta = self.service.get_map_meta()
            stats = self.service.stats()
            places = [place.to_dict() for place in self.service.list_places()]
            history = self.service.list_queries()
            return {
                "map": {
                    "name": meta["name"],
                    "rows": self.map.rows,
                    "cols": self.map.cols,
                    "grid": self.map.grid,
                    "updated_at": meta["updated_at"],
                    "snapshot_hash": self.map.snapshot_hash(),
                },
                "stats": stats,
                "places": places,
                "history": history,
                "meta": {
                    "background": "/static/campus_map.jpg",
                    "cell": 10,
                    "version": "1.0",
                },
            }

    def _endpoint(
        self, payload: dict[str, Any], role: str
    ) -> tuple[tuple[int, int], str, str | None]:
        if "place_id" in payload and payload["place_id"] not in (None, ""):
            row, col, name = self.service.resolve_place(int(payload["place_id"]))
            if self.map.is_walkable(row, col):
                return (row, col), name, None
            nearest = self.map.nearest_walkable(row, col, max_radius=4)
            if nearest is None:
                raise ValueError(f"{name}的入口被障碍物包围，附近没有可走格")
            row, col, distance = nearest
            return (row, col), name, f"{name}入口已吸附到最近可走格，距离 {distance} 格"
        if "row" not in payload or "col" not in payload:
            raise ValueError(f"{role}缺少坐标")
        row, col = int(payload["row"]), int(payload["col"])
        if not self.map.in_bounds(row, col):
            raise ValueError(f"{role}坐标越界")
        note = None
        if not self.map.is_walkable(row, col):
            nearest = self.map.nearest_walkable(row, col, max_radius=4)
            if nearest is None:
                raise ValueError(f"{role}位于障碍物中，附近没有可走格")
            row, col, distance = nearest
            note = f"{role}已吸附到最近可走格，距离 {distance} 格"
        name = payload.get("name") or f"自定义 ({row}, {col})"
        return (row, col), str(name), note

    def route(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self.map = self.service.get_map()
            start, start_name, start_note = self._endpoint(
                payload.get("start", {}), "起点"
            )
            goal, goal_name, goal_note = self._endpoint(payload.get("goal", {}), "终点")
            result = AStarFinder(self.map).search(start, goal)
            query_id = self.service.save_query(
                self.map, start, goal, start_name, goal_name, result
            )
            response = result.to_dict()
            response.update(
                {
                    "query_id": query_id,
                    "start": {"row": start[0], "col": start[1], "name": start_name},
                    "goal": {"row": goal[0], "col": goal[1], "name": goal_name},
                    "snapshot_hash": self.map.snapshot_hash(),
                    "notes": [note for note in (start_note, goal_note) if note],
                }
            )
            return response

    def edit(self, changes: list[list[int]]) -> dict[str, Any]:
        if not isinstance(changes, list) or not changes:
            raise ValueError("没有要保存的修改")
        if len(changes) > 5000:
            raise ValueError("单次修改不能超过 5000 格")
        with self.lock:
            self.map = self.service.get_map()
            self.map.apply_changes(changes)
            self.service.update_cells(changes)
            updated_at = self.service.save_map(self.map)
            return {
                "updated_at": updated_at,
                "stats": {
                    **self.map.counts(),
                    "components": self.map.components(),
                },
                "snapshot_hash": self.map.snapshot_hash(),
            }


class CampusRequestHandler(BaseHTTPRequestHandler):
    server_version = "CampusPath/1.0"
    app: CampusApplication

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/health":
                self._send_json({"ok": True})
            elif path == "/api/state":
                self._send_json(self.app.state())
            elif path == "/api/history":
                self._send_json({"history": self.app.service.list_queries()})
            elif path.startswith("/api/history/"):
                query_id = int(path.rsplit("/", 1)[1])
                item = self.app.service.get_query(query_id)
                if item is None:
                    self._send_error(HTTPStatus.NOT_FOUND, "记录不存在")
                else:
                    self._send_json(item)
            elif path == "/api/map/export":
                bundle = self.app.service.export_bundle()
                self._send_json(
                    bundle,
                    headers={
                        "Content-Disposition": 'attachment; filename="campus-map.json"'
                    },
                )
            elif path == "/" or path == "/index.html":
                self._send_file(STATIC / "index.html")
            elif path.startswith("/static/"):
                relative = path[len("/static/") :]
                candidate = (STATIC / relative).resolve()
                if not candidate.is_relative_to(STATIC.resolve()):
                    self._send_error(HTTPStatus.FORBIDDEN, "非法路径")
                elif not candidate.is_file():
                    self._send_error(HTTPStatus.NOT_FOUND, "文件不存在")
                else:
                    self._send_file(candidate)
            elif path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "页面不存在")
        except Exception as error:  # pragma: no cover - defensive server guard
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            payload = self._read_json()
            if path == "/api/route":
                self._send_json(self.app.route(payload))
            elif path == "/api/edit":
                self._send_json(self.app.edit(payload.get("changes", [])))
            elif path == "/api/map/save":
                with self.app.lock:
                    updated_at = self.app.service.save_map(self.app.map)
                self._send_json(
                    {
                        "updated_at": updated_at,
                        "stats": self.app.map.counts(),
                    }
                )
            elif path == "/api/map/reset":
                with self.app.lock:
                    self.app.map = self.app.service.reset_map()
                self._send_json(self.app.state())
            elif path == "/api/map/snapshot":
                snapshot = payload.get("snapshot", "")
                with self.app.lock:
                    self.app.map = self.app.service.load_snapshot(str(snapshot))
                self._send_json(self.app.state())
            elif path == "/api/map/import":
                with self.app.lock:
                    self.app.map = self.app.service.import_bundle(payload)
                self._send_json(self.app.state())
            elif path == "/api/places":
                self._place_action(payload)
            elif path == "/api/history/clear":
                with self.app.lock:
                    self.app.service.clear_history()
                self._send_json({"ok": True})
            else:
                self._send_error(HTTPStatus.NOT_FOUND, "接口不存在")
        except ValueError as error:
            self._send_error(HTTPStatus.BAD_REQUEST, str(error))
        except KeyError as error:
            self._send_error(HTTPStatus.BAD_REQUEST, f"缺少字段：{error}")
        except Exception as error:  # pragma: no cover - defensive server guard
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))

    def _place_action(self, payload: dict[str, Any]) -> None:
        action = payload.get("action")
        with self.app.lock:
            if action == "add":
                place = self.app.service.add_place(
                    name=payload.get("name", ""),
                    place_type=payload.get("type", "building"),
                    row=int(payload["row"]),
                    col=int(payload["col"]),
                    access_row=payload.get("access_row"),
                    access_col=payload.get("access_col"),
                    aliases=payload.get("aliases", ""),
                )
            elif action == "update":
                place = self.app.service.update_place(
                    place_id=int(payload["id"]),
                    name=payload.get("name", ""),
                    place_type=payload.get("type", "building"),
                    row=int(payload["row"]),
                    col=int(payload["col"]),
                    access_row=int(payload["access_row"]),
                    access_col=int(payload["access_col"]),
                    aliases=payload.get("aliases", ""),
                )
            elif action == "delete":
                self.app.service.delete_place(int(payload["id"]))
                self._send_json({"ok": True})
                return
            else:
                raise ValueError("未知的地点操作")
        self._send_json({"ok": True, "place": place.to_dict()})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("请求体不是合法 JSON") from error
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data

    def _send_file(self, path: Path) -> None:
        content = path.read_bytes()
        content_type, _ = mimetypes.guess_type(path.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        if path.suffix in {".jpg", ".png"}:
            self.send_header("Cache-Control", "public, max-age=3600")
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(
        self,
        data: Any,
        status: int = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        content = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def _send_error(self, status: int, message: str) -> None:
        self._send_json({"ok": False, "error": message}, status=status)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    db_path: Path | None = None,
) -> ThreadingHTTPServer:
    application = CampusApplication(db_path or ROOT / "data" / "campuspath.db")
    handler = type(
        "BoundCampusHandler",
        (CampusRequestHandler,),
        {"app": application},
    )
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="CampusPath 校园地图与 A* 路径查询")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=str(ROOT / "data" / "campuspath.db"))
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    server = create_server(args.host, args.port, Path(args.db))
    url = f"http://{args.host}:{args.port}/"
    print("CampusPath 已启动：", url)
    print("按 Ctrl+C 停止。")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止……")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
