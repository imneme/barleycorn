"""A sky for galaxies_d11.bly (Advent of Code 2023, day 11): a grid of '.' and
'#' whose galaxies, when you look, draw Barnsley's fern, worked out here as
Melissa's program works it out, so the Barleycorn can be checked against it.

The fern is thrown by its four affine maps (a small LCG picks them, so the same
sky comes out everywhere), and each point lights the cell it lands in. Every
seventh row and column is kept empty, lanes through the fern for space to
expand into. Her program sums, over every pair of galaxies, the steps between
them in rows and columns that hold a galaxy (Nml) and those that don't (Exp);
a gap of g makes each empty row or column g wide, so the answer is
Nml + Exp * g: g = 2 is the puzzle's part 1, and 1000000 its part 2.
"""
import argparse
import os

ap = argparse.ArgumentParser(prog='make_galaxies.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('seed', type=int, nargs='?', default=11, help='the throw (default 11, as galaxies_d11.txt has)')
ap.add_argument('-n', type=int, default=600, help='points thrown (default 600)')
a = ap.parse_args()

W, H, LANE = 70, 140, 7                    # cells across and down; every LANE-th row and column is empty


class LCG:
    def __init__(self, seed):
        self.x = seed

    def unit(self):                        # 0 <= r < 1
        self.x = (self.x * 1103515245 + 12345) % 2 ** 31
        return (self.x >> 8) / 2 ** 23


rng = LCG(a.seed)
x = y = 0.0
cells = set()
for _ in range(a.n):
    r = rng.unit()
    if r < 0.01:
        x, y = 0.0, 0.16 * y
    elif r < 0.86:
        x, y = 0.85 * x + 0.04 * y, -0.04 * x + 0.85 * y + 1.6
    elif r < 0.93:
        x, y = 0.20 * x - 0.26 * y, 0.23 * x + 0.22 * y + 1.6
    else:
        x, y = -0.15 * x + 0.28 * y, 0.26 * x + 0.24 * y + 0.44
    c = int((x + 2.4) / 5.2 * W)           # x -2.4..2.8 across, y 0..10 up the sky
    r_ = H - 1 - int(y / 10.0 * H)
    if 0 <= c < W and 0 <= r_ < H and c % LANE != LANE - 1 and r_ % LANE != LANE - 1:
        cells.add((r_, c))
rows = [''.join('#' if (r, c) in cells else '.' for c in range(W)) for r in range(H)]

# her sums: prefix counts of empty columns and rows, then every pair
empty_c = [all(rows[r][c] == '.' for r in range(H)) for c in range(W)]
empty_r = [all(ch == '.' for ch in row) for row in rows]
gal = [(c, r) for r in range(H) for c in range(W) if rows[r][c] == '#']
pc = [0] * (W + 1)
for c in range(W):
    pc[c + 1] = pc[c] + empty_c[c]
pr = [0] * (H + 1)
for r in range(H):
    pr[r + 1] = pr[r] + empty_r[r]
nml = exp = 0
for i in range(len(gal)):
    for j in range(i + 1, len(gal)):
        x1, x2 = sorted((gal[i][0], gal[j][0]))
        y1, y2 = sorted((gal[i][1], gal[j][1]))
        k = pc[x2] - pc[x1] + pr[y2] - pr[y1]
        exp += k
        nml += x2 - x1 + y2 - y1 - k
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'galaxies_d11.txt')
open(out, 'w').write(''.join(r + '\n' for r in rows))
n = len(gal)
print(f'{W} x {H}, {n} galaxies, {n * (n - 1) // 2} pairs; Nml {nml}, Exp {exp}')
print(f'gap 2: {nml + 2 * exp}; gap 1000000: {nml + 1000000 * exp}')
