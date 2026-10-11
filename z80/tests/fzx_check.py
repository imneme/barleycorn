"""Check print #4 (FZX text) against the machine, two ways, with Barleycorn's own test font (interp/tests/sprig.fzx)
and any in FZX_FONTS (paths.py; fonts aren't ours to ship, so they're optional).

The stock driver: if FZX_DRIVER names Einar Saukas's FZXdriver.asm, it's assembled at 65000, the font put at
60000, the channel made with RANDOMIZE USR 65000, then random PRINT #4 lines (AT, text, ') typed into BASIC on
omse-ai's 48K and ended with PAUSE 0. zxgfx.Screen draws the same, and the screens' pixels must agree. This holds
the model to the driver it follows. Lines the model says would go below the screen are left out (the driver
reports an error there, as Barley fails), and a font with stray bits past a character's width can differ at the
right edge, where Barley's adaptation writes nothing (the stock driver puts them on the next row's left).

Our own: random Barley programs that embed the font and print #4 (at, text with characters the font hasn't got,
newlines, numbers), built for the 48K and run there, against the interpreter: the output, a failure's words
included, and the upper 22 rows of the screen. Run it with omse-ai's Python."""
import argparse
import glob
import os
import random
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(HERE, '..'))
import paths                                    # noqa: E402
paths.omse_ai()
from speccy import Speccy                       # noqa: E402
import transcript                               # noqa: E402
import zxgfx                                    # noqa: E402

BUILD = os.path.join(paths.BUILD, 'fzx_check', str(os.getpid()))
ZXBUILD = os.path.join(HERE, '..', 'zxbuild.py')
BARLEY = os.path.join(ROOT, 'interp', 'barley.py')
TEXT = ''.join(chr(c) for c in range(32, 127) if c != ord('"'))
SPRIG = os.path.join(ROOT, 'interp', 'tests', 'sprig.fzx')


def fonts():
    out = [SPRIG]
    if paths.FZX_FONTS and os.path.isdir(paths.FZX_FONTS):
        out += sorted(glob.glob(os.path.join(paths.FZX_FONTS, '*.fzx')))
    return [(os.path.basename(p), open(p, 'rb').read()) for p in out]


def pieces(rng, n):
    """a print #4's items: ('at', (y, x)), ('text', s), ('nl', None)"""
    out = []
    for _ in range(n):
        k = rng.choice(['text', 'text', 'text', 'at', 'nl'])
        if k == 'at':
            out.append(('at', (rng.choice([rng.randrange(192), rng.randrange(150, 192)]),
                               rng.choice([rng.randrange(256), rng.randrange(225, 256)]))))
        elif k == 'text':
            out.append(('text', ''.join(rng.choice(TEXT) for _ in range(rng.randrange(1, 20)))))
        else:
            out.append(('nl', None))
    return out


def model(font, items, sc=None):
    """the model's screen after these items, or None if it says one would go below the screen"""
    sc = sc or zxgfx.Screen(bytes(768))
    sc.fzx(font)
    try:
        for k, v in items:
            if k == 'at':
                sc.fzx_at(*v)
            elif k == 'text':
                for ch in v.encode('latin-1'):
                    sc.fzx_out(ch)
            else:
                sc.fzx_out(10)
    except zxgfx.ScreenError:
        return None
    return sc


def stock(driver, font, items):
    """the stock driver's screen, through BASIC"""
    line = 'CLS: PRINT #4'
    for k, v in items:
        line += {'at': lambda: f';AT {v[0]},{v[1]}', 'text': lambda: f';"{v}"', 'nl': lambda: "'"}[k]()
    zx = Speccy()
    zx.wait_ready()
    zx.write(65000, driver)
    zx.write(60000, font)
    zx.type('RANDOMIZE USR 65000\n')
    zx.wait_ready()
    zx.type(line + ';: PAUSE 0\n')
    if zx.wait_ready(pause=True, max_frames=600) is None:
        return None, line
    return bytes(zx.read(0x4000, 6144)), line


def ours(name, font, items, k):
    """a Barley program printing the same, on the 48K and in the interpreter: (output, upper screen) each"""
    d = os.path.join(BUILD, f'p{k}')
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, 'f.fzx'), 'wb').write(font)
    lines = ['const F = @embed("f.fzx")', '', 'func main()', '  cls()', '  fzx(F)', '  print "before"']
    for kind, v in items:
        if kind == 'at':
            lines.append(f'  print #4; at {v[0]}, {v[1]};')
        elif kind == 'text':
            body = v.replace('\\', '\\\\') + ('\\x01' if k % 3 == 0 else '') + ('\\xc8' if k % 4 == 0 else '')
            lines.append(f'  print #4; "{body}"; {k};')
        else:
            lines.append('  print #4')
    lines += ['  print "after"', 'end']
    src = os.path.join(d, 'p.bly')
    open(src, 'w').write('\n'.join(lines) + '\n')
    scr_i = os.path.join(d, 'i.scr')
    i = subprocess.run([sys.executable, '-I', BARLEY, '--screen', os.path.join(d, 'i.png'), src],
                       capture_output=True, text=True, encoding='latin-1', stdin=subprocess.DEVNULL)
    tap = os.path.join(d, 'p.tap')
    b = subprocess.run([sys.executable, '-I', ZXBUILD, src, '-o', tap], capture_output=True, text=True)
    if b.returncode:
        return (i.stdout, None), (f'BUILD: {(b.stdout + b.stderr).strip()}', None), lines
    zx = Speccy()
    zx.wait_ready()
    zx.load_tap(tap)
    for _ in range(40):
        if zx.wait_ready(max_frames=250) is not None:
            break
    failed = 'after' not in i.stdout                 # a failure's words are on both screens, as the 48K shows them
    seen = lambda a: ((a - 6144) // 32 if a >= 6144 else ((a >> 8) & 0x18) | ((a >> 5) & 7)) < 22
    upper = lambda m: bytes(m[a] for a in range(6912) if seen(a))
    out = transcript.answer(zx.printed())
    if not zx.report().startswith('9 STOP statement' if failed else '0 OK'):    # a failure inside the driver must
        out += f'\nREPORT: {zx.report()}'             # still go back to BASIC as any failure does
    return (i.stdout, upper(open(scr_i, 'rb').read())), (out, upper(bytes(zx.read(0x4000, 6912)))), lines


def main():
    ap = argparse.ArgumentParser(prog='fzx_check.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('n', metavar='N', type=int, nargs='?', default=6, help='runs of each, for each font (default 6)')
    ap.add_argument('seed', metavar='SEED', type=int, nargs='?', default=1, help='their seed (default 1)')
    a = ap.parse_args()
    rng = random.Random(a.seed)
    os.makedirs(BUILD, exist_ok=True)
    bad = runs = 0
    driver = None
    if paths.FZX_DRIVER and os.path.exists(paths.FZX_DRIVER):
        out = os.path.join(BUILD, 'driver.bin')
        r = subprocess.run([paths.SJASMPLUS, '--nologo', f'--raw={out}', paths.FZX_DRIVER], capture_output=True,
                           text=True, cwd=BUILD)
        driver = open(out, 'rb').read() if r.returncode == 0 else None
        if driver is None:
            print(f'the stock driver didn\'t assemble: {r.stdout.strip()[-300:]}')
            bad += 1
    else:
        print('no FZX_DRIVER (paths.py): the stock driver is left out')
    for name, font in fonts():
        for k in range(a.n):
            if driver:                                # the stock driver, through BASIC
                items = []
                for item in pieces(rng, rng.randrange(1, 6)):
                    if model(font, items + [item]) is not None:
                        items.append(item)
                want = model(font, items)
                got, line = stock(driver, font, items)
                runs += 1
                if got != bytes(want.mem[:6144]):
                    bad += 1
                    where = 'BASIC never reached PAUSE 0' if got is None else \
                        f'first at {0x4000 + next(i for i in range(6144) if got[i] != want.mem[i]):04X}h'
                    print(f'FAIL {name}, the stock driver: {where}: {line}')
            items = pieces(rng, rng.randrange(1, 6))      # ours: failing is allowed, and compared
            want, got, lines = ours(name, font, items, k)
            runs += 1
            if want != got:
                bad += 1
                what = 'the output' if want[0] != got[0] else 'the screen'
                print(f'FAIL {name}, ours on the 48K: {what} differs ({got[0]!r} against {want[0]!r})\n  ' +
                      '\n  '.join(lines))
    print(f'{runs - bad} of {runs} runs: print #4 as the FZX driver draws it')
    shutil.rmtree(BUILD, ignore_errors=True)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
