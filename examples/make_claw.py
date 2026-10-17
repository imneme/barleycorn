"""Claw machines for claw_d13.bly (Advent of Code 2024, day 13, part 2), with
the tokens each costs worked out here in Python too, so the Barleycorn can be
checked against it.

Each machine has a button A that moves the claw (dx1, dy1) for 3 tokens, a
button B that moves it (dx2, dy2) for 1, and a prize at (x, y); in part 2 the
prize is really at (x + 10^13, y + 10^13). Most machines are made from the
presses: a steep button and a shallow one, presses near what the far prize
needs, and the prize put wherever those presses land, so they're the answer.
The rest have no answer: a prize the presses can't land on exactly, or two
buttons both steep (or both shallow), where landing on it takes a negative
number of presses. There are two datasets, as Melissa's program has, each with
a title line: a small sample of 4 machines, and a challenge of many more. A
small LCG, so the same machines come out everywhere.
"""
import argparse
import os
from fractions import Fraction

ap = argparse.ArgumentParser(prog='make_claw.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('seed', type=int, nargs='?', default=13,
                help='the machines (default 13, the ones claw_d13.txt holds)')
ap.add_argument('-n', type=int, default=280, metavar='N',
                help='machines in the challenge (default 280)')
args = ap.parse_args()

FAR = 10 ** 13                                  # part 2: every prize is this much further on, in X and Y


class LCG:
    def __init__(self, seed):
        self.x = seed

    def below(self, n):
        self.x = (self.x * 1103515245 + 12345) % 2 ** 31
        return (self.x >> 8) % n


rng = LCG(args.seed)


def steep():
    dx = 11 + rng.below(40)
    return dx, dx + 10 + rng.below(89 - dx)


def shallow():
    dy, dx = steep()
    return dx, dy


def solve(m):
    """Cramer's rule, as her program does it: the presses, or None"""
    dx1, dy1, dx2, dy2, x, y = m
    x, y = x + FAR, y + FAR
    d = dx2 * dy1 - dx1 * dy2
    an, bn = dx2 * y - dy2 * x, dy1 * x - dx1 * y
    if an % d or bn % d or an // d < 0 or bn // d < 0:
        return None
    return an // d, bn // d


def machine(kind):
    while True:
        a_btn, b_btn = (steep(), shallow()) if rng.below(2) else (shallow(), steep())
        if kind == 'backwards':                 # both steep, or both shallow
            b_btn = steep() if a_btn[1] > a_btn[0] else shallow()
        (dx1, dy1), (dx2, dy2) = a_btn, b_btn
        d = dx2 * dy1 - dx1 * dy2
        if d == 0:
            continue
        x0, y0 = 1000 + rng.below(18000), 1000 + rng.below(18000)
        if kind == 'missed':                    # a prize the presses can't land on exactly
            m = (dx1, dy1, dx2, dy2, x0, y0)
            if solve(m) is None:
                return m, None
            continue
        a = round(Fraction(dx2 * (y0 + FAR) - dy2 * (x0 + FAR), d))     # presses near enough, and then
        b = round(Fraction(dy1 * (x0 + FAR) - dx1 * (y0 + FAR), d))     # the prize put where they land
        x, y = a * dx1 + b * dx2 - FAR, a * dy1 + b * dy2 - FAR
        if not (0 < x < 20000 and 0 < y < 20000):
            continue
        if kind == 'backwards':
            assert a < 0 or b < 0
            return (dx1, dy1, dx2, dy2, x, y), None
        return (dx1, dy1, dx2, dy2, x, y), (a, b)


def challenge():                                 # mostly prizes; one in eight missed, one in eight backwards
    k = rng.below(8)
    return 'backwards' if k == 0 else 'missed' if k == 1 else 'made'


datasets = [('Small Sample', 4, lambda i: ['made', 'missed', 'made', 'backwards'][i]),
            ('Challenge Problem', args.n, lambda i: challenge())]
text = []
for title, n, kind in datasets:
    text.append(title)
    tokens = won = 0
    for i in range(n):
        m, presses = machine(kind(i))
        assert solve(m) == presses              # the presses it was made from are the only answer
        dx1, dy1, dx2, dy2, x, y = m
        text += [f'Button A: X+{dx1}, Y+{dy1}', f'Button B: X+{dx2}, Y+{dy2}', f'Prize: X={x}, Y={y}', '']
        if presses:
            tokens += 3 * presses[0] + presses[1]
            won += 1
    print(f'{title}: {n} machines, {won} with prizes, {tokens} tokens')

here = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(here, 'claw_d13.txt'), 'w').write('\n'.join(text[:-1]) + '\n')
