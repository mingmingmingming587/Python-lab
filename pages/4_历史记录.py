import streamlit as st
from database.store import init_database, list_routes

st.title("模拟路线历史")
st.caption("本页显示模拟地图的历史。校园示意地图的历史及图形回放在“校园地图导航”页面底部。时间为 UTC。")
init_database()
records = list_routes()
if not records:
    st.info("暂无查询记录。请先在智能导航页面运行 A*。")
for record in records:
    title = f"#{record['id']} · {record['start_name']} → {record['goal_name']} · {record['created_at']}"
    with st.expander(title):
        st.write("结果：", "找到路线" if record["found"] else "不可达")
        st.write("路径长度（步）：", record["path_length"] if record["found"] else "无")
        st.write("扩展节点数：", record["expanded_count"])
        st.write("查询时网格（0 可通行，1 障碍物）：", record["grid_snapshot"])
        st.write("路径坐标（行，列）：", record["path_snapshot"])
