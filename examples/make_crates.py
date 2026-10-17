"""Stacks of crates and a crane's moves for crates_d05.bly (Advent of Code 2022,
day 5, part 2), worked out here in Python too, so the Barleycorn can be checked
against it. The crane is the CrateMover 9001, which lifts a whole run of crates
at once, so they land in the order they were in.

The stacks start 3 to 8 crates high, and the crane makes a few hundred moves of
1 to 10 crates between them, at random (a small LCG, so the same moves come out
everywhere). No stack ever holds more than 54 crates, as Melissa's program
allows. The crates are lettered last: every crate is followed through the moves,
and the ones that end on top get the letters of the word, so the top of each
stack spells it. The rest are lettered at random.
"""
import argparse
import os

ap = argparse.ArgumentParser(prog='make_crates.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('word', nargs='?', default='MERRYXMAS',
                help='what the tops spell: 1 to 9 letters, a stack for each '
                     '(default MERRYXMAS, as crates_d05.txt has)')
ap.add_argument('seed', type=int, nargs='?', default=3,
                help='the stacks and the moves (default 3, as crates_d05.txt has)')
ap.add_argument('--moves', type=int, default=320, help='how many moves (default 320)')
a = ap.parse_args()
WORD, SEED, MOVES = a.word.upper(), a.seed, a.moves
if not 1 <= len(WORD) <= 9 or not WORD.isalpha() or not WORD.isascii():
    ap.error('the word is 1 to 9 letters, A to Z')
N, MOST = len(WORD), 54


class LCG:
    def __init__(self, seed):
        self.x = seed

    def below(self, n):
        self.x = (self.x * 1103515245 + 12345) % 2 ** 31
        return (self.x >> 8) % n


rng = LCG(SEED)
stacks = [[] for _ in range(N)]            # crates by number, bottom first
crates = 0
for s in stacks:
    for _ in range(3 + rng.below(6)):
        s.append(crates)
        crates += 1
start = [list(s) for s in stacks]


def move(count, src, dst):                 # the CrateMover 9001: the run of crates keeps its order
    run = stacks[src][-count:]
    del stacks[src][-count:]
    stacks[dst].extend(run)


moves = []
tallest = max(len(s) for s in stacks)
while len(moves) < MOVES:
    src, dst = rng.below(N), rng.below(N - 1)
    if dst >= src:
        dst += 1
    most = min(10, len(stacks[src]), MOST - len(stacks[dst]))
    if len(moves) >= MOVES * 9 // 10:      # near the end, leave every stack a crate
        most = min(most, len(stacks[src]) - 1)
    if most > 0:
        moves.append((1 + rng.below(most), src, dst))
        move(*moves[-1])
        tallest = max(tallest, len(stacks[dst]))
for dst in range(N):                       # no stack may end empty: the tallest gives it a crate
    if not stacks[dst]:
        src = max(range(N), key=lambda k: len(stacks[k]))
        moves.append((1, src, dst))
        move(1, src, dst)

letter = [chr(65 + rng.below(26)) for _ in range(crates)]
for k in range(N):
    letter[stacks[k][-1]] = WORD[k]

lines = []                                 # the drawing, top row first, as the puzzle draws it
for h in range(max(len(s) for s in start) - 1, -1, -1):
    lines.append(' '.join(f'[{letter[s[h]]}]' if h < len(s) else '   ' for s in start))
lines.append(' '.join(f' {k + 1} ' for k in range(N)))
lines.append('')
lines += [f'move {c} from {s + 1} to {d + 1}' for c, s, d in moves]
here = os.path.dirname(os.path.abspath(__file__))
open(os.path.join(here, 'crates_d05.txt'), 'w').write(''.join(line + '\n' for line in lines))

# and again from the letters, as her program does it, to be sure the tops spell the word
stacks = [[letter[c] for c in s] for s in start]
for c, s, d in moves:
    move(c, s, d)
tops = ''.join(s[-1] for s in stacks)
assert tops == WORD
moved = sum(c for c, _, _ in moves)
print(f'seed {SEED}: {N} stacks, {crates} crates, {len(moves)} moves of {moved} crates; '
      f'the tallest stack {tallest} crates')
print(f'Tops code: {tops}')
