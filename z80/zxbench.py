"""Exact T-states on omse-ai's 48K for a fixed set of Barley programs, from the program's first instruction to
bly_exit (interrupts on, as they always are: the ROM's IM 1 handler costs about 3%), and code bytes. Each program's
output is checked against the interpreter's. --save keeps bench/baseline.json; every run flags anything more than
0.5% slower or bigger than the baseline (phase one's lesson: one regression was caught only because a number was
remembered).
usage: zxbench.py [--save] [NAME...]          (with a Python that can import omse-ai: paths.py's OMSE_AI_PYTHON)"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
import paths
paths.omse_ai()
import zxbuild
from speccy import Speccy

INTERP = os.path.join(HERE, '..', 'interp', 'barley.py')
BASE = os.path.join(HERE, 'bench', 'baseline.json')


PROGRAMS = {n: (os.path.join(HERE, 'bench', n + '.bly'), lambda: b'') for n in
            ('fib', 'tak', 'ack', 'queens', 'sieve', 'bubble', 'qsort', 'tree', 'expr', 'life', 'crc', 'hanoi', 'perm')}
PROGRAMS['sing'] = (os.path.join(HERE, '..', 'examples', 'sing_d12.bly'),
                    lambda: open(os.path.join(HERE, '..', 'examples', 'hill.txt'), 'rb').read())


def interp(path, text):
    tmp = os.path.join(paths.build_dir('bench'), f'bench-in-{os.getpid()}.txt')
    open(tmp, 'wb').write(text)
    try:
        r = subprocess.run([sys.executable, '-I', INTERP, '--as', 'zx48', path, tmp], capture_output=True)
    finally:
        os.remove(tmp)
    return r.stdout.decode('latin-1')


def bench(name):
    path, inp = PROGRAMS[name]
    text = inp()
    tap, info = zxbuild.build(open(path).read(), text)
    zx = Speccy()
    zx.wait_ready()
    zx.insert_tape(tap)
    zx.type('LOAD ""')                # ENTER by hand, so the breakpoint is set before the loader runs
    zx.press('ENTER')
    hit = zx.run_until(info['org'], frames=50 * 60)
    zx.release('ENTER')
    if hit is None:
        return {'error': 'never started'}
    t0 = zx.lib.zx_tstates(zx.z)
    if zx.run_until(info['sym']['bly_exit'], frames=50 * 60 * 60) is None:
        return {'error': 'no exit within an hour'}
    t = zx.lib.zx_tstates(zx.z) - t0
    zx.wait_ready(max_frames=500)
    out = re.sub(r'\{AT \d+,\d+\}', '', zx.printed())
    mark = 'Bytes: program   \n'
    out = out[out.index(mark) + len(mark):] if mark in out else out
    want = interp(path, text)
    text_only = lambda s: re.sub(r'[^\x20-\x7e\n]', '', s).rstrip('\n')   # omse-ai shows block graphics as Unicode
    ok = text_only(out) == text_only(want)
    return {'T': t, 'code': info['code'], 'ok': bool(ok), 'out': out.strip()[:60] if not ok else ''}


def main(argv):
    save = '--save' in argv
    names = [a for a in argv if not a.startswith('--')] or list(PROGRAMS)
    base = json.load(open(BASE)) if os.path.exists(BASE) else {}
    res = dict(base) if save else {}
    for n in names:
        r = bench(n)
        b = base.get(n)
        note = ''
        if 'error' in r:
            note = r['error']
        else:
            if not r['ok']:
                note += f'  WRONG OUTPUT: {r["out"]!r}'
            if b:
                dt, dc = r['T'] / b['T'], r['code'] / b['code']
                note += f'  {dt:6.3f}x T  {dc:6.3f}x code' + ('  SLOWER' if dt > 1.005 else '') + \
                    ('  BIGGER' if dc > 1.005 else '')
            res[n] = {'T': r['T'], 'code': r['code']}
        print(f'{n:8} {r.get("T", 0):>14,} T  {r.get("code", 0):>6} bytes{note}', flush=True)
    if save:
        json.dump(res, open(BASE, 'w'), indent=1, sort_keys=True)
        print('saved', BASE)


if __name__ == '__main__':
    main(sys.argv[1:])
