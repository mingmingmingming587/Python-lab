"""校园道路采集：与模拟地图分开存储，坐标对应参考图面网格。"""

from contextlib import closing
import sqlite3

from database.store import DB_PATH, init_database

ROWS, COLS = 72, 40
STATUSES = ("待核实", "已核实可通行", "已核实不可通行")


def init_survey(db_path=DB_PATH):
    init_database(db_path)
    with closing(sqlite3.connect(str(db_path))) as conn, conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS campus_survey (
            id INTEGER PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
            row1 INTEGER NOT NULL, col1 INTEGER NOT NULL, row2 INTEGER NOT NULL, col2 INTEGER NOT NULL,
            status TEXT NOT NULL, source TEXT NOT NULL, note TEXT NOT NULL DEFAULT ''
        )""")


def list_survey(db_path=DB_PATH):
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM campus_survey ORDER BY id")]


def save_survey(kind, name, start, end, status, source, note="", *, record_id=None, db_path=DB_PATH):
    if kind not in ("道路", "入口") or status not in STATUSES:
        raise ValueError("记录类型或核实状态无效")
    if not isinstance(name, str) or not name.strip() or not isinstance(source, str) or not source.strip():
        raise ValueError("名称和信息来源不能为空")
    if not isinstance(note, str):
        raise ValueError("备注必须是文字")
    for point in (start, end):
        if (not isinstance(point, (tuple, list)) or len(point) != 2
                or any(type(n) is not int for n in point)
                or not (0 <= point[0] < ROWS and 0 <= point[1] < COLS)):
            raise ValueError("坐标超出校园采集网格范围")
    if kind == "入口" and tuple(start) != tuple(end):
        raise ValueError("入口只能对应一个网格")
    if start[0] != end[0] and start[1] != end[1]:
        raise ValueError("每段道路须为水平或垂直线；转弯请拆成多段")
    values = (kind, name.strip(), *start, *end, status, source.strip(), note.strip())
    with closing(sqlite3.connect(str(db_path))) as conn, conn:
        if record_id is None:
            conn.execute("INSERT INTO campus_survey (kind,name,row1,col1,row2,col2,status,source,note) VALUES (?,?,?,?,?,?,?,?,?)", values)
        else:
            cursor = conn.execute("UPDATE campus_survey SET kind=?,name=?,row1=?,col1=?,row2=?,col2=?,status=?,source=?,note=? WHERE id=?", (*values, record_id))
            if cursor.rowcount != 1:
                raise ValueError("记录已不存在，请刷新页面")


def delete_survey(record_id, db_path=DB_PATH):
    with closing(sqlite3.connect(str(db_path))) as conn, conn:
        if conn.execute("DELETE FROM campus_survey WHERE id=?", (record_id,)).rowcount != 1:
            raise ValueError("记录已不存在，请刷新页面")


def cells(record):
    r1, c1, r2, c2 = (record[key] for key in ("row1", "col1", "row2", "col2"))
    if r1 == r2:
        return [(r1, col) for col in range(min(c1, c2), max(c1, c2) + 1)]
    return [(row, c1) for row in range(min(r1, r2), max(r1, r2) + 1)]


def verified_grid(records):
    """未知默认为不可通行；已核实不可通行覆盖已核实道路。"""
    grid = [[1] * COLS for _ in range(ROWS)]
    for status, value in (("已核实可通行", 0), ("已核实不可通行", 1)):
        for record in records:
            if record["kind"] == "道路" and record["status"] == status:
                for row, col in cells(record):
                    grid[row][col] = value
    return grid


def image_position(row, col):
    """参考图面网格的格子中心；不是经纬度或真实距离。"""
    return 86 + (col + 0.5) * 416 / COLS, 24 + (row + 0.5) * 756 / ROWS
