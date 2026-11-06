"""用 SQLite 分表保存当前地图，查询历史保留当时的地图快照。"""

from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3


SCHEMA = (
    """CREATE TABLE maps (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        rows INTEGER NOT NULL CHECK (rows > 0),
        cols INTEGER NOT NULL CHECK (cols > 0),
        revision INTEGER NOT NULL CHECK (revision >= 0),
        source TEXT,
        source_hash TEXT,
        map_version TEXT,
        building_markers_version TEXT,
        metadata TEXT NOT NULL
    )""",
    """CREATE TABLE map_cells (
        map_id INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
        row INTEGER NOT NULL CHECK (row >= 0),
        col INTEGER NOT NULL CHECK (col >= 0),
        cell_type INTEGER NOT NULL CHECK (cell_type IN (0, 1, 2, 3)),
        PRIMARY KEY (map_id, row, col)
    )""",
    """CREATE TABLE places (
        id INTEGER PRIMARY KEY,
        map_id INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        kind TEXT,
        row INTEGER NOT NULL CHECK (row >= 0),
        col INTEGER NOT NULL CHECK (col >= 0),
        status TEXT,
        UNIQUE (map_id, name)
    )""",
    """CREATE TABLE place_entrances (
        id INTEGER PRIMARY KEY,
        place_id INTEGER NOT NULL REFERENCES places(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        row INTEGER NOT NULL CHECK (row >= 0),
        col INTEGER NOT NULL CHECK (col >= 0),
        enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
        UNIQUE (place_id, name)
    )""",
    """CREATE TABLE campus_route_history (
        id INTEGER PRIMARY KEY,
        map_id INTEGER NOT NULL REFERENCES maps(id),
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        start_name TEXT NOT NULL,
        goal_name TEXT NOT NULL,
        snapshot TEXT NOT NULL,
        found INTEGER NOT NULL,
        path TEXT NOT NULL,
        visited TEXT NOT NULL,
        path_length INTEGER,
        expanded_count INTEGER NOT NULL
    )""",
)

MAP_FIELDS = ("source", "source_hash", "map_version", "building_markers_version")
STATE_FIELDS = {"name", "grid", "classes", "places", "place_kinds", "place_status", "entrances", *MAP_FIELDS}


def _point_2d(point):
    """兼容新二维坐标和旧单层坐标，不丢弃非零层数据。"""
    if len(point) == 2:
        return list(point)
    if len(point) == 3 and point[0] == 0:
        return list(point[1:])
    raise ValueError("旧数据含有非平面坐标，不能自动转换为二维地图")


def _state_2d(state):
    """把旧单层地图或查询快照转换成当前的二维格式。"""
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


def _walkability(classes):
    return [[int(cell_type != 2) for cell_type in row] for row in classes]


class CampusMapService:
    def __init__(self, initial_state, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            if conn.execute("PRAGMA user_version").fetchone()[0] == 1:
                return
            # 建表、复制历史和移除旧表在同一个事务中完成。
            conn.execute("BEGIN IMMEDIATE")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 1:
                return
            if version != 0:
                raise ValueError("数据库结构版本不受支持")
            self._initialize(conn, initial_state)
            conn.execute("PRAGMA user_version = 1")

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize(self, conn, initial_state):
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        legacy = "campus_project" in tables
        if legacy:
            row = conn.execute("SELECT revision, data FROM campus_project WHERE id=1").fetchone()
            if row is None:
                raise ValueError("旧数据库没有当前地图记录")
            revision, state = row["revision"], _state_2d(json.loads(row["data"]))
            if state.get("source_hash") != initial_state.get("source_hash"):
                raise ValueError("旧数据库对应的 PDF 与当前资料不一致")
        else:
            revision, state = 0, _state_2d(initial_state)

        has_history = "campus_route_history" in tables
        if has_history:
            conn.execute("ALTER TABLE campus_route_history RENAME TO legacy_route_history")
        for statement in SCHEMA:
            conn.execute(statement)
        conn.execute("INSERT INTO maps (id, name, rows, cols, revision, metadata) VALUES (1, ?, 1, 1, ?, '{}')",
                     ("校园地图", revision))
        self._write_map(conn, state)
        if has_history:
            conn.execute("""INSERT INTO campus_route_history
                (id, map_id, created_at, start_name, goal_name, snapshot, found, path, visited, path_length, expanded_count)
                SELECT id, 1, created_at, start_name, goal_name, snapshot, found, path, visited, path_length, expanded_count
                FROM legacy_route_history""")
            conn.execute("DROP TABLE legacy_route_history")
        if legacy:
            conn.execute("DROP TABLE campus_project")

    def _write_map(self, conn, state):
        classes = state["classes"]
        rows, cols = len(classes), len(classes[0]) if classes else 0
        if not cols or any(len(row) != cols for row in classes):
            raise ValueError("地图分类网格必须为非空矩形")
        if state["grid"] != _walkability(classes):
            raise ValueError("分类网格与通行网格不一致，不能保存")
        metadata = {key: value for key, value in state.items() if key not in STATE_FIELDS}
        conn.execute("""UPDATE maps SET name=?, rows=?, cols=?, source=?, source_hash=?,
                        map_version=?, building_markers_version=?, metadata=? WHERE id=1""",
                     (state.get("name", "校园地图"), rows, cols, *(state.get(key) for key in MAP_FIELDS),
                      json.dumps(metadata, ensure_ascii=False)))
        conn.execute("DELETE FROM map_cells WHERE map_id=1")
        conn.executemany("INSERT INTO map_cells (map_id, row, col, cell_type) VALUES (1, ?, ?, ?)",
                         ((r, c, value) for r, row in enumerate(classes) for c, value in enumerate(row)))
        conn.execute("DELETE FROM places WHERE map_id=1")
        kinds, statuses = state.get("place_kinds", {}), state.get("place_status", {})
        entrances = state.get("entrances", {})
        if entrances.keys() - state["places"].keys():
            raise ValueError("存在未关联地点的入口")
        for name, (row, col) in state["places"].items():
            if not (0 <= row < rows and 0 <= col < cols):
                raise ValueError(f"地点坐标超出地图：{name}")
            cursor = conn.execute("INSERT INTO places (map_id, name, kind, row, col, status) VALUES (1, ?, ?, ?, ?, ?)",
                                  (name, kinds.get(name), row, col, statuses.get(name)))
            for entry in entrances.get(name, []):
                row, col = entry["point"]
                if not (0 <= row < rows and 0 <= col < cols):
                    raise ValueError(f"入口坐标超出地图：{name} / {entry['name']}")
                conn.execute("INSERT INTO place_entrances (place_id, name, row, col, enabled) VALUES (?, ?, ?, ?, ?)",
                             (cursor.lastrowid, entry["name"], row, col, int(entry.get("enabled", True))))

    def load(self):
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN")
            map_row = conn.execute("SELECT * FROM maps WHERE id=1").fetchone()
            if map_row is None:
                raise ValueError("地图尚未初始化")
            rows, cols = map_row["rows"], map_row["cols"]
            classes = [[0] * cols for _ in range(rows)]
            cells = conn.execute("SELECT row, col, cell_type FROM map_cells WHERE map_id=1").fetchall()
            if len(cells) != rows * cols:
                raise ValueError("地图网格记录不完整")
            for row, col, cell_type in cells:
                if not (0 <= row < rows and 0 <= col < cols):
                    raise ValueError("地图网格坐标超出地图")
                classes[row][col] = cell_type
            state = json.loads(map_row["metadata"])
            state.update(name=map_row["name"], classes=classes, grid=_walkability(classes),
                         places={}, place_kinds={}, place_status={}, entrances={})
            state.update({key: map_row[key] for key in MAP_FIELDS if map_row[key] is not None})
            for place in conn.execute("SELECT * FROM places WHERE map_id=1 ORDER BY id"):
                name = place["name"]
                state["places"][name] = [place["row"], place["col"]]
                if place["kind"] is not None:
                    state["place_kinds"][name] = place["kind"]
                if place["status"] is not None:
                    state["place_status"][name] = place["status"]
            for entry in conn.execute("""SELECT p.name AS place_name, e.name, e.row, e.col, e.enabled
                FROM place_entrances AS e JOIN places AS p ON e.place_id=p.id
                WHERE p.map_id=1 ORDER BY e.id"""):
                state["entrances"].setdefault(entry["place_name"], []).append({
                    "name": entry["name"], "point": [entry["row"], entry["col"]], "enabled": bool(entry["enabled"]),
                })
            return map_row["revision"], state

    def save(self, state):
        state = _state_2d(state)
        with closing(self._connect()) as conn, conn:
            revision = conn.execute("UPDATE maps SET revision=revision+1 WHERE id=1 RETURNING revision").fetchone()
            if revision is None:
                raise ValueError("地图尚未初始化")
            self._write_map(conn, state)
        return revision["revision"]

    def save_route(self, start, goal, state, result):
        state = _state_2d(state)
        with closing(self._connect()) as conn, conn:
            conn.execute("""INSERT INTO campus_route_history
                (map_id,start_name,goal_name,snapshot,found,path,visited,path_length,expanded_count)
                VALUES (1,?,?,?,?,?,?,?,?)""",
                (start, goal, json.dumps(state, ensure_ascii=False), int(result.found),
                 json.dumps(result.path), json.dumps(result.visited_order), result.path_length, result.expanded_count))

    def history(self):
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM campus_route_history WHERE map_id=1 ORDER BY id DESC").fetchall()
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
