"""以 PDF 的行列坐标显示分类网格和真实参与搜索的路径格子。"""

from base64 import b64encode
from html import escape

import plotly.graph_objects as go

from database.pdf_map import ROWS, COLS, CLASS_NAMES

COLORS = ("#f4f6f5", "#ead39b", "#a6d5bd", "#e6afb1")


def _overlay(fig, points, name, color, show_grid=False):
    points = {(p[-2], p[-1]) for p in points}
    if not points:
        return
    fig.add_trace(go.Heatmap(
        x=[c+.5 for c in range(COLS)], y=[r+.5 for r in range(ROWS)],
        z=[[1 if (r, c) in points else None for c in range(COLS)] for r in range(ROWS)],
        colorscale=[[0, color], [1, color]], showscale=False,
        xgap=1 if show_grid else 0, ygap=1 if show_grid else 0, hoverongaps=False,
        customdata=[[[r, c] for c in range(COLS)] for r in range(ROWS)],
        hovertemplate=name + " · 行 %{customdata[0]}，列 %{customdata[1]}<extra></extra>",
        name=name))


def pdf_map_figure(layout, state, start=None, goal=None, result=None, step=None,
                   show_background=False, selected=None, show_building_labels=False,
                   access_start=None, access_goal=None, show_grid=False,
                   show_visited=False, focus=False):
    fig = go.Figure()
    if show_background:
        fig.add_layout_image(source="data:image/png;base64," + b64encode(layout["background"]).decode(),
                             xref="x", yref="y", x=0, y=0, sizex=COLS, sizey=ROWS,
                             sizing="stretch", xanchor="left", yanchor="top", layer="below")
    scale = []
    for i, color in enumerate(COLORS):
        scale.extend([[i/4, color], [(i+1)/4, color]])
    fig.add_trace(go.Heatmap(
        x=[c+.5 for c in range(COLS)], y=[r+.5 for r in range(ROWS)],
        z=state["classes"], zmin=-.5, zmax=3.5, colorscale=scale,
        text=[[CLASS_NAMES[v] for v in row] for row in state["classes"]],
        customdata=[[[r, c] for c in range(COLS)] for r in range(ROWS)],
        hovertemplate="%{text} · 行 %{customdata[0]}，列 %{customdata[1]}<extra></extra>",
        xgap=1 if show_grid else 0, ygap=1 if show_grid else 0,
        opacity=.25 if show_background else 1,
        showscale=False, name="PDF 分类"))
    if result:
        count = result.expanded_count if step is None else step
        if show_visited:
            _overlay(fig, result.visited_order[:count], "已扩展节点", "#f5b44f", show_grid)
        if result.found and count == result.expanded_count:
            _overlay(fig, result.path, "A* 路径", "#2563eb", show_grid)
    for point, name, color in ((start, "起点", "#087f23"), (goal, "终点", "#be123c"),
                               (selected, "所选格子", "#9333ea"),
                               (access_start, "起点道路接入", "#0d9488"),
                               (access_goal, "终点道路接入", "#db2777")):
        if point is not None:
            _overlay(fig, [point], name, color, show_grid)
    if state["places"]:
        names = list(state["places"])
        points = [state["places"][name] for name in names]
        kinds = [state.get("place_kinds",{}).get(name,"建筑") for name in names]
        highlighted = {}
        for point, label, color in ((start,"起点","#15803d"),(goal,"终点","#be123c"),
                                    (selected,"所选地点","#7c3aed")):
            if point is not None:
                highlighted[tuple(point[-2:])] = label, color
        point_colors = [highlighted.get(tuple(p[-2:]),("", "#475569"))[1] for p in points]
        fig.add_trace(go.Scatter(
            x=[p[2]+.5 for p in points], y=[p[1]+.5 for p in points],
            mode="markers+text" if show_building_labels else "markers",
            text=names, textposition="top center",
            textfont=dict(size=10,color="#334155"),
            customdata=[[*p,kind] for p,kind in zip(points,kinds)],
            marker=dict(size=[11 if tuple(p[-2:]) in highlighted else 7 for p in points],
                        color=point_colors, symbol="circle",
                        line=dict(color="white",width=1)),
            name="地点位置标记",
            hovertemplate="%{text} · %{customdata[3]}<br>行 %{customdata[1]}，列 %{customdata[2]}<br>地点中心与导航入口分开<extra></extra>"))
        if not show_building_labels:
            for name,p in zip(names,points):
                if tuple(p[-2:]) in highlighted:
                    label,color = highlighted[tuple(p[-2:])]
                    fig.add_annotation(x=p[2]+.5,y=p[1]+.5,
                        text=escape(label+" · "+name),showarrow=False,yshift=18,
                        font=dict(size=11,color=color),bgcolor="rgba(255,255,255,.94)",
                        bordercolor=color,borderpad=4,
                        xanchor="left" if p[2]<10 else "right" if p[2]>80 else "center")
    x_range,y_range = [0,COLS],[ROWS,0]
    if focus:
        points = [p for p in (start,goal,selected,access_start,access_goal) if p is not None]
        if result and result.found:
            points += result.path
        if points:
            cols,rows = [p[-1] for p in points],[p[-2] for p in points]
            x_range = [max(0,min(cols)-8),min(COLS,max(cols)+9)]
            y_range = [min(ROWS,max(rows)+13),max(0,min(rows)-12)]
    fig.update_xaxes(range=x_range, visible=show_grid, title="列（0～89）", side="top", dtick=10,
                     showgrid=False, zeroline=False, constrain="domain")
    fig.update_yaxes(range=y_range, visible=show_grid, title="行（0～179）", dtick=10,
                     showgrid=False, zeroline=False, scaleanchor="x", scaleratio=1,
                     constrain="domain", constraintoward="top")
    fig.update_layout(height=900, margin=dict(l=35 if show_grid else 10, r=10,
                                             t=35 if show_grid else 10, b=10), showlegend=False,
                      plot_bgcolor="white", paper_bgcolor="white", dragmode="pan",
                      hoverlabel=dict(bgcolor="white",font=dict(size=12,color="#334155")),
                      uirevision="pdf-"+layout["source_hash"]+str((x_range,y_range,focus)))
    return fig
