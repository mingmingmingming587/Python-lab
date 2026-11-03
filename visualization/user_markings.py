"""用户标注的校园道路线索：图面近似描绘，不直接作为 A* 路网。"""

import plotly.graph_objects as go

# 坐标为用户标注图的像素，映射到当前图面；截图缩放及手绘笔宽会引入误差。
def image_point(point):
    x, y = point
    return (86 + (x - 92) / 2.142, 24 + (y - 156) / 2.142)


STREETS = {
    "爱民路": [(493, 198), (495, 600), (496, 985)],
    "海油大街": [(112, 986), (493, 986), (670, 986), (918, 986)],
    "金燕大街": [(494, 610), (645, 610), (738, 610)],
}

# 绿色线是用户所画的路线线索，折点是截图上的近似位置；并非逐段测绘。
PATHS = [
    [(288, 308), (470, 308)],
    [(517, 610), (517, 716), (640, 716), (739, 716)],
    [(517, 779), (640, 779), (739, 779)],
    [(518, 890), (640, 890), (765, 890)],
    [(584, 779), (584, 890)], [(640, 610), (640, 961)],
    [(736, 610), (739, 779), (765, 800), (765, 890), (745, 960)],
    [(517, 890), (517, 959)],
    [(125, 1019), (122, 1105), (154, 1115), (309, 1107), (320, 1093), (314, 1020)],
    [(178, 1020), (178, 1111)], [(126, 1020), (315, 1020)],
    [(314, 1104), (333, 1140), (352, 1191), (494, 1196), (599, 1196), (749, 1196), (916, 1195)],
    [(494, 1196), (494, 1052), (555, 1044), (646, 1044), (749, 1044), (920, 1025)],
    [(646, 1044), (646, 1104), (749, 1105)], [(749, 1044), (749, 1196)],
    [(599, 1196), (599, 1403), (599, 1470)],
    [(599, 1288), (705, 1290), (705, 1197)], [(599, 1355), (705, 1357), (705, 1290)],
    [(705, 1235), (837, 1238), (886, 1234)], [(705, 1290), (765, 1290), (840, 1290), (887, 1290)],
    [(705, 1357), (840, 1357), (887, 1357)], [(837, 1238), (840, 1400), (886, 1400)],
    [(886, 1196), (886, 1471)], [(705, 1357), (720, 1367), (720, 1468)],
    [(599, 1469), (720, 1469), (886, 1471), (904, 1471)],
    [(170, 1474), (171, 1414), (180, 1382), (330, 1385), (340, 1401)],
    [(171, 1430), (330, 1430)], [(171, 1465), (330, 1465)],
    [(330, 1385), (332, 1465)],
    [(351, 1388), (377, 1408), (424, 1408)],
    [(132, 1510), (171, 1510), (171, 1538), (242, 1538), (350, 1542), (468, 1541)],
    [(183, 1537), (173, 1570), (178, 1667), (193, 1684)],
    [(242, 1538), (242, 1601), (242, 1665), (242, 1726)],
    [(350, 1542), (350, 1603), (350, 1664), (350, 1730)],
    [(400, 1542), (400, 1602), (400, 1664), (400, 1727)],
    [(468, 1541), (468, 1602), (468, 1665), (468, 1726)],
    [(183, 1602), (350, 1603), (468, 1602)],
    [(183, 1665), (350, 1664), (468, 1665)],
    [(193, 1684), (195, 1723), (240, 1732), (350, 1734), (468, 1732), (528, 1724), (541, 1706)],
    [(351, 1633), (468, 1633)], [(351, 1685), (468, 1685)],
    [(541, 1705), (645, 1704), (780, 1704), (901, 1705)],
    [(541, 1668), (640, 1668), (779, 1668), (900, 1668)],
    [(778, 1471), (778, 1668)], [(901, 1471), (901, 1705)],
]

# 不将图片上看似重叠的天桥和地面道路合并为一个路口。
BLOCKED = [
    [(111, 1011), (209, 1011)], [(259, 1011), (321, 1011)],
    [(446, 1011), (637, 1011)], [(697, 1011), (920, 1011)],
    [(920, 1025), (920, 1193)], [(519, 780), (519, 881)],
    [(433, 1405), (457, 1397), (481, 1393), (508, 1397), (535, 1422)],
]
UNCERTAIN = [[(523, 1500), (523, 1693)]]
BRIDGE = [(670, 962), (670, 1024)]
GATES = [((670, 968), "天桥北侧门（非全天开放，默认关闭）", "#e5a600"),
         ((670, 1019), "天桥南侧门（位置待核实）", "#176eb3")]


def candidate_records():
    """将主要道路和门的位置作为可编辑的待核实线索，不打开网格。"""
    from database.survey import COLS, ROWS

    def cell(point):
        x, y = image_point(point)
        return (min(ROWS - 1, max(0, int((y - 24) * ROWS / 756))),
                min(COLS - 1, max(0, int((x - 86) * COLS / 416))))

    records = []
    for name, points in STREETS.items():
        start, end = cell(points[0]), cell(points[-1])
        if start[0] != end[0] and start[1] != end[1]:
            raise ValueError(f"{name} 的近似线索不是水平或垂直，需拆分录入")
        records.append(("道路", name + "（用户标注）", start, end))
    for point, name, _ in GATES:
        location = cell(point)
        records.append(("入口", name, location, location))
    return records


def blocked_grid_cells(include_north_gate=True):
    """红线及可选的北侧限时门；不把天桥投影为地面通路。"""
    from database.survey import COLS, ROWS

    cells = set()
    paths = [*BLOCKED]
    if include_north_gate:
        paths.append([(670, 968), (670, 968)])
    for points in paths:
        for first, last in zip(points, points[1:]):
            steps = max(abs(last[0] - first[0]), abs(last[1] - first[1]), 1)
            for i in range(steps + 1):
                t = i / steps
                x, y = image_point((first[0] + (last[0] - first[0]) * t,
                                    first[1] + (last[1] - first[1]) * t))
                row, col = int((y - 24) * ROWS / 756), int((x - 86) * COLS / 416)
                if 0 <= row < ROWS and 0 <= col < COLS:
                    cells.add((row, col))
    return cells


def add_markings(fig):
    """叠加用户标记；仅作待校正图面线索。"""
    for name, points in STREETS.items():
        xy = [image_point(p) for p in points]
        fig.add_trace(go.Scatter(x=[p[0] for p in xy], y=[p[1] for p in xy], mode="lines",
                                 name=name, line=dict(color="#218850", width=5),
                                 hovertemplate=name + " · 用户标注，位置待校正<extra></extra>", showlegend=False))
        x, y = xy[len(xy) // 2]
        fig.add_annotation(x=x, y=y, text=name, showarrow=False, bgcolor="rgba(255,255,255,0.9)",
                           font=dict(color="#136936", size=10))
    for name, paths, color, dash in (("用户标注道路", PATHS, "#288c55", "solid"),
                                      ("红色禁行标记", BLOCKED, "#d82d2d", "solid"),
                                      ("文德楼旁待确认", UNCERTAIN, "#d39d00", "dash"),
                                      ("天桥 · 行人跨街", [BRIDGE], "#176eb3", "dash")):
        x, y = [], []
        for points in paths:
            xy = [image_point(p) for p in points]
            x.extend([*(p[0] for p in xy), None])
            y.extend([*(p[1] for p in xy), None])
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=name, line=dict(color=color, width=3, dash=dash),
                                 hovertemplate=name + " · 图面位置待校正<extra></extra>", showlegend=False))
    for point, name, color in GATES:
        x, y = image_point(point)
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers", name=name,
                                 marker=dict(size=11, color=color, symbol="diamond", line=dict(color="white", width=1)),
                                 hovertemplate=name + "<extra></extra>", showlegend=False))
    return fig
