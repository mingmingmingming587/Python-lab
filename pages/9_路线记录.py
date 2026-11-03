import json
from pathlib import Path

import streamlit as st

from algorithms.path_result import PathResult
from database.campus_project import CampusMapService
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
    if st.session_state.get("campus_history_id") == chosen:
        saved = item["snapshot"]
        historic = PathResult(bool(item["found"]), item["path"], item["visited"], item["expanded_count"], 0.0, item["path_length"])
        st.caption("以下使用查询时保存的地图、门状态和路径快照。")
        st.plotly_chart(navigation_figure(layout, saved, result=historic), use_container_width=True, config={"scrollZoom": True}, key="campus_history_map")
