"""用 SQLite 分表保存当前地图，查询历史保留当时的地图快照。"""

from contextlib import closing
import json
from pathlib import Path
import sqlite3


SCHEMA = (
    """CREATE TABLE maps (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        name TEXT NOT NULL,
        rows INTEGER NOT NULL CHECK (rows > 0),
        cols INTEGER NOT NULL CHECK (cols > 0),
        revision INTEGER NOT NULL CHECK (revision >= 0),
        source_hash TEXT
    )""",
    """CREATE TABLE map_cells (
        row INTEGER NOT NULL CHECK (row >= 0),
        col INTEGER NOT NULL CHECK (col >= 0),
        cell_type INTEGER NOT NULL CHECK (cell_type IN (0, 1, 2, 3)),
        PRIMARY KEY (row, col)
    )""",
    """CREATE TABLE places (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        kind TEXT,
        row INTEGER NOT NULL CHECK (row >= 0),
        col INTEGER NOT NULL CHECK (col >= 0),
        status TEXT,
        entrance_name TEXT,
        entrance_row INTEGER CHECK (entrance_row >= 0),
        entrance_col INTEGER CHECK (entrance_col >= 0),
        entrance_enabled INTEGER CHECK (entrance_enabled IN (0, 1)),
        entrance_source TEXT CHECK (entrance_source IN ('manual', 'map_inferred')),
        CHECK (
            (entrance_name IS NULL AND entrance_row IS NULL AND entrance_col IS NULL
             AND entrance_enabled IS NULL AND entrance_source IS NULL)
            OR
            (entrance_name IS NOT NULL AND entrance_row IS NOT NULL AND entrance_col IS NOT NULL
             AND entrance_enabled IS NOT NULL AND entrance_source IS NOT NULL)
        )
    )""",
    """CREATE TABLE campus_route_history (
        id INTEGER PRIMARY KEY,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        start_name TEXT NOT NULL,
        goal_name TEXT NOT NULL,
        snapshot TEXT NOT NULL,
        found INTEGER NOT NULL,
        path TEXT NOT NULL,
        visited TEXT NOT NULL
    )""",
)

SCHEMA_VERSION = 5


def _walkability(classes):
    return [[int(cell_type != 2) for cell_type in row] for row in classes]


class CampusMapService:
    def __init__(self, initial_state, db_path):
        self.db_path = Path(db_path)
        self.source = initial_state.get("source")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            if conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION:
                return
            conn.execute("BEGIN IMMEDIATE")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == SCHEMA_VERSION:
                return
            if version != 0 or conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1"
            ).fetchone():
                raise ValueError("数据库结构版本不受支持")
            for statement in SCHEMA:
                conn.execute(statement)
            conn.execute("INSERT INTO maps (id, name, rows, cols, revision) VALUES (1, ?, 1, 1, 0)",
                         ("校园地图",))
            self._write_map(conn, initial_state)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _write_map(self, conn, state):
        classes = state["classes"]
        rows, cols = len(classes), len(classes[0]) if classes else 0
        if not cols or any(len(row) != cols for row in classes):
            raise ValueError("地图分类网格必须为非空矩形")
        if state["grid"] != _walkability(classes):
            raise ValueError("分类网格与通行网格不一致，不能保存")
        conn.execute("UPDATE maps SET name=?, rows=?, cols=?, source_hash=? WHERE id=1",
                     (state.get("name", "校园地图"), rows, cols, state.get("source_hash")))
        conn.execute("DELETE FROM map_cells")
        conn.executemany("INSERT INTO map_cells (row, col, cell_type) VALUES (?, ?, ?)",
                         ((r, c, value) for r, row in enumerate(classes) for c, value in enumerate(row)))
        conn.execute("DELETE FROM places")
        kinds, statuses = state.get("place_kinds", {}), state.get("place_status", {})
        entrances = state.get("entrances", {})
        if entrances.keys() - state["places"].keys():
            raise ValueError("存在未关联地点的入口")
        for name, (row, col) in state["places"].items():
            if not (0 <= row < rows and 0 <= col < cols):
                raise ValueError(f"地点坐标超出地图：{name}")
            entries = entrances.get(name, [])
            if len(entries) > 1:
                raise ValueError(f"每个地点只能保存一个入口：{name}")
            entrance_values = (None, None, None, None, None)
            if entries:
                entry = entries[0]
                entrance_row, entrance_col = entry["point"]
                if not (0 <= entrance_row < rows and 0 <= entrance_col < cols):
                    raise ValueError(f"入口坐标超出地图：{name} / {entry['name']}")
                entrance_values = (entry["name"], entrance_row, entrance_col,
                                   int(entry.get("enabled", True)), entry.get("source", "manual"))
            conn.execute("""INSERT INTO places (
                name, kind, row, col, status, entrance_name, entrance_row, entrance_col,
                entrance_enabled, entrance_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (name, kinds.get(name), row, col, statuses.get(name), *entrance_values))

    def load(self):
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN")
            map_row = conn.execute("SELECT * FROM maps WHERE id=1").fetchone()
            if map_row is None:
                raise ValueError("地图尚未初始化")
            rows, cols = map_row["rows"], map_row["cols"]
            classes = [[0] * cols for _ in range(rows)]
            cells = conn.execute("SELECT row, col, cell_type FROM map_cells").fetchall()
            if len(cells) != rows * cols:
                raise ValueError("地图网格记录不完整")
            for row, col, cell_type in cells:
                if not (0 <= row < rows and 0 <= col < cols):
                    raise ValueError("地图网格坐标超出地图")
                classes[row][col] = cell_type
            state = dict(name=map_row["name"], classes=classes, grid=_walkability(classes),
                         places={}, place_kinds={}, place_status={}, entrances={})
            if self.source is not None:
                state["source"] = self.source
            if map_row["source_hash"] is not None:
                state["source_hash"] = map_row["source_hash"]
            for place in conn.execute("SELECT * FROM places ORDER BY id"):
                name = place["name"]
                state["places"][name] = [place["row"], place["col"]]
                if place["kind"] is not None:
                    state["place_kinds"][name] = place["kind"]
                if place["status"] is not None:
                    state["place_status"][name] = place["status"]
                if place["entrance_row"] is not None:
                    entrance = {
                        "name": place["entrance_name"],
                        "point": [place["entrance_row"], place["entrance_col"]],
                        "enabled": bool(place["entrance_enabled"]),
                    }
                    if place["entrance_source"] == "map_inferred":
                        entrance["source"] = place["entrance_source"]
                    state["entrances"][name] = [entrance]
            return map_row["revision"], state

    def save(self, state):
        with closing(self._connect()) as conn, conn:
            revision = conn.execute("UPDATE maps SET revision=revision+1 WHERE id=1 RETURNING revision").fetchone()
            if revision is None:
                raise ValueError("地图尚未初始化")
            self._write_map(conn, state)
        return revision["revision"]

    def save_route(self, start, goal, state, result):
        with closing(self._connect()) as conn, conn:
            conn.execute("""INSERT INTO campus_route_history
                (start_name,goal_name,snapshot,found,path,visited)
                VALUES (?,?,?,?,?,?)""",
                (start, goal, json.dumps(state, ensure_ascii=False), int(result.found),
                 json.dumps(result.path), json.dumps(result.visited_order)))

    def history(self):
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM campus_route_history ORDER BY id DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            for field in ("snapshot", "path", "visited"):
                item[field] = json.loads(item[field])
            item["path_length"] = len(item["path"]) - 1 if item["found"] else None
            item["expanded_count"] = len(item["visited"])
            result.append(item)
        return result
