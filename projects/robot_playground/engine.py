"""Small, bounded graph-search arena. BFS optimizes steps, Dijkstra entry cost.

No learned model is involved. Map symbols are the editable teaching material.
Coordinates are [row, column]; a normal move costs 1, digits cost their value.
"""
from collections import deque
import heapq

DIRECTIONS = {'up': (-1, 0), 'right': (0, 1), 'down': (1, 0), 'left': (0, -1)}
PRESETS = [
    {'id': 'energy', 'title': '近路不一定省电', 'question': '最少步数和最低能耗，会得到同一条路线吗？',
     'grid': ['#########', '#S99999G#', '#.#####.#', '#.......#', '#########']},
    {'id': 'detour', 'title': '绕路才到得了', 'question': '只朝目标方向走，会不会卡住？',
     'grid': ['#########', '#S..#..G#', '#.#.#.#.#', '#.#...#.#', '#.#####.#', '#.......#', '#########']},
    {'id': 'blocked', 'title': '给不可能任务找证据', 'question': '没有路时，系统应该怎样报告，而不是假装成功？',
     'grid': ['#######', '#S#..G#', '###...#', '#.....#', '#######']},
]


def parse_grid(grid):
    if not isinstance(grid, list) or not 3 <= len(grid) <= 20:
        raise ValueError('地图需要 3–20 行。')
    if any(not isinstance(row, str) for row in grid):
        raise ValueError('每一行必须是字符串。')
    width = len(grid[0])
    if not 3 <= width <= 20 or any(len(row) != width for row in grid):
        raise ValueError('地图需要等宽的 3–20 列。')
    if any(c not in '#.SG23456789' for row in grid for c in row):
        raise ValueError('地图只允许 # . S G 和数字 2–9。')
    starts = [(r, c) for r, row in enumerate(grid) for c, value in enumerate(row) if value == 'S']
    goals = [(r, c) for r, row in enumerate(grid) for c, value in enumerate(row) if value == 'G']
    if len(starts) != 1 or len(goals) != 1:
        raise ValueError('地图必须恰好有一个 S 和一个 G。')
    return starts[0], goals[0]


def neighbors(grid, position):
    for action, (dr, dc) in DIRECTIONS.items():
        r, c = position[0] + dr, position[1] + dc
        if 0 <= r < len(grid) and 0 <= c < len(grid[0]) and grid[r][c] != '#':
            yield action, (r, c), int(grid[r][c]) if grid[r][c].isdigit() else 1


def replay(grid, actions):
    start, goal = parse_grid(grid)
    if not isinstance(actions, list) or len(actions) > 400 or any(
        not isinstance(a, str) or a not in DIRECTIONS for a in actions
    ):
        raise ValueError('动作必须是最多 400 个 up/right/down/left 组成的列表。')
    position, path, energy, reason = start, [list(start)], 0, 'incomplete'
    for action in actions:
        if position == goal:
            reason = 'after_goal'
            break
        choices = {a: (pos, cost) for a, pos, cost in neighbors(grid, position)}
        if action not in choices:
            reason = 'blocked'
            break
        position, cost = choices[action]
        path.append(list(position))
        energy += cost
    else:
        reason = 'goal' if position == goal else 'incomplete'
    return {'success': reason == 'goal', 'reason': reason,
            'path': path, 'steps': len(path) - 1, 'energy': energy}


def solve(grid, algorithm='bfs'):
    start, goal = parse_grid(grid)
    if algorithm not in ('bfs', 'dijkstra'):
        raise ValueError('算法只能是 bfs 或 dijkstra。')
    parents, distances, expanded = {start: None}, {start: 0}, []
    queue = deque([start])
    heap = [(0, start)]
    while queue if algorithm == 'bfs' else heap:
        if algorithm == 'bfs':
            position = queue.popleft()
        else:
            distance, position = heapq.heappop(heap)
            if distance != distances[position]:
                continue
        expanded.append(list(position))
        if position == goal:
            actions, cursor = [], goal
            while parents[cursor] is not None:
                cursor, action = parents[cursor]
                actions.append(action)
            actions.reverse()
            return {**replay(grid, actions), 'actions': actions, 'expanded': expanded, 'algorithm': algorithm}
        for action, candidate, cost in neighbors(grid, position):
            new_distance = distances[position] + (1 if algorithm == 'bfs' else cost)
            if candidate not in distances or new_distance < distances[candidate]:
                distances[candidate] = new_distance
                parents[candidate] = (position, action)
                if algorithm == 'bfs':
                    queue.append(candidate)
                else:
                    heapq.heappush(heap, (new_distance, candidate))
    return {'success': False, 'reason': 'unreachable', 'actions': [], 'path': [],
            'steps': None, 'energy': None, 'expanded': expanded, 'algorithm': algorithm}
