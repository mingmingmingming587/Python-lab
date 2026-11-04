import streamlit as st

from database.pdf_map import open_pdf_project
from visualization.pdf_map import pdf_map_figure

from algorithms.path_result import PathResult

st.title("路线记录")
st.caption("仅展示新 PDF 地图的路线；旧版地图和历史仍保留在原数据库。")

try:
    layout, service, revision, state = open_pdf_project()
except (OSError, ValueError, KeyError, TypeError) as error:
    st.error(f"无法加载新 PDF 地图：{error}")
    st.stop()

control_width = st.session_state.get("control_width", 25)
controls, map_panel = st.columns([control_width, 100 - control_width], gap="large")

with controls:
    with st.container(height=700, border=False):
        history = service.history()
        item = None
        if not history:
            st.info("尚无新地图路线记录。")
        else:
            by_id = {r["id"]: r for r in history}
            chosen = st.selectbox("选择历史记录", list(by_id),
                format_func=lambda i: f"#{i} · {by_id[i]['start_name']} → {by_id[i]['goal_name']} · {by_id[i]['created_at']}")
            item = by_id[chosen]
            st.write("结果：", "找到路线" if item["found"] else "不可达")
            st.write("步数：", item["path_length"], "｜扩展节点：", item["expanded_count"])
with map_panel:
    st.subheader("历史路线地图")
    with st.popover("图层与视图"):
        show_background=st.checkbox("显示 PDF 对照底图",value=False)
        show_grid=st.checkbox("显示细网格与坐标",value=False)
        show_labels=st.checkbox("显示全部地点名称",value=False)
        view=st.radio("视图范围",["全校","当前路线"])
    if item:
        saved = item["snapshot"]
        historic = PathResult(bool(item["found"]), item["path"], item["visited"], item["expanded_count"], 0.0, item["path_length"])
        query = saved.get("route_query",{})
        start_access, goal_access = query.get("start_access"), query.get("goal_access")
        st.caption("使用查询时保存的网格和接入点快照；后续修改不会改变这条历史路线。")
        if any(e and e.get("temporary") for e in (start_access,goal_access)):
            st.warning("此记录使用了待核实的临时接入点，长度仅为道路段步数。")
        st.plotly_chart(pdf_map_figure(layout, saved, result=historic, show_background=show_background,
                        access_start=start_access["point"] if start_access else None,
                        access_goal=goal_access["point"] if goal_access else None,
                        show_grid=show_grid,show_building_labels=show_labels,focus=view!="全校"),
                        use_container_width=True, config={"scrollZoom": True})
    else:
        st.plotly_chart(pdf_map_figure(layout, state, show_background=show_background,
                        show_grid=show_grid,show_building_labels=show_labels),
                        use_container_width=True, config={"scrollZoom": True})
