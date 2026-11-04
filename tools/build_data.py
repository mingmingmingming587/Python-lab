"""Build the 180x90 campus grid, POI list and web map image.

This is a one-off data preparation script.  It reads the rendered source map
and the hand-coloured classification produced during map digitisation.
"""

from __future__ import annotations

import json
import math
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
TMP = Path.home() / "AppData" / "Local" / "Temp"
CLASS_FILE = TMP / "cls.npy"
SOURCE_IMAGE = TMP / "orig600.png"
OUT_IMAGE = ROOT / "static" / "campus_map.jpg"
OUT_GRID = ROOT / "data" / "base_map.json"
OUT_PLACES = ROOT / "data" / "places.json"

ROWS, COLS = 180, 90
GRID_BOX_PDF = (93.2, 6.62, 486.8, 799.22)
# The hand-coloured classification was sampled from a crop starting ~35pt lower
# than the printed map crop used for the background image.  Shifting the class
# grid down by 8 rows puts buildings and paths back on top of the printed map.
CLASS_ROW_SHIFT = 8

# (name, type, label x, label y) in PDF points.
PLACES = [
    ("北辰园4号", "dorm", 118.05, 56.9),
    ("北辰园2号", "dorm", 157.30, 55.2),
    ("北辰园3号", "dorm", 118.15, 79.0),
    ("北辰园1号", "dorm", 158.35, 79.0),
    ("北辰园5号", "dorm", 120.55, 100.85),
    ("北辰园6号", "dorm", 157.30, 100.10),
    ("望舒餐厅", "building", 192.25, 73.75),
    ("灾害模拟实验室", "building", 122.05, 122.20),
    ("工程实践中心", "building", 121.95, 134.05),
    ("天仪楼", "building", 210.35, 130.40),
    ("长庚楼", "building", 193.05, 186.20),
    ("地下结构与工程地质实验场", "building", 240.95, 204.90),
    ("职工公寓", "dorm", 355.60, 157.25),
    ("大学生活动中心（第三食堂）", "building", 304.85, 264.70),
    ("学子苑1号", "dorm", 364.65, 268.35),
    ("学子苑2号", "dorm", 366.35, 293.70),
    ("学子苑7号", "dorm", 312.00, 306.50),
    ("学子苑3号", "dorm", 364.65, 325.95),
    ("逸居园1号", "dorm", 299.65, 333.90),
    ("逸居园3号", "dorm", 326.65, 333.65),
    ("学子苑4号", "dorm", 375.05, 354.30),
    ("逸居园2号", "dorm", 299.65, 355.50),
    ("逸居园4号", "dorm", 325.80, 356.10),
    ("学子苑6号", "dorm", 314.65, 396.90),
    ("学子苑5号", "dorm", 367.45, 396.90),
    ("研究生宿舍", "dorm", 421.20, 403.50),
    ("校医院", "building", 397.05, 403.75),
    ("停车棚", "building", 182.00, 123.50),
    ("承基楼", "building", 153.90, 449.55),
    ("图书馆（东）", "building", 417.05, 467.15),
    ("致远楼", "building", 302.85, 469.10),
    ("乒羽馆", "building", 458.05, 493.50),
    ("问地园", "park", 156.45, 481.70),
    ("游泳馆", "building", 223.45, 520.25),
    ("轮滑场", "sports", 341.90, 521.45),
    ("训练馆", "building", 368.65, 535.10),
    ("排球场", "sports", 341.90, 537.05),
    ("运动场（西）", "sports", 164.55, 540.65),
    ("体育馆（西）", "building", 227.45, 546.75),
    ("运动场（东）", "sports", 288.90, 554.20),
    ("桃李苑", "building", 420.50, 555.45),
    ("篮球场（东）", "sports", 351.35, 569.25),
    ("图书馆（西）", "building", 226.00, 585.55),
    ("第一食堂", "building", 464.55, 547.75),
    ("第二食堂", "building", 466.95, 598.15),
    ("学子林", "park", 398.80, 597.85),
    ("博观楼", "building", 347.40, 599.95),
    ("教工5号楼", "building", 159.00, 608.85),
    ("立新楼", "building", 399.85, 618.25),
    ("崇实楼", "building", 267.00, 620.35),
    ("网球场（桃李苑）", "sports", 436.45, 623.95),
    ("求是楼", "building", 305.15, 625.65),
    ("教工4号楼", "building", 157.90, 626.25),
    ("天水湖", "water", 217.65, 629.35),
    ("研究生宿舍楼", "dorm", 475.75, 630.85),
    ("和合广场", "landmark", 273.30, 646.85),
    ("工程训练中心", "building", 308.45, 650.95),
    ("教工2号楼", "building", 172.50, 650.50),
    ("教工3号楼", "building", 127.90, 651.10),
    ("后勤综合服务楼", "building", 246.15, 656.80),
    ("教工餐厅", "building", 235.00, 659.50),
    ("教工1号楼", "building", 172.90, 664.15),
    ("信息楼", "building", 373.60, 669.65),
    ("医务室", "building", 116.05, 679.35),
    ("安科楼", "building", 306.40, 675.65),
    ("篮球场（西）", "sports", 176.70, 684.55),
    ("思源餐厅", "building", 218.80, 688.65),
    ("体育馆（东）", "building", 438.55, 685.45),
    ("思玄苑", "building", 244.60, 686.80),
    ("文德楼", "building", 279.60, 689.70),
    ("老文德楼", "building", 289.90, 677.60),
    ("监测预警实验室", "building", 293.00, 720.00),
    ("礼堂", "building", 316.85, 703.15),
    ("安国园", "park", 374.90, 705.25),
    ("网球场（西）", "sports", 139.90, 709.15),
    ("听心园", "park", 176.70, 713.45),
    ("会议中心", "building", 318.70, 718.50),
    ("南阳居", "building", 232.30, 721.55),
    ("抗震结构实验室", "building", 275.35, 729.45),
    ("明德楼（西）", "building", 172.45, 738.00),
    ("学员公寓", "dorm", 126.00, 746.00),
    ("明德楼（东）", "building", 441.70, 738.95),
    ("办公楼", "building", 315.55, 741.70),
    ("明略楼", "building", 245.95, 749.75),
    ("地震监测预警基地", "building", 273.65, 752.45),
    ("创客空间", "building", 152.30, 752.75),
    ("国家矿山重点实验室", "building", 387.05, 761.20),
    ("北门", "gate", 211.75, 43.45),
    ("东北门", "gate", 441.55, 420.40),
    ("西北门", "gate", 149.75, 423.20),
    ("西门", "gate", 98.65, 650.40),
    ("南门", "gate", 182.95, 767.00),
    ("南2门", "gate", 345.00, 763.15),
    ("拓展场地", "sports", 458.40, 451.15),
    ("网球场（东）", "sports", 455.85, 470.70),
]

# Manual entrance overrides for labels whose nearest coloured component is not
# the building the label belongs to.  Values are (access_row, access_col).
# Entrances are snapped automatically to the main walkable network.  Add an
# entry here only if a specific point needs a manual position.
ACCESS_OVERRIDES: dict[str, tuple[int, int]] = {}

ALIASES = {
    "图书馆（东）": "图书馆东,东图",
    "图书馆（西）": "图书馆西,西图",
    "第一食堂": "一食堂,食堂一",
    "第二食堂": "二食堂,食堂二",
    "大学生活动中心（第三食堂）": "第三食堂,大活",
    "研究生宿舍": "研究生公寓",
    "研究生宿舍楼": "研究生公寓楼",
    "南2门": "南二门",
    "南门": "南大门",
    "北门": "北大门",
}


def pdf_to_grid(x: float, y: float) -> tuple[float, float]:
    x0, y0, x1, y1 = GRID_BOX_PDF
    return ((y - y0) / (y1 - y0) * ROWS, (x - x0) / (x1 - x0) * COLS)


def nearest_green(greens: np.ndarray, row: float, col: float) -> tuple[int, int]:
    distance = (greens[:, 0] - row) ** 2 + (greens[:, 1] - col) ** 2
    index = int(np.argmin(distance))
    return int(greens[index, 0]), int(greens[index, 1])


def main_component_mask(mask: np.ndarray) -> np.ndarray:
    """Return the largest 4-connected region of a boolean mask."""
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    best: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue
            queue = deque([(y, x)])
            seen[y, x] = True
            cells: list[tuple[int, int]] = []
            while queue:
                cy, cx = queue.popleft()
                cells.append((cy, cx))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if (
                        0 <= ny < height
                        and 0 <= nx < width
                        and mask[ny, nx]
                        and not seen[ny, nx]
                    ):
                        seen[ny, nx] = True
                        queue.append((ny, nx))
            if len(cells) > len(best):
                best = cells
    result = np.zeros_like(mask, dtype=bool)
    for cy, cx in best:
        result[cy, cx] = True
    return result


def yellow_components(mask: np.ndarray) -> list[np.ndarray]:
    height, width = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    components: list[np.ndarray] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or seen[y, x]:
                continue
            queue = deque([(y, x)])
            seen[y, x] = True
            cells = []
            while queue:
                cy, cx = queue.popleft()
                cells.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if (
                            0 <= ny < height
                            and 0 <= nx < width
                            and mask[ny, nx]
                            and not seen[ny, nx]
                        ):
                            seen[ny, nx] = True
                            queue.append((ny, nx))
            if len(cells) >= 3:
                components.append(np.asarray(cells))
    return components


def build_entrance(
    cls: np.ndarray,
    components: list[np.ndarray],
    row: float,
    col: float,
) -> tuple[int, int, float]:
    greens = np.argwhere(cls == 2)
    component = min(
        components,
        key=lambda cells: float(
            np.min((cells[:, 0] - row) ** 2 + (cells[:, 1] - col) ** 2)
        ),
    )
    neighbour_green = []
    height, width = cls.shape
    for cy, cx in component:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = int(cy + dy), int(cx + dx)
                if 0 <= ny < height and 0 <= nx < width and cls[ny, nx] == 2:
                    neighbour_green.append((ny, nx))
    if neighbour_green:
        candidates = np.unique(np.asarray(neighbour_green), axis=0)
        access = nearest_green(candidates, row, col)
    else:
        access = nearest_green(greens, row, col)
    distance = math.hypot(access[0] - row, access[1] - col)
    return access[0], access[1], distance


def main() -> None:
    OUT_IMAGE.parent.mkdir(parents=True, exist_ok=True)
    OUT_GRID.parent.mkdir(parents=True, exist_ok=True)

    cls = np.load(CLASS_FILE)
    shifted = np.zeros_like(cls)
    shifted[CLASS_ROW_SHIFT:, :] = cls[:-CLASS_ROW_SHIFT, :]
    cls = shifted
    blocked = (cls != 2).astype(np.int8)
    components = yellow_components(cls == 1)
    greens = np.argwhere(main_component_mask(cls == 2))

    places = []
    for index, (name, kind, x, y) in enumerate(PLACES, start=1):
        row_f, col_f = pdf_to_grid(x, y)
        marker_row, marker_col = round(row_f), round(col_f)
        access_row, access_col = nearest_green(greens, row_f, col_f)
        entrance_distance = math.hypot(access_row - row_f, access_col - col_f)
        if name in ACCESS_OVERRIDES:
            access_row, access_col = ACCESS_OVERRIDES[name]
            entrance_distance = math.hypot(access_row - row_f, access_col - col_f)
        places.append(
            {
                "id": f"p{index:03d}",
                "name": name,
                "type": kind,
                "row": marker_row,
                "col": marker_col,
                "access_row": access_row,
                "access_col": access_col,
                "label_row": round(row_f, 2),
                "label_col": round(col_f, 2),
                "entrance_distance": round(entrance_distance, 2),
                "aliases": ALIASES.get(name, ""),
            }
        )

    with OUT_GRID.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "name": "校园地图（180×90）",
                "rows": ROWS,
                "cols": COLS,
                "grid": blocked.tolist(),
            },
            handle,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    with OUT_PLACES.open("w", encoding="utf-8") as handle:
        json.dump(places, handle, ensure_ascii=False, indent=1)

    source = Image.open(SOURCE_IMAGE).convert("RGB")
    scale = 600 / 72
    x0, y0, x1, y1 = GRID_BOX_PDF
    box = (
        round(x0 * scale),
        round(y0 * scale),
        round(x1 * scale),
        round(y1 * scale),
    )
    map_image = source.crop(box).resize((900, 1800), Image.LANCZOS)
    draw = ImageDraw.Draw(map_image)
    # Hide the cut-off source annotations in the top-right corner.
    draw.rectangle((750, 90, 900, 230), fill="#ffffff")
    map_image.save(OUT_IMAGE, quality=91)

    preview = map_image.copy()
    pdraw = ImageDraw.Draw(preview)
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 14)
    for place in places:
        cx = (place["col"] + 0.5) * 10
        cy = (place["row"] + 0.5) * 10
        pdraw.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill="#e11d48", outline="white")
        pdraw.text((cx + 6, cy - 8), place["id"][1:], fill="#111827", font=font)
    preview.save(TMP / "places_preview.png")
    print(f"places={len(places)} image={map_image.size}")


if __name__ == "__main__":
    main()
