"""读取校园底图和独立的初始分类网格。"""

from collections import Counter, deque
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import pymupdf
from PIL import Image

from database.campus_project import CampusMapService, single_entrances

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "reference" / "campus-map-basemap.pdf"
INITIAL_GRID_PATH = ROOT / "reference" / "initial-grid.json"
PDF_DB_PATH = ROOT / "data" / "campuspath-integrated.db"
BUILDING_MARKERS_PATH = ROOT / "reference" / "building-markers.json"
PLACE_ENTRANCES_PATH = ROOT / "reference" / "place-entrances.json"
ROWS, COLS = 180, 90
MAP_JSON_FORMAT = "campuspath-integrated-1"
MAP_VERSION = "integrated-180x90"
CLASS_NAMES = ("未标注", "建筑", "道路", "边界")
EXPECTED_COUNTS = {0: 10491, 1: 2689, 2: 2227, 3: 793}

def _validate_classes(classes):
    if not isinstance(classes, list) or len(classes) != ROWS or any(
        not isinstance(row, list) or len(row) != COLS
        or any(type(cell) is not int or cell not in range(len(CLASS_NAMES)) for cell in row)
        for row in classes
    ):
        raise ValueError(f"地图分类网格必须为 {ROWS} 行 × {COLS} 列，分类值为 0～3。")


def load_pdf_map(pdf_path=PDF_PATH):
    path = Path(pdf_path)
    # 时间和大小作为缓存键；修改文件后重新解析。
    stat = path.stat()
    grid_stat = INITIAL_GRID_PATH.stat()
    layout = deepcopy(_load_pdf_map(str(path), stat.st_mtime_ns, stat.st_size,
                                    grid_stat.st_mtime_ns, grid_stat.st_size))
    if BUILDING_MARKERS_PATH.exists():
        markers = json.loads(BUILDING_MARKERS_PATH.read_text(encoding="utf-8"))
        if markers.get("source_hash") != layout["source_hash"]:
            raise ValueError("建筑标记与当前网格版本不对应，停止加载")
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
    if PLACE_ENTRANCES_PATH.exists():
        entrances = json.loads(PLACE_ENTRANCES_PATH.read_text(encoding="utf-8"))
        if entrances.get("source_hash") != layout["source_hash"]:
            raise ValueError("入口候选与当前网格版本不对应，停止加载")
        places = {marker["name"] for marker in layout.get("building_markers", [])}
        names = set()
        for entry in entrances["entrances"]:
            place, name, point = entry["place"], entry["name"], entry["point"]
            if (place not in places or not isinstance(name, str) or not name.strip()
                    or (place, name) in names or not _valid_map_point(point)
                    or layout["classes"][point[0]][point[1]] != 2
                    or entry.get("source") != "map_inferred"
                    or type(entry.get("enabled")) is not bool
                    or not isinstance(entry.get("note"), str) or not entry["note"].strip()):
                raise ValueError(f"入口候选名称、坐标或来源无效：{place}")
            names.add((place, name))
        layout["place_entrances"] = entrances["entrances"]
        layout["entrance_markers_version"] = entrances["version"]
    return layout


@lru_cache(maxsize=2)
def _load_pdf_map(path, modified, size, grid_modified, grid_size):
    initial = json.loads(INITIAL_GRID_PATH.read_text(encoding="utf-8"))
    if initial.get("map_version") != MAP_VERSION:
        raise ValueError("初始网格版本不受支持")
    classes = initial["classes"]
    _validate_classes(classes)
    if Counter(v for row in classes for v in row) != EXPECTED_COUNTS:
        raise ValueError("初始网格分类数量已改变，请检查资料版本")
    data = Path(path).read_bytes()
    background_hash = sha256(data).hexdigest()
    if background_hash != initial["basemap"]["sha256"]:
        raise ValueError("底图已更换，请先校准网格边界")
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        if len(doc) != 1:
            raise ValueError("校园底图应为单页 PDF")
        bounds = pymupdf.Rect(initial["basemap"]["bounds"])
        if bounds.is_empty or not doc[0].rect.contains(bounds):
            raise ValueError("底图网格边界无效")
        # 渲染整页内容后裁切网格区域，保留 PDF 的矢量文字和网格。
        pixmap = doc[0].get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=bounds, alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    background = BytesIO()
    image.save(background, format="PNG")
    return {"classes": classes, "background": background.getvalue(),
            "source_hash": initial["source_hash"], "source": initial["source"],
            "background_hash": background_hash,
            "background_source": "reference/" + initial["basemap"]["file"]}


def initial_pdf_state(layout):
    classes = deepcopy(layout["classes"])
    grid = [[0 if value == 2 else 1 for value in row] for row in classes]
    state = {"name": "校园地图", "grid": grid, "classes": classes, "places": {}, "place_status": {},
            "place_kinds": {}, "entrances": {},
            "source": layout["source"],
             "source_hash": layout["source_hash"], "map_version": MAP_VERSION}
    merge_building_markers(state, layout)
    merge_place_entrances(state, layout)
    return state


def _valid_map_point(point):
    return (isinstance(point, list) and len(point) == 2
            and all(type(value) is int for value in point)
            and 0 <= point[0] < ROWS and 0 <= point[1] < COLS)


def import_map_json(data, layout):
    """读取本项目导出的地图，校验完整内容后生成可编辑草稿。"""
    try:
        export = json.loads(data)
    except (ValueError, RecursionError) as error:
        raise ValueError("无法读取地图 JSON，请选择本项目导出的文件。") from error
    if not isinstance(export, dict) or export.get("format") != MAP_JSON_FORMAT:
        raise ValueError("地图 JSON 格式不受支持。")
    state = export.get("state")
    if not isinstance(state, dict) or (state.get("source_hash"), state.get("map_version")) != (
        layout["source_hash"], MAP_VERSION
    ):
        raise ValueError("地图 JSON 与当前网格版本不一致。")
    classes = state.get("classes")
    _validate_classes(classes)

    places = state.get("places")
    if not isinstance(places, dict) or any(
        not name.strip() or not _valid_map_point(point) for name, point in places.items()
    ):
        raise ValueError("地图 JSON 包含无效的地点名称或坐标。")
    kinds, statuses = state.get("place_kinds", {}), state.get("place_status", {})
    if (not isinstance(kinds, dict) or kinds.keys() - places.keys()
            or any(kind not in ("建筑", "场地") for kind in kinds.values())
            or not isinstance(statuses, dict) or statuses.keys() - places.keys()
            or any(not isinstance(status, str) for status in statuses.values())):
        raise ValueError("地图 JSON 包含无效的地点类型或状态。")

    entrances = state.get("entrances", {})
    if not isinstance(entrances, dict) or entrances.keys() - places.keys():
        raise ValueError("地图 JSON 包含未关联地点的入口。")
    for place, entries in entrances.items():
        if not isinstance(entries, list):
            raise ValueError(f"入口列表无效：{place}")
        names = set()
        for entry in entries:
            name = entry.get("name") if isinstance(entry, dict) else None
            if (not isinstance(name, str) or not name.strip() or name in names
                    or not _valid_map_point(entry.get("point"))
                    or type(entry.get("enabled")) is not bool
                    or entry.get("source", "manual") not in ("manual", "map_inferred")):
                raise ValueError(f"入口名称、坐标或启用状态无效：{place}")
            names.add(name)

    result = initial_pdf_state(layout)
    name = state.get("name", result["name"])
    if not isinstance(name, str) or not name.strip():
        raise ValueError("地图名称无效。")
    result.update(name=name, classes=classes, grid=[[0 if cell == 2 else 1 for cell in row] for row in classes],
                  places=places, place_kinds=kinds, place_status=statuses, entrances=entrances)
    result["entrances"] = single_entrances(entrances, result["grid"])
    return result


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
            state["places"][name] = [row, col]
            state["place_status"][name] = "PDF 图面定位；" + marker["note"]
        if name in state["places"]:
            state.setdefault("place_kinds", {}).setdefault(name, kind)
    state["building_markers_version"] = version
    return True


def merge_place_entrances(state, layout):
    """只为尚无入口的地点补入可通行的图面候选，保留已有入口。"""
    version = layout.get("entrance_markers_version")
    if not version or state.get("entrance_markers_version") == version:
        return False
    entrances = state.setdefault("entrances", {})
    missing = {name for name in state["places"] if not entrances.get(name)}
    added = set()
    for marker in layout.get("place_entrances", []):
        row, col = marker["point"]
        if marker["place"] in missing and state["grid"][row][col] == 0:
            entrances.setdefault(marker["place"], []).append({
                "name": marker["name"], "point": [row, col],
                "enabled": marker["enabled"], "source": "map_inferred",
            })
            added.add(marker["place"])
            missing.remove(marker["place"])
    for name in added:
        status = state.get("place_status", {}).get(name, "")
        if status.startswith("PDF 图面定位；"):
            state["place_status"][name] = status.replace("入口未设置", "入口为图面推定，待核实")
    state["entrance_markers_version"] = version
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
    state["places"][name] = [row, col]
    state.setdefault("place_kinds", {})[name] = kind
    state["place_status"][name] = "手动地点标记"


def set_place_entrance(state, place, name, row, col, *, enabled=True, source="manual"):
    """保存明确指定的路网入口；不修改建筑标记或通行格。"""
    name = name.strip()
    if place not in state["places"] or not name:
        raise ValueError("请选择地点，并填写入口名称")
    if not (0 <= row < ROWS and 0 <= col < COLS) or state["grid"][row][col] != 0:
        raise ValueError("入口必须位于可通行道路格")
    if source not in ("manual", "map_inferred"):
        raise ValueError("入口来源无效")
    entry = {"name": name, "point": [row, col], "enabled": bool(enabled)}
    if source == "map_inferred":
        entry["source"] = source
    state.setdefault("entrances", {})[place] = [entry]


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
            state["grid"][row][col] = 0 if classification == 2 else 1


def open_pdf_project(pdf_path=PDF_PATH, db_path=PDF_DB_PATH):
    layout = load_pdf_map(pdf_path)
    service = CampusMapService(initial_pdf_state(layout), db_path)
    revision, state = service.load()
    if state.get("source_hash") != layout["source_hash"]:
        raise ValueError("已保存的地图与当前网格版本不一致")
    building_changed = merge_building_markers(state, layout)
    entrances_changed = merge_place_entrances(state, layout)
    if building_changed or entrances_changed:
        revision = service.save(state)
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
