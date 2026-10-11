"""Rocks for sand_d14.bly (Advent of Code 2022, day 14, part 1): paths of rock
in the puzzle's own form (x,y -> x,y -> ...), and how many grains of sand come
to rest before the first one falls past the lowest rock, counted here twice:
grain by grain, as the puzzle tells it, and with the recursive fill Melissa's
program uses, so the Barleycorn can be checked against both.

The rocks are a Christmas tree: branches that are shallow cups, each wider
than the one above, a trunk, and presents round it. Sand poured in at 500,0
fills the top cup and heaps up like snow. A grain tries down-left before
down-right, so once a cup's left rim is reached, the snow spills off the left
end onto the branch below, and the tree ends up snowed on from the right. The
last of it lands on a present, and the first grain past that falls away. Some
paths come twice, as they do in the puzzle's inputs. A small LCG places the
presents, so the same tree comes out everywhere.
"""
import argparse
import os
import sys

ap = argparse.ArgumentParser(prog='make_sand.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('seed', type=int, nargs='?', default=14,
                help='the presents and the order (default 14, as sand_d14.txt has)')
SEED = ap.parse_args().seed
sys.setrecursionlimit(10000)


class LCG:
    def __init__(self, seed):
        self.x = seed

    def below(self, n):
        self.x = (self.x * 1103515245 + 12345) % 2 ** 31
        return (self.x >> 8) % n


rng = LCG(SEED)
paths = []
y = 14
for w in (5, 11, 18, 26, 35, 45):                   # the branches: cups, each with a rim 4 high
    paths.append([(500 - w, y - 4), (500 - w, y), (500 + w, y), (500 + w, y - 4)])
    y += w // 2 + 8
foot = y + 20
paths.append([(498, y - 6), (498, foot), (502, foot), (502, y - 6)])                 # the trunk


def present(x0, w, h):                               # a box, closed, sitting on the ground
    return [(x0, foot - h), (x0 + w, foot - h), (x0 + w, foot), (x0, foot), (x0, foot - h)]


paths.append(present(451, 8, 4))                    # where the last of the snow falls
for x0 in (470, 481, 506, 517):                     # and four round the trunk, their sizes by the LCG
    paths.append(present(x0, 4 + rng.below(5), 3 + rng.below(4)))
for _ in range(6):                                   # some paths come twice, as in the puzzle's inputs
    paths.append(list(paths[rng.below(len(paths))]))
order = list(range(len(paths)))
for i in range(len(order) - 1, 0, -1):
    j = rng.below(i + 1)
    order[i], order[j] = order[j], order[i]
paths = [paths[i] for i in order]

here = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(here, 'sand_d14.txt'), 'w').write(
    ''.join(' -> '.join(f'{x},{y}' for x, y in p) + '\n' for p in paths))

rock = set()
for p in paths:
    for (x0, y0), (x1, y1) in zip(p, p[1:]):
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                rock.add((x, y))
xs, ys = [x for x, _ in rock], [y for _, y in rock]
lowest = max(ys)

# grain by grain, as the puzzle tells it
full = set(rock)
grains = 0
while True:
    x, y = 500, 0
    while y <= lowest:
        for dx in (0, -1, 1):
            if (x + dx, y + 1) not in full:
                x, y = x + dx, y + 1
                break
        else:
            break
    if y > lowest:
        break
    full.add((x, y))
    grains += 1

# her way: a cell is sand if it, and the cells below, below left and below right, all come to rest
seen = set(rock)


def fill(x, y):
    if (x, y) in seen:
        return True
    if y > lowest:
        return False
    seen.add((x, y))
    if fill(x, y + 1) and fill(x - 1, y + 1) and fill(x + 1, y + 1):
        return True
    seen.discard((x, y))
    return False


fill(500, 0)
assert len(seen) - len(rock) == grains, (len(seen) - len(rock), grains)
print(f'seed {SEED}: {len(paths)} paths, x {min(xs)} to {max(xs)}, y {min(ys)} to {lowest}; {grains} grains')
