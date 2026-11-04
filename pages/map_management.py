import streamlit as st

from database.pdf_map import open_pdf_project, ROWS, COLS, CLASS_NAMES, set_building_marker, set_place_entrance
from visualization.pdf_map import pdf_map_figure

st.title("地图与地点维护")
st.caption("新 PDF 分类网格 · 地点位置、导航入口与可通行道路分开维护")

try:
    layout, service, revision, state = open_pdf_project()
except (OSError, ValueError, KeyError, TypeError) as error:
    st.error(f"无法加载新 PDF 地图：{error}")
    st.stop()

control_width = st.session_state.get("control_width", 25)
controls, map_panel = st.columns([control_width, 100 - control_width], gap="large")

with controls:
    with st.container(height=700, border=False):
        st.subheader("编辑地图格子")
        st.info(f"已保存 {len(state['places'])} 个地点标记；可在下方按名称查找和修改，可单独维护导航入口。")
        with st.form("pdf_cell_edit"):
            row = st.number_input("行", 0, ROWS-1, 0)
            col = st.number_input("列", 0, COLS-1, 0)
            classification = st.selectbox("调整分类", range(4), format_func=lambda i: CLASS_NAMES[i])
            save = st.form_submit_button("保存网格修改")
        st.write("当前格子：", CLASS_NAMES[state["classes"][row][col]])
        st.caption("只有道路格可通行；修改保存在新版本数据库，不覆盖 experiment 的地图。")
        if save:
            state["classes"][row][col] = classification
            state["grids"][0][row][col] = 0 if classification == 2 else 1
            try:
                service.save(state, revision)
                st.session_state.pop("pdf_route", None)
                st.rerun()
            except ValueError as error:
                st.error(str(error))
                st.stop()
        with st.expander("地点位置：查找、修改或新增", expanded=True):
            st.caption("标记可以在建筑内部；保存标记不会开放建筑格，也不会自动生成导航入口。")
            keyword = st.text_input("搜索已有地点", placeholder="输入名称筛选")
            matching = [n for n in state["places"] if keyword.strip().casefold() in n.casefold()]
            selected_name = st.selectbox("选择地点标记", ["新增地点标记", *matching],
                                        index=1 if keyword.strip() and matching else 0)
            old_name = None if selected_name == "新增地点标记" else selected_name
            old_point = state["places"].get(selected_name, [0, 0, 0])
            old_kind = state.get("place_kinds",{}).get(selected_name,"建筑")
            with st.form("pdf_building_marker"):
                marker_kind = st.selectbox("地点类型",["建筑","场地"],index=1 if old_kind=="场地" else 0)
                marker_name = st.text_input("地点名称", value=old_name or "")
                marker_row = st.number_input("地点标记行", 0, ROWS-1, old_point[1])
                marker_col = st.number_input("地点标记列", 0, COLS-1, old_point[2])
                marker_save = st.form_submit_button("保存地点标记")
            if marker_save:
                try:
                    set_building_marker(state, marker_name, marker_row, marker_col, old_name=old_name, kind=marker_kind)
                    service.save(state, revision)
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
                    st.stop()
        if old_name:
            with st.expander("导航入口：新增或修改"):
                st.caption("入口应设在已核对的道路格；可维护多个入口。建筑中心不必移动到道路上。")
                entries = state.get("entrances",{}).get(old_name,[])
                entry_choice = st.selectbox("选择入口",["新增入口",*[e["name"] for e in entries]])
                entry = next((e for e in entries if e["name"]==entry_choice),None)
                entry_point = entry["point"] if entry else old_point
                with st.form("pdf_place_entrance"):
                    entry_name = st.text_input("入口名称",value=entry["name"] if entry else "")
                    entry_row = st.number_input("入口行",0,ROWS-1,entry_point[1])
                    entry_col = st.number_input("入口列",0,COLS-1,entry_point[2])
                    entry_enabled = st.checkbox("入口启用",value=entry.get("enabled",True) if entry else True)
                    entry_save = st.form_submit_button("保存入口")
                if entry_save:
                    try:
                        set_place_entrance(state,old_name,entry_name,entry_row,entry_col,
                                           enabled=entry_enabled,old_name=entry["name"] if entry else None)
                        service.save(state,revision)
                        st.session_state.pop("pdf_route",None)
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
                        st.stop()
with map_panel:
    st.subheader("新地图与所选格子")
    with st.popover("图层与视图"):
        show_background=st.checkbox("显示 PDF 对照底图",value=False)
        show_grid=st.checkbox("显示细网格与坐标",value=False)
        show_building_labels=st.checkbox("显示全部地点名称",value=False)
        view=st.radio("视图范围",["全校","当前地点或格子"])
    st.caption("圆点统一表示地点；紫色高亮为当前选择。悬停查看名称和坐标，可在地图显示中聚焦所选地点。")
    selected = old_point[-2:] if old_name else (row, col)
    st.plotly_chart(pdf_map_figure(layout, state, show_background=show_background, selected=selected,
                                  show_building_labels=show_building_labels,show_grid=show_grid,focus=view!="全校"),
                    use_container_width=True, config={"scrollZoom": True})
