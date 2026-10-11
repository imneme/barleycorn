#!/usr/bin/env python3
"""RUN runs it again, the same: every example in examples/ and examples/small/,
loaded from its tape on omse-ai's 48K, run to the end, then run again by
typing RUN (line 10 of the loader, Melissa's idea: no reloading). The second
run must end with the same report, print the same text, and leave the same
screen (the upper 22 rows, pixels and colours) as the first. The loader's
line 10 puts the colours back as a 48K starts them, so what the first run
left behind can't leak into the second. Programs that read the keyboard are
left out (their keys would have to be typed twice).

Run it with omse-ai's Python (paths.py's OMSE_AI_PYTHON).
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ap = argparse.ArgumentParser(prog='rerun_check.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('only', metavar='TEXT', nargs='?', help='just the examples whose names contain TEXT')
a = ap.parse_args()
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'z80'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import paths                                            # noqa: E402
paths.omse_ai()
from speccy import Speccy                               # noqa: E402
import gallery                                          # noqa: E402  (which examples, their inputs and keys)
import zxbuild                                          # noqa: E402


def until_done(zx):
    """BASIC's report once the program is back at the editor (a report has a line and statement: 0 OK, 2026:10)"""
    for _ in range(2400):                               # 40 minutes of Spectrum time at most
        zx.run(frames=50)
        r = zx.report()
        if ',' in r and ':' in r:
            return r
    return '(still running)'


same, differ, left = 0, [], []
for path in gallery.programs(a.only):
    name = os.path.relpath(path, ROOT)
    _, keys, inp = gallery.what(path)
    if keys:
        left.append(name)
        continue
    zxbuild.z80gen.B.EMBED_DIR = os.path.dirname(path)
    tap, _ = zxbuild.build(open(path).read(), open(inp[0], 'rb').read() if inp else b'')
    zx = Speccy()
    zx.wait_ready()
    zx.insert_tape(tap)
    zx.type('LOAD ""\n')
    r1 = until_done(zx)
    whole = zx.printed()
    t1 = whole.split('Bytes: program   \n', 1)[-1]     # what the program printed, without the tape's messages
    s1 = bytes(zx.read(0x4000, 6144 + 704))
    zx.type('RUN\n')
    r2 = until_done(zx)
    t2 = zx.printed()[len(whole):]
    s2 = bytes(zx.read(0x4000, 6144 + 704))
    bad = [w for w, ok in (('the report', r1 == r2), ('the text', t1 == t2), ('the screen', s1 == s2)) if not ok]
    if bad:
        differ.append(name)
        print(f'DIFFERENT {name}: {", ".join(bad)} (reports {r1!r} and {r2!r})', flush=True)
    else:
        same += 1
print(f'{same} example{"s" if same != 1 else ""} run again by RUN the same, {len(differ)} not; '
      f'left out, as they read keys: {", ".join(os.path.basename(n) for n in left) or "none"}')
sys.exit(1 if differ else 0)
