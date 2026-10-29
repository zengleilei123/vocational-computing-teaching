"""Student-owned baseline. Deliberately goes straight and may hit walls.

Replace plan(grid) locally, keeping the same contract: <=400 direction strings.
Do not edit the evaluator to make the score look better. This is trusted local
Python, not a service that accepts or executes uploaded student code.
"""
from .engine import parse_grid


def plan(grid):
    (r, c), (gr, gc) = parse_grid(grid)
    actions = ['right' if gc > c else 'left'] * abs(gc - c)
    actions += ['down' if gr > r else 'up'] * abs(gr - r)
    return actions
