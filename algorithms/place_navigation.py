"""以地点名称查询路网路线；地点标记与道路入口相互独立。"""

from algorithms.astar import astar


def access_point(state, name):
    if name not in state["places"]:
        raise ValueError("地点不存在")
    grid = state["grid"]
    configured = state.get("entrances", {}).get(name, [])
    if configured:
        entry, = configured
        row, col = entry["point"]
        if not entry.get("enabled", True) or grid[row][col] != 0:
            raise ValueError(f"{name} 没有当前可用的已指定入口")
        return {**entry, "temporary": entry.get("source") == "map_inferred"}
    row, col = state["places"][name]
    roads = [(abs(r-row)+abs(c-col), r, c) for r, line in enumerate(grid)
             for c, value in enumerate(line) if value == 0]
    if not roads:
        raise ValueError("地图没有可通行道路")
    distance, r, c = min(roads)
    return {"name": "图面临时接入点", "point": [r, c],
            "temporary": True, "offset_steps": distance}


def plan_named_route(state, start_name, goal_name):
    start = access_point(state, start_name)
    goal = access_point(state, goal_name)
    result = astar(state["grid"], tuple(start["point"]), tuple(goal["point"]))
    return result, start, goal
