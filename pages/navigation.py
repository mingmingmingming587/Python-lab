import streamlit as st

from algorithms.place_navigation import access_points, plan_named_route
from database.pdf_map import open_pdf_project
from visualization.pdf_map import pdf_map_figure

st.title("校园地图导航")
st.caption("experiment2 · 按建筑或场地名称规划路线")
st.warning("当前为 PDF 平面地图。临时接入点、建筑入口和跨层关系仍需核实，路线仅供地图校对。")

try:
    layout, service, revision, state = open_pdf_project()
except (OSError, ValueError, KeyError, TypeError) as error:
    st.error(f"无法加载新 PDF 地图：{error}")
    st.stop()

control_width = st.session_state.get("control_width", 25)
controls, map_panel = st.columns([control_width, 100-control_width], gap="large")
with controls:
    with st.container(height=700, border=False):
        st.subheader("按名称规划路线")
        start_keyword = st.text_input("搜索起点", placeholder="例如：学子苑、运动场")
        start_names = [n for n in state["places"] if start_keyword.strip().casefold() in n.casefold()]
        start_name = None
        if start_names:
            start_index = start_names.index("学子苑7号") if "学子苑7号" in start_names else 0
            start_name = st.selectbox("起点", start_names, index=start_index)
        else:
            st.info("没有匹配的起点，请更换名称。")
        goal_keyword = st.text_input("搜索终点", placeholder="例如：图书馆、运动场")
        goal_names = [n for n in state["places"] if goal_keyword.strip().casefold() in n.casefold()]
        goal_name = None
        if goal_names:
            goal_index = goal_names.index("图书馆（东）") if "图书馆（东）" in goal_names else min(1,len(goal_names)-1)
            goal_name = st.selectbox("终点", goal_names, index=goal_index)
        else:
            st.info("没有匹配的终点，请更换名称。")
        start_gate = goal_gate = None
        start_access = goal_access = None
        ready = bool(start_name and goal_name)
        if ready:
            try:
                starts, goals = access_points(state,start_name), access_points(state,goal_name)
                if len(starts)>1:
                    choice = st.selectbox("起点入口", ["自动选择最短入口",*[e["name"] for e in starts]])
                    start_gate = None if choice=="自动选择最短入口" else choice
                if len(goals)>1:
                    choice = st.selectbox("终点入口", ["自动选择最短入口",*[e["name"] for e in goals]])
                    goal_gate = None if choice=="自动选择最短入口" else choice
                start_access = next((e for e in starts if e["name"]==start_gate),starts[0])
                goal_access = next((e for e in goals if e["name"]==goal_gate),goals[0])
                for label, name, entries in (("起点",start_name,starts),("终点",goal_name,goals)):
                    if entries[0]["temporary"]:
                        point = entries[0]["point"]
                        st.warning(f"{label}“{name}”尚未设置入口，暂用附近道路格（{point[1]}, {point[2]}）；这不是已核实的实际门。")
                    else:
                        st.caption(f"{label}：使用已手动指定的入口，非实时状态。")
            except ValueError as error:
                st.error(str(error))
                ready=False
        signature = (revision,start_name,goal_name,start_gate,goal_gate)
        stored = st.session_state.get("pdf_route")
        if stored and stored[0]!=signature:
            st.session_state.pop("pdf_route",None)
            stored=None
        if st.button("开始 A* 搜索",type="primary",disabled=not ready,use_container_width=True):
            try:
                result,start_access,goal_access = plan_named_route(state,start_name,goal_name,start_gate,goal_gate)
                snapshot = {**state,"route_query":{"start_access":start_access,"goal_access":goal_access}}
                service.save_route(start_name,goal_name,snapshot,result)
                st.session_state.pdf_route=(signature,result,start_access,goal_access)
                st.session_state.pdf_step=result.expanded_count
                stored=st.session_state.pdf_route
            except ValueError as error:
                st.session_state.pop("pdf_route",None)
                stored=None
                st.error(str(error))
        result=stored[1] if stored else None
        step=None
        show_visited=False
        if result:
            start_access,goal_access=stored[2],stored[3]
            if result.found:
                st.success(f"{start_name} → {goal_name}")
                st.metric("路网段长度",f"{result.path_length} 步")
                st.metric("扩展节点",result.expanded_count)
                st.caption("步数仅计算接入点之间的道路，不包含建筑内部或场地内部行走，也不等于实际米数。")
            else:
                st.warning("当前入口之间没有可达路线，请核对道路和入口。")
            with st.expander("查看 A* 搜索过程"):
                show_visited=st.checkbox("显示已扩展网格",value=False)
                step=st.slider("搜索过程：已扩展节点",0,result.expanded_count,key="pdf_step")
                st.write("起点接入：",start_access["name"],start_access["point"][-2:])
                st.write("终点接入：",goal_access["name"],goal_access["point"][-2:])
with map_panel:
    st.subheader("校园地图与路线")
    with st.popover("图层与视图"):
        show_background=st.checkbox("显示 PDF 对照底图",value=False)
        show_grid=st.checkbox("显示细网格与坐标",value=False)
        show_labels=st.checkbox("显示全部地点名称",value=False)
        view=st.radio("视图范围",["全校","当前路线或地点"])
    st.caption("浅黄建筑、浅绿道路、浅灰未标注、淡红边界；圆点为地点，蓝色为路线。悬停可查看名称和坐标。")
    start=state["places"].get(start_name)
    goal=state["places"].get(goal_name)
    st.plotly_chart(pdf_map_figure(layout,state,start,goal,result,step,show_background,
                    access_start=start_access["point"] if ready and start_access else None,
                    access_goal=goal_access["point"] if ready and goal_access else None,
                    show_grid=show_grid,show_building_labels=show_labels,
                    show_visited=show_visited,focus=view!="全校"),
                    use_container_width=True,config={"scrollZoom":True})
