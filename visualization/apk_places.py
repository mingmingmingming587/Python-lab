"""仅读取本机 APK 分析资料中的候选地点；不复制原始数据到仓库。"""

import math
import re
from pathlib import Path


def load_apk_places(path):
    text = Path(path).read_text(encoding="utf-8")
    pattern = r"'id':\s*'builtin-[^']+',\s*'name':\s*'([^']+)',\s*'longitude':\s*([\d.]+),\s*'latitude':\s*([\d.]+)"
    return [(name, float(lon), float(lat)) for name, lon, lat in re.findall(pattern, text)]


def _offset(lon, lat):
    """常用坐标近似公式，供参考预览；不是精度保证。"""
    x, y = lon - 105.0, lat - 35.0
    dlat = -100 + 2*x + 3*y + 0.2*y*y + 0.1*x*y + 0.2*math.sqrt(abs(x))
    dlat += (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi))*2/3
    dlat += (20*math.sin(y*math.pi) + 40*math.sin(y*math.pi/3))*2/3
    dlat += (160*math.sin(y*math.pi/12) + 320*math.sin(y*math.pi/30))*2/3
    dlon = 300 + x + 2*y + 0.1*x*x + 0.1*x*y + 0.1*math.sqrt(abs(x))
    dlon += (20*math.sin(6*x*math.pi) + 20*math.sin(2*x*math.pi))*2/3
    dlon += (20*math.sin(x*math.pi) + 40*math.sin(x*math.pi/3))*2/3
    dlon += (150*math.sin(x*math.pi/12) + 300*math.sin(x*math.pi/30))*2/3
    radlat = lat / 180 * math.pi
    magic = 1 - 0.006693421622965943 * math.sin(radlat)**2
    root = math.sqrt(magic)
    dlat = dlat * 180 / ((6378245.0 * (1 - 0.006693421622965943)) / (magic * root) * math.pi)
    dlon = dlon * 180 / (6378245.0 / root * math.cos(radlat) * math.pi)
    return dlon, dlat


def gcj02_to_wgs84_approx(lon, lat):
    """迭代反推高德坐标到 WGS84 的近似值，仅适用于中国大陆的参考预览。"""
    if not (72.004 <= lon <= 137.8347 and 0.8293 <= lat <= 55.8271):
        return lon, lat
    x, y = lon, lat
    for _ in range(5):
        dx, dy = _offset(x, y)
        x, y = lon - dx, lat - dy
    return x, y
