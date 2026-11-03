import streamlit as st

st.set_page_config(page_title="CampusPath 校园导航", page_icon="🗺️")

st.sidebar.title("CampusPath")
st.sidebar.caption("AI 智能校园导航系统")

st.title("CampusPath 校园导航")
st.caption("Python 课程综合实验 · 项目开发中")
st.write("使用左侧菜单进入地图管理、导航和算法实验页面。")
st.info("初始地图为模拟数据；导入地图的来源、道路和入口仍需核实，不能直接作为实际导航依据。")

# 页面分隔
st.divider()

# 功能区域
st.header("系统功能")

# 三列布局
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("🗺️ 地图管理")
    st.write("编辑已有地图和地点")
    st.caption("地点管理 · 障碍物编辑")

with col2:
    st.subheader("🧭 智能导航")
    st.write("自动规划校园路线")
    st.caption("A* 算法 · 最短路径")

with col3:
    st.subheader("📊 算法实验")
    st.write("展示 AI 搜索过程")
    st.caption("搜索节点 · 性能分析")

# 再添加一条分隔线
st.divider()

# 项目介绍区域
left, right = st.columns([2, 1])

with left:
    st.subheader("项目介绍")
    st.write(
        "CampusPath 是一个基于 Python 的 AI 智能校园导航系统，"
        "通过 A* 启发式搜索算法实现校园路径规划。"
    )

with right:
    st.subheader("开发信息")
    st.metric("核心算法", "A*")
    st.metric("开发语言", "Python")

# =========================
# 导航交互区域
# =========================

st.divider()

st.header("地点选择练习")
st.caption("以下为界面学习示例；实际 A* 搜索请进入左侧“智能导航”。")

# 校园地点（暂时使用模拟数据）
places = ["教学楼", "图书馆", "食堂", "宿舍", "实验楼"]

# 起点和终点选择
start_col, goal_col = st.columns(2)

with start_col:
    start = st.selectbox("选择起点", places)

with goal_col:
    goal = st.selectbox(
        "选择终点",
        places,
        index=1
    )

# 开始导航
if st.button("开始导航", type="primary"):
    if start == goal:
        st.info("起点和终点相同；实际搜索可返回 0 步。")
    else:
        st.success(f"模拟请求：{start} → {goal}（尚未搜索路线）")

# 地点搜索
st.subheader("地点查询")

keyword = st.text_input("请输入地点名称")

if st.button("查询地点"):
    if not keyword.strip():
        st.warning("请输入地点名称！")
    elif keyword in places:
        st.success(f"找到地点：{keyword}")
    else:
        st.error("没有找到该地点！")

# =========================
# Session State 测试
# =========================

st.divider()
st.header("Session State 测试")

# 初始化状态
if "count" not in st.session_state:
    st.session_state.count = 0

# 点击按钮增加计数
if st.button("计数 +1"):
    st.session_state.count += 1

# 展示计数
st.metric("当前计数", st.session_state.count)
