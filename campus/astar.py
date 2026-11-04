"""A* search on a four-connected grid.

Every move costs one, so the Manhattan distance is an admissible and
consistent heuristic.  The implementation is intentionally self-contained and
readable for a Python course project.
"""

from __future__ import annotations

import heapq
import time
from dataclasses import dataclass, field

from .map import CampusMap
from .models import PathResult


@dataclass(slots=True)
class Node:
    row: int
    col: int
    g: int = 0
    h: int = 0
    parent: "Node | None" = field(default=None, repr=False)

    @property
    def f(self) -> int:
        return self.g + self.h

    def __lt__(self, other: "Node") -> bool:
        return (self.f, self.h) < (other.f, other.h)


class AStarFinder:
    def __init__(self, campus_map: CampusMap):
        self.map = campus_map

    @staticmethod
    def manhattan(start: tuple[int, int], goal: tuple[int, int]) -> int:
        return abs(start[0] - goal[0]) + abs(start[1] - goal[1])

    def search(
        self, start: tuple[int, int], goal: tuple[int, int]
    ) -> PathResult:
        started = time.perf_counter()
        start_row, start_col = start
        goal_row, goal_col = goal

        if not self.map.in_bounds(start_row, start_col):
            return self._invalid("起点坐标越界", started)
        if not self.map.in_bounds(goal_row, goal_col):
            return self._invalid("终点坐标越界", started)
        if not self.map.is_walkable(start_row, start_col):
            return self._invalid("起点位于障碍物或未涂色区域", started)
        if not self.map.is_walkable(goal_row, goal_col):
            return self._invalid("终点位于障碍物或未涂色区域", started)
        if start == goal:
            return PathResult(
                found=True,
                path=[start],
                cost=0,
                expanded=0,
                expanded_order=[],
                message="起点与终点相同",
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )

        start_node = Node(
            start_row,
            start_col,
            h=self.manhattan(start, goal),
        )
        frontier: list[Node] = [start_node]
        best_g: dict[tuple[int, int], int] = {start: 0}
        closed: set[tuple[int, int]] = set()
        expanded_order: list[tuple[int, int]] = []

        while frontier:
            current = heapq.heappop(frontier)
            position = (current.row, current.col)
            if position in closed:
                continue
            closed.add(position)
            expanded_order.append(position)

            if position == goal:
                path = self._reconstruct(current)
                return PathResult(
                    found=True,
                    path=path,
                    cost=len(path) - 1,
                    expanded=len(expanded_order),
                    expanded_order=expanded_order,
                    message=f"已找到最短路径，共 {len(path) - 1} 步",
                    elapsed_ms=(time.perf_counter() - started) * 1000,
                )

            for next_row, next_col in self.map.neighbors(current.row, current.col):
                next_position = (next_row, next_col)
                next_g = current.g + 1
                if next_g >= best_g.get(next_position, 10**9):
                    continue
                best_g[next_position] = next_g
                child = Node(
                    next_row,
                    next_col,
                    g=next_g,
                    h=self.manhattan(next_position, goal),
                    parent=current,
                )
                heapq.heappush(frontier, child)

        return PathResult(
            found=False,
            path=[],
            cost=0,
            expanded=len(expanded_order),
            expanded_order=expanded_order,
            message=(
                f"终点不可达：已扩展 {len(expanded_order)} 个节点，"
                "请检查起点/终点是否被障碍物隔开"
            ),
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    @staticmethod
    def _reconstruct(node: Node) -> list[tuple[int, int]]:
        path = []
        current: Node | None = node
        while current is not None:
            path.append((current.row, current.col))
            current = current.parent
        path.reverse()
        return path

    def _invalid(self, message: str, started: float) -> PathResult:
        return PathResult(
            found=False,
            message=message,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )
