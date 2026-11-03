# 协作约定

## 数据约定

- 网格用非空矩形 `list[list[int]]` 表示：`0` 可通行，`1` 是障碍物。
- 道路采集页的 `verified_grid(records, blocked_cells=())` 可叠加额外禁行格，禁行格优先；普通网格和 `astar_search` 接口不变。天桥与地面道路的立体交叉目前不能由单层网格安全表达。
- 坐标统一为 `(row, col)`，从 0 开始；上、下、左、右移动，每步代价为 1。
- A* 使用曼哈顿距离并自主实现；BFS 对比为后续可选功能。
- 校园导航实验额外使用三张相同大小的二维网格（校内、校外道路、天桥）；`algorithms.layered_astar.layered_astar(grids, start, goal, portals)` 的坐标为 `(layer, row, col)`。每层四方向、代价为 1；仅在明确连接点换层，换层代价也为 1。曼哈顿启发式忽略层号，不会高估。原 `astar_search(grid, start, goal)` 保持不变。
- 天桥只在端点连接校内网格，不能因图面与海油大街相交就直接换层；通向校外道路只通过标记的校门连接。北侧限时门默认关闭，状态需手动设置，不是实时门禁数据。图面坐标和端点仍为近似，禁止将试算结果表述为实际安全路线。
- 校园实验地图和历史保存在 SQLite 独立表中，JSON 状态包含 `grids`、`places`、`place_status`、`portals` 和 `north_gate_open`；保存采用版本检查，历史保存查询快照。不会覆盖原有模拟地图和历史。
- 算法输入约定为 `grid, start, goal`，返回 `algorithms.path_result.PathResult`。具体函数由成员 B 实现。
- `path` 包含起点和终点，`path_length` 为移动步数；起点等于终点时为 0，不可达时为 `None`。`visited_order` 记录实际扩展顺序，`expanded_count` 与其长度一致，`elapsed_ms` 为算法耗时。
- 非法网格、越界或障碍物上的起终点应明确报错；不可达是正常搜索结果，`found=False` 且路径为空。

地图和地点应在数据库中关联地图 ID；路线记录应保存算法、起终点、结果及统计信息。表结构和数据访问函数由成员 A 与其他成员共同确定后实现，不由页面直接操作数据库。

## 分支与协作

`main` 是共同开发基线；从最新 `main` 建立下列功能分支：

| 分支 | 工作内容 |
| --- | --- |
| `feature/map-management` | A：地图和数据库 |
| `feature/path-planning` | B：算法和测试 |
| `feature/navigation-ui` | C：导航和可视化 |

各自提交后通过 Pull Request 请求其他成员检查并合并到 `main`；合并后同步 `main`，必要时更新各自分支。

不要提交 `local/`、虚拟环境、缓存或本地 SQLite 数据库；公共接口有变更时先沟通。真实校园数据应注明来源和核实状态，路线仅反映录入地图，定位为未来可选功能。运行时间受设备和测量方式影响，实验比较应保持条件一致，不应预设 A* 一定更快。
