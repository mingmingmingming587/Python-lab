"""保留的界面学习练习；可用 streamlit run learning/streamlit_练习.py 单独运行。"""

import streamlit as st

st.title("地点选择与 Session State 练习")
st.caption("以下是界面练习，不会计算路径。")
places = ["教学楼", "图书馆", "食堂", "宿舍", "实验楼"]
start_col, goal_col = st.columns(2)
with start_col:
    start = st.selectbox("选择起点", places)
with goal_col:
    goal = st.selectbox("选择终点", places, index=1)
if st.button("演示地点选择"):
    if start == goal:
        st.info("起点和终点相同；实际搜索可返回 0 步。")
    else:
        st.success(f"模拟请求：{start} → {goal}（尚未搜索路线）")
keyword = st.text_input("请输入地点名称")
if st.button("查询地点"):
    if not keyword.strip():
        st.warning("请输入地点名称！")
    elif keyword in places:
        st.success(f"找到地点：{keyword}")
    else:
        st.error("没有找到该地点！")
if "count" not in st.session_state:
    st.session_state.count = 0
if st.button("计数 +1"):
    st.session_state.count += 1
st.metric("当前计数", st.session_state.count)
