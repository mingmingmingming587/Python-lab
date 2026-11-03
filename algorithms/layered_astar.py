"""多层网格 A*：每层上下左右移动，仅在明确的连接点换层。"""

from heapq import heappop, heappush
from itertools import count
from time import perf_counter
from dataclasses import dataclass

from algorithms.path_result import PathResult


@dataclass(frozen=True)
class Node:
    """地图节点；坐标为 (层, 行, 列)。"""
    layer: int
    row: int
    col: int

    def neighbors(self):
        return [(self.layer, self.row - 1, self.col), (self.layer, self.row + 1, self.col),
                (self.layer, self.row, self.col - 1), (self.layer, self.row, self.col + 1)]


class CampusMap:
    """地图负责网格合法性和可通行判断。"""
    def __init__(self, grids, portals=()):
        if not isinstance(grids, list) or not grids or not isinstance(grids[0], list) or not grids[0] or not isinstance(grids[0][0], list) or not grids[0][0]:
            raise ValueError("地图不能为空")
        self.grids = grids
        self.rows, self.cols = len(grids[0]), len(grids[0][0])
        if any(not isinstance(g, list) or len(g) != self.rows or any(not isinstance(line, list) or len(line) != self.cols or any(type(v) is not int or v not in (0, 1) for v in line) for line in g) for g in grids):
            raise ValueError("各层必须是相同大小且只含 0 或 1 的矩形网格")
        self.links = {}
        for a, b in portals:
            a, b = tuple(a), tuple(b)
            if not self.contains(a) or not self.contains(b) or a[0] == b[0] or a[1:] != b[1:]:
                raise ValueError("跨层连接必须是同一行列的不同层")
            if self.walkable(a) and self.walkable(b):
                self.links.setdefault(a, []).append(b)
                self.links.setdefault(b, []).append(a)

    def contains(self, point):
        return (isinstance(point, tuple) and len(point) == 3 and all(type(v) is int for v in point)
                and 0 <= point[0] < len(self.grids) and 0 <= point[1] < self.rows and 0 <= point[2] < self.cols)

    def walkable(self, point):
        return self.contains(point) and self.grids[point[0]][point[1]][point[2]] == 0

    def neighbors(self, point):
        return [p for p in [*Node(*point).neighbors(), *self.links.get(point, [])] if self.walkable(p)]


class PathFinder:
    """路径搜索器：使用曼哈顿距离运行 A*。"""
    def __init__(self, campus_map):
        self.map = campus_map

    def search(self, start, goal):
        if not self.map.walkable(start) or not self.map.walkable(goal):
            raise ValueError("起点和终点必须位于可通行网格")
        return _search(self.map, start, goal)


def _search(campus_map, start, goal):
    started = perf_counter()
    order = count()
    heuristic = lambda p: abs(p[1] - goal[1]) + abs(p[2] - goal[2])
    queue = [(heuristic(start), next(order), 0, start)]
    distances, parents, expanded, visited = {start: 0}, {}, set(), []
    while queue:
        _, _, cost, current = heappop(queue)
        if current in expanded or cost != distances.get(current):
            continue
        expanded.add(current)
        visited.append(current)
        if current == goal:
            path = [current]
            while path[-1] in parents:
                path.append(parents[path[-1]])
            path.reverse()
            return PathResult(True, path, visited, len(visited), (perf_counter() - started) * 1000, len(path) - 1)
        for nxt in campus_map.neighbors(current):
            if nxt not in expanded and cost + 1 < distances.get(nxt, float("inf")):
                distances[nxt], parents[nxt] = cost + 1, current
                heappush(queue, (cost + 1 + heuristic(nxt), next(order), cost + 1, nxt))
    return PathResult(False, [], visited, len(visited), (perf_counter() - started) * 1000, None)


def layered_astar(grids, start, goal, portals=()):
    """坐标为 (层, 行, 列)；同格跨层代价为 1，曼哈顿距离忽略层数。"""
    return PathFinder(CampusMap(grids, portals)).search(start, goal)
