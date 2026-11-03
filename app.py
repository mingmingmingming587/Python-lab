import streamlit as st

st.set_page_config(page_title="CampusPath 校园导航", page_icon="🗺️", layout="wide", initial_sidebar_state="collapsed")

pages = [
    st.Page("pages/7_校园地图导航.py", title="校园导航", icon="🧭", url_path="校园地图导航", default=True),
    st.Page("pages/8_地图与地点维护.py", title="地图与地点维护", icon="🛠️", url_path="地图维护"),
    st.Page("pages/9_路线记录.py", title="路线记录", icon="🕘", url_path="路线记录"),
    st.Page("pages/6_校园道路采集.py", title="道路信息核查", icon="📍", url_path="校园道路采集"),
]

st.sidebar.title("CampusPath")
st.sidebar.caption("校园地图与路线查询")
page = st.navigation(pages)
if "control_width" not in st.session_state:
    st.session_state.control_width = 25
if "_control_width" not in st.session_state:
    st.session_state._control_width = st.session_state.control_width


def save_control_width():
    st.session_state.control_width = st.session_state._control_width


with st.popover("调整操作台宽度"):
    st.slider("左侧宽度（%）", min_value=25, max_value=33, key="_control_width", on_change=save_control_width,
              help="宽度按页面内容区计算；屏幕较窄时页面会自动上下排列。")
page.run()
