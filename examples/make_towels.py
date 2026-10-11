"""Towels and designs for towels_d19.bly (Advent of Code 2024, day 19, part 2):
in how many ways a heap of striped towels can make each design, counted here in
Python too (as Melissa's program counts them), so the Barleycorn can be checked
against it.

A stripe is one of five colours, w, u, b, r and g. The towels are 120 patterns
of 1 to 8 stripes, most of them short, and every colour is a towel on its own
but r, so an r has to come inside a longer towel: some designs can't be made at
all. The designs are 30 of 40 to 60 stripes, most laid end to end from towels,
the rest at random. A small LCG, so the same heap comes out everywhere.
"""
import argparse
import os

ap = argparse.ArgumentParser(prog='make_towels.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('seed', type=int, nargs='?', default=19, help='the heap (default 19, the one towels_d19.txt holds)')
SEED = ap.parse_args().seed


class LCG:
    def __init__(self, seed):
        self.x = seed

    def below(self, n):
        self.x = (self.x * 1103515245 + 12345) % 2 ** 31
        return (self.x >> 8) % n


rng = LCG(SEED)
towels = ['w', 'u', 'b', 'g']
while len(towels) < 120:
    t = ''.join('wubrg'[rng.below(5)] for _ in range([2, 2, 2, 3, 3, 3, 4, 5, 6, 7, 8][rng.below(11)]))
    if t not in towels:
        towels.append(t)
designs = []
for k in range(30):
    n = 40 + rng.below(21)
    if k % 3 == 2:                                  # at random
        d = ''.join('wubrg'[rng.below(5)] for _ in range(n))
    else:                                           # end to end
        d = ''
        while len(d) < n:
            d += towels[rng.below(len(towels))]
        d = d[:60]
    designs.append(d)

here = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(here, 'towels_d19.txt'), 'w').write(', '.join(towels) + '\n\n' + ''.join(d + '\n' for d in designs))

# the count, as her program does it: dp[left] is the number of ways to make the design's last `left` stripes
total = possible = most = 0
for design in designs:
    q = len(design)
    dp = [1] + [0] * q
    for left in range(1, q + 1):
        dp[left] = sum(dp[left - len(t)] for t in towels if len(t) <= left and design[q - left:q - left + len(t)] == t)
    total += dp[q]
    possible += dp[q] > 0
    most = max(most, dp[q])
print(f'seed {SEED}: {len(towels)} towels, {len(designs)} designs, {possible} of them possible; '
      f'the most ways for one {most:,}')
print(f'total {total}')
