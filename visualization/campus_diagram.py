"""根据校园参考图的标签位置绘制示意地图，不用于路径计算。"""

import plotly.graph_objects as go


def build_campus_diagram(places, focus=None, footprints=None, show_labels=True):
    fig = go.Figure()
    # 对照参考图所见空隙绘制局部小路；先绘制使场地和建筑覆盖不准确的线段。
    paths = [
        [(138, 43), (138, 105)], [(101, 108), (174, 108)],
        [(163, 108), (163, 214)], [(101, 160), (266, 160)],
        [(283, 282), (390, 282)], [(283, 312), (390, 312)],
        [(283, 360), (393, 360)],
        [(287, 382), (338, 382)], [(345, 382), (393, 382)],
        [(104, 510), (200, 510)], [(203, 510), (468, 510)],
        [(105, 594), (200, 594)], [(240, 595), (282, 595)],
        [(240, 507), (240, 594)], [(284, 595), (284, 634)],
        [(375, 511), (375, 633)], [(437, 510), (437, 633)],
        [(375, 581), (437, 581)],
        [(105, 634), (284, 634)], [(105, 664), (201, 664)],
        [(201, 665), (285, 665)], [(105, 750), (200, 750)],
        [(201, 750), (284, 750)], [(287, 750), (469, 750)],
    ]
    path = " ".join("M " + " L ".join(f"{x},{y}" for x, y in points) for points in paths)
    fig.add_shape(type="path", path=path, line=dict(color="#a9b5aa", width=1.5), layer="below")
    # 浅色场地和建筑均由参考图色块近似提取；空隙不是可通行网格。
    for color, fill in (("ground", "#e6ece9"), ("blue", "#245a85"), ("gray", "#8f969c")):
        runs = (footprints or {}).get(color, [])
        if runs:
            path = " ".join(f"M {x},{y} L {x+length},{y} L {x+length},{y+1} L {x},{y+1} Z" for x, y, length in runs)
            fig.add_shape(type="path", path=path, fillcolor=fill,
                          line=dict(width=0), layer="below")

    for place in places:
        x, y, name = place["x"], place["y"], place["name"]
        fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers", text=[name], name=name,
                                 marker=dict(size=10, opacity=0.01),
                                 hovertemplate="%{text}<br>参考图面位置，入口待核实<extra></extra>",
                                 showlegend=False))
        if show_labels:
            fig.add_annotation(x=x, y=y, text=name, showarrow=False, font=dict(size=10, color="#111827"),
                               bgcolor="rgba(255,255,255,0.88)", bordercolor="rgba(0,0,0,0.10)", borderwidth=1)

    # 按参考图的道路文字与位置绘制概略线，不表示道路可通行或长度准确。
    roads = [
        ("雄虹路", [(102, 214), (269, 214)]),
        ("学府北路", [(343, 230), (343, 406)]),
        ("学府中路", [(343, 429), (343, 508)]),
        ("天水路", [(200, 509), (200, 632)]),
        ("博观路", [(275, 637), (465, 637)]),
        ("学府东路", [(405, 638), (405, 756)]),
        ("学府南路", [(343, 638), (343, 756)]),
    ]
    for name, points in roads:
        fig.add_trace(go.Scatter(x=[point[0] for point in points], y=[point[1] for point in points],
                                 mode="lines", name=name, line=dict(color="#d89020", width=2, dash="dot"),
                                 hovertemplate=f"{name}（位置示意、通行待核实）<extra></extra>", showlegend=False))
        midpoint = ((points[0][0] + points[-1][0]) / 2, (points[0][1] + points[-1][1]) / 2)
        fig.add_annotation(x=midpoint[0], y=midpoint[1], text=name, showarrow=False,
                           font=dict(color="#7a4b00", size=9), bgcolor="rgba(255,255,255,0.8)")

    if focus is None:
        x_range, y_range = [86, 502], [780, 24]
    else:
        x, y = focus["x"], focus["y"]
        x_range, y_range = [x-55, x+55], [y+80, y-80]
    fig.update_xaxes(range=x_range, visible=False, constrain="domain")
    fig.update_yaxes(range=y_range, visible=False, scaleanchor="x", scaleratio=1, constrain="domain")
    fig.update_layout(height=1500, margin=dict(l=0, r=0, t=10, b=0),
                      paper_bgcolor="white", plot_bgcolor="white", dragmode="pan")
    return fig
