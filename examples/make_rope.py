"""Moves for rope_d09.bly (Advent of Code 2022, day 9): head moves that make
the last knot of a rope of ten draw a picture, worked out here with both
answers, so the Barleycorn can be checked against it.

Melissa's own inputs did this: her rope wrote "Merry Xmas" and drew lines and
curves, from paths she traced and turned into moves. The tail can't lift off
the page, so a picture is one line, which may go back over itself. The default
is Barley the cat, sitting with his tail curled up behind him: 77 squares.

How the tail is steered. Pulled straight, the rope's tail follows the head's
line exactly, nine knots behind. At a corner the head walks back along its
own path: the rope folds up behind it and the tail stays where it is. Then
the head sets off the new way, and the rope pays out straight from the
corner, so the tail turns it sharply (her movepart2.pl pulled the rope taut
the same way). A diagonal is the head zigzagging. For each stroke this tries
folding back each number of steps, and each way round a zigzag, runs each
try, and keeps the shortest that draws the stroke exactly. At the end, the
head walks to where the window, which follows it, frames the whole picture.

A picture of your own can be rows of # (drawn) and . (not), whose squares
join at their sides or corners. It's walked depth first, from a square near
its middle, stepping back along squares already drawn when it's boxed in,
which takes many more moves than a picture drawn as strokes.
"""
import argparse
import os
import sys

# Barley, as the points his line goes through, x across and y down; each stroke between two is straight, across,
# up or down, or at 45 degrees.
BARLEY = [(9, 17), (2, 17), (2, 14), (5, 11), (5, 10), (1, 6), (1, 3), (4, 0), (6, 2),   # his left side and ear
          (7, 2), (7, 4), (7, 2),              # his tabby stripes, hanging from his brow
          (9, 2), (9, 5), (9, 2),
          (11, 2), (11, 4), (11, 2),
          (12, 2), (14, 0), (17, 3), (17, 6), (13, 10), (13, 11), (16, 14), (16, 17),   # his right ear and side
          (20, 17), (23, 14), (23, 11), (21, 9),   # his tail, curling up behind him,
          (23, 11), (23, 14), (20, 17), (16, 17),  # and back down it
          (9, 17)]                             # and along the ground to where he started

ap = argparse.ArgumentParser(prog='make_rope.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('picture', nargs='?',
                help='a picture of your own: rows of # and . (default Barley, as rope_d09.txt has)')
ap.add_argument('-o', default=None, help='where the moves go (default rope_d09.txt beside this script)')
a = ap.parse_args()
KNOTS = 10
D = {'U': (0, -1), 'D': (0, 1), 'L': (-1, 0), 'R': (1, 0)}
BACK = {'U': 'D', 'D': 'U', 'L': 'R', 'R': 'L'}
NAME = {(1, 0): 'R', (-1, 0): 'L', (0, -1): 'U', (0, 1): 'D'}


def sign(v):
    return (v > 0) - (v < 0)


def squares(points):                       # the squares a line through these points covers, in order
    out = [points[0]]
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        n, vx, vy = max(abs(bx - ax), abs(by - ay)), sign(bx - ax), sign(by - ay)
        out += [(ax + vx * j, ay + vy * j) for j in range(1, n + 1)]
    return out


if a.picture:                              # a picture of squares: walk it depth first, from near its middle
    rows = [r for r in open(a.picture).read().split('\n') if r.strip()]
    cells = {(x, y) for y, r in enumerate(rows) for x, ch in enumerate(r) if ch == '#'}
    if not cells:
        ap.error('the picture has no # in it')
    mx = (min(x for x, _ in cells) + max(x for x, _ in cells)) / 2
    my = (min(y for _, y in cells) + max(y for _, y in cells)) / 2
    start = min(cells, key=lambda c: ((c[0] - mx) ** 2 + (c[1] - my) ** 2, c[1], c[0]))
    KING = [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, 1), (-1, -1), (1, -1)]
    walk, seen = [start], {start}
    sys.setrecursionlimit(20000)

    def visit(c, came):                    # straight on if it can, then square, then diagonal; and back
        for d in sorted(KING, key=lambda d: (d != came, d[0] != 0 and d[1] != 0)):
            n = (c[0] + d[0], c[1] + d[1])
            if n in cells and n not in seen:
                seen.add(n)
                walk.append(n)
                visit(n, d)
                walk.append(c)

    visit(start, (1, 0))
    if seen != cells:
        ap.error(f'the picture is in more than one piece: {len(cells) - len(seen)} squares can\'t be reached '
                 f'(squares join at their sides or corners)')
    points, came = [walk[0]], None         # runs of the same step are one stroke
    for i in range(1, len(walk)):
        step = (walk[i][0] - walk[i - 1][0], walk[i][1] - walk[i - 1][1])
        if step == came:
            points[-1] = walk[i]
        else:
            points.append(walk[i])
        came = step
else:
    points = BARLEY
picture = squares(points)
cells = set(picture)


def pull(rope, m):                         # the head moves one step, and each knot keeps up with the one before
    dx, dy = D[m]
    k = list(rope)
    k[0] = (k[0][0] + dx, k[0][1] + dy)
    for i in range(1, len(k)):
        (px, py), (x, y) = k[i - 1], k[i]
        if abs(px - x) > 1 or abs(py - y) > 1:
            k[i] = (x + sign(px - x), y + sign(py - y))
    return tuple(k)


rope = tuple([points[0]] * KNOTS)
moves = []
for (ax, ay), (bx, by) in zip(points, points[1:]):
    dx, dy = bx - ax, by - ay
    if not (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
        sys.exit(f'make_rope.py: the stroke from {ax},{ay} to {bx},{by} is neither straight nor diagonal')
    n, v = max(abs(dx), abs(dy)), (sign(dx), sign(dy))
    zigzags = [NAME[v[0], 0] + NAME[0, v[1]], NAME[0, v[1]] + NAME[v[0], 0]] if v[0] and v[1] else [NAME[v]]
    best = None
    for k in range(min(len(moves), 30) + 1):     # fold back k steps of the head's own path
        fold = [BACK[m] for m in reversed(moves[len(moves) - k:])]
        r = rope
        for m in fold:
            r = pull(r, m)
            if r[-1] != rope[-1]:
                break
        else:
            for zz in zigzags:             # then out along the stroke, until the tail has drawn it
                out, s, tail, drawn = [], r, rope[-1], 0
                while drawn < n and len(out) < 4 * n + 40:
                    out.append(zz[len(out) % len(zz)])
                    s = pull(s, out[-1])
                    if s[-1] != tail:
                        if s[-1] != (tail[0] + v[0], tail[1] + v[1]):
                            break          # it went the wrong way
                        tail, drawn = s[-1], drawn + 1
                if drawn == n and (best is None or len(fold) + len(out) < len(best[0])):
                    best = (fold + out, s)
    if best is None:
        sys.exit(f'make_rope.py: no way found to draw the stroke from {ax},{ay} to {bx},{by}')
    moves += best[0]
    rope = best[1]

# the last window: the head at column 16, row 11 of 32 by 22, rows 20 and 21 for the answers
xs, ys = [x for x, _ in cells], [y for _, y in cells]
lo_x, hi_x, lo_y, hi_y = max(xs) - 15, min(xs) + 16, max(ys) - 8, min(ys) + 11
if lo_x > hi_x or lo_y > hi_y:
    sys.exit(f'make_rope.py: the picture is {max(xs) - min(xs) + 1} squares by {max(ys) - min(ys) + 1}, '
             f'and the last window shows 32 by 20')
goal = ((lo_x + hi_x) // 2, (lo_y + hi_y) // 2)
best = None
for k in range(min(len(moves), 30) + 1):   # fold back, then walk there, without the tail moving
    fold = [BACK[m] for m in reversed(moves[len(moves) - k:])]
    for first in 'xy':
        r, path, h = rope, list(fold), list(rope[0])
        for m in fold:
            h = [h[0] + D[m][0], h[1] + D[m][1]]
        for axis in (first, 'y' if first == 'x' else 'x'):
            i = 0 if axis == 'x' else 1
            while h[i] != goal[i]:
                m = NAME[(sign(goal[0] - h[0]), 0)] if i == 0 else NAME[(0, sign(goal[1] - h[1]))]
                path.append(m)
                h[i] += sign(goal[i] - h[i])
        for m in path:
            r = pull(r, m)
            if r[-1] != rope[-1]:
                break
        else:
            if best is None or len(path) < len(best[0]):
                best = (path, r)
if best is None:
    sys.exit('make_rope.py: no way found for the head to frame the picture at the end')
moves += best[0]

lines = []
for m in moves:                            # runs of the same way are one move
    if lines and lines[-1][0] == m:
        lines[-1][1] += 1
    else:
        lines.append([m, 1])

# the puzzle, run as it says, for both answers, and to check the last knot drew the picture and nothing else
knots = [points[0]] * KNOTS
near, far, trail = {knots[1]}, {knots[-1]}, [knots[-1]]
for m, n in lines:
    for _ in range(n):
        knots = list(pull(knots, m))
        near.add(knots[1])
        far.add(knots[-1])
        if knots[-1] != trail[-1]:
            trail.append(knots[-1])
assert trail == picture, 'the tail strayed from the picture'
assert tuple(knots[0]) == goal

out = a.o or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rope_d09.txt')
open(out, 'w').write(''.join(f'{m} {n}\n' for m, n in lines))
print(f'{len(cells)} squares, {len(moves)} moves of the head in {len(lines)} lines')
print(f'positions visited by knot 1 (part 1): {len(near)}; by knot 9 (part 2): {len(far)}')
if max(len(near), len(far)) > 500:
    print(f'(rope_d09.bly\'s sets hold 500 squares each, its ROOM: raise it for this, and it may not fit a 48K)')
