"""校园地图和查询快照的 SQLite 保存服务。每版地图使用独立数据库。"""

from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3


def _point_2d(point):
    """兼容新二维坐标和旧单层坐标，不丢弃非零层数据。"""
    if len(point) == 2:
        return list(point)
    if len(point) == 3 and point[0] == 0:
        return list(point[1:])
    raise ValueError("旧数据含有非平面坐标，不能自动转换为二维地图")


def _state_2d(state):
    """读取旧单层地图时在内存中转换，原记录保持不变。"""
    state = deepcopy(state)
    if "grids" in state:
        grids = state.pop("grids")
        if len(grids) != 1 or state.get("portals") or "grid" in state:
            raise ValueError("旧地图包含多层或跨层连接，不能自动转换为二维地图")
        state["grid"] = grids[0]
    if state.get("portals"):
        raise ValueError("地图包含跨层连接，不能自动转换为二维地图")
    state.pop("portals", None)
    state["places"] = {name: _point_2d(point) for name, point in state.get("places", {}).items()}
    for entries in state.get("entrances", {}).values():
        for entry in entries:
            entry["point"] = _point_2d(entry["point"])
    query = state.get("route_query", {})
    for key in ("start_access", "goal_access"):
        if query.get(key):
            query[key]["point"] = _point_2d(query[key]["point"])
    return state


class CampusMapService:
    def __init__(self, initial_state, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(str(self.db_path))) as conn, conn:
            conn.execute("CREATE TABLE IF NOT EXISTS campus_project (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL)")
            conn.execute("""CREATE TABLE IF NOT EXISTS campus_route_history (
                id INTEGER PRIMARY KEY, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                start_name TEXT NOT NULL, goal_name TEXT NOT NULL, snapshot TEXT NOT NULL,
                found INTEGER NOT NULL, path TEXT NOT NULL, visited TEXT NOT NULL,
                path_length INTEGER, expanded_count INTEGER NOT NULL)""")
            conn.execute("INSERT OR IGNORE INTO campus_project VALUES (1, 0, ?)",
                         (json.dumps(initial_state, ensure_ascii=False),))

    def load(self):
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            row = conn.execute("SELECT revision, data FROM campus_project WHERE id=1").fetchone()
            if row is None:
                raise ValueError("地图尚未初始化")
            return row[0], _state_2d(json.loads(row[1]))

    def save(self, state, revision):
        state = _state_2d(state)
        with closing(sqlite3.connect(str(self.db_path))) as conn, conn:
            cursor = conn.execute("UPDATE campus_project SET data=?, revision=revision+1 WHERE id=1 AND revision=?",
                                  (json.dumps(state, ensure_ascii=False), revision))
            if cursor.rowcount != 1:
                raise ValueError("地图已被其他会话修改，请重新加载后再编辑")
        return revision + 1

    def save_route(self, start, goal, state, result):
        state = _state_2d(state)
        with closing(sqlite3.connect(str(self.db_path))) as conn, conn:
            conn.execute("""INSERT INTO campus_route_history
                (start_name,goal_name,snapshot,found,path,visited,path_length,expanded_count)
                VALUES (?,?,?,?,?,?,?,?)""",
                (start, goal, json.dumps(state, ensure_ascii=False), int(result.found),
                 json.dumps(result.path), json.dumps(result.visited_order), result.path_length, result.expanded_count))

    def history(self):
        with closing(sqlite3.connect(str(self.db_path))) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM campus_route_history ORDER BY id DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            for field in ("snapshot", "path", "visited"):
                item[field] = json.loads(item[field])
            item["snapshot"] = _state_2d(item["snapshot"])
            for field in ("path", "visited"):
                item[field] = [_point_2d(point) for point in item[field]]
            result.append(item)
        return result
