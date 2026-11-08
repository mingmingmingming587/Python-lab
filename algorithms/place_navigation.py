"""以地点名称查询路网路线；地点标记与道路入口相互独立。"""

from algorithms.astar import astar


def access_points(state, name):
    if name not in state["places"]:
        raise ValueError("地点不存在")
    grid = state["grid"]
    configured = state.get("entrances", {}).get(name, [])
    if configured:
        available = [e for e in configured if e.get("enabled", True) and
                     grid[e["point"][0]][e["point"][1]] == 0]
        if not available:
            raise ValueError(f"{name} 没有当前可用的已指定入口")
        entry = available[0]
        return [{**entry, "temporary": entry.get("source") == "map_inferred"}]
    row, col = state["places"][name]
    roads = [(abs(r-row)+abs(c-col), r, c) for r, line in enumerate(grid)
             for c, value in enumerate(line) if value == 0]
    if not roads:
        raise ValueError("地图没有可通行道路")
    distance, r, c = min(roads)
    return [{"name": "图面临时接入点", "point": [r, c],
             "temporary": True, "offset_steps": distance}]


def plan_named_route(state, start_name, goal_name):
    start = access_points(state, start_name)[0]
    goal = access_points(state, goal_name)[0]
    result = astar(state["grid"], tuple(start["point"]), tuple(goal["point"]))
    return result, start, goal
