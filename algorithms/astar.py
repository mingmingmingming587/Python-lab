"""四方向、单位代价的网格 A* 搜索。"""

from heapq import heappop, heappush
from itertools import count
from time import perf_counter

from algorithms.path_result import PathResult


def astar_search(grid, start, goal):
    """在 0 可通行、1 为障碍物的矩形网格中搜索最短路径。"""
    if not isinstance(grid, list) or not grid or not all(isinstance(row, list) and row for row in grid):
        raise ValueError("地图必须是非空二维列表")
    cols = len(grid[0])
    if any(len(row) != cols or any(type(cell) is not int or cell not in (0, 1) for cell in row) for row in grid):
        raise ValueError("地图必须为矩形，格子只能是整数 0 或 1")
    rows = len(grid)
    for name, point in (("起点", start), ("终点", goal)):
        if not isinstance(point, tuple) or len(point) != 2 or any(type(n) is not int for n in point):
            raise ValueError(f"{name}必须是 (行, 列) 整数元组")
        row, col = point
        if not (0 <= row < rows and 0 <= col < cols):
            raise ValueError(f"{name}超出地图范围")
        if grid[row][col] != 0:
            raise ValueError(f"{name}不能位于障碍物")

    started = perf_counter()
    sequence = count()
    def heuristic(point):
        return abs(point[0] - goal[0]) + abs(point[1] - goal[1])

    queue = [(heuristic(start), next(sequence), 0, start)]
    distances = {start: 0}
    parents = {}
    visited_order = []
    expanded = set()

    while queue:
        _, _, distance, current = heappop(queue)
        if current in expanded or distance != distances[current]:
            continue
        expanded.add(current)
        visited_order.append(current)
        if current == goal:
            path = [current]
            while current in parents:
                current = parents[current]
                path.append(current)
            path.reverse()
            return PathResult(True, path, visited_order, len(visited_order), (perf_counter() - started) * 1000, len(path) - 1)

        row, col = current
        for nr, nc in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            neighbor = (nr, nc)
            new_distance = distance + 1
            if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == 0 and neighbor not in expanded and new_distance < distances.get(neighbor, float("inf")):
                distances[neighbor] = new_distance
                parents[neighbor] = current
                heappush(queue, (new_distance + heuristic(neighbor), next(sequence), new_distance, neighbor))

    return PathResult(False, [], visited_order, len(visited_order), (perf_counter() - started) * 1000, None)
