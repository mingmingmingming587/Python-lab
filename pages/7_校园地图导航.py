import json
from pathlib import Path

import streamlit as st

from algorithms.layered_astar import layered_astar
from database.campus_project import CampusMapService, active_portals, LAYER_NAMES
from visualization.campus_navigation import navigation_figure

st.title("校园地图导航")
st.caption("应急管理大学 · 地点查询与路线规划")
st.warning("当前地图和入口位置依据参考资料近似绘制，尚未全面核实，路线仅供课程演示，请勿用于实际出行。")

layout_path = Path(__file__).resolve().parents[1] / "reference" / "campus-layout.json"
if not layout_path.exists():
    st.info("请先按 reference/README.md 准备参考图并生成布局。")
    st.stop()
try:
    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    service = CampusMapService(layout)
    revision, state = service.load()
except (OSError, ValueError, KeyError, TypeError) as error:
    st.error(f"无法读取校园地图：{error}")
    st.stop()



control_width = st.session_state.get("control_width", 25)
controls, map_panel = st.columns([control_width, 100 - control_width], gap="large")
with controls:
    with st.container(height=700, border=False):
        st.subheader("规划路线")
        st.caption("输入名称筛选地点，选择起点和终点后开始搜索。")
        start_keyword = st.text_input("搜索起点", placeholder="例如：学子苑")
        start_names = [name for name in state["places"] if start_keyword.strip() in name]
        goal_keyword = st.text_input("搜索终点", placeholder="例如：图书馆")
        goal_names = [name for name in state["places"] if goal_keyword.strip() in name]
        start_name = goal_name = None
        if start_names:
            start_index = start_names.index("学子苑7号") if "学子苑7号" in start_names else 0
            start_name = st.selectbox("起点", start_names, index=start_index, key="campus_start")
        else:
            st.info("没有找到匹配的起点，请尝试其他名称。")
        if goal_names:
            goal_index = goal_names.index("图书馆（东）") if "图书馆（东）" in goal_names else min(1, len(goal_names) - 1)
            goal_name = st.selectbox("终点", goal_names, index=goal_index, key="campus_goal")
        else:
            st.info("没有找到匹配的终点，请尝试其他名称。")
        statuses = state.get("place_status", {})
        if start_name and goal_name:
            st.caption(f"起点：{statuses.get(start_name, '图面近似')}；终点：{statuses.get(goal_name, '图面近似')}。")
        with st.expander("天桥下校门状态", expanded=True):
            st.caption("南侧门在模型中始终开放；北侧限时门需手动设置，不代表实时门禁状态。")
            opened = st.checkbox("北侧限时门开放", value=state["north_gate_open"])
            if opened != state["north_gate_open"]:
                state["north_gate_open"] = opened
                try:
                    service.save(state, revision)
                    st.session_state.pop("campus_route", None)
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
                    st.stop()
        start = tuple(state["places"][start_name]) if start_name else None
        goal = tuple(state["places"][goal_name]) if goal_name else None
        signature = (revision, start_name, goal_name)
        stored = st.session_state.get("campus_route")
        if stored and stored[0] != signature:
            st.session_state.pop("campus_route", None)
            stored = None
        if st.button("开始 A* 搜索", type="primary", disabled=not (start and goal), use_container_width=True):
            try:
                result = layered_astar(state["grids"], start, goal, active_portals(state))
                service.save_route(start_name, goal_name, state, result)
                st.session_state.campus_route = (signature, result)
                st.session_state.campus_step = result.expanded_count
                stored = st.session_state.campus_route
            except ValueError as error:
                st.session_state.pop("campus_route", None)
                stored = None
                st.error(str(error))
        result = stored[1] if stored else None
        step = None
        if result:
            if result.found:
                st.success("已找到当前网格中的最短路径。")
                c1, c2 = st.columns(2)
                c1.metric("路径长度", f"{result.path_length} 步")
                c2.metric("扩展节点", result.expanded_count)
                st.caption("步数包含跨层切换，不能直接换算为实际距离。")
            else:
                st.warning("当前网格中终点不可达。请检查道路、入口和校门状态。")
            with st.expander("查看 A* 搜索过程"):
                step = st.slider("搜索过程：已扩展节点", 0, result.expanded_count, key="campus_step")
                st.caption("拖动进度查看搜索过程；到达最后时显示完整路径。")
                if result.found:
                    st.write("路径坐标（层、行、列）：", result.path)
        show_grid = st.checkbox("显示通行状态网格", value=True)
        grid_layer = st.selectbox("显示地图层", range(len(LAYER_NAMES)), format_func=lambda i: LAYER_NAMES[i])
        st.caption("绿：可通行；灰：不可通行或未录入；红：标注禁行；黄：限时门。路线格子按校内、校外、天桥分别显示为蓝、紫、青。")

with map_panel:
    st.subheader("校园地图")
    st.caption("可滚动缩放、拖动查看；路线格子的颜色区分校内、校外道路与天桥。")
    fig = navigation_figure(layout, state, start, goal, result, step, show_grid, grid_layer=grid_layer)
    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True})
