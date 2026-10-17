"""Check print against BASIC's PRINT itself: after random colours and a CLS, random PRINT statements (text, AT,
colour items, and the separators ; and , anywhere a BASIC program puts them: first, twice or more in a row, straight
after AT's column), to the screen and to the lower screen, typed as one line on omse-ai's 48K and ended with PAUSE 0,
so the ROM prints them; the same statements, written in Barley, run in the interpreter. While the 48K waits in
PAUSE, the whole screen (pixels and attributes) must agree. A program the interpreter refuses (one that would grow
the lower screen) is left out, and said so. With --machines, C's screen and the 48K's (the program held in a loop at
its end, so BASIC's report doesn't cover the lower screen) must be the interpreter's too. Run it with omse-ai's
Python."""
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
BLY = os.path.join(HERE, '..', '..', 'bly')
LETTERS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .-+*='
COLOURS = {'ink': list(range(8)) + [8, 9, 9], 'paper': list(range(8)) + [8, 9, 9], 'bright': [0, 1, 8],
           'flash': [0, 1, 8], 'inverse': [0, 1], 'over': [0, 1]}


def colour(rng):
    k = rng.choice(list(COLOURS))
    return k, rng.choice(COLOURS[k])


def statement(rng):
    """one PRINT: its stream (2, or 0 or 1 for the lower screen) and its pieces, in order: ('text', s), ('at', (r, c)),
    (',', None) or (';', None). Separators may come anywhere; two things that print have one between them"""
    stream = rng.choice([2, 2, 2, 0, 1])
    pieces, need_sep = [], False
    for _ in range(rng.randrange(1, 7 if stream == 2 else 4)):         # the lower screen has two lines to fill
        k = rng.choice(['text', 'text', 'at', ',', ',', ';', 'colour', 'colour'])
        if k in (',', ';'):
            pieces.append((k, None))
            need_sep = False
            continue
        if need_sep:
            pieces.append((rng.choice([';', ',']), None))
        if k == 'text':
            n = rng.randrange(1, 12 if stream == 2 else 6)
            pieces.append(('text', ''.join(rng.choice(LETTERS) for _ in range(n))))
        elif k == 'colour':
            pieces.append(('colour', colour(rng)))
        else:
            pieces.append(('at', (rng.randrange(2), rng.randrange(32)) if stream != 2 else
                           (rng.randrange(22), rng.randrange(32))))
        need_sep = True
    colours = [i for i, (k, _) in enumerate(pieces) if k == 'colour']
    if colours and not any(k in ('text', ',') for k, _ in pieces[colours[-1]:]):    # something printed follows each
        pieces += [(';', None), ('text', rng.choice(LETTERS))]
    return stream, pieces


def basic(stream, pieces):
    out = 'PRINT ' + ('' if stream == 2 else f'#{stream};')
    for k, v in pieces:
        out += {'text': lambda: f'"{v}"', 'at': lambda: f'AT {v[0]},{v[1]}',
                'colour': lambda: f'{v[0].upper()} {v[1]}'}.get(k, lambda: k)()
    return out


def barley(stream, pieces):
    out = 'print ' + ('' if stream == 2 else f'#{stream}; ')
    for k, v in pieces:
        out += {'text': lambda: f'"{v}"', 'at': lambda: f'at {v[0]}, {v[1]}',
                'colour': lambda: f'{v[0]}({v[1]})'}.get(k, lambda: k)()
    return out


def c_screen(d, p):
    """the screen C leaves (bly c, then the executable with BARLEY_SCREEN), or None"""
    exe, scr = os.path.join(d, 'tc'), os.path.join(d, 'tc.scr')
    if subprocess.run([BLY, 'c', '-o', exe, p], capture_output=True).returncode:
        return None
    subprocess.run([exe], capture_output=True, stdin=subprocess.DEVNULL, env=dict(os.environ, BARLEY_SCREEN=scr))
    return open(scr, 'rb').read() if os.path.exists(scr) else None


def zx_screen(d, p):
    """the screen the 48K's runtime leaves, the program held in a loop at its end so BASIC's report doesn't cover the
    lower screen: or None"""
    held = os.path.join(d, 'tz.bly')
    open(held, 'w').write(open(p).read().rstrip('\n')[:-len('end')] + '  while true do pause(1) end\nend\n')
    png = os.path.join(d, 'tz.png')
    subprocess.run([BLY, 'zx', '--minutes', '0.05', '--scr', png, held], capture_output=True, stdin=subprocess.DEVNULL)
    scr = os.path.join(d, 'tz.scr')
    return open(scr, 'rb').read() if os.path.exists(scr) else None


def main():
    ap = argparse.ArgumentParser(prog='print_check.py', description=__doc__)
    ap.add_argument('n', metavar='N', type=int, nargs='?', default=60, help='how many runs (default 60)')
    ap.add_argument('seed', metavar='SEED', type=int, nargs='?', default=1, help='their seed (default 1)')
    ap.add_argument('--machines', action='store_true', help="C's screen and the 48K's against the interpreter's too")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    bad = skipped = 0
    with tempfile.TemporaryDirectory() as d:
        p, png = os.path.join(d, 't.bly'), os.path.join(d, 't.png')
        for k in range(a.n):
            stmts = [statement(rng) for _ in range(rng.randrange(1, 5))]
            perm = [colour(rng) for _ in range(rng.randrange(4))] + [('border', rng.randrange(8))]
            open(p, 'w').write('func main()\n' + ''.join(f'  {k}({v})\n' for k, v in perm) + '  cls()\n'
                               + ''.join(f'  {barley(*st)}\n' for st in stmts) + 'end\n')
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
            line = ': '.join([f'{k.upper()} {v}' for k, v in perm] + ['CLS', 'POKE 23692,255']
                             + [basic(*st) for st in stmts] + ['PAUSE 0'])     # the POKE after
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
                continue
            if a.machines:
                for name, scr in (('C', c_screen(d, p)), ("the 48K's runtime", zx_screen(d, p))):
                    if scr != want:
                        bad += 1
                        diff = next((i for i in range(6912) if scr is None or scr[i] != want[i]), 0)
                        where = ' (no screen)' if scr is None else f' at byte {diff}: {scr[diff]:02X}, not {want[diff]:02X}'
                        print(f'FAIL run {k}: {name} differs from the interpreter{where}\n' + open(p).read())
                        break
    print(f'{a.n - bad - skipped} of {a.n} runs: the screen as BASIC prints it'
          + (f' ({skipped} left out: they would grow the lower screen)' if skipped else ''))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
