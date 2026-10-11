"""A board for monkey_d22.bly (Advent of Code 2022, day 22, part 2): six
50 x 50 faces of a cube, their walls, and a path, walked here in Python too
(as Melissa's program walks it), so the Barleycorn can be checked against it.

The faces join as Melissa's Spectrum program has them: which face lies beyond
each edge, and how it's turned, as her cubeinfo.pl worked them out from the
puzzle's net. The walls and the path are our own: about one square in ten a
wall, scattered, and 2,001 moves of 1 to 50 steps with a turn between each two.
On the top of the left-hand cube the walls draw a cat. A small LCG, so the same
board comes out everywhere.
"""
import argparse
import os

ap = argparse.ArgumentParser(prog='make_monkey.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('seed', type=int, nargs='?', default=22, help='the board (default 22, the one monkey_d22.txt holds)')
SEED = ap.parse_args().seed

# face f's neighbour beyond edges 1-4 (up, right, down, left in its plane), and how it's turned (1 = not at all, 2 =
# a quarter, 3 = a half, 4 = three quarters)
ADJ = ['4326', '1356', '1452', '1653', '4623', '4125']
ROT = ['3211', '1132', '4141', '3211', '1132', '4141']


class LCG:
    def __init__(self, seed):
        self.x = seed

    def below(self, n):
        self.x = (self.x * 1103515245 + 12345) % 2 ** 31
        return (self.x >> 8) % n


def cat(mx, my):
    """on face 1, the top of the left cube, drawn as a diamond: 'line' for the cat's outline and features, 'in' inside
    or near it (no scattered walls there), None elsewhere"""
    def inside(u, w):
        head = (u / 17) ** 2 + ((w + 3) / 13) ** 2 <= 1
        ears = any(w >= 6 and w <= 20 and abs(u - s * 11) <= (20 - w) * 0.45 for s in (-1, 1))
        return head or ears
    u, w = (mx - my) * 155 / 128, 51 - mx - my            # where the square shows: right, and up
    if not inside(u, w):
        near = (-7, -3.5, 0, 3.5, 7)                    # a clearing round her, so she shows
        return 'in' if any(inside(u + du, w + dw) for du in near for dw in near) else None
    if not all(inside(u + du, w + dw) for du, dw in ((-1.3, 0), (1.3, 0), (0, -1.3), (0, 1.3))):
        return 'line'
    eye = any(((u - s * 6.5) / 2.5) ** 2 + ((w - 1) / 2) ** 2 <= 1 for s in (-1, 1))
    nose = abs(u) <= 1.3 and -5 <= w <= -3
    whisker = 9 <= abs(u) <= 15.5 and any(abs(w + 6 - s * (abs(u) - 9) * 0.3) < 0.7 for s in (1, -1))
    return 'line' if eye or nose or whisker else 'in'


rng = LCG(SEED)
faces = []
for f in range(1, 7):
    rows = []
    for my in range(1, 51):
        row = ''
        for mx in range(1, 51):
            c = cat(mx, my) if f == 1 else None
            wall = c == 'line' or (c is None and rng.below(100) < 10 and (f, mx, my) != (1, 1, 1))
            row += '#' if wall else '.'
        rows.append(row)
    faces.append(rows)
path = ''
for k in range(2001):
    path += chr(50 + 1 + rng.below(50)) + ('12'[rng.below(2)] if k < 2000 else '0')

here = os.path.dirname(os.path.abspath(__file__))
lines = [x for k in range(6) for x in (ADJ[k], ROT[k])] + [r for rows in faces for r in rows] + \
    [path[i:i + 110] for i in range(0, len(path), 110)]
open(os.path.join(here, 'monkey_d22.txt'), 'w').write('\n'.join(lines) + '\n')

# the walk, as her program walks it
adj = {(f + 1, d + 1): int(ADJ[f][d]) for f in range(6) for d in range(4)}
rot = {(f + 1, d + 1): int(ROT[f][d]) for f in range(6) for d in range(4)}
mx = my = f = 1
dx, dy = 1, 0


def rotate(r):
    global mx, my, dx, dy
    if r == 2:
        mx, my, dx, dy = 51 - my, mx, -dy, dx
    elif r == 3:
        mx, my, dx, dy = 51 - mx, 51 - my, -dx, -dy
    elif r == 4:
        mx, my, dx, dy = my, 51 - mx, dy, -dx
    if dx < 0 and mx == 0:
        mx = 50
    elif dx > 0 and mx == 51:
        mx = 1
    elif dy < 0 and my == 0:
        my = 50
    elif dy > 0 and my == 51:
        my = 1


steps = crossings = 0
for ch in path:
    if ch == '0':
        break
    if ch == '1':
        dx, dy = dy, -dx
        continue
    if ch == '2':
        dx, dy = -dy, dx
        continue
    for _ in range(ord(ch) - 50):
        was = mx, my, f, dx, dy
        mx += dx
        my += dy
        for off, k in ((my == 0, 1), (mx == 51, 2), (my == 51, 3), (mx == 0, 4)):
            if off:
                rotate(rot[f, k])
                f = adj[f, k]
                break
        if faces[f - 1][my - 1][mx - 1] == '#':
            mx, my, f, dx, dy = was
            break
        steps += 1
        crossings += was[2] != f
facing = {(1, 0): 'right', (-1, 0): 'left', (0, 1): 'down', (0, -1): 'up'}[dx, dy]
print(f'seed {SEED}: {sum(r.count("#") for rows in faces for r in rows)} walls, {steps} steps taken, '
      f'{crossings} edges crossed')
print(f'Ended at {mx},{my}; facing {facing}, on face {f}')
