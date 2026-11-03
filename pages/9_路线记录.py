import json
from pathlib import Path

import streamlit as st

from algorithms.path_result import PathResult
from database.campus_project import CampusMapService, LAYER_NAMES
from visualization.campus_navigation import navigation_figure

st.title("路线记录")
st.caption("查看过去的校园路线查询；地图与路径按查询时的状态保存。")

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
        history = service.history()
        if not history:
            st.info("尚无校园路线查询记录。")
        else:
            labels = {item["id"]: f"#{item['id']} · {item['start_name']} → {item['goal_name']} · {item['created_at']} UTC" for item in history}
            chosen = st.selectbox("选择历史记录", list(labels), format_func=labels.get)
            item = next(r for r in history if r["id"] == chosen)
            st.write("结果：", "找到路线" if item["found"] else "不可达", "｜步数：", item["path_length"], "｜扩展节点：", item["expanded_count"])
            if st.button("显示这条历史路线"):
                st.session_state.campus_history_id = chosen
            grid_layer = st.selectbox("查看地图层", range(len(LAYER_NAMES)), format_func=lambda i: LAYER_NAMES[i])

with map_panel:
    st.subheader("历史路线地图")
    if not history:
        st.info("查询路线后，可在这里查看当时的地图和路线。")
    elif st.session_state.get("campus_history_id") != chosen:
        st.info("选择记录并点击“显示这条历史路线”。")
    else:
        saved = item["snapshot"]
        historic = PathResult(bool(item["found"]), item["path"], item["visited"], item["expanded_count"], 0.0, item["path_length"])
        st.caption("使用查询时保存的地图、门状态和路径快照。绿：可通行；灰：不可通行或未录入；红：禁行；黄：限时门；蓝、紫、青分别为校内、校外、天桥路线。")
        st.plotly_chart(navigation_figure(layout, saved, result=historic, grid_layer=grid_layer), use_container_width=True, config={"scrollZoom": True}, key="campus_history_map")
