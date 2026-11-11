"""用 SQLite 分表保存当前地图，查询历史保留当时的地图快照。"""

from contextlib import closing
from copy import deepcopy
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
        status TEXT
    )""",
    """CREATE TABLE place_entrances (
        place_id INTEGER PRIMARY KEY REFERENCES places(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        row INTEGER NOT NULL CHECK (row >= 0),
        col INTEGER NOT NULL CHECK (col >= 0),
        enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
        source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'map_inferred'))
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

SCHEMA_VERSION = 4
TABLES = ("maps", "map_cells", "places", "place_entrances", "campus_route_history")
HISTORY_FIELDS = "id, created_at, start_name, goal_name, snapshot, found, path, visited"


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


def single_entrances(entrances, grid):
    """兼容旧地图，优先保留已启用且道路可通行的入口。"""
    def preference(entry):
        row, col = entry["point"]
        enabled = entry.get("enabled", True)
        walkable = (0 <= row < len(grid) and 0 <= col < len(grid[row])
                    and grid[row][col] == 0)
        return (not (enabled and walkable), not enabled)

    return {place: [min(entries, key=preference)]
            for place, entries in entrances.items() if entries}


class CampusMapService:
    def __init__(self, initial_state, db_path):
        self.db_path = Path(db_path)
        self.map_info = {key: initial_state[key] for key in ("source", "map_version") if key in initial_state}
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            if conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION:
                return
            # 建表、复制历史和移除旧表在同一个事务中完成。
            conn.execute("BEGIN IMMEDIATE")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == SCHEMA_VERSION:
                return
            if version not in (0, 1, 2, 3):
                raise ValueError("数据库结构版本不受支持")
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "maps" in tables:
                self._migrate_tables(conn, initial_state.get("source_hash"))
            else:
                self._initialize(conn, initial_state)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _migrate_tables(self, conn, source_hash):
        maps = conn.execute("SELECT id, source_hash FROM maps").fetchall()
        if len(maps) != 1 or maps[0]["id"] != 1:
            raise ValueError("只能迁移地图 ID 为 1 的单地图数据库")
        if maps[0]["source_hash"] != source_hash:
            raise ValueError("已保存的地图与当前网格版本不一致")
        if conn.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("旧数据库存在无效关联，不能迁移")
        for table in TABLES:
            conn.execute(f"ALTER TABLE {table} RENAME TO legacy_{table}")
        for statement in SCHEMA:
            conn.execute(statement)
        conn.execute("""INSERT INTO maps (id,name,rows,cols,revision,source_hash)
            SELECT id,name,rows,cols,revision,source_hash FROM legacy_maps""")
        conn.execute("""INSERT INTO map_cells (row,col,cell_type)
            SELECT row,col,cell_type FROM legacy_map_cells""")
        conn.execute("""INSERT INTO places (id,name,kind,row,col,status)
            SELECT id,name,kind,row,col,status FROM legacy_places""")

        columns = {row["name"] for row in conn.execute("PRAGMA table_info(legacy_place_entrances)")}
        source = "e.source" if "source" in columns else "'manual'"
        conn.execute(f"""INSERT INTO place_entrances (place_id,name,row,col,enabled,source)
            SELECT place_id,name,row,col,enabled,source FROM (
                SELECT e.place_id,e.name,e.row,e.col,e.enabled,{source} AS source,
                    ROW_NUMBER() OVER (PARTITION BY e.place_id ORDER BY
                        CASE WHEN e.enabled=1 AND c.cell_type=2 THEN 0
                             WHEN e.enabled=1 THEN 1 ELSE 2 END, e.id) AS priority
                FROM legacy_place_entrances e
                LEFT JOIN map_cells c ON c.row=e.row AND c.col=e.col
            ) WHERE priority=1""")
        if conn.execute("SELECT 1 FROM legacy_place_entrances GROUP BY place_id HAVING count(*) > 1").fetchone():
            conn.execute("UPDATE maps SET revision=revision+1 WHERE id=1")
        conn.execute(f"""INSERT INTO campus_route_history ({HISTORY_FIELDS})
            SELECT {HISTORY_FIELDS} FROM legacy_campus_route_history""")
        for table in reversed(TABLES):
            conn.execute(f"DROP TABLE legacy_{table}")

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
        conn.execute("INSERT INTO maps (id, name, rows, cols, revision) VALUES (1, ?, 1, 1, ?)",
                     ("校园地图", revision))
        self._write_map(conn, state)
        if has_history:
            conn.execute(f"""INSERT INTO campus_route_history ({HISTORY_FIELDS})
                SELECT {HISTORY_FIELDS} FROM legacy_route_history""")
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
        entrances = single_entrances(entrances, state["grid"])
        for name, (row, col) in state["places"].items():
            if not (0 <= row < rows and 0 <= col < cols):
                raise ValueError(f"地点坐标超出地图：{name}")
            cursor = conn.execute("INSERT INTO places (name, kind, row, col, status) VALUES (?, ?, ?, ?, ?)",
                                  (name, kinds.get(name), row, col, statuses.get(name)))
            for entry in entrances.get(name, []):
                row, col = entry["point"]
                if not (0 <= row < rows and 0 <= col < cols):
                    raise ValueError(f"入口坐标超出地图：{name} / {entry['name']}")
                conn.execute("""INSERT INTO place_entrances (place_id, name, row, col, enabled, source)
                                VALUES (?, ?, ?, ?, ?, ?)""",
                             (cursor.lastrowid, entry["name"], row, col, int(entry.get("enabled", True)),
                              entry.get("source", "manual")))

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
            state = self.map_info.copy()
            state.update(name=map_row["name"], classes=classes, grid=_walkability(classes),
                         places={}, place_kinds={}, place_status={}, entrances={})
            if map_row["source_hash"] is not None:
                state["source_hash"] = map_row["source_hash"]
            for place in conn.execute("SELECT * FROM places ORDER BY id"):
                name = place["name"]
                state["places"][name] = [place["row"], place["col"]]
                if place["kind"] is not None:
                    state["place_kinds"][name] = place["kind"]
                if place["status"] is not None:
                    state["place_status"][name] = place["status"]
            for entry in conn.execute("""SELECT p.name AS place_name, e.name, e.row, e.col, e.enabled, e.source
                FROM place_entrances AS e JOIN places AS p ON e.place_id=p.id
                ORDER BY p.id"""):
                entrance = {
                    "name": entry["name"], "point": [entry["row"], entry["col"]], "enabled": bool(entry["enabled"]),
                }
                if entry["source"] == "map_inferred":
                    entrance["source"] = entry["source"]
                state["entrances"].setdefault(entry["place_name"], []).append(entrance)
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
            item["snapshot"] = _state_2d(item["snapshot"])
            for field in ("path", "visited"):
                item[field] = [_point_2d(point) for point in item[field]]
            item["path_length"] = len(item["path"]) - 1 if item["found"] else None
            item["expanded_count"] = len(item["visited"])
            result.append(item)
        return result
