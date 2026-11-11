# CampusPath 项目协作说明

## 项目目标

- 面向 Python 初学者开发校园地图与最短路径查询 Web 应用；优先使用简单、易理解的实现。
- 使用 Python、Streamlit、SQLite 和 Plotly。以真实校园为原型维护可编辑网格、地点和查询记录。
- 核心路径搜索自主实现 A*；四方向、单位步长、曼哈顿距离是当前约定。BFS、实时定位和自动播放属于后续可选功能。
- 真实道路、建筑入口及地图数据应标注来源和核实状态；不要把未核实的路线描述为实际可安全通行。

## 分工与接口

- 地图与数据库：`feature/map-management`，主要在 `database/` 和地图管理页面工作。
- A* 与测试：`feature/path-planning`，主要在 `algorithms/` 和 `tests/` 工作。
- 导航与可视化：`feature/navigation-ui`，主要在 `pages/` 和 `visualization/` 工作。
- 共同开发基线为 `main`。修改公共数据格式或接口前先查看 `docs/新PDF地图.md`，并在变更时同步更新说明。
- 网格使用 `0` 表示可通行、`1` 表示障碍物。当前地图和路径坐标均为二维 `(row, col)`，地图、算法和页面应使用一致的数据。

## 开发约束

- `local/` 是仅供本机参考的资料，不纳入提交；不要复制其中的反编译代码、密钥或未经授权的数据到仓库。
- 不提交虚拟环境、缓存或本地 SQLite 数据库；提交初始化脚本和允许分发的示例数据。
- 修改前先检查工作区和相关代码，保留他人的未提交工作；不要擅自提交、推送或删除分支。
- 按变更范围运行适当的检查；报告实际完成的功能与仍为占位的部分。

## experiment 当前实现

- 当前底图为 `reference/campus-map-basemap.pdf`，180×90 初始分类来自 `reference/initial-grid.json`。底图指纹与网格来源标识分别校验，保留已有数据库和 JSON 的坐标兼容性。旧版三层描述对应提交 `327c7b1`，不直接套用旧的校门和天桥坐标。
- 新地图代码在 database/pdf_map.py、visualization/pdf_map.py 和 pages/ 下四个产品页面。
- 建筑标记可位于建筑内部，不修改通行状态；新 PDF 已有 70 个建筑及 19 个场地标记，来源和坐标位于 reference/building-markers.json，入口与地点标记分开维护，缺少入口时使用明确标注待核实的临时接入点。
- `reference/place-entrances.json` 提供图面候选入口。候选使用 `source="map_inferred"`，保留待核实状态。初始资料在建库或手动恢复时加载，已有数据库读取已保存的地图。
- 每个地点只维护一个入口。入口字典仍使用单元素列表以兼容 JSON 格式，旧多入口优先保留已启用且可通行的一条。A* 对固定接入点计算一次，历史快照保留原内容。
- 旧模拟、APK/OSM 和旧图运行脚手架已清理，历史说明对应提交 `327c7b1`。
- `visualization/workspace.py` 和 `visualization/workspace.css` 为共用地图工作台；保留 Streamlit、Plotly、SQLite 和现有 A*。地图选择和撤销只更新草稿，保存地图时在 SQLite 事务中替换整张地图。
