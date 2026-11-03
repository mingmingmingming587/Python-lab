"""校园图面上的通行网格、路线格子与 A* 搜索过程。"""
import plotly.graph_objects as go

from database.campus_project import LAYER_NAMES
from database.survey import ROWS, COLS, image_position
from visualization.campus_diagram import build_campus_diagram
from visualization.user_markings import blocked_grid_cells


def add_cells(fig, cells, name, color, opacity=0.8):
    """用图面坐标绘制网格，缩放地图时格子也随之缩放。"""
    points = set(cells)
    if not points:
        return
    z = [[1 if (r, c) in points else None for c in range(COLS)] for r in range(ROWS)]
    fig.add_trace(go.Heatmap(
        x=[image_position(0, c)[0] for c in range(COLS)],
        y=[image_position(r, 0)[1] for r in range(ROWS)], z=z,
        customdata=[[[r, c] for c in range(COLS)] for r in range(ROWS)],
        colorscale=[[0, color], [1, color]], zmin=0, zmax=1,
        showscale=False, opacity=opacity, name=name, xgap=1, ygap=1, hoverongaps=False,
        hovertemplate=name + " · 行 %{customdata[0]}，列 %{customdata[1]}<extra></extra>"))


def navigation_figure(layout, state, start=None, goal=None, result=None, step=None,
                      show_grid=True, show_places=False, grid_layer=0):
    fig = build_campus_diagram(layout["places"], footprints=layout.get("footprints"))
    if show_grid:
        grid = state["grids"][grid_layer]
        blocked = blocked_grid_cells(include_north_gate=False) if grid_layer != 2 else set()
        closed = [(r, c) for r in range(ROWS) for c in range(COLS) if grid[r][c] == 1 and (r, c) not in blocked]
        open_cells = [(r, c) for r in range(ROWS) for c in range(COLS) if grid[r][c] == 0 and (r, c) not in blocked]
        add_cells(fig, closed, LAYER_NAMES[grid_layer] + " · 不可通行或未录入", "#aab2b8", 0.12)
        add_cells(fig, open_cells, LAYER_NAMES[grid_layer] + " · 可通行", "#22a35a", 0.65)
        add_cells(fig, blocked, "标注禁行", "#e14242", 0.7)
        for a, b, row, col, name in state["portals"]:
            if name == "北侧限时门" and grid_layer in (a, b):
                add_cells(fig, [(row, col)], "北侧限时门 · " + ("设为开放" if state["north_gate_open"] else "设为关闭"), "#d99a00", 0.9)
    if show_places and state["places"]:
        names = list(state["places"])
        positions = [state["places"][name] for name in names]
        xy = [image_position(p[1], p[2]) for p in positions]
        fig.add_trace(go.Scatter(x=[p[0] for p in xy], y=[p[1] for p in xy], mode="markers",
                                 name="已保存地点", text=names, customdata=positions,
                                 marker=dict(size=9, color="#e76f22"),
                                 hovertemplate="%{text}<br>层 %{customdata[0]} · 行 %{customdata[1]}，列 %{customdata[2]}<extra></extra>"))
    if result:
        count = len(result.visited_order) if step is None else step
        add_cells(fig, [(p[1], p[2]) for p in result.visited_order[:count]], "已扩展节点", "#f59e0b", 0.7)
        if result.found and count == len(result.visited_order):
            for layer, color in enumerate(("#2563eb", "#7c3aed", "#06b6d4")):
                add_cells(fig, [(p[1], p[2]) for p in result.path if p[0] == layer], LAYER_NAMES[layer] + "路线", color)
    for point, name, color in ((start, "起点", "#16a34a"), (goal, "终点", "#dc2626")):
        if point is not None:
            x, y = image_position(point[1], point[2])
            fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", text=[name], textposition="top center",
                                     name=name, marker=dict(size=14, color=color)))
    return fig
