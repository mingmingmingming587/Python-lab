import json
from pathlib import Path

import streamlit as st

from visualization.campus_diagram import build_campus_diagram

st.set_page_config(page_title="校园示意地图", layout="wide")
st.title("校园示意地图")
st.warning("根据参考图重新绘制：场地和建筑为色块近似提取，线条为道路及小路示意；道路、入口和跨街通行尚未核实，不能用于实际导航或 A*。")
st.caption("参考图由应急通信与控制工程学院宣传部绘制，原图注明内容尚有不完善之处。请结合现场确认。")

layout_file = Path(__file__).resolve().parents[1] / "reference" / "campus-layout.json"
if not layout_file.exists():
    st.info("本机未找到参考图的布局数据。请先阅读 reference/README.md 中的生成说明。")
    st.stop()

try:
    layout = json.loads(layout_file.read_text(encoding="utf-8"))
    places = layout["places"]
    if not places:
        raise ValueError("没有可显示的地点")
    footprints = layout.get("footprints")
    if not footprints:
        st.warning("当前布局文件缺少建筑轮廓，请按 reference/README.md 重新生成。")
    elif "ground" not in footprints:
        st.info("布局缺少场地色块，请按 reference/README.md 重新生成，才能显示更多小路细节。")
    show_labels = st.checkbox("显示地点名称", value=True, help="关闭后可更清楚查看场地和小路，地点仍可用鼠标悬停查看。")
    choice = st.selectbox("选择地点放大查看", range(-1, len(places)),
                          format_func=lambda index: "全部地点" if index == -1 else f"{places[index]['name']}（{index + 1}）")
    focus = None if choice == -1 else places[choice]
    st.plotly_chart(build_campus_diagram(places, focus, footprints, show_labels), use_container_width=True, config={"scrollZoom": True})
    st.caption(f"从参考 PDF 提取到 {len(places)} 个地点标签；名称和位置是图面线索，可能有识别遗漏或偏差。可使用滚轮放大和鼠标拖动。")
    st.markdown("参考资料：[UEM Wiki 校园地图](https://github.com/uem-wiki/uem_wiki/blob/main/docs/%E6%A0%A1%E5%9B%AD%E7%94%9F%E6%B4%BB/%E5%9C%B0%E5%9B%BE.pdf)")
except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
    st.error(f"无法绘制校园示意地图：{error}")
