import streamlit as st
import hashlib
import json
from database.store import init_database, load_map, add_place, update_place, delete_place, replace_map

st.title("校园地图管理")
st.caption("初始地图是模拟数据；导入数据的道路、入口和使用权限需要自行核实。网格编辑请在智能导航页面进行。")
init_database()
data = load_map()
grid, places = data["grid"], data["places"]
st.write("地图：", data["name"], "｜尺寸：", len(grid), "行 ×", len(grid[0]), "列")
st.write("地点入口（行、列）：", places)

st.subheader("备份与导入地图")
st.caption("导入会替换当前地图和地点；历史路线及其查询时快照会保留。下载的地图备份不包含历史记录。")
backup = json.dumps({"name": data["name"], "grid": grid, "places": places}, ensure_ascii=False, indent=2)
st.download_button("下载当前地图 JSON", backup, file_name="campus-map.json", mime="application/json")
uploaded = st.file_uploader("选择地图 JSON", type=["json"], help="格式：name 为地图名称，grid 为二维 0/1 列表，places 为地点名称到 [行, 列] 的对象。")
if uploaded:
    try:
        raw = uploaded.getvalue()
        if len(raw) > 2_000_000:
            raise ValueError("文件不能超过 2 MB")
        def unique_keys(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"JSON 中有重复字段：{key}")
                result[key] = value
            return result
        candidate = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_keys)
        if not isinstance(candidate, dict) or set(candidate) != {"name", "grid", "places"}:
            raise ValueError("JSON 顶层必须包含且仅包含 name、grid、places")
        digest = hashlib.sha256(raw).hexdigest()
        if st.session_state.get("import_digest") != digest:
            st.session_state.import_digest = digest
            st.session_state.import_baseline = (data["name"], grid, places)
        st.write("导入文件的地图名称：", candidate["name"])
        st.caption("导入前会校验网格和入口；地图数据是否真实、是否获授权仍需人工确认。")
        confirm = st.checkbox("我已备份，并确认替换当前地图", key=f"confirm_import_{digest}")
        if st.button("导入并替换地图", disabled=not confirm):
            expected_name, expected_grid, expected_places = st.session_state.import_baseline
            replace_map(candidate["name"], candidate["grid"], candidate["places"], expected_name=expected_name, expected_grid=expected_grid, expected_places=expected_places)
            st.session_state.pop("import_digest", None)
            st.rerun()
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        st.error(f"无法导入地图：{error}")

with st.form("add_place"):
    st.subheader("添加地点")
    name = st.text_input("名称")
    row = st.number_input("行", min_value=0, max_value=len(grid)-1, step=1)
    col = st.number_input("列", min_value=0, max_value=len(grid[0])-1, step=1)
    if st.form_submit_button("添加"):
        try:
            add_place(name, int(row), int(col))
            st.rerun()
        except ValueError as error:
            st.error(str(error))

if places:
    selected = st.selectbox("选择地点", list(places))
    with st.form("edit_place"):
        st.subheader("修改地点")
        new_name = st.text_input("新名称", value=selected)
        new_row = st.number_input("入口行", min_value=0, max_value=len(grid)-1, value=places[selected][0], step=1)
        new_col = st.number_input("入口列", min_value=0, max_value=len(grid[0])-1, value=places[selected][1], step=1)
        if st.form_submit_button("保存地点"):
            try:
                update_place(selected, new_name, int(new_row), int(new_col))
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    confirm = st.checkbox("确认删除所选地点", key=f"confirm_delete_{selected}")
    if st.button("删除地点", disabled=not confirm):
        try:
            delete_place(selected)
            st.rerun()
        except ValueError as error:
            st.error(str(error))
