"""以 PDF 的行列坐标显示分类网格和真实参与搜索的路径格子。"""

from base64 import b64encode
from html import escape

import plotly.graph_objects as go

from database.pdf_map import ROWS, COLS, CLASS_NAMES

COLORS = ("#f4f6f5", "#ead39b", "#a6d5bd", "#e6afb1")


def _name_positions(points, names, cell_pixels):
    """尝试八个方向放名称，优先减少文字重叠和超出图面。"""
    height, gap = 15/cell_pixels, 8/cell_pixels
    occupied, positions = [], ["top center"] * len(points)
    for index in sorted(range(len(points)),key=lambda i:points[i]):
        row,col = points[index]
        x,y = col+.5,row+.5
        width = (sum(.55 if ord(c)<128 else 1 for c in names[index])*12+4)/cell_pixels
        candidates = [
            ("top center",x-width/2,y-gap-height),
            ("bottom center",x-width/2,y+gap),
            ("middle right",x+gap,y-height/2),
            ("middle left",x-gap-width,y-height/2),
            ("top right",x+gap,y-gap-height),
            ("top left",x-gap-width,y-gap-height),
            ("bottom right",x+gap,y+gap),
            ("bottom left",x-gap-width,y+gap),
        ]
        def score(candidate):
            _,left,top = candidate
            right,bottom = left+width,top+height
            overlap = sum(max(0,min(right,r)-max(left,l))*max(0,min(bottom,b)-max(top,t))
                          for l,t,r,b in occupied)
            outside = max(0,-left)+max(0,right-COLS)+max(0,-top)+max(0,bottom-ROWS)
            return overlap+outside*100
        position,left,top = min(candidates,key=score)
        positions[index] = position
        occupied.append((left,top,left+width,top+height))
    return positions


def _overlay(fig, points, name, color, show_grid=False):
    points = {tuple(point) for point in points}
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
                   show_visited=False, focus=False, selectable_cells=False,
                   selection_bounds=None, view_revision=0, label_cell_pixels=9.5,
                   review_cells=None):
    fig = go.Figure()
    if show_background:
        fig.add_layout_image(source="data:image/png;base64," + b64encode(layout["background"]).decode(),
                             xref="x", yref="y", x=0, y=0, sizex=COLS, sizey=ROWS,
                             sizing="stretch", xanchor="left", yanchor="top", layer="below")
    display_scale = []
    for i, color in enumerate(COLORS):
        display_color = "rgba(0,0,0,0)" if show_background and i == 0 else color
        display_scale.extend([[i/4, display_color], [(i+1)/4, display_color]])
    x, y = [c+.5 for c in range(COLS)], [r+.5 for r in range(ROWS)]
    gap = 1 if show_grid else 0
    fig.add_trace(go.Heatmap(
        x=x, y=y,
        z=state["classes"], zmin=-.5, zmax=3.5, colorscale=display_scale,
        text=[[CLASS_NAMES[v] for v in row] for row in state["classes"]],
        customdata=[[[r, c] for c in range(COLS)] for r in range(ROWS)],
        hovertemplate="%{text} · 行 %{customdata[0]}，列 %{customdata[1]}<extra></extra>",
        xgap=gap, ygap=gap,
        opacity=.55 if show_background else 1,
        showscale=False, name="地图分类"))
    if review_cells:
        _overlay(fig, review_cells, "核查道路区域", "rgba(124,58,237,.55)", show_grid)
    if result:
        count = result.expanded_count if step is None else step
        if show_visited:
            _overlay(fig, result.visited_order[:count], "已扩展节点", "#f5b44f", show_grid)
        if result.found and count == result.expanded_count:
            _overlay(fig, result.path, "A* 路径", "#2563eb", show_grid)
    for point, name, color in ((start, "起点", "#087f23"), (goal, "终点", "#7c3aed"),
                               (selected if not selection_bounds else None, "所选格子", "#9333ea"),
                               (access_start, "起点道路接入", "#0d9488"),
                               (access_goal, "终点道路接入", "#db2777")):
        if point is not None:
            _overlay(fig, [point], name, color, show_grid)
    if selection_bounds:
        r1, c1, r2, c2 = selection_bounds
        fig.add_shape(type="rect", x0=c1, y0=r1, x1=c2+1, y1=r2+1,
                      line=dict(color="#9333ea", width=2), fillcolor="rgba(0,0,0,0)")
    if selectable_cells:
        # 热力图不提供原生点选；仅在编辑时增加可选择的格心散点层。
        fig.add_trace(go.Scattergl(
            x=[c+.5 for r in range(ROWS) for c in range(COLS)],
            y=[r+.5 for r in range(ROWS) for c in range(COLS)],
            mode="markers", marker=dict(size=7, color="rgba(15,118,110,.025)"),
            customdata=[[r,c,"网格",""] for r in range(ROWS) for c in range(COLS)],
            hovertemplate="行 %{customdata[0]}，列 %{customdata[1]}<extra></extra>",
            name="网格选取", selected=dict(marker=dict(opacity=.25)),
            unselected=dict(marker=dict(opacity=.025))))
    if state["places"]:
        names = list(state["places"])
        points = [state["places"][name] for name in names]
        kinds = [state.get("place_kinds",{}).get(name,"建筑") for name in names]
        highlighted = {}
        for point, label, color in ((start,"起点","#15803d"),(goal,"终点","#be123c"),
                                    (selected,"所选地点","#7c3aed")):
            if point is not None:
                highlighted[tuple(point)] = label, color
        point_colors = [highlighted.get(tuple(p),("", "#475569"))[1] for p in points]
        fig.add_trace(go.Scatter(
            x=[p[1]+.5 for p in points], y=[p[0]+.5 for p in points],
            mode="markers+text" if show_building_labels else "markers",
            text=[escape(name) for name in names],
            textposition=_name_positions(points,names,label_cell_pixels) if show_building_labels else "top center",
            textfont=dict(size=12,color="#18362d",family="Microsoft YaHei, sans-serif",
                          shadow="0 0 3px white, 0 0 3px white, 0 0 2px white"),
            cliponaxis=False,
            customdata=[[*p,kind,name] for p,kind,name in zip(points,kinds,names)],
            marker=dict(size=[11 if tuple(p) in highlighted else 7 for p in points],
                        color=point_colors, symbol="circle",
                        line=dict(color="white",width=1)),
            name="地点位置标记",
            hovertemplate="%{text} · %{customdata[2]}<br>行 %{customdata[0]}，列 %{customdata[1]}<br>地点中心与导航入口分开<extra></extra>"))
        if not show_building_labels:
            for name,p in zip(names,points):
                if tuple(p) in highlighted:
                    label,color = highlighted[tuple(p)]
                    fig.add_annotation(x=p[1]+.5,y=p[0]+.5,
                        text=escape(label+" · "+name),showarrow=False,yshift=18,
                        font=dict(size=11,color=color),bgcolor="rgba(255,255,255,.94)",
                        bordercolor=color,borderpad=4,
                        xanchor="left" if p[1]<10 else "right" if p[1]>80 else "center")
    entrances = []
    for place, items in state.get("entrances", {}).items():
        if place not in state["places"]:
            continue
        for entry in items:
            row, col = entry["point"]
            if not (0 <= row < ROWS and 0 <= col < COLS):
                continue
            inferred = entry.get("source") == "map_inferred"
            provenance = "图面推定，待核实" if inferred else "手动录入，实际情况待核实"
            if not entry.get("enabled", True):
                status, color, symbol = "已停用", "#64748b", "square-open"
            elif state["grid"][row][col] != 0:
                status, color, symbol = "道路不可通行", "#ea580c", "diamond"
            else:
                status, color = "已启用", "#0f766e"
                symbol = "square-open" if inferred else "square"
            entrances.append((place, entry["name"], row, col, status, color, symbol, provenance))
    if entrances:
        fig.add_trace(go.Scatter(
            x=[col+.5 for _, _, _, col, _, _, _, _ in entrances],
            y=[row+.5 for _, _, row, _, _, _, _, _ in entrances],
            mode="markers", name="已录入入口",
            marker=dict(size=12, color=[item[5] for item in entrances],
                        symbol=[item[6] for item in entrances],
                        line=dict(color=[item[5] for item in entrances], width=2)),
            customdata=[[row, col, "入口", place, entry_name, status, provenance]
                        for place, entry_name, row, col, status, _, _, provenance in entrances],
            hovertemplate=("%{customdata[3]} · %{customdata[4]}<br>"
                           "%{customdata[5]} · 行 %{customdata[0]}，列 %{customdata[1]}"
                           "<br>%{customdata[6]}<extra></extra>")))
    x_range,y_range = [0,COLS],[ROWS,0]
    if focus or review_cells:
        points = list(review_cells) if review_cells else [
            p for p in (start,goal,selected,access_start,access_goal) if p is not None]
        if not review_cells and result and result.found:
            points += result.path
        if points:
            rows, cols = zip(*points)
            x_range = [max(0,min(cols)-8),min(COLS,max(cols)+9)]
            y_range = [min(ROWS,max(rows)+13),max(0,min(rows)-12)]
    fig.update_xaxes(range=x_range, visible=show_grid, title="列（0～89）", side="top", dtick=10,
                     showgrid=False, zeroline=False, constrain="domain")
    fig.update_yaxes(range=y_range, visible=show_grid, title="行（0～179）", dtick=10,
                     showgrid=False, zeroline=False, scaleanchor="x", scaleratio=1,
                     constrain="domain", constraintoward="top")
    fig.update_layout(height=900, margin=dict(l=35 if show_grid else 10, r=10,
                                             t=35 if show_grid else 10, b=10), showlegend=False,
                      plot_bgcolor="#fffdf7", paper_bgcolor="#fffdf7", dragmode="pan",
                      clickmode="event+select",
                      hoverlabel=dict(bgcolor="white",font=dict(size=12,color="#334155")),
                      uirevision="pdf-"+layout.get("background_hash", layout["source_hash"])+str((x_range,y_range,focus,view_revision)))
    return fig
