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
        return [{**e, "temporary": e.get("source") == "map_inferred"} for e in available]
    row, col = state["places"][name]
    roads = [(abs(r-row)+abs(c-col), r, c) for r, line in enumerate(grid)
             for c, value in enumerate(line) if value == 0]
    if not roads:
        raise ValueError("地图没有可通行道路")
    distance, r, c = min(roads)
    return [{"name": "图面临时接入点", "point": [r, c],
             "temporary": True, "offset_steps": distance}]


def plan_named_route(state, start_name, goal_name, start_gate=None, goal_gate=None):
    starts, goals = access_points(state, start_name), access_points(state, goal_name)
    if start_gate is not None:
        starts = [e for e in starts if e["name"] == start_gate]
    if goal_gate is not None:
        goals = [e for e in goals if e["name"] == goal_gate]
    if not starts or not goals:
        raise ValueError("所选入口已不可用，请重新选择")
    best = None
    for start in starts:
        for goal in goals:
            result = astar(state["grid"], tuple(start["point"]), tuple(goal["point"]))
            if best is None or (result.found and
                    (not best[0].found or result.path_length < best[0].path_length)):
                best = result, start, goal
    return best
