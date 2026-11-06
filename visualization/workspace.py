"""Streamlit 地图工作台。四个入口共用地图、视图设置和会话选择。"""

from collections import Counter, deque
from copy import deepcopy
import json
from math import ceil, floor
from pathlib import Path

import streamlit as st

from algorithms.path_result import PathResult
from algorithms.place_navigation import access_points, plan_named_route
from database.pdf_map import (CLASS_NAMES, COLS, ROWS, open_pdf_project,
                              road_components, set_building_marker,
                              set_grid_region, set_place_entrance)
from visualization.pdf_map import pdf_map_figure


MODES = ["导航", "地点", "历史", "维护"]
EDIT_HISTORY_LIMIT = 20


def _swap_endpoints():
    ss = st.session_state
    ss.nav_start, ss.nav_goal = ss.nav_goal, ss.nav_start
    ss.nav_gate_start, ss.nav_gate_goal = ss.nav_gate_goal, ss.nav_gate_start
    ss.pop("nav_route", None)
    ss.playing = False


def _remember(widget, domain):
    st.session_state[domain] = st.session_state[widget]


def _use_map_place(side):
    ss = st.session_state
    ss["nav_"+side] = ss.map_place
    ss["nav_gate_"+side] = None
    ss.pop("nav_route",None)
    ss.playing = False


def _choose(widget, domain, fallback):
    st.session_state[domain] = st.session_state[widget] or fallback


def _map_selected():
    """只更新会话选择；保存按钮才会写入 SQLite。"""
    ss = st.session_state
    if ss.get("playing",False) or ss.workspace_mode == "历史":
        return
    selection = ss.get("workspace_map", {}).get("selection", {})
    boxes, points = selection.get("box", []), selection.get("points", [])
    if ss.workspace_mode == "维护" and ss.map_tool == "框选" and boxes:
        box = boxes[-1]
        xs, ys = box.get("x", []), box.get("y", [])
        if len(xs) != 2 or len(ys) != 2:
            return
        # 按格心是否落入框选范围确定闭区间，与显示格子一致。
        c1, c2 = max(0, ceil(min(xs)-.5)), min(COLS-1, floor(max(xs)-.5))
        r1, r2 = max(0, ceil(min(ys)-.5)), min(ROWS-1, floor(max(ys)-.5))
        if r1 > r2 or c1 > c2:
            return
        ss.edit_bounds = (r1,c1,r2,c2)
        ss._edit_row, ss._edit_col = r1,c1
    elif points:
        data = points[-1].get("customdata", [])
        if len(data) < 2:
            return
        row, col = int(data[0]), int(data[1])
        if not (0 <= row < ROWS and 0 <= col < COLS):
            return
        name = data[3] if len(data) > 3 else ""
        if ss.workspace_mode == "导航" and name:
            if ss.map_tool == "设起点":
                ss.nav_start, ss.nav_gate_start = name, None
            elif ss.map_tool == "设终点":
                ss.nav_goal, ss.nav_gate_goal = name, None
            ss.map_place = name
            if ss.map_tool in ("设起点", "设终点"):
                ss.pop("nav_route", None)
                ss.playing = False
        elif ss.workspace_mode == "地点" and ss.map_tool in ("标记位置", "入口位置"):
            prefix = "_marker" if ss.map_tool == "标记位置" else "_entry"
            ss[prefix+"_row"], ss[prefix+"_col"] = row,col
        elif ss.workspace_mode == "维护" and ss.map_tool in ("选格", "框选"):
            ss.edit_bounds = (row,col,row,col)
            ss._edit_row, ss._edit_col = row,col
        elif name:
            ss.map_place = name
            ss.selected_place = name
    else:
        return
    ss.map_needs_app = True


def _stage_edit(revision, before, edited):
    if edited == before:
        return
    ss = st.session_state
    draft = ss.get("map_draft")
    if draft is None:
        draft = {"revision": revision, "undo": deque(maxlen=EDIT_HISTORY_LIMIT), "redo": []}
        ss.map_draft = draft
    draft["undo"].append(before)
    draft["redo"].clear()
    draft["state"] = edited
    st.rerun()


def _reset_place_forms():
    ss = st.session_state
    ss.pop("marker_for", None)
    ss.pop("entry_for", None)


def _draft_controls(saved, service, revision):
    ss = st.session_state
    draft = ss.get("map_draft")
    st.caption("地图草稿 · 应用修改后可预览，点击「保存地图」后生效。")
    left, right = st.columns(2)
    back = left.button("后退", key="map_draft_undo", disabled=not (draft and draft["undo"]),
                       width="stretch")
    forward = right.button("前进", key="map_draft_redo", disabled=not (draft and draft["redo"]),
                           width="stretch")
    st.caption("Ctrl+Z 后退 · Ctrl+Y 前进")
    st.html("""<script>
        if (!window.campusPathDraftShortcuts) {
            window.campusPathDraftShortcuts = true;
            document.addEventListener("keydown", (event) => {
                if (!event.ctrlKey || event.shiftKey || event.altKey || event.metaKey ||
                    event.repeat || event.defaultPrevented ||
                    event.target.closest?.("input, textarea, select, [role=textbox]") ||
                    event.target.isContentEditable) return;
                const key = event.key.toLowerCase();
                const action = {z: "undo", y: "redo"}[key];
                if (!action) return;
                const button = document.querySelector(".st-key-map_draft_" + action + " button");
                if (!button || button.disabled) return;
                event.preventDefault();
                button.click();
            });
        }
        </script>""", unsafe_allow_javascript=True)

    if back or forward:
        source, destination = ("undo", "redo") if back else ("redo", "undo")
        draft[destination].append(draft["state"])
        draft["state"] = draft[source].pop()
        _reset_place_forms()
        st.rerun()

    stale = draft is not None and draft["revision"] != revision
    if stale:
        st.warning("地图已被其他会话修改。请放弃当前草稿，再基于最新地图编辑。")
    save = st.button("保存地图", type="primary", width="stretch",
                     disabled=draft is None or stale or draft["state"] == saved)
    if st.button("放弃草稿", width="stretch", disabled=draft is None):
        ss.pop("map_draft")
        _reset_place_forms()
        st.rerun()
    if not save:
        return

    try:
        service.save(draft["state"], draft["revision"])
    except ValueError as error:
        st.error(str(error))
        return
    ss.pop("map_draft")
    ss.pop("nav_route", None)
    ss.playing = False
    ss.notice = "地图已保存"
    st.rerun()


def _header(state, revision):
    roads = sum(v == 0 for line in state["grid"] for v in line)
    st.html(Path(__file__).with_name("workspace.css").read_text(encoding="utf-8"))
    st.html(f'''<header class="campus-header">
      <div class="campus-brand"><span class="campus-logo">CP</span>
        <div><h1>校园地图</h1><p>CampusPath · 应急管理大学</p></div></div>
      <div class="campus-stats"><span><b>{ROWS} × {COLS}</b> 网格</span>
        <span><b>{len(state['places'])}</b> 地点</span><span><b>{roads:,}</b> 道路格</span></div>
      <div class="campus-status"><i></i> 已加载 · 版本 {revision}<small>图面数据 · 入口待核实</small></div>
    </header>''')


def _navigation(state, service, revision):
    ss = st.session_state
    names = list(state["places"])
    st.subheader("规划一条校园路线")
    st.caption("输入名称查找，或在地图上点选地点。")
    if ss.get("map_place") in state["places"]:
        st.info("当前点选："+ss.map_place)
        c1,c2 = st.columns(2)
        c1.button("设为起点",on_click=_use_map_place,args=("start",),width="stretch")
        c2.button("设为终点",on_click=_use_map_place,args=("goal",),width="stretch")
    for side, label, preferred in (("start","起点","学子苑7号"),("goal","终点","图书馆（东）")):
        key = "nav_"+side
        if ss.get(key) not in names:
            ss[key] = preferred if preferred in names else (names[min(side=="goal",len(names)-1)] if names else None)
        ss["_"+key] = ss[key]
        st.selectbox(label, names, key="_"+key, disabled=not names,
                     placeholder="输入名称搜索地点",
                     on_change=_remember,args=("_"+key,key))
    st.button("交换起点与终点", on_click=_swap_endpoints, width="stretch")
    start, goal = (ss.nav_start if names else None), (ss.nav_goal if names else None)
    ready = bool(start and goal)
    chosen, entries = {}, {}
    if ready:
        try:
            for side, label, name in (("start","起点",start),("goal","终点",goal)):
                available = access_points(state,name)
                entries[side] = available
                options = ["自动选择最短入口"]+[e["name"] for e in available]
                gate_key = "nav_gate_"+side
                if ss.get(gate_key) not in options:
                    ss[gate_key] = "自动选择最短入口"
                if len(available)>1:
                    ss["_"+gate_key] = ss[gate_key]
                    st.selectbox(label+"入口", options, key="_"+gate_key,
                                 on_change=_remember,args=("_"+gate_key,gate_key))
                chosen[side] = None if ss[gate_key]=="自动选择最短入口" else ss[gate_key]
            if any(items[0]["temporary"] for items in entries.values()):
                st.warning("部分地点尚未录入入口，暂用附近道路格接入；这些点不是已核实的实际门。")
        except ValueError as error:
            st.error(str(error))
            ready = False
    signature = (revision,start,goal,chosen.get("start"),chosen.get("goal"))
    route = ss.get("nav_route")
    if route and route["signature"] != signature:
        ss.pop("nav_route",None)
        ss.playing = False
        route = None
    if st.button("开始 A* 搜索",type="primary",disabled=not ready,width="stretch"):
        try:
            result, a, b = plan_named_route(state,start,goal,chosen["start"],chosen["goal"])
            service.save_route(start,goal,{**state,"route_query":{"start_access":a,"goal_access":b}},result)
            route = {"signature":signature,"result":result,"start_access":a,"goal_access":b}
            ss.nav_route = route
            ss.search_step = result.expanded_count
            ss.playing = False
        except ValueError as error:
            st.error(str(error))
    view = {"start":state["places"].get(start),"goal":state["places"].get(goal)}
    if route:
        result = route["result"]
        st.divider()
        if result.found:
            st.success(f"{start} → {goal}")
        else:
            st.warning("当前入口之间没有可达路线，请核对道路和入口。")
        st.html(f'''<div class="route-metrics"><div><small>路网长度</small><b>{result.path_length if result.found else '—'}<em> 步</em></b></div>
          <div><small>扩展节点</small><b>{result.expanded_count}</b></div>
          <div><small>计算耗时</small><b>{result.elapsed_ms:.1f}<em> ms</em></b></div></div>''')
        st.caption("只计算入口间的道路段步数，不含建筑内部，也不等于实际米数。")
        with st.expander("A* 搜索过程",expanded=True):
            ss._show_visited = ss.show_visited
            st.checkbox("显示已扩展网格",key="_show_visited",on_change=_remember,
                        args=("_show_visited","show_visited"))
            ss._search_step = ss.search_step
            st.slider("搜索过程：已扩展节点",0,result.expanded_count,key="_search_step",disabled=ss.playing,
                      on_change=_remember,args=("_search_step","search_step"))
            if st.button("暂停播放" if ss.playing else "播放搜索过程",width="stretch"):
                ss.playing = not ss.playing
                if ss.playing:
                    ss.show_visited = True
                    if ss.search_step >= result.expanded_count:
                        ss.search_step = 0
                st.rerun()
            for side,label in (("start","起点"),("goal","终点")):
                entry = route[side+"_access"]
                st.caption(f"{label}接入：{entry['name']} · {tuple(entry['point'][-2:])}" +
                           (" · 待核实" if entry["temporary"] else " · 手动指定"))
        view.update(result=result,access_start=route["start_access"]["point"],
                    access_goal=route["goal_access"]["point"])
    else:
        st.html('<div class="campus-empty"><b>A*</b><p>选好起终点，开始探索校园</p><small>四方向移动 · 单位步长 · 曼哈顿距离</small></div>')
    return view


def _places(state, revision):
    ss = st.session_state
    st.subheader("地点与建筑入口")
    options = ["新增地点标记",*state["places"]]
    selected = ss.get("selected_place", "新增地点标记")
    if selected not in options:
        selected = "新增地点标记"
    ss._place_select = selected
    st.selectbox("选择地点标记",options,key="_place_select",placeholder="输入名称搜索地点",on_change=_remember,
                 args=("_place_select","selected_place"))
    ss.selected_place = selected
    old_name = None if selected=="新增地点标记" else selected
    point = state["places"].get(selected,[0,0])
    if ss.get("marker_for") != selected or "_marker_name" not in ss:
        ss.marker_for = selected
        ss._marker_name = old_name or ""
        ss._marker_row, ss._marker_col = point
        ss._marker_kind = state.get("place_kinds",{}).get(selected,"建筑")
    st.caption("地点圆点可以放在建筑内部；入口单独设置在道路上。")
    with st.form("place_marker"):
        st.text_input("地点名称",key="_marker_name")
        st.selectbox("地点类型",["建筑","场地"],key="_marker_kind")
        c1,c2 = st.columns(2)
        c1.number_input("地点标记行",0,ROWS-1,key="_marker_row")
        c2.number_input("地点标记列",0,COLS-1,key="_marker_col")
        if st.form_submit_button("应用地点标记",width="stretch"):
            edited = deepcopy(state)
            try:
                set_building_marker(edited,ss._marker_name,ss._marker_row,ss._marker_col,
                                    old_name=old_name,kind=ss._marker_kind)
            except ValueError as error:
                st.error(str(error))
            else:
                ss.selected_place = ss._marker_name.strip()
                _stage_edit(revision,state,edited)
    selected_point = [ss._marker_row,ss._marker_col]
    if old_name:
        with st.expander("导航入口：新增或修改",expanded=True):
            entries = state.get("entrances",{}).get(old_name,[])
            if not entries:
                st.caption("该地点尚未录入入口。应用入口后，地图预览会显示方形图标。")
            entry_choice = st.selectbox("选择入口",["新增入口",*[e["name"] for e in entries]])
            entry = next((e for e in entries if e["name"]==entry_choice),None)
            identity = (old_name,entry_choice)
            if ss.get("entry_for") != identity or "_entry_name" not in ss:
                ss.entry_for = identity
                ss._entry_name = entry["name"] if entry else ""
                ss._entry_row,ss._entry_col = entry["point"] if entry else point
                ss._entry_enabled = entry.get("enabled",True) if entry else True
            with st.form("place_entry"):
                st.text_input("入口名称",key="_entry_name",placeholder="例如：南门、北门")
                c1,c2 = st.columns(2)
                c1.number_input("入口行",0,ROWS-1,key="_entry_row")
                c2.number_input("入口列",0,COLS-1,key="_entry_col")
                st.checkbox("入口启用",key="_entry_enabled")
                if st.form_submit_button("应用入口",width="stretch"):
                    edited = deepcopy(state)
                    try:
                        set_place_entrance(edited,old_name,ss._entry_name,ss._entry_row,ss._entry_col,
                                          enabled=ss._entry_enabled,old_name=entry["name"] if entry else None)
                    except ValueError as error:
                        st.error(str(error))
                    else:
                        _stage_edit(revision,state,edited)
            st.caption("入口必须位于道路格。可维护多个入口，停用后不参与导航。")
            if ss.map_tool == "入口位置":
                selected_point = [ss._entry_row,ss._entry_col]
    return {"selected":selected_point}


def _history(state, service):
    st.subheader("路线记录")
    history = service.history()
    if not history:
        st.html('<div class="campus-empty"><b>↗</b><p>还没有查询记录</p><small>完成一次导航后，路线会自动保存在这里。</small></div>')
        return state,{}
    by_id = {item["id"]:item for item in history}
    chosen = st.selectbox("选择历史记录",list(by_id),
        format_func=lambda i:f"#{i} · {by_id[i]['start_name']} → {by_id[i]['goal_name']}")
    item = by_id[chosen]
    st.caption(item["created_at"])
    st.write("结果：", "找到路线" if item["found"] else "不可达")
    c1,c2 = st.columns(2)
    c1.metric("路网段步数",item["path_length"] if item["found"] else "—")
    c2.metric("扩展节点",item["expanded_count"])
    st.info("地图展示查询时保存的快照，后续编辑不会改写这条历史路线。")
    saved = item["snapshot"]
    query = saved.get("route_query",{})
    a,b = query.get("start_access"),query.get("goal_access")
    if any(e and e.get("temporary") for e in (a,b)):
        st.warning("此记录使用了待核实的临时接入点，长度仅为道路段步数。")
    result = PathResult(bool(item["found"]),item["path"],item["visited"],item["expanded_count"],0.0,item["path_length"])
    return saved,{"result":result,"start":saved["places"].get(item["start_name"]),
                  "goal":saved["places"].get(item["goal_name"]),
                  "access_start":a["point"] if a else None,"access_goal":b["point"] if b else None}


def _maintenance(state, revision):
    ss = st.session_state
    st.subheader("地图维护")
    st.caption("点选一个格子，或框选一片区域，再把分类应用到草稿。")
    with st.form("grid_edit"):
        c1,c2 = st.columns(2)
        row = c1.number_input("行",0,ROWS-1,key="_edit_row")
        col = c2.number_input("列",0,COLS-1,key="_edit_col")
        bounds = ss.get("edit_bounds",(row,col,row,col))
        if (row,col) != tuple(bounds[:2]):
            bounds = (row,col,row,col)
        count = (bounds[2]-bounds[0]+1)*(bounds[3]-bounds[1]+1)
        st.caption(f"选区：行 {bounds[0]}～{bounds[2]}，列 {bounds[1]}～{bounds[3]} · {count} 格")
        classification = st.selectbox("调整分类",range(4),format_func=lambda i:CLASS_NAMES[i])
        st.caption("当前首格："+CLASS_NAMES[state["classes"][row][col]])
        if st.form_submit_button("应用网格修改",width="stretch"):
            edited = deepcopy(state)
            set_grid_region(edited,bounds,classification)
            _stage_edit(revision,state,edited)
    st.caption("仅道路格可通行。框选只预览选区。")
    st.download_button("导出当前地图 JSON",json.dumps({"format":"campuspath-integrated-1","state":state},ensure_ascii=False,indent=2),
                       file_name="campus-map.json",mime="application/json",width="stretch")
    with st.expander("道路信息核查",expanded=True):
        counts = Counter(v for line in state["classes"] for v in line)
        st.dataframe([{"分类":CLASS_NAMES[i],"格子数":counts[i]} for i in range(4)],hide_index=True,width="stretch")
        components = road_components(state["grid"])
        st.write("四方向道路连通区域：",len(components))
        st.dataframe([{"区域":i+1,"道路格数":len(c)} for i,c in enumerate(components)],hide_index=True,width="stretch")
    with st.expander("地图来源与使用范围"):
        st.write("来源：reference/campus-map-integrated.pdf")
        st.write("第 2 页分类与第 3 页道路网格逐格核对。")
        st.warning("当前为平面网格，不含已核实的天桥跨层关系。路线用于课程与图面校对，不能作为实地导航依据。")
    return {"selected":[row,col],"selection_bounds":bounds}


def render_workspace(default_mode="导航"):
    ss = st.session_state
    try:
        layout,service,revision,state = open_pdf_project()
    except (OSError,ValueError,KeyError,TypeError) as error:
        st.error(f"无法加载校园地图：{error}")
        st.stop()
    defaults = {"control_width":25,"playing":False,"show_visited":False,
                "show_background":True,"show_grid":False,"show_labels":True,
                "focus_map":False,"view_revision":0,"map_tool":"查看",
                "nav_gate_start":None,"nav_gate_goal":None,"map_scale":"清晰浏览"}
    for key,value in defaults.items():
        ss.setdefault(key,value)
    if not ss.get("coordinates_2d_applied"):
        # 旧浏览器会话中的路线仍可能使用三维坐标，需重新查询。
        ss.pop("nav_route", None)
        ss.playing = False
        ss.coordinates_2d_applied = True
    if not ss.get("map_text_defaults_applied"):
        # 为已经打开的旧会话恢复文字；之后仍尊重使用者手动切换的选项。
        ss.show_background = ss.show_labels = True
        ss.map_scale = "清晰浏览"
        ss.view_revision += 1
        ss.map_text_defaults_applied = True
    if ss.get("entry_mode") != default_mode:
        ss.entry_mode = default_mode
        ss.workspace_mode = default_mode
        ss.pop("_workspace_mode",None)
    mode = ss.get("workspace_mode",default_mode)
    tools = {"导航":["查看","设起点","设终点"],"地点":["查看","标记位置","入口位置"],
             "历史":["查看"],"维护":["查看","选格","框选"]}[mode]
    if ss.map_tool not in tools:
        ss.map_tool = "查看"
    editing = mode in ("地点", "维护")
    draft = ss.get("map_draft") if editing else None
    display_state = draft["state"] if draft else state
    _header(display_state,revision)
    controls,map_panel = st.container(key="workspace_layout").columns(
        [ss.control_width,100-ss.control_width],gap="medium")
    view = {}
    with controls:
        with st.container(height=780,border=True,key="workspace_controls"):
            st.segmented_control("操作台",MODES,key="_workspace_mode",default=mode,selection_mode="single",
                                 on_change=_choose,args=("_workspace_mode","workspace_mode",mode),
                                 label_visibility="collapsed",width="stretch")
            # 切换模式时结束播放；导航结果与视图保留在会话里。
            if mode != "导航":
                ss.playing = False
            notice = ss.pop("notice",None)
            if notice:
                st.success(notice)
            if editing:
                _draft_controls(state, service, revision)
            if mode=="导航":
                view = _navigation(state,service,revision)
            elif mode=="地点":
                view = _places(display_state,revision)
            elif mode=="历史":
                display_state,view = _history(state,service)
            else:
                view = _maintenance(display_state,revision)
    with map_panel:
        with st.container(height=780,border=True,key="workspace_map_panel"):
            tools_col,options_col = st.columns([3,2],vertical_alignment="center")
            with tools_col:
                tool = st.segmented_control("地图操作",tools,key="_map_tool",default=ss.map_tool,
                                     on_change=_choose,args=("_map_tool","map_tool","查看"),
                                     label_visibility="collapsed",width="stretch")
                ss.map_tool = tool or "查看"
            with options_col:
                with st.popover("图层与布局",width="stretch"):
                    ss._map_scale = ss.map_scale
                    st.radio("地图尺度",["清晰浏览","全校总览"],key="_map_scale",
                             on_change=_remember,args=("_map_scale","map_scale"),
                             help="清晰浏览放大图面，可在地图区域上下滚动；全校总览用于查看整体布局。")
                    for key,label in (("show_background","显示 PDF 对照底图"),
                                      ("show_grid","显示细网格与坐标"),
                                      ("show_labels","显示全部地点名称"),
                                      ("focus_map","聚焦当前路线或地点")):
                        widget = "_view_"+key
                        ss[widget] = ss[key]
                        st.checkbox(label,key=widget,on_change=_remember,args=(widget,key))
                    ss._control_width = ss.control_width
                    st.slider("左侧宽度（%）",25,33,key="_control_width",on_change=_remember,
                              args=("_control_width","control_width"))
                    if st.button("复位地图视图",width="stretch"):
                        ss.view_revision += 1
                    st.caption("当前为平面地图；入口与实际通行情况仍需核实。")
            hints = {"查看":"悬停查看地点；可用地图右上角工具缩放，拖动平移。",
                     "设起点":"点击地点圆点，将其设为起点。","设终点":"点击地点圆点，将其设为终点。",
                     "标记位置":"点击格心回填地点坐标，确认后保存。","入口位置":"先选择地点，再点击道路格回填入口坐标。",
                     "选格":"点击格心选择待修改格子，确认后保存。","框选":"拖出矩形选区，确认分类后保存。"}
            st.caption(hints[ss.map_tool]+(" 在地图区域上下滚动可查看其余校园。" if ss.map_scale=="清晰浏览" and not ss.focus_map else ""))

            @st.fragment(run_every=.18 if ss.playing else None)
            def map_canvas():
                if ss.pop("map_needs_app",False):
                    st.rerun()
                result = view.get("result")
                step = result.expanded_count if result else None
                if mode=="导航" and result:
                    step = min(ss.get("search_step",result.expanded_count),result.expanded_count)
                    if ss.playing:
                        step = min(result.expanded_count,step+max(1,ceil(result.expanded_count/45)))
                        ss.search_step = step
                        if step==result.expanded_count:
                            ss.playing = False
                            st.rerun()
                detailed = ss.map_scale=="清晰浏览" and not ss.focus_map
                map_height = 1800 if detailed else 600
                figure = pdf_map_figure(layout,display_state,**view,step=step,
                    show_background=ss.show_background,show_grid=ss.show_grid,
                    show_building_labels=ss.show_labels,show_visited=ss.show_visited and mode=="导航",
                    focus=ss.focus_map,view_revision=(ss.view_revision,ss.map_scale),
                    label_cell_pixels=9.5 if detailed else 3.2,
                    selectable_cells=ss.map_tool in ("标记位置","入口位置","选格","框选"))
                figure.update_layout(height=map_height,dragmode="select" if ss.map_tool=="框选" else "pan")
                st.plotly_chart(figure,key="workspace_map",width="stretch",height=map_height,
                    theme=None,on_select=_map_selected,selection_mode=("points","box"),
                    config={"scrollZoom":not detailed,"displaylogo":False,
                            "modeBarButtonsToRemove":["select2d","lasso2d"]})
            with st.container(height=620,border=False,key="map_canvas_scroll"):
                map_canvas()
            st.html('<div class="campus-legend"><span><i class="legend-building"></i>建筑</span><span><i class="legend-road"></i>道路</span><span><i class="legend-boundary"></i>边界</span><span><i class="legend-route"></i>A* 路线</span><span><i class="legend-entrance"></i>入口启用</span><span><i class="legend-entrance-blocked"></i>入口受阻</span><span><i class="legend-entrance-disabled"></i>入口停用</span></div>')
