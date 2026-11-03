# 地图和数据库

`schema.sql` 定义地图、网格、地点和路线记录四张关联表；`store.py` 负责初始化和数据访问。第一次初始化会建立一张**模拟地图**及示例地点，不是真实校园数据。数据库默认存放在 `data/campuspath.db`，受 Git 忽略；测试可以在导入模块前设置 `CAMPUSPATH_DB_PATH` 指定独立的数据库路径。

主要接口：`init_database()`、`load_map()`、`save_grid(grid, expected_grid=..., expected_places=...)`、`add_place(...)`、`update_place(...)`、`delete_place(...)`、`save_route(...)` 和 `list_routes()`。保存网格时传入原始网格及地点基线，可检测其他会话的修改；保存查询时同时保存网格、起终点名称与坐标、路径和扩展顺序快照；调用 `save_route` 时应通过 `expected_start`、`expected_goal` 传入计算时的坐标，地点已被修改则拒绝保存。

当前只提供一张地图。`save_grid` 不调整地图尺寸，并检查所有地点入口，入口不能被改成障碍物；`replace_map(name, grid, places, *, expected_grid, expected_places)` 可在校验基线后原子替换整张地图、尺寸及地点，保留历史快照。地点是名称到 `(row, col)` 或 `[row, col]` 的字典；入口必须位于可通行区域，名称不得重复。删除地点不删除历史记录。数据库写入前应处理 `ValueError` 和 SQLite 错误，向用户显示适当提示。
