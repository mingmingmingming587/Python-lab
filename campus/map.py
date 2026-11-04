"""Editable campus grid.

The public convention is deliberately the one used in the course brief:
``0`` means walkable and ``1`` means blocked.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any, Iterable


class CampusMap:
    def __init__(self, rows: int, cols: int, grid: list[list[int]] | None = None):
        if rows <= 0 or cols <= 0:
            raise ValueError("地图行列数必须为正")
        self.rows = rows
        self.cols = cols
        if grid is None:
            self.grid = [[0 for _ in range(cols)] for _ in range(rows)]
        else:
            self.grid = self._validate_grid(grid)

    def _validate_grid(self, grid: Iterable[Iterable[int]]) -> list[list[int]]:
        result = []
        for row in grid:
            values = [1 if int(value) else 0 for value in row]
            if len(values) != self.cols:
                raise ValueError(f"每一行必须有 {self.cols} 列")
            result.append(values)
        if len(result) != self.rows:
            raise ValueError(f"地图必须有 {self.rows} 行")
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CampusMap":
        return cls(
            rows=int(data["rows"]),
            cols=int(data["cols"]),
            grid=data["grid"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "cols": self.cols,
            "grid": [row[:] for row in self.grid],
        }

    def clone(self) -> "CampusMap":
        return CampusMap(self.rows, self.cols, self.grid)

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.rows and 0 <= col < self.cols

    def is_walkable(self, row: int, col: int) -> bool:
        return self.in_bounds(row, col) and self.grid[row][col] == 0

    def neighbors(self, row: int, col: int) -> list[tuple[int, int]]:
        result = []
        for d_row, d_col in ((-1, 0), (0, 1), (1, 0), (0, -1)):
            next_row, next_col = row + d_row, col + d_col
            if self.is_walkable(next_row, next_col):
                result.append((next_row, next_col))
        return result

    def set_cell(self, row: int, col: int, value: int) -> None:
        if not self.in_bounds(row, col):
            raise ValueError(f"坐标越界：({row}, {col})")
        self.grid[row][col] = 0 if int(value) == 0 else 1

    def apply_changes(self, changes: Iterable[Iterable[int]]) -> int:
        count = 0
        for change in changes:
            row, col, value = (int(part) for part in change)
            self.set_cell(row, col, value)
            count += 1
        return count

    def counts(self) -> dict[str, int]:
        walkable = sum(row.count(0) for row in self.grid)
        return {
            "walkable": walkable,
            "blocked": self.rows * self.cols - walkable,
            "total": self.rows * self.cols,
        }

    def snapshot(self) -> str:
        return "".join("".join(str(value) for value in row) for row in self.grid)

    def snapshot_hash(self) -> str:
        return hashlib.sha1(self.snapshot().encode("ascii")).hexdigest()[:12]

    def load_snapshot(self, snapshot: str) -> None:
        expected = self.rows * self.cols
        if len(snapshot) != expected:
            raise ValueError(f"快照长度应为 {expected}")
        values = [0 if char == "0" else 1 for char in snapshot]
        self.grid = [
            values[index * self.cols : (index + 1) * self.cols]
            for index in range(self.rows)
        ]

    def nearest_walkable(
        self, row: int, col: int, max_radius: int = 12
    ) -> tuple[int, int, int] | None:
        if self.is_walkable(row, col):
            return row, col, 0
        queue = deque([(row, col, 0)])
        seen = {(row, col)}
        while queue:
            current_row, current_col, distance = queue.popleft()
            if distance >= max_radius:
                continue
            for d_row, d_col in ((-1, 0), (0, 1), (1, 0), (0, -1)):
                next_row, next_col = current_row + d_row, current_col + d_col
                if (next_row, next_col) in seen or not self.in_bounds(
                    next_row, next_col
                ):
                    continue
                seen.add((next_row, next_col))
                if self.is_walkable(next_row, next_col):
                    return next_row, next_col, distance + 1
                queue.append((next_row, next_col, distance + 1))
        return None

    def components(self) -> list[int]:
        """Return component sizes for walkable cells, largest first."""
        seen = [[False] * self.cols for _ in range(self.rows)]
        sizes = []
        for row in range(self.rows):
            for col in range(self.cols):
                if not self.is_walkable(row, col) or seen[row][col]:
                    continue
                queue = deque([(row, col)])
                seen[row][col] = True
                size = 0
                while queue:
                    current_row, current_col = queue.popleft()
                    size += 1
                    for next_row, next_col in self.neighbors(current_row, current_col):
                        if not seen[next_row][next_col]:
                            seen[next_row][next_col] = True
                            queue.append((next_row, next_col))
                sizes.append(size)
        return sorted(sizes, reverse=True)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    def __repr__(self) -> str:
        counts = self.counts()
        return (
            f"CampusMap(rows={self.rows}, cols={self.cols}, "
            f"walkable={counts['walkable']})"
        )
