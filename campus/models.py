"""Core value objects used by the map, search and database layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Place:
    """A named campus location.

    ``row``/``col`` is the marker position.  ``access_row``/``access_col`` is
    the walkable cell used as the route endpoint, which lets a building marker
    sit on the building while routing starts at its entrance.
    """

    id: int
    name: str
    type: str
    row: int
    col: int
    access_row: int
    access_col: int
    aliases: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "row": self.row,
            "col": self.col,
            "access_row": self.access_row,
            "access_col": self.access_col,
            "aliases": self.aliases,
        }


@dataclass(slots=True)
class PathResult:
    found: bool
    path: list[tuple[int, int]] = field(default_factory=list)
    cost: int = 0
    expanded: int = 0
    expanded_order: list[tuple[int, int]] = field(default_factory=list)
    message: str = ""
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "path": [[row, col] for row, col in self.path],
            "cost": self.cost,
            "expanded": self.expanded,
            "expanded_order": [[row, col] for row, col in self.expanded_order],
            "message": self.message,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }
