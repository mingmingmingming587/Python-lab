import streamlit as st

from database.pdf_map import open_pdf_project, CLASS_NAMES
from visualization.pdf_map import pdf_map_figure

from collections import Counter
from database.pdf_map import road_components

st.title("道路信息核查")
st.caption("核查新 PDF 的分类、道路数量和连通性；不导入旧图的道路坐标。")

try:
    layout, service, revision, state = open_pdf_project()
except (OSError, ValueError, KeyError, TypeError) as error:
    st.error(f"无法加载新 PDF 地图：{error}")
    st.stop()

control_width = st.session_state.get("control_width", 25)
controls, map_panel = st.columns([control_width, 100 - control_width], gap="large")

with controls:
    with st.container(height=700, border=False):
        st.subheader("当前地图统计")
        counts = Counter(value for line in state["classes"] for value in line)
        st.dataframe([{"分类": CLASS_NAMES[i], "格子数": counts[i]} for i in range(4)], hide_index=True)
        components = road_components(state["grids"][0])
        st.write("四方向道路连通区域：", len(components))
        st.dataframe([{"区域": i+1, "道路格数": len(c), "示例(行,列)": str(c[0])} for i, c in enumerate(components)], hide_index=True)
        st.info("孤立道路不会被自动连接；可在地图维护中对照 PDF 校对。建筑圆点表示位置，导航入口仍需单独录入。")
        with st.expander("资料及限制", expanded=True):
            st.write("来源：reference/campus-map-integrated.pdf")
            st.write("第 2 页的四分类与第 3 页的道路网格逐格交叉核对。")
            st.warning("PDF 是平面网格，不包含天桥和校门跨层关系；当前结果不能用于实际出行。")
with map_panel:
    st.subheader("新 PDF 分类地图")
    with st.popover("图层与视图"):
        show_background=st.checkbox("显示 PDF 对照底图",value=False)
        show_grid=st.checkbox("显示细网格与坐标",value=False)
        show_labels=st.checkbox("显示全部地点名称",value=False)
    st.plotly_chart(pdf_map_figure(layout, state, show_background=show_background,
                    show_grid=show_grid,show_building_labels=show_labels),
                    use_container_width=True, config={"scrollZoom": True})
