PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS maps (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    rows INTEGER NOT NULL CHECK(rows > 0),
    cols INTEGER NOT NULL CHECK(cols > 0)
);

CREATE TABLE IF NOT EXISTS map_cells (
    map_id INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
    row INTEGER NOT NULL CHECK(row >= 0),
    col INTEGER NOT NULL CHECK(col >= 0),
    cell_type INTEGER NOT NULL CHECK(cell_type IN (0, 1)),
    PRIMARY KEY (map_id, row, col)
);

CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY,
    map_id INTEGER NOT NULL REFERENCES maps(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    row INTEGER NOT NULL CHECK(row >= 0),
    col INTEGER NOT NULL CHECK(col >= 0),
    UNIQUE(map_id, name)
);

CREATE TABLE IF NOT EXISTS route_records (
    id INTEGER PRIMARY KEY,
    map_id INTEGER NOT NULL REFERENCES maps(id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    start_name TEXT NOT NULL,
    goal_name TEXT NOT NULL,
    start_row INTEGER NOT NULL,
    start_col INTEGER NOT NULL,
    goal_row INTEGER NOT NULL,
    goal_col INTEGER NOT NULL,
    algorithm TEXT NOT NULL,
    found INTEGER NOT NULL CHECK(found IN (0, 1)),
    path_length INTEGER,
    expanded_count INTEGER NOT NULL,
    elapsed_ms REAL NOT NULL,
    grid_snapshot TEXT NOT NULL,
    path_snapshot TEXT NOT NULL,
    visited_snapshot TEXT NOT NULL
);
