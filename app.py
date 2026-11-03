import streamlit as st

st.set_page_config(page_title="CampusPath 校园导航", page_icon="🗺️", layout="wide")

pages = [
    st.Page("pages/7_校园地图导航.py", title="校园导航", icon="🧭", url_path="校园地图导航", default=True),
    st.Page("pages/8_地图与地点维护.py", title="地图与地点维护", icon="🛠️", url_path="地图维护"),
    st.Page("pages/9_路线记录.py", title="路线记录", icon="🕘", url_path="路线记录"),
    st.Page("pages/6_校园道路采集.py", title="道路信息核查", icon="📍", url_path="校园道路采集"),
]

st.sidebar.title("CampusPath")
st.sidebar.caption("校园地图与路线查询")
st.navigation(pages).run()
