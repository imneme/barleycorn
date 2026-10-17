"""Robots for robots_d14.bly (Advent of Code 2024, day 14, part 2): 500 robots
on a floor 101 tiles wide and 103 tall, each moving in a straight line and
wrapping at the edges, which at one moment line up into a picture. Here the
picture is a fern (Barnsley's, drawn by its own maps), and the moment is
secret: the program is an instrument for finding it. Most of the robots make
the fern and its pot; the rest wander at random, as some do in the puzzle's
inputs.

The fern's robots are made by running them backwards: each starts on a tile
of the fern with a random velocity, and goes back that many seconds to where
the input says it begins. Then the moment is found again the way a person finds
it, from scratch: the columns bunch up once every 101 seconds and the rows
once every 103, and only one time in 10,403 has both. This script checks that
that time is the secret one, and that the robots then make the fern.
It prints the time, and the keys that step the program there, for its
-- keys: line. A small LCG, so the same robots come out everywhere.
"""
import argparse
import collections
import math
import os

W, H, N = 101, 103, 500
ap = argparse.ArgumentParser(prog='make_robots.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('seed', type=int, nargs='?', default=14,
                help='the fern, the velocities and the moment (default 14, as robots_d14.txt has)')
SEED = ap.parse_args().seed


class LCG:
    def __init__(self, seed):
        self.x = seed

    def below(self, n):
        self.x = (self.x * 1103515245 + 12345) % 2 ** 31
        return (self.x >> 8) % n


rng = LCG(SEED)

# the fern: Barnsley's. Its first map squashes the whole fern onto its stalk, and the other three make smaller
# copies of the whole fern: the rest of it up the spine, and the first frond on each side. So drawing the stalk,
# then the stalk under every combination of the other three, down to copies shorter than a tile and a half,
# draws the fern itself: the spine, and the fronds, smaller towards the tip.
MAPS = ((0.85, 0.04, -0.04, 0.85, 0.0, 1.6), (0.2, -0.26, 0.23, 0.22, 0.0, 1.6), (-0.15, 0.28, 0.26, 0.24, 0.0, 0.44))


def then(t, f):                                       # t after f
    a, b, c, d, e, g = t
    p, q, r, s, u, v = f
    return (a * p + b * r, a * q + b * s, c * p + d * r, c * q + d * s, a * u + b * v + e, c * u + d * v + g)


def tile(t, x, y):                                    # a point of the fern (x -2.2..2.7, y 0..10) on the floor
    a, b, c, d, e, g = t
    return 50 + (a * x + b * y + e) * 8.4, 86 - (c * x + d * y + g) * 8.0


fern, order, todo = set(), [], [(1, 0, 0, 1, 0, 0)]
while todo:
    t = todo.pop()
    (x0, y0), (x1, y1) = tile(t, 0, 0), tile(t, 0, 1.6)
    if math.hypot(x1 - x0, y1 - y0) < 1.5:
        continue
    x0, y0, x1, y1 = round(x0), round(y0), round(x1), round(y1)
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(n + 1):
        p = (round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n))
        if p not in fern:
            fern.add(p)
            order.append(p)
    todo += [then(t, f) for f in MAPS]


def plant(p):
    if p not in fern:
        fern.add(p)
        order.append(p)


# and its pot: a rim two rows thick (the rows bunch there, as the columns bunch in the fern), sides, and a base
for x in range(34, 67):
    plant((x, 87))
    plant((x, 88))
for y in range(89, 100):
    plant((36 + (y - 89) // 3, y))
    plant((64 - (y - 89) // 3, y))
for x in range(39, 62):
    plant((x, 100))

T = 1500 + rng.below(8000)                                # the secret moment
robots = []
for i in range(N):                                         # the fern's robots, then strays to make up 500
    vx = vy = 0
    while vx == 0 or vy == 0:
        vx, vy = rng.below(199) - 99, rng.below(199) - 99
    if i < len(order):
        tx, ty = order[i]
        robots.append(((tx - vx * T) % W, (ty - vy * T) % H, vx, vy))
    else:
        robots.append((rng.below(W), rng.below(H), vx, vy))
k = list(range(N))                                         # in no particular order
for i in range(N - 1, 0, -1):
    j = rng.below(i + 1)
    k[i], k[j] = k[j], k[i]
robots = [robots[i] for i in k]

here = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(here, 'robots_d14.txt'), 'w').write(
    ''.join(f'p={px},{py} v={vx},{vy}\n' for px, py, vx, vy in robots))


def at(t):
    return [((px + vx * t) % W, (py + vy * t) % H) for px, py, vx, vy in robots]


assert fern <= set(at(T))

# found again, as a person would: the most bunched columns, the most bunched rows, and the one time with both
def spread(vals, size):
    return sum(c * c for c in collections.Counter(vals).values())        # bigger when they bunch


tx = max(range(W), key=lambda t: spread([p[0] for p in at(t)], W))
ty = max(range(H), key=lambda t: spread([p[1] for p in at(t)], H))
found = next(t for t in range(W * H) if t % W == tx and t % H == ty)
assert found == T, (found, T)

# the keys from time 0 to T, fewest first: x and z step 1, q and a 101, p and o 103; 0 ends the simulation
steps = {'x': 1, 'z': -1, 'q': W, 'a': -W, 'p': H, 'o': -H}
came = {0: None}
todo = collections.deque([0])
while T not in came:
    t = todo.popleft()
    for k, d in steps.items():
        n = (t + d) % (W * H)
        if n not in came:
            came[n] = (t, k)
            todo.append(n)
keys, t = '', T
while came[t]:
    t, k = came[t]
    keys = k + keys
print(f'seed {SEED}: {N} robots; the fern at {T} seconds (columns bunch at {tx} mod 101, rows at {ty} mod 103)')
print(f'keys: {keys}0   ({len(keys)} steps)')
