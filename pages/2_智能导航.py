import streamlit as st
import plotly.graph_objects as go
from algorithms.astar import astar_search
from database.store import init_database, load_map, save_grid, save_route

st.title("模拟地图导航")
st.caption("当前地图的道路和入口需要核实；结果仅代表录入网格，不保证现实通行。")

init_database()
saved_map = load_map()
st.write("当前地图：", saved_map["name"])
saved_signature = (saved_map["name"], tuple(tuple(line) for line in saved_map["grid"]), tuple(saved_map["places"].items()))

# 当前会话中的编辑保留到用户保存或明确重新加载。
if "grid" not in st.session_state:
    st.session_state.grid = [line[:] for line in saved_map["grid"]]
    st.session_state.saved_map_signature = saved_signature

if st.button("重新加载已保存地图"):
    st.session_state.grid = [line[:] for line in saved_map["grid"]]
    st.session_state.saved_map_signature = saved_signature
    st.session_state.pop("path_result", None)
    st.rerun()

grid = st.session_state.grid
is_stale = st.session_state.get("saved_map_signature") != saved_signature
if is_stale:
    st.warning("已保存的地图或地点发生变化；请先重新加载地图。当前会话中未保存的编辑会被放弃。")


# 2. 模拟地点及入口坐标
places = saved_map["places"]
if not places:
    st.warning("请先在地图管理中添加至少一个地点。")
    st.stop()

# 3. 显示地图基本信息
st.subheader("地图信息")
st.write("地图行数：", len(grid))
st.write("地图列数：", len(grid[0]))

# 4. 选择起点和终点
st.subheader("地点选择")

col1, col2 = st.columns(2)

with col1:
    start_name = st.selectbox(
        "选择起点",
        list(places.keys()),
        key="start_place"
    )

with col2:
    goal_name = st.selectbox(
        "选择终点",
        list(places.keys()),
        index=min(1, len(places) - 1),
        key="goal_place"
    )

# 5. 将地点名称转换成坐标
start = places[start_name]
goal = places[goal_name]

# =========================
# 地图编辑区域
# =========================

st.subheader("模拟地图编辑")

# 选择需要编辑的网格坐标
row = st.number_input(
    "选择行",
    min_value=0,
    max_value=len(grid) - 1,
    value=3
)

col = st.number_input(
    "选择列",
    min_value=0,
    max_value=len(grid[0]) - 1,
    value=4
)

# 编辑按钮
edit_col1, edit_col2 = st.columns(2)

with edit_col1:
    if st.button("设置为障碍物"):

        if (row, col) in places.values():
            st.warning("不能将地点入口设置为障碍物！")

        else:
            grid[row][col] = 1
            st.success("障碍物设置成功！")

with edit_col2:
    if st.button("恢复通行"):

        grid[row][col] = 0
        st.success("区域已恢复通行！")

if st.button("保存地图", disabled=is_stale):
    try:
        save_grid(grid, expected_grid=saved_map["grid"], expected_places=saved_map["places"])
        st.session_state.saved_map_signature = (saved_map["name"], tuple(tuple(line) for line in grid), tuple(places.items()))
        st.success("地图已保存；重启后可以加载。")
    except ValueError as error:
        st.error(str(error))

# 先编辑，再显示当前状态和计算结果。
st.write(f"当前坐标：({row}, {col})")
if grid[row][col] == 0:
    st.success("当前区域：可通行")
else:
    st.warning("当前区域：障碍物")

# 结果只适用于搜索时的网格和起终点；输入改变后清除旧结果。
search_input = (tuple(tuple(line) for line in grid), start, goal)
if is_stale or st.session_state.get("search_input") != search_input:
    st.session_state.pop("path_result", None)

if st.button("开始 A* 搜索", type="primary", disabled=is_stale):
    try:
        st.session_state.path_result = astar_search(grid, start, goal)
        save_route(start_name, goal_name, grid, st.session_state.path_result, expected_start=start, expected_goal=goal)
        st.session_state.search_input = search_input
        st.session_state.search_step = st.session_state.path_result.expanded_count
    except ValueError as error:
        st.session_state.pop("path_result", None)
        st.error(str(error))

result = st.session_state.get("path_result")

if result:
    st.subheader("搜索过程回放")
    st.caption("算法已经计算完成；拖动滑块回看节点的扩展顺序。蓝色路径在回放结束时显示。")
    step = st.slider("已扩展节点", 0, result.expanded_count, key="search_step")
    shown_nodes = result.visited_order[:step]

# 创建画布
fig = go.Figure()

# 绘制网格
fig.add_trace(go.Heatmap(
    z=grid,
    x=list(range(len(grid[0]))),
    y=list(range(len(grid))),

    colorscale=[
        [0.0, "#DDEFE2"],
        [0.499, "#DDEFE2"],
        [0.5, "#596273"],
        [1.0, "#596273"]
    ],

    zmin=0,
    zmax=1,
    showscale=False,
    xgap=3,
    ygap=3
))

# 按扩展顺序展示已搜索节点；横轴是列，纵轴是行。
if result and shown_nodes:
    fig.add_trace(go.Scatter(
        x=[point[1] for point in shown_nodes],
        y=[point[0] for point in shown_nodes],
        mode="markers",
        name="已扩展节点",
        marker=dict(size=14, color="orange", opacity=0.7, symbol="square")
    ))

# 回放结束后显示最终路径。
if result and result.found and step == result.expanded_count:
    fig.add_trace(go.Scatter(
        x=[point[1] for point in result.path],
        y=[point[0] for point in result.path],
        mode="lines+markers",
        name="A* 路径",
        line=dict(color="blue", width=4),
        marker=dict(size=8)
    ))

# 标记起点
fig.add_trace(go.Scatter(
    x=[start[1]],
    y=[start[0]],
    mode="markers+text",
    name="起点",
    text=["起点"],
    textposition="top center",
    marker=dict(size=16, color="green")
))

# 标记终点
fig.add_trace(go.Scatter(
    x=[goal[1]],
    y=[goal[0]],
    mode="markers+text",
    name="终点",
    text=["终点"],
    textposition="top center",
    marker=dict(size=16, color="red")
))

# 设置坐标轴
fig.update_xaxes(
    title="列（col）",
    dtick=1,
    side="top"
)

fig.update_yaxes(
    title="行（row）",
    dtick=1,
    autorange="reversed",
    scaleanchor="x",
    scaleratio=1
)

# 设置图表
fig.update_layout(
    title=saved_map["name"],
    height=500
)

# 在 Streamlit 页面显示
st.plotly_chart(fig, use_container_width=True)

if result:
    if result.found:
        st.success("已找到当前网格中的最短路径。")
        st.metric("路径长度", f"{result.path_length} 步")
        st.metric("扩展节点", result.expanded_count)
        st.write("路径坐标：", result.path)
    else:
        st.warning("当前网格中没有可行路线。")
