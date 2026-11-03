import json
from pathlib import Path

import streamlit as st

from database.campus_project import LAYER_NAMES, CampusMapService
from database.survey import ROWS, COLS
from visualization.campus_navigation import navigation_figure
from visualization.user_markings import blocked_grid_cells

st.title("地图与地点维护")
st.caption("维护校园地图的通行状态、地点和校门设置。修改保存在本机。")
st.warning("图面位置及入口仍需实地核实；请只将确认通行的区域设为可通行。")

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


def persist(data):
    try:
        service.save(data, revision)
        st.session_state.pop("campus_route", None)
        st.rerun()
    except ValueError as error:
        st.error(str(error))
        st.stop()


control_width = st.session_state.get("control_width", 25)
controls, map_panel = st.columns([control_width, 100 - control_width], gap="large")
with controls:
    with st.container(height=700, border=False):
        st.caption("校内、校外道路和天桥分别维护；坐标为行、列，从 0 开始。")
        north_open = st.checkbox("将北侧限时门设为开放（状态保存在本机）", value=state["north_gate_open"], help="此开关只是实验设置，不能反映校门实时状态；用完后请按实际情况调整。")
        if north_open != state["north_gate_open"]:
            state["north_gate_open"] = north_open
            persist(state)

        with st.expander("地图维护：编辑通行网格"):
            st.caption("修改后立即保存到本机。红色禁行线和北侧限时门所在格子不能在校内或校外道路层强行改为可通行；门的开放状态通过上方开关设置。")
            with st.form("campus_cell_edit"):
                layer = st.selectbox("地图层", range(len(LAYER_NAMES)), format_func=lambda i: LAYER_NAMES[i])
                c1, c2 = st.columns(2)
                row = c1.number_input("行", min_value=0, max_value=ROWS - 1, value=0)
                col = c2.number_input("列", min_value=0, max_value=COLS - 1, value=0)
                cell_type = st.radio("调整为", ["不可通行", "可通行"], horizontal=True)
                apply_cell = st.form_submit_button("保存网格修改")
            st.write("当前格子：", "可通行" if state["grids"][layer][row][col] == 0 else "不可通行")
            if apply_cell:
                if cell_type == "可通行" and layer != 2 and (row, col) in blocked_grid_cells():
                    st.error("该格包含红色禁行线或限时门，不能直接设为可通行。")
                elif cell_type == "不可通行" and any(point == [layer, row, col] for point in state["places"].values()):
                    st.error("该格已有地点，请先调整地点位置，再将其设为不可通行。")
                else:
                    state["grids"][layer][row][col] = 0 if cell_type == "可通行" else 1
                    persist(state)

        with st.expander("地点维护：添加、修改或删除"):
            st.caption("从参考图自动生成的地点是附近道路位置；只有核实真实入口后，才应设为“用户已核实入口”。")
            options = ["新增地点", *state["places"]]
            selected = st.selectbox("选择要维护的地点", options)
            old = state["places"].get(selected, [0, 0, 0])
            old_status = state.get("place_status", {}).get(selected, "图面近似")
            with st.form("campus_place_edit"):
                name = st.text_input("地点名称", value="" if selected == "新增地点" else selected)
                layer_value = st.selectbox("地点所在层", range(len(LAYER_NAMES)), index=old[0], format_func=lambda i: LAYER_NAMES[i])
                a, b = st.columns(2)
                place_row = a.number_input("地点行", 0, ROWS - 1, old[1])
                place_col = b.number_input("地点列", 0, COLS - 1, old[2])
                place_status = st.selectbox("地点状态", ["图面近似", "用户已核实入口"], index=0 if old_status == "图面近似" else 1)
                save_place = st.form_submit_button("保存地点")
            if save_place:
                cleaned = name.strip()
                if not cleaned:
                    st.error("地点名称不能为空。")
                elif cleaned != selected and cleaned in state["places"]:
                    st.error("地点名称已存在。")
                elif state["grids"][layer_value][place_row][place_col] != 0:
                    st.error("地点必须位于对应层的可通行格。")
                else:
                    statuses = state.setdefault("place_status", {})
                    if selected != "新增地点" and selected != cleaned:
                        del state["places"][selected]
                        statuses.pop(selected, None)
                    state["places"][cleaned] = [layer_value, place_row, place_col]
                    statuses[cleaned] = place_status
                    persist(state)
            if selected != "新增地点" and st.button("删除所选地点"):
                del state["places"][selected]
                state.setdefault("place_status", {}).pop(selected, None)
                persist(state)

with map_panel:
    st.subheader("查看可通行网格")
    st.caption("绿色：可通行；灰色：不可通行或未录入；红色：标注禁行；黄色：限时门。鼠标悬停格子可查看行列。")
    grid_layer = st.selectbox("查看地图层", range(len(LAYER_NAMES)), format_func=lambda i: LAYER_NAMES[i])
    st.plotly_chart(navigation_figure(layout, state, show_grid=True, show_places=True, grid_layer=grid_layer), use_container_width=True, config={"scrollZoom": True})
