"""Check the reference's text against the real ROM: random programs of prints (wrapping, scrolling, print at,
block graphics, UDGs, characters that print as ?) and colour changes (8 and 9 too), run in the interpreter and on
omse-ai's 48K;
the upper 22 rows of the screen must be identical. Run it with omse-ai's Python."""
import argparse
import os, random, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
import paths
paths.omse_ai()
from speccy import Speccy
HERE = os.path.dirname(os.path.abspath(__file__))
BARLEY = os.path.join(HERE, '..', '..', 'interp', 'barley.py')
ZXBUILD = os.path.join(HERE, '..', 'zxbuild.py')


def text(rng):
    out = []
    for _ in range(rng.randrange(0, 40)):
        k = rng.random()
        if k < 0.7:
            out.append(chr(rng.randrange(32, 127)).replace('"', 'q').replace('\\', '/'))
        elif k < 0.8:
            out.append(f'\\x{rng.randrange(0x80, 0x90):02X}')          # block graphics
        elif k < 0.9:
            out.append(f'\\x{rng.randrange(0x90, 0xA5):02X}')          # UDGs
        else:
            out.append(f'\\x{rng.choice([0x60, 0x7F, 0xA5, 0xC8, 0xFF, 0x01, 0x05, 0x10, 0x16]):02X}')
    return ''.join(out)


COLOURS = list(range(8)) + [8, 8, 9, 9, 9, 9]      # 8 and 9 often: they're where the rules are


def program(rng):
    lines = ['func main()', '  cls()']
    for _ in range(rng.randrange(5, 40)):
        k = rng.random()
        if k < 0.45:
            end = rng.choice(['', ';'])
            lines.append(f'  print "{text(rng)}"{end}')
        elif k < 0.6:
            lines.append(f'  print at {rng.randrange(22)}, {rng.randrange(32)}; "{text(rng)}"{rng.choice(["", ";"])}')
        elif k < 0.67:
            lines.append(f'  ink({rng.choice(COLOURS)})')                # 8: transparent, 9: contrast
        elif k < 0.72:
            lines.append(f'  paper({rng.choice(COLOURS)})')
        elif k < 0.76:
            lines.append(f'  {rng.choice(["bright", "flash"])}({rng.choice(["true", "false", "0", "1", "8", "8"])})')
        elif k < 0.79:                                                   # squares that differ, for masks to keep
            r, c = rng.randrange(22), rng.randrange(28)
            lines.append(f'  for c in {c}..{c + 5} do attr({r}, c, byte(c * 37 + {rng.randrange(256)})) end')
        elif k < 0.8:
            lines.append('  cls()')
        elif k < 0.85:
            lines.append(f'  inverse({rng.choice(["true", "false"])})')
        elif k < 0.9:
            lines.append(f'  over({rng.choice(["true", "false"])})')
        elif k < 0.95:
            lines.append(f'  print')
        else:
            lines.append(f'  print "{text(rng)}", "{text(rng)}"')
    lines.append('end')
    return '\n'.join(lines) + '\n'


def upper(i):
    if i >= 6144:
        return (i - 6144) // 32 < 22
    return (i >> 11) < 2 or ((i >> 5) & 7) < 6


def main():
    ap = argparse.ArgumentParser(prog='rom_text_check.py', description=__doc__)
    ap.add_argument('n', metavar='N', type=int, nargs='?', default=20, help='how many programs (default 20)')
    ap.add_argument('seed', metavar='SEED', type=int, nargs='?', default=1, help='their seed (default 1)')
    a = ap.parse_args()
    n = a.n
    rng = random.Random(a.seed)
    bad = 0
    with tempfile.TemporaryDirectory() as d:
        for k in range(n):
            src = program(rng)
            p = os.path.join(d, 't.bly')
            open(p, 'w').write(src)
            subprocess.run([sys.executable, '-I', BARLEY, '--screen', os.path.join(d, 't.png'), p],
                           capture_output=True, stdin=subprocess.DEVNULL)
            want = open(os.path.join(d, 't.scr'), 'rb').read()
            b = subprocess.run(['python3', '-I', ZXBUILD, p, '-o', os.path.join(d, 't.tap')], capture_output=True, text=True)
            if b.returncode:
                print('build failed:', b.stdout, b.stderr[-300:])
                bad += 1
                continue
            zx = Speccy()
            zx.wait_ready()
            zx.load_tap(os.path.join(d, 't.tap'))
            zx.wait_ready(max_frames=50 * 120)
            got = bytes(zx.read(0x4000, 6912))
            diff = [i for i in range(6912) if upper(i) and got[i] != want[i]]
            if diff:
                bad += 1
                keep = os.path.join(paths.build_dir('romtext'), f'romtext-{k}.bly')
                open(keep, 'w').write(src)
                print(f'program {k}: {len(diff)} bytes differ (kept as {keep})')
    print(f'{n - bad} of {n} screens identical to the ROM')
    return bad


sys.exit(1 if main() else 0)                            # a screen that differs fails ./check, not just its words
