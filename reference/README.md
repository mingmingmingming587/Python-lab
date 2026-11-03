# 校园地图参考资料

以下文件由用户提供的 UEM Wiki 链接获得，供本机学习和核对：

- `reference/campus-map.webp`：[原始网页图](https://github.com/uem-wiki/uem_wiki/blob/main/docs/%E6%A0%A1%E5%9B%AD%E7%94%9F%E6%B4%BB/%E5%9C%B0%E5%9B%BE%E9%AB%98%E6%B8%85.webp)
- `reference/campus-map.pdf`：[原始 PDF](https://github.com/uem-wiki/uem_wiki/blob/main/docs/%E6%A0%A1%E5%9B%AD%E7%94%9F%E6%B4%BB/%E5%9C%B0%E5%9B%BE.pdf)

两者是同一幅校园示意图的不同格式。原图署名“应急通信与控制工程学院宣传部 制”，图中注明内容尚有不完善之处；原 Wiki 说明材料仅供学习参考，未明确图片公开再分发和改编许可。以上两个原始文件由 `.gitignore` 排除；获得相应授权前不要强制提交或公开发布。其他成员需按原链接自行获取并放在此目录。

图中没有可验证的经纬度网格或比例尺，不应直接把像素当作真实地理坐标，也不能仅据图推断道路、建筑入口或校门开放状态。更多对照见 `note/校园地图资料.md`。

## 重绘校园示意地图

程序读取 `reference/campus-layout.json` 中从 PDF 提取的地点位置和从 WEBP 色块提取的近似场地、建筑轮廓，以 Plotly 重新画成可缩放的示意地图。该布局文件是衍生参考资料，也被 `.gitignore` 排除。已有文件时，启动应用后打开“地图资料预览”即可；若需重新生成，准备 `reference/campus-map.pdf`、`reference/campus-map.webp` 和支持 PyMuPDF、Pillow 的 Python 环境，再运行：

```powershell
python reference/extract_layout.py
```

地点名称主要来自 PDF 文字提取，部分多行名称经过合并，停车棚按图面补充；仍可能有遗漏或文字拆分。浅色场地和建筑轮廓来自色块近似提取，黄虚线与小路线条按参考图粗略重绘；这些不是精确边界或通行数据，不可用于判断道路通行或计算真实路线。
