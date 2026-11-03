import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from algorithms.astar import astar_search
from database.survey import (COLS, ROWS, STATUSES, delete_survey, image_position,
                             init_survey, list_survey, save_survey, verified_grid)
from visualization.campus_diagram import build_campus_diagram

st.set_page_config(page_title="校园道路采集", layout="wide")
st.title("校园道路采集与 A* 试算")
st.warning("这是采集和校对工具，网格位置是参考图面坐标，不是经纬度。资料未完整核实，试算结果不能用于实际导航。")
st.caption("按图上行列录入水平或垂直路段；拐弯拆成多段。道路与入口需分别记录来源和核实状态。")

layout_path = Path(__file__).resolve().parents[1] / "reference" / "campus-layout.json"
if not layout_path.exists():
    st.info("请先根据 reference/README.md 准备校园参考图并生成布局数据。")
    st.stop()
try:
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    places = layout["places"]
    init_survey()
    records = list_survey()
except (OSError, ValueError, KeyError, TypeError) as error:
    st.error(f"无法读取地图或采集数据：{error}")
    st.stop()

st.subheader("参考道路线索")
st.caption("可以把根据校园参考图粗画的道路示意线加入清单。它们仅供对照，位置、校内外归属和通行状态均待核实，不会自动成为可通行道路。已保存的记录不会随底图更新，请逐条检查和修改。")
if st.button("加入已有道路示意线索"):
    # 与已有示意图中的近似线一致，只作为待核实的起点。
    candidates = [
        ("学府北路", (343, 230), (343, 406)), ("学府中路", (343, 429), (343, 508)),
        ("天水路", (200, 509), (200, 632)), ("博观路", (275, 637), (465, 637)),
        ("学府东路", (405, 638), (405, 756)), ("学府南路", (343, 638), (343, 756)),
    ]
    source = "现有校园参考图示意线，位置与通行待核实"
    existing = {(item["name"], item["source"]) for item in records}
    added = 0
    for name, p1, p2 in candidates:
        if (name, source) in existing:
            continue
        def to_cell(point):
            x, y = point
            return (min(ROWS - 1, max(0, int((y - 24) * ROWS / 756))),
                    min(COLS - 1, max(0, int((x - 86) * COLS / 416))))
        save_survey("道路", name, to_cell(p1), to_cell(p2), "待核实", source)
        added += 1
    st.success(f"已加入 {added} 条待核实线索。")
    records = list_survey()

st.subheader("录入或修改记录")
by_id = {record["id"]: record for record in records}
record_id = st.selectbox("选择记录", [0, *by_id], format_func=lambda item: "新增记录" if item == 0 else f"#{item} {by_id[item]['kind']} · {by_id[item]['name']}")
current = by_id.get(record_id, {})
with st.form("survey_record"):
    kind = st.selectbox("类型", ("道路", "入口"), index=1 if current.get("kind") == "入口" else 0)
    name = st.text_input("道路或入口名称", value=current.get("name", ""))
    a, b, c, d = st.columns(4)
    row1 = a.number_input("起点行", 0, ROWS - 1, int(current.get("row1", 0)))
    col1 = b.number_input("起点列", 0, COLS - 1, int(current.get("col1", 0)))
    row2 = c.number_input("道路终点行", 0, ROWS - 1, int(current.get("row2", 0)))
    col2 = d.number_input("道路终点列", 0, COLS - 1, int(current.get("col2", 0)))
    st.caption("入口只使用起点行列；道路两端必须同行或同列。")
    status = st.selectbox("核实状态", STATUSES, index=STATUSES.index(current.get("status", "待核实")))
    source = st.text_input("信息来源", value=current.get("source", ""), placeholder="例如：校园参考图、现场核实日期及人员")
    note = st.text_input("备注", value=current.get("note", ""), placeholder="例如：校门开放时间、围栏或路段疑点")
    submitted = st.form_submit_button("保存记录")
if submitted:
    try:
        end = (row1, col1) if kind == "入口" else (row2, col2)
        save_survey(kind, name, (row1, col1), end, status, source, note, record_id=record_id or None)
        st.success("记录已保存到本机数据库。")
        records = list_survey()
    except ValueError as error:
        st.error(str(error))

if record_id and st.button("删除所选记录"):
    delete_survey(record_id)
    st.rerun()

by_id = {record["id"]: record for record in records}
if records:
    st.subheader("采集记录")
    st.dataframe([{"编号": r["id"], "类型": r["kind"], "名称": r["name"],
                   "起点(行,列)": f"({r['row1']}, {r['col1']})", "终点(行,列)": f"({r['row2']}, {r['col2']})",
                   "状态": r["status"], "来源": r["source"], "备注": r["note"]} for r in records], hide_index=True)

st.subheader("A* 网格试算")
st.caption("只有标为已核实可通行的道路进入 A*；未知和不可通行均不通行。如记录冲突，不可通行优先。入口本身不会自动打通道路。")
grid = verified_grid(records)
entrances = [r for r in records if r["kind"] == "入口" and r["status"] == "已核实可通行" and grid[r["row1"]][r["col1"]] == 0]
path = []
if entrances:
    names = {r["id"]: f"{r['name']} (#{r['id']})" for r in entrances}
    a, b = st.columns(2)
    start_id = a.selectbox("起点入口", list(names), format_func=names.get)
    goal_id = b.selectbox("终点入口", list(names), index=min(1, len(names) - 1), format_func=names.get)
    if st.button("试算 A* 路线"):
        start, goal = by_id[start_id], by_id[goal_id]
        result = astar_search(grid, (start["row1"], start["col1"]), (goal["row1"], goal["col1"]))
        if result.found:
            path = result.path
            st.success(f"已找到网格路线：{result.path_length} 步；扩展 {result.expanded_count} 个节点。步数不等于实际距离。")
        else:
            st.warning("当前已核实道路未连通；请检查道路、入口或待核实路段。")
else:
    st.info("请先录入位于已核实道路上的已核实入口，才能试算。")

st.subheader("校园图面与采集网格")
st.caption("横轴是列，纵轴是行。橙色：待核实；绿色：已核实可通行；红色：已核实不可通行；蓝色：本次试算路线。网格相邻不代表现实中一定相通。")
fig = build_campus_diagram(places, footprints=layout.get("footprints"))
for record in records:
    x1, y1 = image_position(record["row1"], record["col1"])
    x2, y2 = image_position(record["row2"], record["col2"])
    color = {"待核实": "#d89020", "已核实可通行": "#16803d", "已核实不可通行": "#c52b2b"}[record["status"]]
    fig.add_trace(go.Scatter(x=[x1, x2], y=[y1, y2], mode="markers" if record["kind"] == "入口" else "lines+markers",
                             marker=dict(size=7, color=color), line=dict(color=color, width=4), name=record["name"],
                             text=[f"{record['name']} · {record['status']}"] * 2,
                             hovertemplate="%{text}<extra></extra>", showlegend=False))
if path:
    xy = [image_position(*point) for point in path]
    fig.add_trace(go.Scatter(x=[p[0] for p in xy], y=[p[1] for p in xy], mode="lines", name="A* 试算",
                             line=dict(color="#2563eb", width=5), showlegend=False))
fig.update_xaxes(visible=True, side="top", title="列", tickvals=[image_position(0, c)[0] for c in range(0, COLS, 5)],
                 ticktext=[str(c) for c in range(0, COLS, 5)], showgrid=True, gridcolor="rgba(30,50,70,0.2)",
                 minor=dict(dtick=416 / COLS, tick0=86, showgrid=True, gridcolor="rgba(30,50,70,0.10)"))
fig.update_yaxes(visible=True, title="行", tickvals=[image_position(r, 0)[1] for r in range(0, ROWS, 5)],
                 ticktext=[str(r) for r in range(0, ROWS, 5)], showgrid=True, gridcolor="rgba(30,50,70,0.2)",
                 minor=dict(dtick=756 / ROWS, tick0=24, showgrid=True, gridcolor="rgba(30,50,70,0.10)"))
st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True})
