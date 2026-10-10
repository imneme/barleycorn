"""Check the reference's lower screen (print #0 and #1) against BASIC itself: random BORDER, INK, PAPER, INVERSE
and OVER, a CLS, then random PRINT #0 and PRINT #1 statements (AT 0 or 1, text, ;, ' and the newline at the end),
typed as one line on omse-ai's 48K and ended with PAUSE 0, so the ROM's own channel K prints them; the same calls
go to zxgfx.Screen. While the 48K waits in PAUSE, rows 22 and 23 (their pixels and attributes) must agree. A
statement that would grow the lower screen, which Barley refuses, is left out: the model says which. Run it with
omse-ai's Python."""
import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(HERE, '..'))
import paths                                    # noqa: E402
paths.omse_ai()
from speccy import Speccy                       # noqa: E402
import zxgfx                                    # noqa: E402

LETTERS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .-+*='


def colours(rng):
    """BORDER first, so CLS clears the lower screen in its colours; then what the lower screen should ignore"""
    out = [('border', rng.randrange(8))]
    for _ in range(rng.randrange(4)):
        k = rng.choice(['ink', 'paper', 'inverse', 'over'])
        out.append((k, rng.randrange(8) if k in ('ink', 'paper') else rng.randrange(2)))
    return out


def statement(rng):
    """one PRINT #0 or #1: items as (kind, value), and whether it ends with a newline"""
    items = []
    for _ in range(rng.randrange(1, 5)):
        k = rng.choice(['text', 'text', 'at', 'nl'])
        if k == 'text':
            items.append(('text', ''.join(rng.choice(LETTERS) for _ in range(rng.randrange(1, 14)))))
        elif k == 'at':
            items.append(('at', (rng.randrange(2), rng.randrange(32))))
        else:
            items.append(('nl', None))
    return rng.randrange(2), items, rng.random() < 0.5


def basic(stream, items, newline):
    out, sep = f'PRINT #{stream}', ';'
    for k, v in items:
        if k == 'text':
            out += f'{sep}"{v}"'
        elif k == 'at':
            out += f'{sep}AT {v[0]},{v[1]}'
        else:
            out += "'"
            sep = ''
            continue
        sep = ';'
    return out + ('' if newline else ';')


def model(sc, items, newline):
    for k, v in items:
        if k == 'text':
            for ch in v.encode():
                sc.lout(ch)
        elif k == 'at':
            sc.lat(*v)
        else:
            sc.lout(10)
    if newline:
        sc.lout(10)


def lower(mem):
    """rows 22 and 23: their pixel bytes and attributes"""
    rows = bytes(mem[((r & 0x18) << 8) | (i << 8) | ((r & 7) << 5) + c] for r in (22, 23) for i in range(8)
                 for c in range(32))
    return rows + bytes(mem[6144 + 22 * 32:6144 + 24 * 32])


def main():
    ap = argparse.ArgumentParser(prog='lower_check.py', description=__doc__)
    ap.add_argument('n', metavar='N', type=int, nargs='?', default=40, help='how many runs (default 40)')
    ap.add_argument('seed', metavar='SEED', type=int, nargs='?', default=1, help='their seed (default 1)')
    a = ap.parse_args()
    rng = random.Random(a.seed)
    bad = 0
    for k in range(a.n):
        sc = zxgfx.Screen(glyphs=zxgfx.font())
        cols = colours(rng)
        for name, v in cols:
            {'inverse': sc.set_inverse, 'over': sc.set_over}.get(name, getattr(sc, name, None))(v)
        sc.cls()
        stmts = []
        for _ in range(rng.randrange(1, 4)):
            st = statement(rng)
            trial = zxgfx.Screen(glyphs=sc.font)          # would it grow the lower screen? then leave it out
            trial.mem[:], trial.lrow, trial.lcol, trial.border_colour = sc.mem, sc.lrow, sc.lcol, sc.border_colour
            try:
                model(trial, st[1], st[2])
            except zxgfx.ScreenError:
                continue
            model(sc, st[1], st[2])
            stmts.append(st)
        line = ': '.join([f'{n.upper()} {v}' for n, v in cols] + ['CLS'] + [basic(*st) for st in stmts] + ['PAUSE 0'])
        zx = Speccy()
        zx.wait_ready()
        zx.type(line + '\n')
        if zx.wait_ready(pause=True, max_frames=400) is None:
            print(f'FAIL run {k}: BASIC never reached PAUSE 0: {line}')
            bad += 1
            continue
        got, want = lower(zx.read(0x4000, 6912)), lower(sc.mem)
        if got != want:
            bad += 1
            diff = next(i for i in range(len(got)) if got[i] != want[i])
            print(f'FAIL run {k}: byte {diff} of rows 22-23 is {got[diff]:02X} on the 48K, {want[diff]:02X} in the '
                  f'model: {line}')
    print(f'{a.n - bad} of {a.n} runs: the lower screen as BASIC prints it')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
