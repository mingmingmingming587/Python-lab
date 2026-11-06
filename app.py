import streamlit as st

st.set_page_config(page_title="CampusPath 校园导航", page_icon="🗺️", layout="wide", initial_sidebar_state="collapsed")

pages = [
    st.Page("pages/navigation.py", title="校园导航", icon="🧭", url_path="校园地图导航", default=True),
    st.Page("pages/map_management.py", title="地图与地点维护", icon="🛠️", url_path="地图维护"),
    st.Page("pages/route_history.py", title="路线记录", icon="🕘", url_path="路线记录"),
    st.Page("pages/road_review.py", title="道路信息核查", icon="📍", url_path="校园道路采集"),
]

# 保留原有地址入口；实际操作在同一个地图工作台中切换。
st.navigation(pages, position="hidden").run()
