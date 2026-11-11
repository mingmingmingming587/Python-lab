# 检查

在仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -q
```

- `test_astar.py`：与独立 BFS 比较二维最短步数、非法端点和不可达。
- `test_pdf_map.py`：PDF 分类数量及道路逐格交叉校验、连通性、地图快照、来源变更保护、建筑内部标记。读取原 PDF 的检查在缺少参考文件时跳过。
- `test_campus_app.py`：按网格查询、编辑后重算、历史回放、草稿保存顺序、建筑标记保存。
- `test_navigation.py`：产品页面切换及操作台宽度设置保留。

测试使用临时数据库。

`test_place_navigation.py` 检查名称查询、临时接入点、唯一入口设置、停用提示及场地标记。
