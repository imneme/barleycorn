"""A sudoku for sudoku.bly, and its solution, worked out here in Python so the
Barleycorn can be checked against it.

It fills a grid at random (a small LCG, so the same puzzle comes out
everywhere), then takes clues away in a random order for as long as the answer
stays unique. The seed was chosen by trying a few dozen: plain backtracking
(cells in reading order, digits 1 to 9, which is what sudoku.bly does) needs
anything from a few hundred placements to two million, depending on the
puzzle. This one needs a couple of thousand: enough to watch the search back
up, and few enough for a 48K to finish while you're still watching.
"""
import argparse
import os
import sys

ap = argparse.ArgumentParser(prog='make_sudoku.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('seed', type=int, nargs='?', default=3, help='the puzzle (default 3, the one sudoku.txt holds)')
SEED = ap.parse_args().seed


class LCG:
    def __init__(self, seed):
        self.x = seed

    def below(self, n):
        self.x = (self.x * 1103515245 + 12345) % 2 ** 31
        return (self.x >> 8) % n

    def shuffle(self, xs):
        for i in range(len(xs) - 1, 0, -1):
            j = self.below(i + 1)
            xs[i], xs[j] = xs[j], xs[i]


def ok(g, k, d):
    r, c = divmod(k, 9)
    b = r // 3 * 27 + c // 3 * 3
    return all(g[r * 9 + i] != d and g[i * 9 + c] != d and g[b + i // 3 * 9 + i % 3] != d for i in range(9))


def fill(g, rng, k=0):
    if k == 81:
        return True
    ds = list(range(1, 10))
    rng.shuffle(ds)
    for d in ds:
        if ok(g, k, d):
            g[k] = d
            if fill(g, rng, k + 1):
                return True
    g[k] = 0
    return False


def count(g, limit=2, k=0):
    """the number of solutions, stopping at limit"""
    while k < 81 and g[k]:
        k += 1
    if k == 81:
        return 1
    n = 0
    for d in range(1, 10):
        if ok(g, k, d):
            g[k] = d
            n += count(g, limit - n, k + 1)
            if n >= limit:
                break
    g[k] = 0
    return n


def placements(g):
    """how many digits the plain search puts down, and its answer"""
    g = list(g)
    n = 0

    def go(k):
        nonlocal n
        while k < 81 and g[k]:
            k += 1
        if k == 81:
            return True
        for d in range(1, 10):
            if ok(g, k, d):
                g[k] = d
                n += 1
                if go(k + 1):
                    return True
        g[k] = 0
        return False

    go(0)
    return n, g


def puzzle(seed):
    rng = LCG(seed)
    g = [0] * 81
    fill(g, rng)
    order = list(range(81))
    rng.shuffle(order)
    for k in order:
        keep, g[k] = g[k], 0
        if count(g) != 1:
            g[k] = keep
    return g


p = puzzle(SEED)
n, answer = placements(p)
here = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(here, 'sudoku.txt'), 'w').write(
    ''.join(''.join(str(d) if d else '.' for d in p[r * 9:r * 9 + 9]) + '\n' for r in range(9)))
print(f'seed {SEED}: {sum(1 for d in p if d)} clues, {n} placements')
for r in range(9):
    row = ''.join(map(str, answer[r * 9:r * 9 + 9]))
    print(row[0:3], row[3:6], row[6:9])
