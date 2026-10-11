"""A program for the little CPU of crt_d10.bly (Advent of Code 2022, day 10):
addx and noop instructions whose CRT spells a word, worked out here, with the
sum of the signal strengths at cycles 20, 60, ... 220, so the Barleycorn can be
checked against it.

The CRT is 40 pixels by 6 rows, one pixel a cycle. A pixel lights when the
3-pixel sprite, centred on X, covers it, and X changes only when an addx
finishes, two cycles after it starts. So which instructions light which pixels
is a search: over (cycle, X), from the last cycle back, which X values can
still finish the picture. Where there's a choice it takes one at random (a
small LCG, so the same program comes out everywhere), so the program looks like
a real one rather than a pattern.

The sprite starts at X = 1, and nothing can move it before the third cycle, so
the first two pixels of the top row always light: the word's first letter needs
its top-left corner lit (which is why our S has a flat top).
"""
import argparse
import os

FONT = {                           # 4 x 6, our own; M is 5 wide, so it fits only as the last letter
    'S': ['####', '#...', '.##.', '...#', '...#', '###.'],
    'P': ['###.', '#..#', '#..#', '###.', '#...', '#...'],
    'E': ['####', '#...', '###.', '#...', '#...', '####'],
    'C': ['.##.', '#..#', '#...', '#...', '#..#', '.##.'],
    'T': ['###.', '.#..', '.#..', '.#..', '.#..', '.#..'],
    'R': ['###.', '#..#', '#..#', '###.', '#.#.', '#..#'],
    'U': ['#..#', '#..#', '#..#', '#..#', '#..#', '.##.'],
    'M': ['#...#', '##.##', '#.#.#', '#...#', '#...#', '#...#'],
    'A': ['.##.', '#..#', '#..#', '####', '#..#', '#..#'],
    'B': ['###.', '#..#', '###.', '#..#', '#..#', '###.'],
    'L': ['#...', '#...', '#...', '#...', '#...', '####'],
    'Y': ['#..#', '#..#', '.##.', '..#.', '..#.', '..#.'],
    'Z': ['####', '...#', '..#.', '.#..', '#...', '####'],
    'X': ['#..#', '#..#', '.##.', '.##.', '#..#', '#..#'],
    '8': ['.##.', '#..#', '.##.', '#..#', '#..#', '.##.'],
    '0': ['.##.', '#..#', '#.##', '##.#', '#..#', '.##.'],
}
ap = argparse.ArgumentParser(prog='make_crt.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('word', nargs='?', default='SPECTRUM',
                help='up to eight of ' + ''.join(sorted(FONT)) +
                     ' (an M only last); default SPECTRUM, as crt_d10.txt has')
ap.add_argument('seed', type=int, nargs='?', default=10, help='the program\'s choices (default 10)')
a = ap.parse_args()
WORD, SEED = a.word.upper(), a.seed
if len(WORD) > 8 or any(ch not in FONT for ch in WORD) or 'M' in WORD[:-1]:
    ap.error('the word is up to eight of ' + ''.join(sorted(FONT)) + ', and M fits only last')
W, H = 40, 6
XS = range(-3, W + 3)              # X values worth considering


class LCG:
    def __init__(self, seed):
        self.x = seed

    def below(self, n):
        self.x = (self.x * 1103515245 + 12345) % 2 ** 31
        return (self.x >> 8) % n


# the picture, a row of 40 pixels at a time
rows = [''] * H
for k, ch in enumerate(WORD):
    for r in range(H):
        rows[r] += FONT[ch][r] + ('.' if len(FONT[ch][r]) == 4 else '')
rows = [(r + '.' * W)[:W] for r in rows]
want = [rows[c // W][c % W] == '#' for c in range(W * H)]


def ok(c, x):                      # does X = x at cycle c (from 0) light the pixel just as the picture wants?
    return (abs(x - c % W) <= 1) == want[c]


# can[c] is the set of X values from which cycles c... can all come out right
can = [set() for _ in range(W * H + 2)]
can[W * H] = set(XS)
can[W * H + 1] = set(XS)
for c in range(W * H - 1, -1, -1):
    for x in XS:
        if not ok(c, x):
            continue
        if x in can[c + 1] or (c + 1 < W * H and ok(c + 1, x) and can[c + 2]):
            can[c].add(x)
assert 1 in can[0], 'no program draws this from X = 1'

rng = LCG(SEED)
prog, c, x = [], 0, 1
while c < W * H:
    noop = x in can[c + 1]
    addx = c + 1 < W * H and ok(c + 1, x) and sorted(can[c + 2])
    if addx and (not noop or rng.below(3)):
        nx = addx[rng.below(len(addx))]
        if nx == x and len(addx) > 1:
            nx = addx[(addx.index(x) + 1) % len(addx)]
        prog.append(f'addx {nx - x}')
        c, x = c + 2, nx
    else:
        prog.append('noop')
        c += 1

here = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(here, 'crt_d10.txt'), 'w').write(''.join(p + '\n' for p in prog))

# run it as the puzzle says, for the sum and the picture
x, cycle, total, screen = 1, 0, 0, []
for p in prog:
    for _ in range(2 if p.startswith('addx') else 1):
        cycle += 1
        if cycle in (20, 60, 100, 140, 180, 220):
            total += cycle * x
        screen.append('#' if abs(x - (cycle - 1) % W) <= 1 else '.')
    if p.startswith('addx'):
        x += int(p.split()[1])
assert screen == ['#' if w else '.' for w in want]
print(f'{WORD}, seed {SEED}: {len(prog)} instructions, {cycle} cycles; signal strengths sum {total}')
for r in range(H):
    print(''.join(screen[r * W:(r + 1) * W]))
