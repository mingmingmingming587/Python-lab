"""在校园图面叠加网格、分层路径和 A* 搜索过程。"""

import plotly.graph_objects as go

from database.campus_project import LAYER_NAMES
from database.survey import image_position
from visualization.campus_diagram import build_campus_diagram
from visualization.user_markings import add_markings


def navigation_figure(layout, state, start=None, goal=None, result=None, step=None, show_grid=False, show_places=False):
    fig = add_markings(build_campus_diagram(layout["places"], footprints=layout.get("footprints")))
    if show_grid:
        # 只叠加可走格子的中心，避免遮挡建筑和用户标注。
        for layer, color in enumerate(("#56a86d", "#88ad40", "#598add")):
            points = [(r, c) for r, line in enumerate(state["grids"][layer]) for c, value in enumerate(line) if value == 0]
            xy = [image_position(*p) for p in points]
            fig.add_trace(go.Scatter(x=[p[0] for p in xy], y=[p[1] for p in xy], mode="markers", name=LAYER_NAMES[layer] + "可通行格",
                                     customdata=points,
                                     marker=dict(size=5, color=color, opacity=0.65, symbol="square"), showlegend=True,
                                     hovertemplate=LAYER_NAMES[layer] + " · 行 %{customdata[0]}，列 %{customdata[1]}<extra></extra>"))
    if show_places and state["places"]:
        names = list(state["places"])
        positions = [state["places"][name] for name in names]
        xy = [image_position(p[1], p[2]) for p in positions]
        fig.add_trace(go.Scatter(x=[p[0] for p in xy], y=[p[1] for p in xy], mode="markers",
                                 name="已保存地点", text=names, customdata=positions,
                                 marker=dict(size=9, color="#e76f22", line=dict(color="white", width=1)),
                                 hovertemplate="%{text}<br>层 %{customdata[0]} · 行 %{customdata[1]}，列 %{customdata[2]}<extra></extra>"))
    if result:
        count = len(result.visited_order) if step is None else step
        visited = [image_position(p[1], p[2]) for p in result.visited_order[:count]]
        if visited:
            fig.add_trace(go.Scatter(x=[p[0] for p in visited], y=[p[1] for p in visited], mode="markers",
                                     name="已扩展节点", marker=dict(size=5, color="#f59e0b", opacity=0.6)))
        if result.found and count == len(result.visited_order):
            for layer, color in enumerate(("#2563eb", "#7c3aed", "#06b6d4")):
                x, y = [], []
                for point in result.path:
                    if point[0] == layer:
                        px, py = image_position(point[1], point[2])
                        x.append(px); y.append(py)
                    else:
                        x.append(None); y.append(None)
                if any(v is not None for v in x):
                    fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers", name=LAYER_NAMES[layer] + "路线",
                                             line=dict(color=color, width=5), marker=dict(size=4)))
    for point, name, color in ((start, "起点", "#16a34a"), (goal, "终点", "#dc2626")):
        if point is not None:
            x, y = image_position(point[1], point[2])
            fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers+text", text=[name], textposition="top center",
                                     name=name, marker=dict(size=14, color=color, line=dict(color="white", width=2))))
    return fig
