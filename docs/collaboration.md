# 协作约定

当前开发分支为 `experiment`，已合入原 `experiment1.2`，运行入口为 `app.py`。

## 数据

- `classes` 是 180×90 的列表套列表，0 未标注、1 建筑、2 道路、3 边界。
- `grids[0]` 是由分类生成的通行网格：道路为 0，其余为 1。当前 PDF 仅有平面层，`portals` 为空；旧版三层门和天桥坐标不迁入。
- 算法坐标为 `(layer, row, col)`，当前 layer 为 0；同层上下左右移动，单位代价，曼哈顿启发式。未来加入跨层连接时只能显式指定。
- `places` 为建筑位置标记，可以位于建筑格内；保存标记不得把建筑变成可走格。建筑标记与导航入口分开，入口尚未录入。`reference/building-markers.json` 包含 70 个建筑和 19 个场地标记，并绑定 PDF 文件指纹；首次加载时只补入缺失名称，不覆盖手动同名标记。
- 新版本使用 `data/campuspath-integrated.db`，不修改旧数据库。

## 接口

- `open_pdf_project()` 返回 layout、service、revision、state。
- `CampusMapService(initial_state, db_path)` 初始化独立地图，提供 load、save、save_route、history。save 使用 revision 检查并发修改，历史保存查询时的地图快照。
- `layered_astar(grids, start, goal, portals=())` 返回 PathResult；path 包含两端，path_length 为步数，不可达为 None。建筑内部或越界端点应报错。

旧版地图实现可查看提交 `327c7b1`；协作约定的历史计划见 `docs/计划书261030.md`。地图来源及当前限制见 `note/新PDF地图.md`。

## 地点与入口

- `place_kinds[name]` 为建筑或场地。场地中心可位于未标注格，但不会将其转换为可走格。
- `entrances[name]` 为入口列表，每项含 name、point（层、行、列）、enabled。入口必须落在道路格。
- `access_points` 优先使用已指定且可用的入口，缺少入口时才返回有 temporary 标志的临时道路接入点。
- `plan_named_route` 比较可用入口组合的 A* 道路段步数；不会打开建筑或场地内部。
- 查询快照 `route_query` 保存实际使用的接入点及是否临时。

## 地图工作台

- `visualization/workspace.py` 共用导航、地点、历史和维护界面；`pages/` 保留原地址入口。样式在 `visualization/workspace.css`，Streamlit 主题在 `.streamlit/config.toml`。
- `set_grid_region(state, bounds, classification)` 同步修改分类和通行网格；`bounds` 是闭区间 `(起始行, 起始列, 结束行, 结束列)`，必须先校验整个范围，再改格子。
- 图面仍使用热力图；编辑时临时增加格心散点接收 Plotly 原生选择事件。地点点选数据为 `[layer, row, col, kind, name]`。选择只更新会话，确认保存时才写 SQLite。
- 导航选择、视图和播放进度与控件临时键分开保存，避免切换模式或入口时被 Streamlit 清理。单步撤销也使用数据库 revision 校验，不覆盖其他会话的修改。
