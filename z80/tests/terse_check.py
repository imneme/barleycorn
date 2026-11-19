#!/usr/bin/env python3
"""--terse against the ordinary build, on every program in the suite's semantics.txt: built both ways for CP/M (or,
with --zx, for the 48K) and run. A program that doesn't fail must print exactly the same both ways. One that does
must, in the terse build, print what the ordinary one printed before its failure (the start of its output) and then
only the terse ending: "?" and a newline on CP/M, "C Nonsense in BASIC" for BASIC's report on the 48K. And the terse
build must keep no line for a failure (no ld (bly_line),hl but the program's own two). Speccy-Zone Fern, 19 Nov 2026.

    terse_check.py [--zx] [TEXT]    TEXT: only the cases whose names contain it
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..')
sys.path.insert(0, ROOT)
import paths                                    # noqa: E402

Z80GEN = os.path.join(HERE, '..', 'z80gen.py')
ZXBUILD = os.path.join(HERE, '..', 'zxbuild.py')
ZXRUN = os.path.join(HERE, '..', 'zxrun.py')
SEMANTICS = os.path.join(ROOT, 'interp', 'tests', 'semantics.txt')
FAILED = re.compile(r' at line \d+( of \S+)?\n*$')     # an ordinary build's failure ends its words like this


def cases(only=''):
    """(name, program, input text or None) of every semantics case that types no keys"""
    out = []
    for c in open(SEMANTICS).read().split('\n=== ')[1:]:
        name, rest = c.split('\n', 1)
        prog = rest.split('\n--- expect\n')[0]
        if '\n--- keys' in prog or only not in name:
            continue
        prog = prog.replace('\n--- screen', '').replace('\n--- as cpm', '')
        text = None
        if '\n--- input\n' in prog:
            prog, text = prog.split('\n--- input\n')
            text += '\n'
        out.append((name, prog, text))
    return out


def cpm(d, prog, text, terse):
    """what the .COM prints under tnylpo, or None if it isn't for CP/M (or not built: the suite says why)"""
    src = os.path.join(d, 'p.bly')
    open(src, 'w').write(prog)
    g = subprocess.run([sys.executable, '-I', Z80GEN, src] + (['--terse'] if terse else []), capture_output=True,
                       text=True, encoding='latin-1')
    if g.returncode:
        return None, None
    asm = os.path.join(d, 'p.asm')
    open(asm, 'w').write(g.stdout)
    a = subprocess.run([paths.SJASMPLUS, '--nologo', f'--raw={os.path.join(d, "p.com")}', asm], capture_output=True,
                       text=True)
    if a.returncode:
        return 'ASSEMBLER: ' + a.stdout[-300:], g.stdout
    conf = os.path.join(d, 'tn.conf')
    open(conf, 'w').write(f'drive a = "{d}"\ndefault drive = a\n')
    args = []
    if text is not None:
        open(os.path.join(d, 'input.txt'), 'w').write(text)
        args = ['input.txt']
    try:
        r = subprocess.run([paths.TNYLPO, '-f', conf, 'p'] + args, capture_output=True, text=True,
                           encoding='latin-1', timeout=120)
    except subprocess.TimeoutExpired:
        return 'TIMEOUT', g.stdout
    return r.stdout, g.stdout


def zx(d, prog, text, terse):
    src = os.path.join(d, 'p.bly')
    open(src, 'w').write(prog)
    inp = []
    if text is not None:
        open(os.path.join(d, 'p.txt'), 'w').write(text)
        inp = [os.path.join(d, 'p.txt')]
    tap = os.path.join(d, 'p.tap')
    b = subprocess.run([sys.executable, '-I', ZXBUILD, src] + inp + ['-o', tap] + (['--terse'] if terse else []),
                       capture_output=True, text=True, encoding='latin-1')
    if b.returncode:
        return None, None
    paths.omse_ai()
    try:
        r = subprocess.run([paths.OMSE_AI_PYTHON, ZXRUN, tap], capture_output=True, text=True, encoding='latin-1',
                           timeout=600)
    except subprocess.TimeoutExpired:
        return 'TIMEOUT', None
    # zxrun's exit: 0 for 0 OK, 1 for a failure (9 STOP statement), 3 for any other report, which it names
    end = {0: 'OK', 1: 'STOP'}.get(r.returncode, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else '?')
    return r.stdout + f'\nEND: {end}', None


def judge(plain, terse, on_zx):
    """'' if the terse output is right against the ordinary one, else why not"""
    if on_zx:
        p_text, _, p_end = plain.rpartition('\nEND: ')
        t_text, _, t_end = terse.rpartition('\nEND: ')
        if p_end != 'STOP':
            return '' if terse == plain else 'it doesn\'t fail, but the terse build prints something else'
        if 'C Nonsense in BASIC' not in t_end:
            return f'it fails, but the terse build ends {t_end!r}, not with C Nonsense in BASIC'
        if not p_text.startswith(t_text):
            return 'the terse build printed something the ordinary one didn\'t, before its failure'
        return ''
    if not FAILED.search(plain):
        return '' if terse == plain else 'it doesn\'t fail, but the terse build prints something else'
    if not terse.endswith('?\n'):
        return f'it fails, but the terse build ends {terse[-20:]!r}, not with "?"'
    if not plain.startswith(terse[:-2]):
        return 'the terse build printed something the ordinary one didn\'t, before its failure'
    return ''


def main():
    ap = argparse.ArgumentParser(prog='terse_check.py', description=__doc__.split('\n\n')[0])
    ap.add_argument('--zx', action='store_true', help="on omse-ai's 48K, not CP/M")
    ap.add_argument('only', metavar='TEXT', nargs='?', default='', help='only the cases whose names contain TEXT')
    a = ap.parse_args()
    run = zx if a.zx else cpm
    bad = failing = done = 0
    d = tempfile.mkdtemp(prefix='terse-', dir=paths.build_dir('terse'))
    try:
        for name, prog, text in cases(a.only):
            plain, _ = run(d, prog, text, False)
            if plain is None:
                continue                                # not for this machine, or refused: the suite's business
            terse, asm = run(d, prog, text, True)
            done += 1
            why = judge(plain, terse or '', a.zx)
            if asm is not None and len(re.findall(r'ld \(bly_line\),hl', asm)) > 2:
                why = why or 'the terse build still keeps a line for a failure'
            failing += bool(FAILED.search(plain) if not a.zx else plain.endswith('END: STOP'))
            if why:
                bad += 1
                print(f'WRONG {name}: {why}\n  ordinary: {plain[-160:]!r}\n  terse:    {(terse or "")[-160:]!r}')
    finally:
        shutil.rmtree(d, ignore_errors=True)
    print(f'terse ({"48K" if a.zx else "CP/M"}): {done - bad} of {done} programs right, {failing} of them failing '
          f'ones' + (f'; {bad} wrong' if bad else ''))
    return 1 if bad or not done else 0


if __name__ == '__main__':
    sys.exit(main())
