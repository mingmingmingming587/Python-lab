# 地图和数据库

项目使用同一个本地 SQLite 数据库保存三类彼此独立的数据：

- **模拟地图**：`schema.sql` 定义地图、网格、地点和路线记录四张关联表；`store.py` 负责初始化和数据访问。第一次初始化建立模拟地图及示例地点。
- **道路采集**：`survey.py` 维护道路、入口、来源和核实状态，记录不自动修改校园实验网格。
- **校园导航实验**：`campus_project.py` 使用 `campus_project` 和 `campus_route_history` 两张独立表保存分层网格、地点、校门状态与路线快照；不会替换模拟地图。

数据库默认存放在 `data/campuspath.db`，受 Git 忽略；测试可以在导入模块前设置 `CAMPUSPATH_DB_PATH` 指定独立的数据库路径。校园数据首次初始化后不会因参考图或代码变化而自动覆盖；删除数据库会同时删除本机模拟数据、校园数据和历史，应先备份。

主要接口：`init_database()`、`load_map()`、`save_grid(grid, expected_grid=..., expected_places=...)`、`add_place(...)`、`update_place(...)`、`delete_place(...)`、`save_route(...)` 和 `list_routes()`。保存网格时传入原始网格及地点基线，可检测其他会话的修改；保存查询时同时保存网格、起终点名称与坐标、路径和扩展顺序快照；调用 `save_route` 时应通过 `expected_start`、`expected_goal` 传入计算时的坐标，地点已被修改则拒绝保存。

模拟地图目前只有一张。`save_grid` 不调整地图尺寸，并检查所有地点入口；`replace_map(name, grid, places, *, expected_name, expected_grid, expected_places)` 在校验基线后原子替换整张模拟地图、尺寸及地点，保留历史快照。地点是名称到 `(row, col)` 或 `[row, col]` 的字典；入口必须位于可通行区域，名称不得重复。删除地点不删除历史记录。

校园实验通过 `CampusMapService` 读取和保存，状态包含三张网格、地点、地点核实状态、跨层连接和限时门状态。保存时使用版本号检测冲突；校园历史保存查询时的状态、路径和扩展顺序。数据库写入前应处理 `ValueError` 和 SQLite 错误，向用户显示适当提示。
