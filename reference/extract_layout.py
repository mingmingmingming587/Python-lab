"""从本地参考 PDF 提取文字位置；结果仅用于重绘示意图。"""

import json
import re
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent
KEYWORDS = ("楼", "馆", "食堂", "餐厅", "医院", "门", "公寓", "实验", "园", "中心", "场", "礼堂", "天桥", "宿舍", "苑", "训练", "湖", "棚")


def main():
    source = ROOT / "campus-map.pdf"
    target = ROOT / "campus-layout.json"
    document = pymupdf.open(source)
    page = document[0]
    labels = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        lines = []
        for line in block["lines"]:
            for span in line["spans"]:
                text = re.sub(r"\s+", "", span["text"])
                if text:
                    lines.append((text, span["bbox"]))
        if len(lines) > 1 and all(len(text) == 1 for text, _ in lines):
            lines = [("".join(text for text, _ in lines), block["bbox"])]
        for name, box in lines:
            x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            incomplete = {"中心", "楼", "实验室", "警实验", "工程训练", "餐厅"}
            if 90 <= x <= 495 and 25 <= y <= 775 and name not in incomplete and any(word in name for word in KEYWORDS):
                labels.append({"name": name, "x": round(x, 2), "y": round(y, 2)})
        # PDF 将这几处名称拆在多行，并与附近标签放在同一个文字块中。
        for parts, name in ((["思源", "餐厅"], "思源餐厅"),
                            (["工程训练", "中心"], "工程训练中心"),
                            (["文", "德", "楼"], "文德楼")):
            if all(any(text == part for text, _ in lines) for part in parts):
                boxes = [box for text, box in lines if text in parts]
                x = (min(box[0] for box in boxes) + max(box[2] for box in boxes)) / 2
                y = (min(box[1] for box in boxes) + max(box[3] for box in boxes)) / 2
                if 90 <= x <= 495 and 25 <= y <= 775:
                    labels.append({"name": name, "x": round(x, 2), "y": round(y, 2)})
    # 第三食堂的两行分别处于相邻文字块，合并为一个地点标注。
    activity = next((p for p in labels if p["name"] == "大学生活动中心"), None)
    canteen = next((p for p in labels if p["name"] == "（第三食堂）"), None)
    if activity and canteen and abs(activity["x"] - canteen["x"]) < 5 and abs(activity["y"] - canteen["y"]) < 15:
        activity["name"] = "大学生活动中心（第三食堂）"
        activity["y"] = round((activity["y"] + canteen["y"]) / 2, 2)
        labels.remove(canteen)
    # 参考图中该标注不可作为 PDF 文字提取，手工补充图面近似位置。
    if not any(p["name"] == "停车棚" for p in labels):
        labels.append({"name": "停车棚", "x": 153, "y": 134})
    if not labels:
        raise ValueError("没有提取到校园地点，请检查 PDF。")
    # 从参考图的颜色提取示意轮廓；不是建筑矢量测绘，也不能用作通行区域。
    image = Image.open(ROOT / "campus-map.webp").convert("RGB").resize((595, 842), Image.Resampling.BOX)
    footprints = {"ground": [], "blue": [], "gray": []}
    for y in range(25, 775):
        starts = {"ground": None, "blue": None, "gray": None}
        for x in range(90, 496):
            r, g, b = image.getpixel((x, y))
            colors = {
                # 参考图浅灰色的场地块。空隙中可看到道路，但不代表现实通行。
                "ground": x < 495 and 220 <= min(r, g, b) and max(r, g, b) <= 247 and max(r, g, b) - min(r, g, b) < 12,
                "blue": x < 495 and r < 65 and 35 <= g < 130 and b > 85 and b > r * 1.45 and b > g * 1.1,
                "gray": x < 495 and 40 <= r <= 145 and max(r, g, b) - min(r, g, b) < 18,
            }
            for color, selected in colors.items():
                if selected and starts[color] is None:
                    starts[color] = x
                elif not selected and starts[color] is not None:
                    if x - starts[color] >= 2:
                        footprints[color].append([starts[color], y, x - starts[color]])
                    starts[color] = None
    target.write_text(json.dumps({"width": page.rect.width, "height": page.rect.height, "places": labels, "footprints": footprints}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"提取 {len(labels)} 个图面标签，保存到 reference/campus-layout.json")


if __name__ == "__main__":
    main()
