"""Check print against BASIC's PRINT itself: random PRINT statements (text, AT, and the separators ; and , anywhere a
BASIC program puts them: first, twice or more in a row, straight after AT's column), to the screen and to the lower
screen, typed as one line on omse-ai's 48K after a CLS and ended with PAUSE 0, so the ROM prints them; the same
statements, written in Barley, run in the interpreter. While the 48K waits in PAUSE, the whole screen (pixels and
attributes) must agree. A program the interpreter refuses (one that would grow the lower screen) is left out, and
said so. Run it with omse-ai's Python."""
import argparse
import os
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import paths                                    # noqa: E402
paths.omse_ai()
from speccy import Speccy                       # noqa: E402
BARLEY = os.path.join(HERE, '..', '..', 'interp', 'barley.py')
LETTERS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .-+*='


def statement(rng):
    """one PRINT: its stream (2, or 0 or 1 for the lower screen) and its pieces, in order: ('text', s), ('at', (r, c)),
    (',', None) or (';', None). Separators may come anywhere; two things that print have one between them"""
    stream = rng.choice([2, 2, 2, 0, 1])
    pieces, need_sep = [], False
    for _ in range(rng.randrange(1, 7 if stream == 2 else 4)):         # the lower screen has two lines to fill
        k = rng.choice(['text', 'text', 'at', ',', ',', ';'])
        if k in (',', ';'):
            pieces.append((k, None))
            need_sep = False
            continue
        if need_sep:
            pieces.append((rng.choice([';', ',']), None))
        if k == 'text':
            n = rng.randrange(1, 12 if stream == 2 else 6)
            pieces.append(('text', ''.join(rng.choice(LETTERS) for _ in range(n))))
        else:
            pieces.append(('at', (rng.randrange(2), rng.randrange(32)) if stream != 2 else
                           (rng.randrange(22), rng.randrange(32))))
        need_sep = True
    return stream, pieces


def basic(stream, pieces):
    out = 'PRINT ' + ('' if stream == 2 else f'#{stream};')
    for k, v in pieces:
        out += {'text': lambda: f'"{v}"', 'at': lambda: f'AT {v[0]},{v[1]}'}.get(k, lambda: k)()
    return out


def barley(stream, pieces):
    out = 'print ' + ('' if stream == 2 else f'#{stream}; ')
    for k, v in pieces:
        out += {'text': lambda: f'"{v}"', 'at': lambda: f'at {v[0]}, {v[1]}'}.get(k, lambda: k)()
    return out


def main():
    ap = argparse.ArgumentParser(prog='print_check.py', description=__doc__)
    ap.add_argument('n', metavar='N', type=int, nargs='?', default=60, help='how many runs (default 60)')
    ap.add_argument('seed', metavar='SEED', type=int, nargs='?', default=1, help='their seed (default 1)')
    a = ap.parse_args()
    rng = random.Random(a.seed)
    bad = skipped = 0
    with tempfile.TemporaryDirectory() as d:
        p, png = os.path.join(d, 't.bly'), os.path.join(d, 't.png')
        for k in range(a.n):
            stmts = [statement(rng) for _ in range(rng.randrange(1, 5))]
            open(p, 'w').write('func main()\n  cls()\n' + ''.join(f'  {barley(*st)}\n' for st in stmts) + 'end\n')
            r = subprocess.run([sys.executable, '-I', BARLEY, '--screen', png, p], capture_output=True, text=True,
                               stdin=subprocess.DEVNULL)
            if r.returncode:
                if 'grow the lower screen' not in r.stdout + r.stderr:
                    print(f'FAIL run {k}: the interpreter refused it: {(r.stdout + r.stderr).strip()[-200:]}')
                    print(open(p).read())
                    bad += 1
                else:
                    skipped += 1
                continue
            want = open(os.path.join(d, 't.scr'), 'rb').read()
            line = ': '.join(['CLS', 'POKE 23692,255'] + [basic(*st) for st in stmts] + ['PAUSE 0'])   # after
            # CLS, which sets the scroll count to 1, so a scroll never asks "scroll?", as Barley's never does
            zx = Speccy()
            zx.wait_ready()
            zx.type(line + '\n')
            if zx.wait_ready(pause=True, max_frames=400) is None:
                print(f'FAIL run {k}: BASIC never reached PAUSE 0: {line}')
                bad += 1
                continue
            got = bytes(zx.read(0x4000, 6912))
            if got != want:
                bad += 1
                diff = next(i for i in range(6912) if got[i] != want[i])
                print(f'FAIL run {k}: byte {diff} of the screen is {got[diff]:02X} on the 48K, {want[diff]:02X} in '
                      f'the interpreter: {line}')
    print(f'{a.n - bad - skipped} of {a.n} runs: the screen as BASIC prints it'
          + (f' ({skipped} left out: they would grow the lower screen)' if skipped else ''))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
