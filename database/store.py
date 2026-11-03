"""用 SQLite 保存一张地图、地点与查询时的路线快照。"""

from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3


DB_PATH = Path(os.environ.get("CAMPUSPATH_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "campuspath.db"))
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
MAP_ID = 1
DEMO_GRID = [
    [1, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 1, 0, 0, 1],
    [1, 0, 1, 0, 1, 0, 0, 1],
    [1, 0, 1, 0, 0, 0, 1, 1],
    [1, 0, 0, 0, 1, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 1],
]
DEMO_PLACES = {
    "模拟教学楼入口": (1, 1), "模拟图书馆入口": (1, 5),
    "模拟食堂入口": (4, 2), "模拟宿舍入口": (4, 6),
}


def _connect(db_path):
    connection = sqlite3.connect(str(db_path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _validate_grid(grid):
    if not isinstance(grid, list) or not grid or not all(isinstance(row, list) and row for row in grid):
        raise ValueError("地图必须是非空二维列表")
    cols = len(grid[0])
    if any(len(row) != cols or any(type(cell) is not int or cell not in (0, 1) for cell in row) for row in grid):
        raise ValueError("地图必须为矩形，格子只能是整数 0 或 1")


def _validate_place(name, row, col, grid):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("地点名称不能为空")
    if type(row) is not int or type(col) is not int or not (0 <= row < len(grid) and 0 <= col < len(grid[0])):
        raise ValueError("地点坐标超出地图范围")
    if grid[row][col] != 0:
        raise ValueError("地点入口必须位于可通行区域")
    return name.strip()


def init_database(db_path=DB_PATH):
    """仅当没有地图时写入明确标注为模拟的初始数据。"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(db_path)) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM maps WHERE id = ?", (MAP_ID,)).fetchone() is None:
                conn.execute("INSERT INTO maps (id, name, rows, cols) VALUES (?, ?, ?, ?)",
                             (MAP_ID, "模拟校园地图", len(DEMO_GRID), len(DEMO_GRID[0])))
                conn.executemany("INSERT INTO map_cells VALUES (?, ?, ?, ?)",
                                 [(MAP_ID, r, c, v) for r, row in enumerate(DEMO_GRID) for c, v in enumerate(row)])
                conn.executemany("INSERT INTO places (map_id, name, row, col) VALUES (?, ?, ?, ?)",
                                 [(MAP_ID, name, r, c) for name, (r, c) in DEMO_PLACES.items()])


def _load_map(conn):
    record = conn.execute("SELECT id, name, rows, cols FROM maps WHERE id = ?", (MAP_ID,)).fetchone()
    if record is None:
        raise ValueError("地图不存在，请先初始化数据库")
    grid = [[None] * record["cols"] for _ in range(record["rows"])]
    cells = conn.execute("SELECT row, col, cell_type FROM map_cells WHERE map_id = ?", (MAP_ID,)).fetchall()
    for cell in cells:
        grid[cell["row"]][cell["col"]] = cell["cell_type"]
    _validate_grid(grid)
    places = {p["name"]: (p["row"], p["col"]) for p in conn.execute(
        "SELECT name, row, col FROM places WHERE map_id = ? ORDER BY id", (MAP_ID,))}
    return {"id": record["id"], "name": record["name"], "grid": grid, "places": places}


def load_map(db_path=DB_PATH):
    with closing(_connect(db_path)) as conn:
        return _load_map(conn)


def save_grid(grid, db_path=DB_PATH, *, expected_grid=None, expected_places=None):
    _validate_grid(grid)
    with closing(_connect(db_path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = _load_map(conn)
        if expected_grid is not None and expected_grid != existing["grid"]:
            raise ValueError("地图已被其他会话修改，请重新加载后再编辑")
        if expected_places is not None and expected_places != existing["places"]:
            raise ValueError("地点已被其他会话修改，请重新加载后再编辑")
        if len(grid) != len(existing["grid"]) or len(grid[0]) != len(existing["grid"][0]):
            raise ValueError("暂不支持改变地图尺寸")
        for name, (r, c) in existing["places"].items():
            _validate_place(name, r, c, grid)
        conn.executemany("UPDATE map_cells SET cell_type = ? WHERE map_id = ? AND row = ? AND col = ?",
                         [(v, MAP_ID, r, c) for r, row in enumerate(grid) for c, v in enumerate(row)])


def replace_map(name, grid, places, *, expected_name, expected_grid, expected_places, db_path=DB_PATH):
    """原子替换地图和地点；旧查询记录保留各自的历史快照。"""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("地图名称不能为空")
    _validate_grid(grid)
    if not isinstance(places, dict):
        raise ValueError("地点必须是名称到坐标的字典")

    normalized = {}
    for place_name, point in places.items():
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("地点坐标必须包含行和列")
        row, col = point
        cleaned = _validate_place(place_name, row, col, grid)
        if cleaned in normalized:
            raise ValueError("地点名称不能重复")
        normalized[cleaned] = (row, col)

    with closing(_connect(db_path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = _load_map(conn)
        if expected_name != existing["name"] or expected_grid != existing["grid"] or expected_places != existing["places"]:
            raise ValueError("地图或地点已被其他会话修改，请重新加载后再导入")
        conn.execute("UPDATE maps SET name = ?, rows = ?, cols = ? WHERE id = ?",
                     (name.strip(), len(grid), len(grid[0]), MAP_ID))
        conn.execute("DELETE FROM map_cells WHERE map_id = ?", (MAP_ID,))
        conn.executemany("INSERT INTO map_cells (map_id, row, col, cell_type) VALUES (?, ?, ?, ?)",
                         [(MAP_ID, r, c, v) for r, line in enumerate(grid) for c, v in enumerate(line)])
        conn.execute("DELETE FROM places WHERE map_id = ?", (MAP_ID,))
        conn.executemany("INSERT INTO places (map_id, name, row, col) VALUES (?, ?, ?, ?)",
                         [(MAP_ID, place_name, r, c) for place_name, (r, c) in normalized.items()])


def add_place(name, row, col, db_path=DB_PATH):
    with closing(_connect(db_path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        name = _validate_place(name, row, col, _load_map(conn)["grid"])
        try:
            conn.execute("INSERT INTO places (map_id, name, row, col) VALUES (?, ?, ?, ?)", (MAP_ID, name, row, col))
        except sqlite3.IntegrityError as exc:
            raise ValueError("地点名称已存在") from exc


def update_place(old_name, name, row, col, db_path=DB_PATH):
    with closing(_connect(db_path)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        name = _validate_place(name, row, col, _load_map(conn)["grid"])
        try:
            cursor = conn.execute("UPDATE places SET name = ?, row = ?, col = ? WHERE map_id = ? AND name = ?",
                                  (name, row, col, MAP_ID, old_name))
        except sqlite3.IntegrityError as exc:
            raise ValueError("地点名称已存在") from exc
        if cursor.rowcount == 0:
            raise ValueError("地点不存在")


def delete_place(name, db_path=DB_PATH):
    with closing(_connect(db_path)) as conn, conn:
        cursor = conn.execute("DELETE FROM places WHERE map_id = ? AND name = ?", (MAP_ID, name))
        if cursor.rowcount == 0:
            raise ValueError("地点不存在")


def save_route(start_name, goal_name, grid, result, db_path=DB_PATH, *, expected_start=None, expected_goal=None):
    """将查询输入、路径、扩展顺序和网格快照在一次事务中保存。"""
    _validate_grid(grid)
    with closing(_connect(db_path)) as conn, conn:
        # 读取地点和写入记录使用同一写事务，避免并发更改地点。
        conn.execute("BEGIN IMMEDIATE")
        data = _load_map(conn)
        if len(grid) != len(data["grid"]) or len(grid[0]) != len(data["grid"][0]):
            raise ValueError("查询地图尺寸与保存的地图不一致")
        if start_name not in data["places"] or goal_name not in data["places"]:
            raise ValueError("起点或终点不存在，请重新加载")
        start, goal = data["places"][start_name], data["places"][goal_name]
        if (expected_start is None) != (expected_goal is None):
            raise ValueError("必须同时提供查询时的起点和终点")
        if expected_start is not None and (start != expected_start or goal != expected_goal):
            raise ValueError("地点坐标已变化，请重新加载并搜索")
        _validate_place(start_name, *start, grid)
        _validate_place(goal_name, *goal, grid)
        if result.found and (not result.path or result.path[0] != start or result.path[-1] != goal):
            raise ValueError("路线与当前起终点不一致，请重新搜索")
        if not result.found and result.path:
            raise ValueError("不可达结果不应包含路径")
        cursor = conn.execute("""INSERT INTO route_records
            (map_id, start_name, goal_name, start_row, start_col, goal_row, goal_col, algorithm,
             found, path_length, expanded_count, elapsed_ms, grid_snapshot, path_snapshot, visited_snapshot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (MAP_ID, start_name, goal_name, *start, *goal, "A*", int(result.found), result.path_length,
             result.expanded_count, result.elapsed_ms, json.dumps(grid), json.dumps(result.path), json.dumps(result.visited_order)))
        return cursor.lastrowid


def list_routes(db_path=DB_PATH):
    with closing(_connect(db_path)) as conn:
        records = []
        for row in conn.execute("SELECT * FROM route_records WHERE map_id = ? ORDER BY id DESC", (MAP_ID,)):
            record = dict(row)
            for field in ("grid_snapshot", "path_snapshot", "visited_snapshot"):
                record[field] = json.loads(record[field])
            record["found"] = bool(record["found"])
            records.append(record)
        return records
