"""Check the reference's colours against BASIC itself: random runs of BORDER, INK, PAPER, BRIGHT and FLASH (8 and 9
too), then CLS, typed as BASIC commands on omse-ai's 48K, so the ROM's own CO-TEMP sets them; the same calls go to
zxgfx.Screen. Afterwards ATTR_P, MASK_P, P_FLAG's INK 9 and PAPER 9 bits, BORDCR and the squares CLS cleared (an
upper one and a lower one) must agree. (rom_text_check holds the drawing to the ROM's PO-ATTR; this holds the
colours it draws with.) Run it with omse-ai's Python."""
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

ATTR_P, MASK_P, P_FLAG, BORDCR = 0x5C8D, 0x5C8E, 0x5C91, 0x5C48
RESET = [('border', 7), ('ink', 0), ('paper', 7), ('bright', 0), ('flash', 0)]


def calls(rng):
    out = []
    for _ in range(rng.randrange(1, 7)):
        k = rng.choice(['ink', 'paper', 'ink', 'paper', 'bright', 'flash', 'border'])
        if k in ('ink', 'paper'):
            out.append((k, rng.choice(list(range(8)) + [8, 8, 9, 9, 9])))
        elif k == 'border':
            out.append((k, rng.randrange(8)))
        else:
            out.append((k, rng.choice([0, 1, 8])))
    return out


def basic(zx, cs):
    zx.type(': '.join(f'{k.upper()} {n}' for k, n in cs) + ': CLS\n')
    if zx.wait_ready() is None:
        raise RuntimeError('BASIC never came back')
    return {'attr_p': zx.peek(ATTR_P), 'mask': zx.peek(MASK_P), 'ink9': bool(zx.peek(P_FLAG) & 0x20),
            'paper9': bool(zx.peek(P_FLAG) & 0x80), 'bordcr': zx.peek(BORDCR), 'upper': zx.peek(0x5800 + 7 * 32 + 9),
            'lower': zx.peek(0x5800 + 23 * 32 + 1)}


def model(sc, cs):
    for k, n in cs:
        getattr(sc, k)(n)
    sc.cls()
    return {'attr_p': sc.attr_p, 'mask': sc.mask, 'ink9': sc.ink9, 'paper9': sc.paper9, 'bordcr': sc.bordcr(),
            'upper': sc.mem[6144 + 7 * 32 + 9], 'lower': sc.mem[6144 + 23 * 32 + 1]}


def main():
    ap = argparse.ArgumentParser(prog='co_temp_check.py', description=__doc__)
    ap.add_argument('n', metavar='N', type=int, nargs='?', default=60, help='how many runs (default 60)')
    ap.add_argument('seed', metavar='SEED', type=int, nargs='?', default=1, help='their seed (default 1)')
    a = ap.parse_args()
    rng = random.Random(a.seed)
    zx = Speccy()
    zx.wait_ready()
    sc = zxgfx.Screen(glyphs=bytes(768))
    bad = 0
    for k in range(a.n):
        cs = calls(rng)
        basic(zx, RESET)
        model(sc, RESET)
        got, want = basic(zx, cs), model(sc, cs)
        if got != want:
            bad += 1
            diff = {key: (f'{got[key]}', f'{want[key]}') for key in got if got[key] != want[key]}
            print(f'FAIL run {k}: {cs}: BASIC, the model: {diff}')
    print(f'{a.n - bad} of {a.n} runs: the colours as BASIC sets them')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
