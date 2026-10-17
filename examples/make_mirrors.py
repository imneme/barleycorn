"""Patterns for mirrors_d13.bly (Advent of Code 2023, day 13): grids of ash
(.) and rock (#), each with a mirror in it, and a smudge, worked out here in
Python too (as Melissa's program works them out), so the Barleycorn can be
checked against it.

Each pattern reflects perfectly about exactly one line, between two rows or
two columns: that's the answer with no smudges. And it reflects about exactly
one other line but for a single square: fix that square, the smudge, and it
reflects there too, which is the answer with one smudge. They're built that
way: squares that either mirror pairs up are tied together, each group of
tied squares is ash or rock at random, and then one square is flipped where
the first mirror doesn't reach, but the second does. Every other line is
checked to be out by two squares or more, so there's no doubt which line is
meant. A small LCG, so the same patterns come out everywhere.
"""
import argparse
import os

ap = argparse.ArgumentParser(prog='make_mirrors.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('seed', type=int, nargs='?', default=396,
                help='the patterns (default 396, the ones mirrors_d13.txt holds)')
ap.add_argument('-n', type=int, default=50, help='how many patterns (default 50)')
ap.add_argument('-o', default=None, help='where they go (default mirrors_d13.txt beside this script)')
a = ap.parse_args()


class LCG:
    def __init__(self, seed):
        self.x = seed

    def below(self, n):
        self.x = (self.x * 1103515245 + 12345) % 2 ** 31
        return (self.x >> 8) % n


def partner(line, r, c, h, w):
    """the square a mirror pairs (r, c) with, or None where its reflection falls off the pattern"""
    kind, at = line
    if kind == 'row':
        rr = 2 * at - 1 - r
        return (rr, c) if 0 <= rr < h else None
    cc = 2 * at - 1 - c
    return (r, cc) if 0 <= cc < w else None


def mismatches(rows, line):
    h, w = len(rows), len(rows[0])
    return sum(1 for r in range(h) for c in range(w)
               if (p := partner(line, r, c, h, w)) and rows[r][c] != rows[p[0]][p[1]]) // 2


def pattern(rng):
    while True:
        h, w = 5 + rng.below(13), 5 + rng.below(13)          # 5 to 17 each way, as hers are
        lines = [('row', k) for k in range(1, h)] + [('col', k) for k in range(1, w)]
        perfect = lines[rng.below(len(lines))]
        smudged = lines[rng.below(len(lines))]
        if smudged == perfect:
            continue
        group = list(range(h * w))                           # union-find: squares a mirror ties together

        def find(i):
            while group[i] != i:
                group[i] = group[group[i]]
                i = group[i]
            return i
        for line in (perfect, smudged):
            for r in range(h):
                for c in range(w):
                    p = partner(line, r, c, h, w)
                    if p:
                        group[find(r * w + c)] = find(p[0] * w + p[1])
        rock = {}
        rows = [['#' if rock.setdefault(find(r * w + c), rng.below(2)) else '.' for c in range(w)]
                for r in range(h)]
        spots = [(r, c) for r in range(h) for c in range(w)
                 if not partner(perfect, r, c, h, w) and partner(smudged, r, c, h, w)]
        if not spots:
            continue
        r, c = spots[rng.below(len(spots))]
        rows[r][c] = '.' if rows[r][c] == '#' else '#'
        rows = [''.join(row) for row in rows]
        if all(mismatches(rows, line) == {perfect: 0, smudged: 1}.get(line, 99) or
               (line not in (perfect, smudged) and mismatches(rows, line) >= 2) for line in lines):
            return rows


rng = LCG(a.seed)
patterns = [pattern(rng) for _ in range(a.n)]
here = os.path.dirname(os.path.abspath(__file__))
out = a.o or os.path.join(here, 'mirrors_d13.txt')
open(out, 'w').write('\n\n'.join('\n'.join(rows) for rows in patterns) + '\n')


def her_fold(rows, s):
    """her @findFold: the first fold, counting rows above it, whose mirror image is out by exactly s squares"""
    for f in range(1, len(rows)):
        if mismatches(rows, ('row', f)) == s:
            return f
    return None


for s in (0, 1):                                 # her answers, as she finds them: rows first, then transposed
    h = v = 0
    for rows in patterns:
        f = her_fold(rows, s)
        if f:
            v += f
        else:
            f = her_fold([''.join(col) for col in zip(*rows)], s)
            h += f or 0
    print(f'{s} smudges: H Sum: {h}  V Sum: {v}  Total: {h + 100 * v}')
