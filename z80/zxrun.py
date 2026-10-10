#!/usr/bin/env python3
"""Load a Barleycorn tape on omse-ai's 48K, let it run, and print what the program printed (after LOAD's own lines).
usage: zxrun.py PROG.tap [--scr out.scr] [--minutes N]    (with a Python that can import omse-ai: paths.py's
OMSE_AI_PYTHON)

It waits up to --minutes of Spectrum time (10 by default), counted in T-states, which keep counting while a beep
plays (the ROM's BEEPER turns interrupts off, and with them the frame counter). A program still running then is
reported, with what it had printed so far, and the exit status is 2."""
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import paths                                            # noqa: E402
paths.omse_ai()
from speccy import Speccy                               # noqa: E402


def arg(flag, default):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


minutes = float(arg('--minutes', 10))
zx = Speccy()
zx.wait_ready()
zx.load_tap(sys.argv[1])
t0 = zx.lib.zx_tstates(zx.z)
limit = int(minutes * 60 * zx.clock)
done = False
while zx.lib.zx_tstates(zx.z) - t0 < limit:
    if zx.wait_ready(max_frames=250) is not None:       # back at BASIC's editor: the program has finished
        done = True
        break
out = zx.printed()
if '--scr' in sys.argv:                                 # the screen memory too, for comparing pictures
    open(arg('--scr', None), 'wb').write(bytes(zx.read(0x4000, 6912)))
out = re.sub(r'\{AT \d+,\d+\}', '', out)               # omse-ai shows print at's control codes; they aren't text
mark = 'Bytes: program   \n'
sys.stdout.write(out[out.index(mark) + len(mark):] if mark in out else 'LOADER: ' + out)
if not done:
    sys.stderr.write(f'\nzxrun: still running after {minutes:g} minutes of Spectrum time (--minutes N for longer)\n')
    sys.exit(2)
