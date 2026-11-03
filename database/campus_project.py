"""保存校园示意网格、近似地点和查询历史，不覆盖原模拟地图。"""

from contextlib import closing
import json
import sqlite3

from database.store import DB_PATH, init_database
from database.survey import ROWS, COLS
from visualization.user_markings import PATHS, STREETS, blocked_grid_cells, image_point

LAYER_NAMES = ("校内", "校外道路", "天桥")
NAMED_ROADS = [((102, 214), (269, 214)), ((343, 230), (343, 406)),
               ((343, 429), (343, 508)), ((200, 509), (200, 632)),
               ((275, 637), (465, 637)), ((405, 638), (405, 756)), ((343, 638), (343, 756))]


def map_cell(x, y):
    return (min(ROWS - 1, max(0, int((y - 24) * ROWS / 756))),
            min(COLS - 1, max(0, int((x - 86) * COLS / 416))))


def marked_cell(point):
    return map_cell(*image_point(point))


def draw_line(grid, start, end, value=0):
    """将两个图面网格点连接成四方向阶梯线。"""
    row, col = start
    end_row, end_col = end
    grid[row][col] = value
    while (row, col) != (end_row, end_col):
        if col != end_col:
            col += 1 if col < end_col else -1
            grid[row][col] = value
        if row != end_row:
            row += 1 if row < end_row else -1
            grid[row][col] = value


def _draw_paths(grid, paths, convert):
    for points in paths:
        for a, b in zip(points, points[1:]):
            draw_line(grid, convert(a), convert(b))


def initial_campus(layout):
    """以用户手绘路线生成示意网格；地点均为附近道路，非已核实入口。"""
    campus, street, bridge = [[[1] * COLS for _ in range(ROWS)] for _ in range(3)]
    _draw_paths(campus, PATHS, marked_cell)
    _draw_paths(campus, NAMED_ROADS, lambda p: map_cell(*p))
    _draw_paths(street, STREETS.values(), marked_cell)
    red = blocked_grid_cells(include_north_gate=False)
    for row, col in red:
        campus[row][col] = street[row][col] = 1

    # 天桥接到用户标注的北、南侧校内道路，不在与海油大街交叉处换层。
    north, south = marked_cell((670, 960)), marked_cell((670, 1044))
    north_road, south_road = marked_cell((640, 960)), marked_cell((646, 1044))
    if north[1] != south[1]:
        raise ValueError("天桥两端网格未对齐")
    # 此处是根据手绘图近似建立的短连接，后续需要现场核对。
    if north not in red and north_road not in red:
        draw_line(campus, north_road, north)
    if south not in red and south_road not in red:
        draw_line(campus, south_road, south)
    draw_line(bridge, north, south)
    portals = [[0, 2, *north, "天桥北端"], [0, 2, *south, "天桥南端"]]

    # 按用户说明，天桥下南、北侧各有门；坐标只是截图近似。
    north_gate, south_gate = marked_cell((670, 968)), marked_cell((670, 1019))
    sea = marked_cell((670, 986))
    north_district_gate = marked_cell((640, 610))
    draw_line(street, sea, south_gate)
    for point in (north_gate, south_gate):
        if point not in red:
            campus[point[0]][point[1]] = 0
    # 短连接仅为示意，必须继续核对门、道路和天桥入口的实际位置。
    if south_gate not in red:
        draw_line(campus, south_gate, south)
    portals.extend([[0, 1, *north_gate, "北侧限时门"], [0, 1, *south_gate, "南侧门"],
                    [0, 1, *north_district_gate, "北区北门"]])
    for row, col in red:
        campus[row][col] = street[row][col] = 1

    available = [(r, c) for r in range(ROWS) for c in range(COLS) if campus[r][c] == 0]
    places = {}
    for item in layout.get("places", []):
        name = item["name"].strip()
        row, col = map_cell(item["x"], item["y"])
        nearest = min(available, key=lambda p: abs(p[0] - row) + abs(p[1] - col))
        # ponytail: 近邻仅用于示意，不自动认定为建筑入口；精确入口应人工录入。
        if abs(nearest[0] - row) + abs(nearest[1] - col) <= 3:
            key = name
            suffix = 2
            while key in places:
                key = f"{name}（{suffix}）"
                suffix += 1
            places[key] = [0, *nearest]
    return {"grids": [campus, street, bridge], "places": places,
            "place_status": {name: "图面近似" for name in places}, "portals": portals,
            "north_gate_open": False, "source": "用户确认道路及手绘图；图面坐标和入口为近似"}


def init_campus(layout, db_path=DB_PATH):
    init_database(db_path)
    with closing(sqlite3.connect(str(db_path))) as conn, conn:
        conn.execute("CREATE TABLE IF NOT EXISTS campus_project (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL)")
        conn.execute("""CREATE TABLE IF NOT EXISTS campus_route_history (
            id INTEGER PRIMARY KEY, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            start_name TEXT NOT NULL, goal_name TEXT NOT NULL, snapshot TEXT NOT NULL,
            found INTEGER NOT NULL, path TEXT NOT NULL, visited TEXT NOT NULL, path_length INTEGER, expanded_count INTEGER NOT NULL)""")
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM campus_project WHERE id=1").fetchone() is None:
            conn.execute("INSERT INTO campus_project VALUES (1, 0, ?)", (json.dumps(initial_campus(layout), ensure_ascii=False),))


def load_campus(db_path=DB_PATH):
    with closing(sqlite3.connect(str(db_path))) as conn:
        row = conn.execute("SELECT revision, data FROM campus_project WHERE id=1").fetchone()
        if row is None:
            raise ValueError("请先初始化校园地图")
        return row[0], json.loads(row[1])


def save_campus(state, expected_revision, db_path=DB_PATH):
    with closing(sqlite3.connect(str(db_path))) as conn, conn:
        cursor = conn.execute("UPDATE campus_project SET data=?, revision=revision+1 WHERE id=1 AND revision=?",
                              (json.dumps(state, ensure_ascii=False), expected_revision))
        if cursor.rowcount != 1:
            raise ValueError("地图已被其他会话修改，请重新加载后再编辑")
    return expected_revision + 1


def active_portals(state):
    links = []
    for a, b, r, c, name in state["portals"]:
        if name == "北侧限时门" and not state["north_gate_open"]:
            continue
        links.append(((a, r, c), (b, r, c)))
    return links


def save_campus_route(start, goal, state, result, db_path=DB_PATH):
    with closing(sqlite3.connect(str(db_path))) as conn, conn:
        conn.execute("INSERT INTO campus_route_history (start_name,goal_name,snapshot,found,path,visited,path_length,expanded_count) VALUES (?,?,?,?,?,?,?,?)",
                     (start, goal, json.dumps(state, ensure_ascii=False), int(result.found), json.dumps(result.path),
                      json.dumps(result.visited_order), result.path_length, result.expanded_count))


def campus_history(db_path=DB_PATH):
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM campus_route_history ORDER BY id DESC").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for field in ("snapshot", "path", "visited"):
            item[field] = json.loads(item[field])
        result.append(item)
    return result


class CampusMapService:
    """地图服务：初始化、保存校园地图并维护路线历史。"""
    def __init__(self, layout, db_path=DB_PATH):
        self.db_path = db_path
        init_campus(layout, db_path)

    def load(self):
        return load_campus(self.db_path)

    def save(self, state, revision):
        return save_campus(state, revision, self.db_path)

    def save_route(self, start, goal, state, result):
        return save_campus_route(start, goal, state, result, self.db_path)

    def history(self):
        return campus_history(self.db_path)
