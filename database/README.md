# 地图数据保存

`pdf_map.py` 从新 PDF 提取 180×90 分类，并只将道路格转为可通行。`campus_project.py` 的 `CampusMapService` 接收初始地图状态与数据库路径，使用 SQLite 保存地图版本和查询快照。

新数据库为 `data/campuspath-integrated.db`，不纳入提交。程序只访问 `campus_project` 和 `campus_route_history` 两张表；保存检查 revision 防止覆盖其他会话的编辑。旧数据库不读取、不覆盖。

建筑标记可放在建筑内部，位置保存在 `places`，不会改变通行网格。地图初始包含已核对的 70 个建筑图面标记，入口尚未设置。旧的新地图数据库只补入缺失标记，不覆盖已有同名标记或改变通行网格。
