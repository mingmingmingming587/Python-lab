"""SQLite persistence for maps, places and route history."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .map import CampusMap
from .models import PathResult, Place


SCHEMA = """
CREATE TABLE IF NOT EXISTS maps (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    rows INTEGER NOT NULL,
    cols INTEGER NOT NULL,
    grid TEXT NOT NULL,
    is_base INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    map_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'building',
    row INTEGER NOT NULL,
    col INTEGER NOT NULL,
    access_row INTEGER NOT NULL,
    access_col INTEGER NOT NULL,
    aliases TEXT NOT NULL DEFAULT '',
    UNIQUE(map_id, name),
    FOREIGN KEY(map_id) REFERENCES maps(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cells (
    map_id INTEGER NOT NULL,
    row INTEGER NOT NULL,
    col INTEGER NOT NULL,
    blocked INTEGER NOT NULL,
    PRIMARY KEY (map_id, row, col),
    FOREIGN KEY(map_id) REFERENCES maps(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    map_id INTEGER NOT NULL,
    start_name TEXT NOT NULL,
    end_name TEXT NOT NULL,
    start_row INTEGER NOT NULL,
    start_col INTEGER NOT NULL,
    end_row INTEGER NOT NULL,
    end_col INTEGER NOT NULL,
    found INTEGER NOT NULL,
    cost INTEGER NOT NULL,
    expanded INTEGER NOT NULL,
    elapsed_ms REAL NOT NULL,
    message TEXT NOT NULL,
    path TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(map_id) REFERENCES maps(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_queries_created ON queries(created_at DESC);
"""


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


class MapService:
    def __init__(
        self,
        db_path: str | Path = "data/campuspath.db",
        base_map_path: str | Path = "data/base_map.json",
        places_path: str | Path = "data/places.json",
    ):
        self.db_path = Path(db_path)
        self.base_map_path = Path(base_map_path)
        self.places_path = Path(places_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.base_data = json.loads(self.base_map_path.read_text(encoding="utf-8"))
        self.base_places = json.loads(self.places_path.read_text(encoding="utf-8"))
        self._initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            row = connection.execute(
                "SELECT id, rows, cols, grid FROM maps WHERE id = 1"
            ).fetchone()
            created = row is None
            if row is None:
                timestamp = now_text()
                connection.execute(
                    """
                    INSERT INTO maps
                        (id, name, rows, cols, grid, is_base, created_at, updated_at)
                    VALUES (1, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        self.base_data.get("name", "校园地图（180×90）"),
                        int(self.base_data["rows"]),
                        int(self.base_data["cols"]),
                        json.dumps(self.base_data["grid"], separators=(",", ":")),
                        timestamp,
                        timestamp,
                    ),
                )
            if created:
                self._insert_seed_places(connection)
            cell_count = connection.execute(
                "SELECT COUNT(*) AS count FROM cells WHERE map_id = 1"
            ).fetchone()["count"]
            if cell_count == 0:
                if created:
                    current = CampusMap.from_dict(self.base_data)
                else:
                    current = CampusMap(
                        int(row["rows"]),
                        int(row["cols"]),
                        json.loads(row["grid"]),
                    )
                self._replace_cells(connection, current)

    def _insert_seed_places(self, connection: sqlite3.Connection) -> None:
        connection.executemany(
            """
            INSERT OR IGNORE INTO places
                (map_id, name, type, row, col, access_row, access_col, aliases)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    place["name"],
                    place.get("type", "building"),
                    int(place["row"]),
                    int(place["col"]),
                    int(place["access_row"]),
                    int(place["access_col"]),
                    place.get("aliases", ""),
                )
                for place in self.base_places
            ],
        )

    def _replace_cells(
        self, connection: sqlite3.Connection, campus_map: CampusMap
    ) -> None:
        connection.execute("DELETE FROM cells WHERE map_id = 1")
        connection.executemany(
            "INSERT INTO cells (map_id, row, col, blocked) VALUES (1, ?, ?, ?)",
            [
                (row, col, campus_map.grid[row][col])
                for row in range(campus_map.rows)
                for col in range(campus_map.cols)
            ],
        )

    def update_cells(self, changes: Iterable[Iterable[int]]) -> None:
        rows = []
        for change in changes:
            row, col, value = (int(part) for part in change)
            rows.append((row, col, 0 if value == 0 else 1))
        if not rows:
            return
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO cells (map_id, row, col, blocked)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(map_id, row, col)
                DO UPDATE SET blocked = excluded.blocked
                """,
                rows,
            )

    def get_map(self) -> CampusMap:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT rows, cols, grid FROM maps WHERE id = 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("数据库中没有地图")
        return CampusMap(
            rows=int(row["rows"]),
            cols=int(row["cols"]),
            grid=json.loads(row["grid"]),
        )

    def get_map_meta(self) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT name, rows, cols, updated_at FROM maps WHERE id = 1"
            ).fetchone()
        if row is None:
            raise RuntimeError("数据库中没有地图")
        return dict(row)

    def save_map(self, campus_map: CampusMap, name: str | None = None) -> str:
        timestamp = now_text()
        with self.connect() as connection:
            if name:
                connection.execute(
                    "UPDATE maps SET name = ?, updated_at = ? WHERE id = 1",
                    (name, timestamp),
                )
            connection.execute(
                """
                UPDATE maps
                SET rows = ?, cols = ?, grid = ?, updated_at = ?
                WHERE id = 1
                """,
                (
                    campus_map.rows,
                    campus_map.cols,
                    json.dumps(campus_map.grid, separators=(",", ":")),
                    timestamp,
                ),
            )
        return timestamp

    def reset_map(self) -> CampusMap:
        campus_map = CampusMap.from_dict(self.base_data)
        self.save_map(campus_map, self.base_data.get("name", "校园地图（180×90）"))
        with self.connect() as connection:
            self._replace_cells(connection, campus_map)
        return campus_map

    def load_snapshot(self, snapshot: str) -> CampusMap:
        campus_map = self.get_map()
        campus_map.load_snapshot(snapshot)
        self.save_map(campus_map)
        with self.connect() as connection:
            self._replace_cells(connection, campus_map)
        return campus_map

    def list_places(self) -> list[Place]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM places WHERE map_id = 1 ORDER BY id"
            ).fetchall()
        return [
            Place(
                id=int(row["id"]),
                name=row["name"],
                type=row["type"],
                row=int(row["row"]),
                col=int(row["col"]),
                access_row=int(row["access_row"]),
                access_col=int(row["access_col"]),
                aliases=row["aliases"],
            )
            for row in rows
        ]

    def get_place(self, place_id: int) -> Place | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM places WHERE map_id = 1 AND id = ?", (place_id,)
            ).fetchone()
        if row is None:
            return None
        return Place(
            id=int(row["id"]),
            name=row["name"],
            type=row["type"],
            row=int(row["row"]),
            col=int(row["col"]),
            access_row=int(row["access_row"]),
            access_col=int(row["access_col"]),
            aliases=row["aliases"],
        )

    def add_place(
        self,
        name: str,
        place_type: str,
        row: int,
        col: int,
        access_row: int | None = None,
        access_col: int | None = None,
        aliases: str = "",
    ) -> Place:
        name = name.strip()
        if not name:
            raise ValueError("地点名称不能为空")
        campus_map = self.get_map()
        if not campus_map.in_bounds(row, col):
            raise ValueError("地点坐标越界")
        if access_row is None or access_col is None:
            nearest = campus_map.nearest_walkable(row, col)
            if nearest is None:
                raise ValueError("地点附近找不到可走格")
            access_row, access_col, _ = nearest
        access_row, access_col = int(access_row), int(access_col)
        if not campus_map.is_walkable(access_row, access_col):
            raise ValueError("入口格必须可走（0）")
        with self.connect() as connection:
            try:
                cursor = connection.execute(
                    """
                    INSERT INTO places
                        (map_id, name, type, row, col, access_row, access_col, aliases)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        place_type,
                        row,
                        col,
                        access_row,
                        access_col,
                        aliases.strip(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("地点名称已存在") from error
        return Place(
            id=int(cursor.lastrowid),
            name=name,
            type=place_type,
            row=row,
            col=col,
            access_row=access_row,
            access_col=access_col,
            aliases=aliases.strip(),
        )

    def update_place(
        self,
        place_id: int,
        name: str,
        place_type: str,
        row: int,
        col: int,
        access_row: int,
        access_col: int,
        aliases: str = "",
    ) -> Place:
        name = name.strip()
        if not name:
            raise ValueError("地点名称不能为空")
        campus_map = self.get_map()
        access_row, access_col = int(access_row), int(access_col)
        if not campus_map.in_bounds(row, col):
            raise ValueError("地点坐标越界")
        if not campus_map.is_walkable(access_row, access_col):
            raise ValueError("入口格必须可走（0）")
        with self.connect() as connection:
            try:
                cursor = connection.execute(
                    """
                    UPDATE places
                    SET name = ?, type = ?, row = ?, col = ?,
                        access_row = ?, access_col = ?, aliases = ?
                    WHERE id = ? AND map_id = 1
                    """,
                    (
                        name,
                        place_type,
                        row,
                        col,
                        access_row,
                        access_col,
                        aliases.strip(),
                        place_id,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("地点名称已存在") from error
            if cursor.rowcount == 0:
                raise ValueError("地点不存在")
        return Place(
            id=place_id,
            name=name,
            type=place_type,
            row=row,
            col=col,
            access_row=access_row,
            access_col=access_col,
            aliases=aliases.strip(),
        )

    def delete_place(self, place_id: int) -> None:
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM places WHERE id = ? AND map_id = 1", (place_id,)
            )

    def resolve_place(self, place_id: int) -> tuple[int, int, str]:
        place = self.get_place(place_id)
        if place is None:
            raise ValueError("地点不存在")
        return place.access_row, place.access_col, place.name

    def save_query(
        self,
        campus_map: CampusMap,
        start: tuple[int, int],
        goal: tuple[int, int],
        start_name: str,
        end_name: str,
        result: PathResult,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO queries
                    (map_id, start_name, end_name, start_row, start_col,
                     end_row, end_col, found, cost, expanded, elapsed_ms,
                     message, path, snapshot, snapshot_hash, created_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    start_name,
                    end_name,
                    start[0],
                    start[1],
                    goal[0],
                    goal[1],
                    1 if result.found else 0,
                    result.cost,
                    result.expanded,
                    result.elapsed_ms,
                    result.message,
                    json.dumps(result.path, separators=(",", ":")),
                    campus_map.snapshot(),
                    campus_map.snapshot_hash(),
                    now_text(),
                ),
            )
            query_id = int(cursor.lastrowid)
            connection.execute(
                """
                DELETE FROM queries
                WHERE id NOT IN (
                    SELECT id FROM queries ORDER BY id DESC LIMIT 100
                )
                """
            )
        return query_id

    def list_queries(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, start_name, end_name, start_row, start_col,
                       end_row, end_col, found, cost, expanded, elapsed_ms,
                       message, snapshot_hash, created_at
                FROM queries
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_query(self, query_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM queries WHERE id = ?", (query_id,)
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["path"] = json.loads(data["path"])
        data["found"] = bool(data["found"])
        return data

    def clear_history(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM queries")

    def export_bundle(self) -> dict[str, Any]:
        campus_map = self.get_map()
        return {
            "format": "campuspath-map",
            "version": 1,
            "name": self.get_map_meta()["name"],
            "rows": campus_map.rows,
            "cols": campus_map.cols,
            "grid": campus_map.grid,
            "places": [place.to_dict() for place in self.list_places()],
        }

    def import_bundle(self, bundle: dict[str, Any]) -> CampusMap:
        if bundle.get("format") not in (None, "campuspath-map"):
            raise ValueError("不是 CampusPath 地图文件")
        rows = int(bundle.get("rows", 0))
        cols = int(bundle.get("cols", 0))
        if (rows, cols) != (180, 90):
            raise ValueError("当前前端只支持 180×90 地图")
        campus_map = CampusMap(rows, cols, bundle["grid"])
        places = bundle.get("places", [])
        if not isinstance(places, list):
            raise ValueError("places 必须是列表")
        with self.connect() as connection:
            connection.execute(
                "UPDATE maps SET name = ?, rows = ?, cols = ?, grid = ?, updated_at = ? WHERE id = 1",
                (
                    str(bundle.get("name", "导入地图")),
                    rows,
                    cols,
                    json.dumps(campus_map.grid, separators=(",", ":")),
                    now_text(),
                ),
            )
            self._replace_cells(connection, campus_map)
            connection.execute("DELETE FROM places WHERE map_id = 1")
            try:
                for place in places:
                    access_row = int(place.get("access_row", place["row"]))
                    access_col = int(place.get("access_col", place["col"]))
                    if not campus_map.is_walkable(access_row, access_col):
                        nearest = campus_map.nearest_walkable(access_row, access_col)
                        if nearest is None:
                            raise ValueError(
                                f"地点“{place.get('name', '')}”的入口格不可走"
                            )
                        access_row, access_col, _ = nearest
                    connection.execute(
                        """
                        INSERT INTO places
                            (map_id, name, type, row, col, access_row, access_col, aliases)
                        VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(place["name"]),
                            str(place.get("type", "building")),
                            int(place["row"]),
                            int(place["col"]),
                            access_row,
                            access_col,
                            str(place.get("aliases", "")),
                        ),
                    )
            except sqlite3.IntegrityError as error:
                raise ValueError("导入地点名称重复或格式不正确") from error
        return campus_map

    def stats(self) -> dict[str, Any]:
        with self.connect() as connection:
            place_count = connection.execute(
                "SELECT COUNT(*) AS count FROM places WHERE map_id = 1"
            ).fetchone()["count"]
            query_count = connection.execute(
                "SELECT COUNT(*) AS count FROM queries"
            ).fetchone()["count"]
        campus_map = self.get_map()
        return {
            **campus_map.counts(),
            "places": place_count,
            "queries": query_count,
            "components": campus_map.components(),
            "snapshot_hash": campus_map.snapshot_hash(),
        }

    def reset_database(self) -> None:
        """Delete all rows and rebuild the seed data.  Used only by tests."""
        with self.connect() as connection:
            connection.executescript(
                "DROP TABLE IF EXISTS queries;"
                "DROP TABLE IF EXISTS places;"
                "DROP TABLE IF EXISTS maps;"
            )
        self._initialize()
