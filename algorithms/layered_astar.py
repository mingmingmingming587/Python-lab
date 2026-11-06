"""二维网格 A*：上下左右移动，使用曼哈顿距离。"""

from heapq import heappop, heappush
from itertools import count
from time import perf_counter
from dataclasses import dataclass

from algorithms.path_result import PathResult


@dataclass(frozen=True)
class Node:
    """地图节点；坐标为 (行, 列)。"""
    row: int
    col: int

    def neighbors(self):
        return [(self.row - 1, self.col), (self.row + 1, self.col),
                (self.row, self.col - 1), (self.row, self.col + 1)]


class CampusMap:
    """地图负责网格合法性和可通行判断。"""
    def __init__(self, grid):
        if not isinstance(grid, list) or not grid or not isinstance(grid[0], list) or not grid[0]:
            raise ValueError("地图不能为空")
        self.grid = grid
        self.rows, self.cols = len(grid), len(grid[0])
        if any(not isinstance(line, list) or len(line) != self.cols or
               any(type(v) is not int or v not in (0, 1) for v in line) for line in grid):
            raise ValueError("地图必须是只含 0 或 1 的矩形网格")

    def contains(self, point):
        return (isinstance(point, tuple) and len(point) == 2 and all(type(v) is int for v in point)
                and 0 <= point[0] < self.rows and 0 <= point[1] < self.cols)

    def walkable(self, point):
        return self.contains(point) and self.grid[point[0]][point[1]] == 0

    def neighbors(self, point):
        return [p for p in Node(*point).neighbors() if self.walkable(p)]


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
    heuristic = lambda p: abs(p[0] - goal[0]) + abs(p[1] - goal[1])
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


def astar(grid, start, goal):
    """在二维网格上按 (行, 列) 计算最短路线。"""
    return PathFinder(CampusMap(grid)).search(start, goal)
