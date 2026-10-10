"""Check the reference's ports against omse-ai's 48K: random programs of outp, border, beep and inp, each address
spelled as a literal or as a variable of a random type, compiled for the 48K and run there, and the same calls made
on zxgfx.Screen. What inp read and the border showing at the end must agree. (The suite's cases hold the
interpreter and C to the same words; this holds the model to the machine, including what the suite can't see:
the border, which only a picture shows.) Run it with omse-ai's Python."""
import argparse
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(HERE, '..'))
import paths                                    # noqa: E402
paths.omse_ai()
from speccy import Speccy                       # noqa: E402
import transcript                               # noqa: E402
import zxgfx                                    # noqa: E402

ZXBUILD = os.path.join(HERE, '..', 'zxbuild.py')
BUILD = os.path.join(paths.BUILD, 'ula_check', str(os.getpid()))


def port(rng):
    """the ULA's (even), the joystick's (bits 5-7 clear), or nothing's, each with any top byte"""
    lo = rng.choice([rng.randrange(0, 256, 2), rng.randrange(1, 32, 2), rng.randrange(33, 256, 2)])
    return rng.randrange(256) << 8 | lo


def calls(rng):
    out = []
    for _ in range(rng.randrange(10, 30)):
        k = rng.choice(['outp', 'outp', 'outp', 'inp', 'inp', 'inp', 'border', 'beep'])
        if k == 'outp':
            out.append((k, port(rng), rng.randrange(256)))
        elif k == 'inp':
            out.append((k, port(rng)))
        elif k == 'border':
            out.append((k, rng.randrange(8)))
        else:                                   # short: a zero-cycle one isn't played, and changes nothing
            out.append((k, rng.randrange(4), rng.randrange(-60, 70)))
    return out


def program(rng, cs):
    lines, n = ['func main()'], 0
    for c in cs:
        if c[0] in ('outp', 'inp'):
            types = ['word', 'long', 'dword', 'quad'] + (['int'] if c[1] < 32768 else [])
            p = str(c[1])
            if rng.random() < 0.6:
                n += 1
                lines.append(f'  var p{n}: {rng.choice(types)} = {c[1]}')
                p = f'p{n}'
            lines.append(f'  outp({p}, {c[2]})' if c[0] == 'outp' else f'  print inp({p})')
        else:
            lines.append(f'  {c[0]}({", ".join(str(v) for v in c[1:])})')
    return '\n'.join(lines + ['end']) + '\n'


def model(cs):
    sc, out = zxgfx.Screen(glyphs=bytes(768)), []
    for c in cs:
        if c[0] == 'inp':
            out.append(f'{sc.inp(c[1])}\n')
        else:
            getattr(sc, c[0])(*c[1:])
    return ''.join(out), sc.shown_border


def machine(src, k):
    """build it, run it on a fresh 48K, and take what it printed and the border it left"""
    bly, tap = os.path.join(BUILD, f'u{k}.bly'), os.path.join(BUILD, f'u{k}.tap')
    open(bly, 'w').write(src)
    b = subprocess.run([sys.executable, '-I', ZXBUILD, bly, '-o', tap], capture_output=True, text=True)
    if b.returncode:
        return f'BUILD: {(b.stdout + b.stderr).strip()}', None
    zx = Speccy()
    zx.wait_ready()
    zx.load_tap(tap)
    for _ in range(40):
        if zx.wait_ready(max_frames=250) is not None:
            return transcript.answer(zx.printed()), zx.border
    return 'TIMEOUT', None


def main():
    ap = argparse.ArgumentParser(prog='ula_check.py', description=__doc__)
    ap.add_argument('n', metavar='N', type=int, nargs='?', default=40, help='how many programs (default 40)')
    ap.add_argument('seed', metavar='SEED', type=int, nargs='?', default=1, help='their seed (default 1)')
    a = ap.parse_args()
    rng = random.Random(a.seed)
    os.makedirs(BUILD, exist_ok=True)
    bad = 0
    for k in range(a.n):
        cs = calls(rng)
        src = program(rng, cs)
        got, want = machine(src, k), model(cs)
        if got != want:
            bad += 1
            print(f'FAIL program {k}: the 48K printed {got[0]!r} and left border {got[1]}; the model says {want[0]!r} '
                  f'and {want[1]}\n{src}')
    print(f'{a.n - bad} of {a.n} programs: the ports as omse-ai\'s 48K answers them')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
