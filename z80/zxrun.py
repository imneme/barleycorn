#!/usr/bin/env python3
"""Load a Barleycorn tape on omse-ai's 48K, let it run, and print what the
program printed (after LOAD's own lines). Run it with a Python that can import
omse-ai: paths.py's OMSE_AI_PYTHON.

It waits up to --minutes of Spectrum time (10 by default), counted in
T-states, which keep counting while a beep plays (the ROM's BEEPER turns
interrupts off, and with them the frame counter). A program still running then
is reported, with what it had printed so far, and the exit status is 2.
"""
import argparse
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import paths                                            # noqa: E402
paths.omse_ai()
from speccy import Speccy                               # noqa: E402


ap = argparse.ArgumentParser(prog='zxrun.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('tap', metavar='PROG.tap', help='the tape (zxbuild.py makes them)')
ap.add_argument('--scr', metavar='OUT.scr', help="save the 48K's screen at the end")
ap.add_argument('--minutes', type=float, default=10, metavar='N',
                help='give up after N minutes of Spectrum time (default 10)')
a = ap.parse_args()
if not os.path.exists(a.tap):
    sys.exit(f'zxrun.py: {a.tap}: no such file')
minutes = a.minutes
zx = Speccy()
zx.wait_ready()
zx.load_tap(a.tap)
t0 = zx.lib.zx_tstates(zx.z)
limit = int(minutes * 60 * zx.clock)
done = False
while zx.lib.zx_tstates(zx.z) - t0 < limit:
    if zx.wait_ready(max_frames=250) is not None:       # back at BASIC's editor: the program has finished
        done = True
        break
out = zx.printed()
if a.scr:                                               # the screen memory too, for comparing pictures
    open(a.scr, 'wb').write(bytes(zx.read(0x4000, 6912)))
out = re.sub(r'\{AT \d+,\d+\}', '', out)               # omse-ai shows print at's control codes; they aren't text
mark = 'Bytes: program   \n'
sys.stdout.write(out[out.index(mark) + len(mark):] if mark in out else 'LOADER: ' + out)
if not done:
    sys.stderr.write(f'\nzxrun: still running after {minutes:g} minutes of Spectrum time (--minutes N for longer)\n')
    sys.exit(2)
