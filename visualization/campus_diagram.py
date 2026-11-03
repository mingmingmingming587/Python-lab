"""根据校园参考图的标签位置绘制示意地图，不用于路径计算。"""

import plotly.graph_objects as go


def build_campus_diagram(places, focus=None, footprints=None, show_labels=True):
    fig = go.Figure()
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

    if focus is None:
        x_range, y_range = [86, 502], [780, 24]
    else:
        x, y = focus["x"], focus["y"]
        x_range, y_range = [x-55, x+55], [y+80, y-80]
    fig.update_xaxes(range=x_range, visible=False, constrain="domain")
    fig.update_yaxes(range=y_range, visible=False, scaleanchor="x", scaleratio=1, constrain="domain", constraintoward="top")
    fig.update_layout(height=1100, margin=dict(l=0, r=0, t=10, b=0),
                      paper_bgcolor="white", plot_bgcolor="white", dragmode="pan", showlegend=False)
    return fig
