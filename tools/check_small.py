#!/usr/bin/env python3
"""Hold each small example (examples/small) to what it says it does.

An example's first line is "-- " and the one construct it shows, in a
sentence, ending " [zx]" if it's the Spectrum's alone. At its end, after
"-- prints:", is what it prints, a line each as "-- > text" ("-- >" for an
empty line). Before that, it may have "-- keys:" and the lines typed, as
"-- < text", and "-- input: NAME.txt", the input file beside it.

For each one this runs it in the interpreter, typing the keys, and wants
exactly the prints block, with no line of it ending in a space (an editor
would take the space away); then `bly all`, which wants the interpreter, C,
CP/M (unless it's [zx]) and the 48K to print the same, and the 48K's screen
to be the interpreter's. A [zx] example has NAME.png beside it, and any
NAME.png must be the picture `bly run --screen NAME.png NAME.bly` makes.
A font beside an example (sprig.fzx) must be the tests' own copy.
"""
import argparse
import concurrent.futures
import glob
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLY = os.path.join(ROOT, 'bly')
SMALL = os.path.join(ROOT, 'examples', 'small')


def shape(path):
    """what the example says of itself: (problems, zx, keys, input file, the lines it prints)"""
    lines = open(path).read().split('\n')
    problems, keys, want, inp, block = [], [], [], [], None
    if not (lines[0].startswith('-- ') and len(lines[0]) > 3):
        problems.append('line 1 should be "-- " and the construct it shows, in a sentence')
    zx = lines[0].endswith(' [zx]')
    for l in lines[1:]:
        if l == '-- keys:':
            block = 'keys'
        elif l == '-- prints:':
            block = 'prints'
        elif l.startswith('-- input: '):
            inp = [os.path.join(os.path.dirname(path), l[len('-- input: '):].strip())]
            if not os.path.exists(inp[0]):
                problems.append(f'its input, {inp[0]}, isn\'t there')
            block = None
        elif block == 'keys' and l.startswith('-- <'):
            keys.append(l[5:] if l.startswith('-- < ') else '')
        elif block == 'prints' and l.startswith('-- >'):
            want.append(l[5:] if l.startswith('-- > ') else '')
        elif block == 'prints' and l.strip():
            problems.append(f'after "-- prints:", a line that isn\'t "-- > ...": {l!r}')
        elif l.strip():
            block = None
    return problems, zx, ''.join(k + '\n' for k in keys), inp, want


def check(path):
    name = os.path.relpath(path, ROOT)
    problems, zx, typed, inp, want = shape(path)
    stem = os.path.splitext(path)[0]
    run = lambda *args: subprocess.run([sys.executable, BLY] + list(args), input=typed.encode('latin-1'),
                                       capture_output=True, timeout=1200)
    r = run('run', path, *inp)
    got = r.stdout.decode('latin-1').split('\n')
    if got[-1] == '':
        got.pop()
    if got != want:
        first = next((i for i in range(max(len(got), len(want)))
                      if i >= len(got) or i >= len(want) or got[i] != want[i]), 0)
        problems.append(f'it prints {got[first] if first < len(got) else "(no more)"!r} where its prints block says '
                        f'{want[first] if first < len(want) else "(no more)"!r} (line {first + 1})')
    for i, l in enumerate(got):
        if l.endswith(' '):
            problems.append(f'line {i + 1} of what it prints ends in a space, which a "-- > " line can\'t keep')
            break
    a = run('all', path, *inp)
    if a.returncode:
        verdicts = [l.strip() for l in a.stdout.decode('latin-1').split('\n')
                    if l.startswith('  ') and ('DIFFERENT' in l or 'differ' in l or 'nothing ran' in l)]
        problems.append('bly all: ' + ('; '.join(verdicts) or f'exit {a.returncode}'))
    png = stem + '.png'
    if zx and not os.path.exists(png):
        problems.append(f'a [zx] example has its picture beside it: bly run --screen {os.path.basename(png)} '
                        f'{os.path.basename(path)}')
    if os.path.exists(png):
        with tempfile.TemporaryDirectory() as d:
            fresh = os.path.join(d, 'fresh.png')
            run('run', '--screen', fresh, path, *inp)
            if not os.path.exists(fresh) or open(fresh, 'rb').read() != open(png, 'rb').read():
                problems.append(f'{os.path.basename(png)} isn\'t the picture it makes now: bly run --screen '
                                f'{os.path.basename(png)} {os.path.basename(path)}')
    return name, zx, problems


def main():
    ap = argparse.ArgumentParser(prog='check_small.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('examples', nargs='*', metavar='NAME.bly', help='these (default: all of examples/small)')
    ap.add_argument('-j', type=int, default=4, metavar='N', help='how many at once (default 4)')
    a = ap.parse_args()
    paths = a.examples or sorted(glob.glob(os.path.join(SMALL, '*.bly')))
    bad, fonts_bad = 0, False
    with concurrent.futures.ThreadPoolExecutor(a.j) as pool:
        for name, zx, problems in pool.map(check, paths):
            print(f'{"ok  " if not problems else "FAIL"} {name}' + (' [zx]' if zx else ''))
            for p in problems:
                print(f'       {p}')
            bad += bool(problems)
    for font in sorted(glob.glob(os.path.join(SMALL, '*.fzx'))):        # a font travels beside its example,
        theirs = os.path.join(ROOT, 'interp', 'tests', os.path.basename(font))     # and is the tests' own
        if not os.path.exists(theirs) or open(font, 'rb').read() != open(theirs, 'rb').read():
            print(f'FAIL {os.path.relpath(font, ROOT)} isn\'t the tests\' {os.path.basename(font)}')
            fonts_bad = True
    print(f'{len(paths) - bad} of {len(paths)} small examples are what they say')
    return 1 if bad or fonts_bad else 0


if __name__ == '__main__':
    sys.exit(main())
