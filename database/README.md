# 地图数据库

`pdf_map.py` 加载 180×90 初始分类和 PDF 底图，只将道路格转为可通行。`campus_project.py` 的 `CampusMapService` 接收初始地图状态与数据库路径，使用 SQLite 保存地图修订和查询快照。

数据库文件为 `data/campuspath-integrated.db`，保存在本机。固定使用一张地图，四张业务表由 `campus_project.py` 初始化。

| 表 | 保存内容 |
| --- | --- |
| `maps` | 固定 ID、名称、大小、修订号和网格来源指纹 |
| `map_cells` | 每个格子的行列与分类，使用 `(row, col)` 作为主键 |
| `places` | 地点 ID、唯一名称、类型、标记位置、状态说明和可选入口 |
| `campus_route_history` | 查询 ID、时间、起终点、结果、路径、扩展顺序和查询快照 |

地图加载时依据分类生成二维通行网格。保存修改时在同一个事务中替换地图数据并递增修订号，供导航刷新结果。入口是否可用取决于启用状态和当前格子是否可通行。

`places` 的 `row`、`col` 保存地点标记坐标。`entrance_name`、`entrance_row`、`entrance_col`、`entrance_enabled` 和 `entrance_source` 保存入口信息，未设置入口时五列均为 `NULL`。入口来源为 `manual`（手工录入）或 `map_inferred`（图面推定，待核实）。初始地点和入口在建库或手动恢复初始地图时加载。地图 JSON 使用网格来源指纹校验坐标是否对应。

SQLite 用 `user_version = 5` 识别表结构。查询快照、路径和扩展顺序都使用二维坐标。历史步数和扩展节点数由读取层根据路径和扩展顺序计算。
