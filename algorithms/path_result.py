from dataclasses import dataclass


@dataclass
class PathResult:
    """一次搜索的结果；坐标使用 (row, col)。"""

    found: bool
    path: list[tuple[int, int]]
    visited_order: list[tuple[int, int]]
    expanded_count: int
    elapsed_ms: float
    path_length: int | None
