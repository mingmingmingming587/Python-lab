"""读取本地 OpenStreetMap XML，供地图资料预览，不参与路线计算。"""

from xml.etree import ElementTree


def read_osm(path):
    root = ElementTree.parse(path).getroot()
    nodes = {node.get("id"): (float(node.get("lon")), float(node.get("lat"))) for node in root.findall("node")}
    ways = {}
    for way in root.findall("way"):
        ways[way.get("id")] = {
            "nodes": [nd.get("ref") for nd in way.findall("nd")],
            "tags": {tag.get("k"): tag.get("v") for tag in way.findall("tag")},
        }
    return nodes, ways, root


def lines_for_ways(nodes, ways, selected_ids):
    """用 None 分隔线段；缺失节点也会断开线，避免画出虚假连接。"""
    x, y = [], []
    for way_id in selected_ids:
        way = ways.get(way_id)
        if way is None:
            continue
        for node_id in way["nodes"]:
            point = nodes.get(node_id)
            x.append(point[0] if point else None)
            y.append(point[1] if point else None)
        x.append(None)
        y.append(None)
    return x, y
