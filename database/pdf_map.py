"""读取指定 PDF 的分类网格；旧地图和数据库不参与新版本。"""

from collections import Counter, deque
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import pymupdf
from PIL import Image

from database.campus_project import CampusMapService

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "reference" / "campus-map-integrated.pdf"
PDF_DB_PATH = ROOT / "data" / "campuspath-integrated.db"
BUILDING_MARKERS_PATH = ROOT / "reference" / "building-markers.json"
ROWS, COLS = 180, 90
CLASS_NAMES = ("未标注", "建筑", "道路", "边界")
EXPECTED_COUNTS = {0: 10491, 1: 2689, 2: 2227, 3: 793}
# 此 PDF 嵌入的是 2480×3508 图片。以下为图面网格的像素原点和步长。
# 这是针对这一份资料的校准；不对其他 PDF 猜测坐标。
ORIGIN_X, ORIGIN_Y, CELL_SIZE = 510, 217, 16.28


def _color_class(rgb):
    r, g, b = rgb
    if max(rgb) - min(rgb) < 70:
        return 0
    if r > g * 1.35 and r > b * 1.35:
        return 3
    if g > r * 1.1 and g > b * 1.1:
        return 2
    if r > 150 and g > 120 and b < 130:
        return 1
    return 0


def _read_classes(image):
    return [[_color_class(image.getpixel((
        round(ORIGIN_X + (c + .5) * CELL_SIZE),
        round(ORIGIN_Y + (r + .5) * CELL_SIZE),
    ))) for c in range(COLS)] for r in range(ROWS)]


def load_pdf_map(pdf_path=PDF_PATH):
    path = Path(pdf_path)
    # 时间和大小作为缓存键；修改文件后重新解析。
    stat = path.stat()
    layout = deepcopy(_load_pdf_map(str(path), stat.st_mtime_ns, stat.st_size))
    if BUILDING_MARKERS_PATH.exists():
        markers = json.loads(BUILDING_MARKERS_PATH.read_text(encoding="utf-8"))
        if markers.get("source_hash") != layout["source_hash"]:
            raise ValueError("建筑标记与当前 PDF 不对应，停止加载")
        names = set()
        for point in markers["markers"]:
            name, row, col = point["name"], point["row"], point["col"]
            allowed = (0, 1, 2) if point.get("kind") == "场地" else (1,)
            if not isinstance(name, str) or not name.strip() or name in names:
                raise ValueError("建筑标记名称无效或重复")
            if (type(row) is not int or type(col) is not int or
                    not (0 <= row < ROWS and 0 <= col < COLS) or
                    layout["classes"][row][col] not in allowed):
                raise ValueError(f"地点标记不在对应的分类格内：{name}")
            names.add(name)
        layout["building_markers"] = markers["markers"]
        layout["building_markers_version"] = markers["version"]
    return layout


@lru_cache(maxsize=2)
def _load_pdf_map(path, modified, size):
    data = Path(path).read_bytes()
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if len(doc) != 3:
            raise ValueError("新地图应为三页的 campus-map-integrated.pdf")
        images = []
        for page in doc:
            embedded = page.get_images()
            if len(embedded) != 1:
                raise ValueError("PDF 页面结构已改变，请重新校准提取方式")
            im = Image.open(BytesIO(doc.extract_image(embedded[0][0])["image"])).convert("RGB")
            if im.size != (2480, 3508):
                raise ValueError("PDF 图像尺寸已改变，请重新校准图面网格")
            images.append(im)
    classes = _read_classes(images[1])
    counts = Counter(v for row in classes for v in row)
    if counts != EXPECTED_COUNTS:
        raise ValueError(f"提取的分类数量与 PDF 图例不一致：{dict(counts)}")
    binary_page = _read_classes(images[2])
    if any((classes[r][c] == 2) != (binary_page[r][c] == 2)
           for r in range(ROWS) for c in range(COLS)):
        raise ValueError("分类图与 A* 输入图的道路格子不一致，停止加载")
    crop = (ORIGIN_X, ORIGIN_Y,
            round(ORIGIN_X + COLS * CELL_SIZE), round(ORIGIN_Y + ROWS * CELL_SIZE))
    background = BytesIO()
    images[0].crop(crop).save(background, format="PNG")
    return {"classes": classes, "background": background.getvalue(),
            "source_hash": sha256(data).hexdigest(),
            "source": "reference/campus-map-integrated.pdf，第 2、3 页逐格交叉核对"}


def initial_pdf_state(layout):
    classes = deepcopy(layout["classes"])
    grid = [[0 if value == 2 else 1 for value in row] for row in classes]
    state = {"grids": [grid], "classes": classes, "places": {}, "place_status": {},
            "place_kinds": {}, "entrances": {},
            "portals": [], "north_gate_open": False, "source": layout["source"],
            "source_hash": layout["source_hash"], "map_version": "integrated-180x90"}
    merge_building_markers(state, layout)
    return state


def merge_building_markers(state, layout):
    """首次补入图面建筑标记，保留已有同名标记和用户修改过的格子。"""
    version = layout.get("building_markers_version")
    if not version or state.get("building_markers_version") == version:
        return False
    for marker in layout.get("building_markers", []):
        name, row, col = marker["name"], marker["row"], marker["col"]
        kind = marker.get("kind", "建筑")
        allowed = (0, 1, 2) if kind == "场地" else (1,)
        if name not in state["places"] and state["classes"][row][col] in allowed:
            state["places"][name] = [0, row, col]
            state["place_status"][name] = "PDF 图面定位；" + marker["note"]
        if name in state["places"]:
            state.setdefault("place_kinds", {}).setdefault(name, kind)
    state["building_markers_version"] = version
    return True


def set_building_marker(state, name, row, col, *, old_name=None, kind="建筑"):
    """建筑位置标记可位于建筑内部；不修改可通行格，也不自动猜测入口。"""
    name = name.strip()
    if not name:
        raise ValueError("建筑名称不能为空")
    if name in state["places"] and name != old_name:
        raise ValueError("建筑名称已存在")
    if not (0 <= row < ROWS and 0 <= col < COLS):
        raise ValueError("建筑标记坐标超出地图")
    if kind not in ("建筑", "场地"):
        raise ValueError("地点类型无效")
    allowed = (0, 1, 2) if kind == "场地" else (1, 2)
    if state["classes"][row][col] not in allowed:
        raise ValueError("请在建筑或道路格上放置标记；未标注区域请先核实分类")
    if old_name and old_name != name:
        state["places"].pop(old_name, None)
        state["place_status"].pop(old_name, None)
        state.setdefault("place_kinds", {}).pop(old_name, None)
        if old_name in state.get("entrances", {}):
            state["entrances"][name] = state["entrances"].pop(old_name)
    state["places"][name] = [0, row, col]
    state.setdefault("place_kinds", {})[name] = kind
    state["place_status"][name] = "手动地点标记"


def set_place_entrance(state, place, name, row, col, *, enabled=True, old_name=None):
    """保存明确指定的路网入口；不修改建筑标记或通行格。"""
    name = name.strip()
    if place not in state["places"] or not name:
        raise ValueError("请选择地点，并填写入口名称")
    if not (0 <= row < ROWS and 0 <= col < COLS) or state["grids"][0][row][col] != 0:
        raise ValueError("入口必须位于可通行道路格")
    entries = state.setdefault("entrances", {}).setdefault(place, [])
    if any(e["name"] == name and e["name"] != old_name for e in entries):
        raise ValueError("入口名称已存在，请选择已有入口修改")
    if old_name:
        entries[:] = [e for e in entries if e["name"] != old_name]
    entries.append({"name": name, "point": [0, row, col], "enabled": bool(enabled)})


def set_grid_region(state, bounds, classification):
    """修改闭区间内的分类与通行网格；选择和预览本身不写数据库。"""
    if (len(bounds) != 4 or any(type(v) is not int for v in bounds) or
            type(classification) is not int or classification not in range(4)):
        raise ValueError("网格选区或分类无效")
    r1, c1, r2, c2 = bounds
    if not (0 <= r1 <= r2 < ROWS and 0 <= c1 <= c2 < COLS):
        raise ValueError("网格选区超出地图")
    for row in range(r1, r2+1):
        for col in range(c1, c2+1):
            state["classes"][row][col] = classification
            state["grids"][0][row][col] = 0 if classification == 2 else 1


def open_pdf_project(pdf_path=PDF_PATH, db_path=PDF_DB_PATH):
    layout = load_pdf_map(pdf_path)
    service = CampusMapService(initial_pdf_state(layout), db_path)
    revision, state = service.load()
    if state.get("source_hash") != layout["source_hash"]:
        raise ValueError("PDF 已更换，与已保存的地图版本不一致；请使用新的数据库")
    if merge_building_markers(state, layout):
        revision = service.save(state, revision)
    return layout, service, revision, state


def road_components(grid):
    """按上下左右邻接检查道路连通性，不自动补路。"""
    remaining = {(r, c) for r, line in enumerate(grid) for c, v in enumerate(line) if v == 0}
    components = []
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        queue = deque([seed])
        component = [seed]
        while queue:
            r, c = queue.popleft()
            for p in ((r-1, c), (r+1, c), (r, c-1), (r, c+1)):
                if p in remaining:
                    remaining.remove(p)
                    queue.append(p)
                    component.append(p)
        components.append(component)
    return sorted(components, key=len, reverse=True)
