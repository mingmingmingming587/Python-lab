# 新地图参考资料

当前使用用户提供的 `reference/campus-map-integrated.pdf`。三页依次为原图叠加、四分类及 A* 输入网格。程序读取原 PDF，不再生成或使用旧布局文件。

`database/pdf_map.py` 的图面位置校准针对这一份 PDF。提取要求分类数量符合图例，并逐格核对第 2、3 页的道路；资料结构、尺寸或分类变化时应停止并重新校准。

原图名来自 PDF 图面，建筑位置不会自动转为导航点。PDF 不包含天桥三层结构，当前仅按平面地图计算。

此前的 `reference/campus-map.pdf`、`reference/campus-map.webp` 和 `reference/campus-layout.json` 留作本机历史资料；对应提取与旧图实现保留在 experiment 分支。它们不参与 experiment2 运行。资料公开分发权限需单独核实。
