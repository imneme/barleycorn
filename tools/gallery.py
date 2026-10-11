#!/usr/bin/env python3
"""A gallery of everything in the distribution: each program in examples/ and
examples/small/ run three ways (the interpreter, C, and the 48K on omse-ai),
timed by the wall clock, with the screen it ends on kept as a picture. Out
comes a folder that is a static web page (index.html and the pictures),
to look through, or to put on a site as it is.

Each program gets its input file (its "-- input:" line, or NAME.txt beside
it) and the keys its "-- keys:" lines type. A run that's still going after
--timeout seconds is stopped and shown as such.
"""
import argparse
import html
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import check_small                                         # noqa: E402  (shape: an example's keys and input)

BLY = os.path.join(ROOT, 'bly')
INPUTS = {'sing_d12.bly': 'hill.txt'}             # inputs not named after their program (examples/README.md)


def programs(only):
    found = sorted(os.path.join(ROOT, 'examples', n) for n in os.listdir(os.path.join(ROOT, 'examples'))
                   if n.endswith('.bly'))
    small = os.path.join(ROOT, 'examples', 'small')
    found += sorted(os.path.join(small, n) for n in os.listdir(small) if n.endswith('.bly'))
    return [p for p in found if not only or only in os.path.basename(p)]


def what(path):
    """(its first line, the keys it types, its input file or None)"""
    first = open(path).readline().strip().lstrip('-').strip()
    _, _, keys, inp, _ = check_small.shape(path)
    if not inp:
        side = os.path.join(os.path.dirname(path), INPUTS.get(os.path.basename(path), ''))
        if not INPUTS.get(os.path.basename(path)):
            side = os.path.splitext(path)[0] + '.txt'
        inp = [side] if os.path.exists(side) else []
    return first, keys, inp


def run(cmd, keys, timeout, env=None):
    """(seconds, the exit code or None if stopped, the output's last lines, what it printed)"""
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, input=keys, capture_output=True, text=True, encoding='latin-1', timeout=timeout,
                           env=env, cwd=ROOT)
        return time.monotonic() - t0, p.returncode, (p.stdout + p.stderr).strip().splitlines()[-3:], p.stdout
    except subprocess.TimeoutExpired:
        return time.monotonic() - t0, None, ['(stopped after the time allowed)'], ''


def blank(scr):
    """True if a .scr has no pixel set: C prints to the terminal when a program never draws"""
    return os.path.exists(scr) and not any(open(scr, 'rb').read()[:6144])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'gallery'), help='the folder (default build/gallery)')
    ap.add_argument('--only', metavar='TEXT', help='just the programs whose names contain TEXT')
    ap.add_argument('--timeout', type=int, default=600, help='seconds a run may take (default 600)')
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    rows = []
    for path in programs(a.only):
        name = os.path.splitext(os.path.relpath(path, os.path.join(ROOT, 'examples')))[0].replace(os.sep, '-')
        first, keys, inp = what(path)
        cells = []
        for way in ('interpreter', 'C', '48K'):
            png = os.path.join(a.out, f'{name}-{way}.png')
            if os.path.exists(png):
                os.remove(png)
            text = None
            if way == 'interpreter':
                secs, code, tail, _ = run([BLY, 'run', '--screen', png, path] + inp, keys, a.timeout)
            elif way == 'C':
                scr = os.path.join(a.out, f'{name}-C.scr')
                env = dict(os.environ, BARLEY_SCREEN=scr)
                secs, code, tail, out = run([BLY, 'c', path] + inp, keys, a.timeout, env)
                if blank(scr) and out.strip():          # it printed instead: show that, as the terminal had it
                    text = out
            else:
                secs, code, tail, _ = run([BLY, 'zx', '--scr', png, path] + inp, keys, a.timeout)
            cells.append((way, os.path.basename(png) if os.path.exists(png) else None, secs, code, tail, text))
            print(f'{name:28} {way:11} {secs:8.1f} s  ' + ('stopped' if code is None else f'exit {code}'), flush=True)
        rows.append((name, first, inp, cells))
        write(a.out, rows)
    print(f'{len(rows)} programs: {os.path.join(a.out, "index.html")}')


def write(out, rows):
    esc = html.escape
    parts = ['<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
             '<title>Barleycorn gallery</title><style>',
             'body{background:#14110f;color:#e8e0d4;font:15px/1.4 Georgia,serif;margin:0 16px}',
             'h1{font-weight:normal}section{margin:28px 0;border-top:1px solid #3a332c;padding-top:12px}',
             '.row{display:flex;flex-wrap:wrap;gap:12px}figure{margin:0;max-width:100%}',
             'img{width:320px;max-width:100%;image-rendering:pixelated;display:block}',
             'figcaption{font-size:13px;color:#b8ad9c}code{color:#f0c674}',
             'pre{width:320px;max-width:100%;height:256px;overflow:auto;margin:0;box-sizing:border-box;padding:8px;',
             'background:#000;color:#d7d7d7;font:12px/1.3 Menlo,monospace;white-space:pre-wrap}</style>',
             '<h1>Barleycorn: everything it draws</h1>',
             '<p>Each program in the distribution, run three ways: the interpreter, C, and the 48K (on '
             'omse-ai). The pictures are the screens they end on; the times are the wall clock\'s. C prints to '
             'the terminal when a program never draws, so for those it\'s the terminal that\'s shown.</p>']
    for name, first, inp, cells in rows:
        parts.append(f'<section><h2><code>{esc(name)}</code></h2><p>{esc(first)}</p><div class="row">')
        for way, png, secs, code, tail, text in cells:
            state = 'stopped' if code is None else ('ok' if code == 0 else f'exit {code}')
            img = f'<img src="{esc(png)}" alt="{esc(name)}, {way}">' if png else '<p>(no picture)</p>'
            if text is not None:
                img = f'<pre>{esc(text)}</pre>'
                state += ', printed to the terminal'
            parts.append(f'<figure>{img}<figcaption>{way}: {secs:.1f} s, {state}'
                         + (f'<br>{esc(tail[-1])}' if code not in (0, None) and tail else '') + '</figcaption></figure>')
        parts.append('</div></section>')
    open(os.path.join(out, 'index.html'), 'w').write('\n'.join(parts) + '\n')


if __name__ == '__main__':
    main()
