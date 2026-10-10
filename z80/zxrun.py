#!/usr/bin/env python3
"""Load a Barley tape on omse-ai's 48K, let it run, and print what the program printed (after LOAD's own lines).
usage: zxrun.py PROG.tap [--scr out.scr]        (with a Python that can import omse-ai: paths.py's OMSE_AI_PYTHON)"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import paths                                            # noqa: E402
paths.omse_ai()
from speccy import Speccy                               # noqa: E402

zx = Speccy()
zx.wait_ready()
zx.load_tap(sys.argv[1])
zx.wait_ready(max_frames=50 * 60 * 10)                 # ten minutes of Spectrum time, at most
out = zx.printed()
if '--scr' in sys.argv:                                 # the screen memory too, for comparing pictures
    open(sys.argv[sys.argv.index('--scr') + 1], 'wb').write(bytes(zx.read(0x4000, 6912)))
import re
out = re.sub(r'\{AT \d+,\d+\}', '', out)               # omse-ai shows print at's control codes; they aren't text
mark = 'Bytes: program   \n'
sys.stdout.write(out[out.index(mark) + len(mark):] if mark in out else 'LOADER: ' + out)
