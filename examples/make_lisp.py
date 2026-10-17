"""Brackets for lisp_d01.bly (Advent of Code 2015, day 1): a ( takes Santa up a
floor and a ) down one, and the program draws his floor as a line across a sky
and the ground. Ours draw a street: three houses with pointed roofs, a little
above the ground, and then the stairs down into the basement. Worked out here in
Python too (his last floor, and where he first goes below the ground floor), so
the Barleycorn can be checked against it.

The program plots one pixel column for every 32 brackets, and a floor is an
eighth of a pixel, so each column's 32 brackets are its rise or fall in floors
(at most 32), the rest in pairs, shuffled so the line has some texture. A small
LCG, so the same street comes out everywhere.
"""
import argparse
import os

ap = argparse.ArgumentParser(prog='make_lisp.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('seed', type=int, nargs='?', default=2015, help='the shuffle (default 2015, the one lisp_d01.txt holds)')
SEED = ap.parse_args().seed


class LCG:
    def __init__(self, seed):
        self.x = seed

    def below(self, n):
        self.x = (self.x * 1103515245 + 12345) % 2 ** 31
        return (self.x >> 8) % n


def street():
    """the floor to be on after each pixel column, in floors (8 to a pixel), from the ground floor: 200 columns"""
    ground = 16                                     # two pixels up: the shuffle never dips into the basement here
    path = [ground] * 6
    for _ in range(3):                              # a house: a wall up, a pointed roof, a wall down, a garden
        path += [ground + 32 * k for k in range(1, 9)]          # 8 columns of wall: 32 pixels high
        top = path[-1]
        path += [top + 8 * k for k in range(1, 15)]             # the roof up, a pixel a column
        peak = path[-1]
        path += [peak - 8 * k for k in range(1, 15)]            # and down
        path += [top - 32 * k for k in range(1, 9)]             # the wall down to the ground
        path += [ground] * 10                                   # the garden between houses
    while path[-1] > -240:                          # then the stairs down into the basement: a step, a landing
        path += [path[-1] - 32] + [path[-1] - 32] * 3
    return path + [path[-1]] * (200 - len(path))


rng = LCG(SEED)
out, floor = [], 0
for want in street():
    rise = want - floor
    assert abs(rise) <= 32 and rise % 2 == 0
    col = ['('] * ((32 + rise) // 2) + [')'] * ((32 - rise) // 2)
    for i in range(len(col) - 1, 0, -1):            # shuffled, so the line wobbles a little
        j = rng.below(i + 1)
        col[i], col[j] = col[j], col[i]
    out += col
    floor = want
text = ''.join(out)
here = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(here, 'lisp_d01.txt'), 'w').write(text + '\n')

# the answers, as the puzzle asks them
floor, first = 0, 0
for i, ch in enumerate(text, 1):
    floor += 1 if ch == '(' else -1
    if floor < 0 and not first:
        first = i
print(f'seed {SEED}: {len(text)} brackets; floor {floor}; first in the basement at position {first}')
