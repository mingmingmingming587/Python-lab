# CampusPath 校园导航

Python 课程综合实验：基于网格地图的校园导航。项目使用 Streamlit 构建 Web 界面，计划使用 SQLite 保存地图和路线，并自主实现 A* 和 BFS。

当前是协作骨架：页面、数据库和算法尚待实现，不能用于实际导航。

## 启动

建议使用 Python 3.13。在项目根目录的 PowerShell 中执行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

如果本机没有 Python 3.13，可将第一行换成已安装的兼容版本。安装后按终端提示在浏览器打开应用。

## 分工与目录

| 成员 | 负责内容 | 主要目录 |
| --- | --- | --- |
| A | 地图、地点管理与数据库 | `database/`、`pages/1_地图管理.py` |
| B | A*、BFS、算法测试 | `algorithms/`、`tests/` |
| C | 导航、可视化及整合 | `app.py`、`pages/`、`visualization/` |

三人共享的数据约定和开发分支见 [协作约定](docs/collaboration.md)。需求、接口或分工调整应先与组员沟通。

1. A 实现地图、地点与路线记录的持久化接口。
2. B 自主实现四方向 A* 和 BFS，输出统一的搜索结果。
3. C 使用模拟数据开发地图展示，再接入 A、B 的接口。
4. 整合后验证完整业务流程，并对照老师的任务书验收。

Streamlit 是否符合课程对 Web GUI 的具体要求，建议向老师确认；本仓库的规划不替代原始任务书。
