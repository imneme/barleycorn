#!/usr/bin/env python3
"""Load a Barleycorn tape on omse-ai's 48K, let it run, and print what the
program printed (after LOAD's own lines). Run it with a Python that can import
omse-ai: paths.py's OMSE_AI_PYTHON.

It waits up to --minutes of Spectrum time (10 by default), counted in
T-states, which keep counting while a beep plays (the ROM's BEEPER turns
interrupts off, and with them the frame counter). A program still running then
is reported, with what it had printed so far, and the exit status is 2.

With --keys FILE it types FILE's keys as the program runs, a newline being
ENTER. Each goes into the editor when the program is waiting in ask(); if it
doesn't ask within half a second, the key is pressed and let go (for key() and
inkey()), and a few frames pass before the next. When the keys run out and the
program is waiting in ask(), it presses cursor down, which stops it, as the end
of the keys does in the interpreter and C.

A program that ends well leaves BASIC saying 0 OK, and the exit status is 0;
one that fails leaves it saying 9 STOP statement, and the exit status is 1, as
the interpreter's is. Any other report is the ROM's own error: it's printed,
and the exit status is 3.
"""
import argparse
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import paths                                            # noqa: E402
paths.omse_ai()
from speccy import Speccy                               # noqa: E402
import transcript                                       # noqa: E402


ap = argparse.ArgumentParser(prog='zxrun.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('tap', metavar='PROG.tap', help='the tape (zxbuild.py makes them)')
ap.add_argument('--scr', metavar='OUT.scr', help="save the 48K's screen at the end")
ap.add_argument('--minutes', type=float, default=10, metavar='N',
                help='give up after N minutes of Spectrum time (default 10)')
ap.add_argument('--keys', metavar='FILE', help='type these keys as the program runs (see above)')
a = ap.parse_args()
if not os.path.exists(a.tap):
    sys.exit(f'zxrun.py: {a.tap}: no such file')
minutes = a.minutes
zx = Speccy()
zx.wait_ready()
WAIT_KEY1, FLAGX = 0x15DE, 0x5C71                       # the editor's key wait; FLAGX bit 5: INPUT mode


def state(frames=1):
    """'ask' if the program is waiting in ask() (the editor, in INPUT mode), 'done' if it's back at BASIC's own
    editor, None if it's running (perhaps reading keys itself)"""
    if zx.run_until(WAIT_KEY1, frames=frames) is None:
        return None
    return 'ask' if zx.peek(FLAGX) & 0x20 else 'done'


def type_key(ch):
    """one key: into the editor if the program asks within half a second, else pressed and let go"""
    for _ in range(25):
        st = state()
        if st:
            break
    if st == 'done':
        return False
    if st == 'ask':
        zx.settle()                                     # the editor's mode is only true once the line's redrawn
        chords = ['ENTER'] if ch == '\n' else zx.kt.strokes_for(zx.kt.char_code(ch), zx)
    else:
        chords = ['ENTER'] if ch == '\n' else zx.kt._strokes_plain(zx.kt.char_code(ch), zx, 'L')
    for c in chords:
        names = zx.kt.chord(c)
        if st is None and len(names) > 1:               # a shift a frame early, as fingers do: pressed at once,
            zx.press(names[0])                          # a key scan already under way could find the letter
            zx.run(1)                                   # without it
        zx.keystroke(c)
    if st is None:
        zx.run(5)                                       # time to see it let go
    return True


zx.load_tap(a.tap)
t0 = zx.lib.zx_tstates(zx.z)
limit = int(minutes * 60 * zx.clock)
done = False
keys = list(open(a.keys, 'rb').read().decode('latin-1')) if a.keys else []
while keys and zx.lib.zx_tstates(zx.z) - t0 < limit:
    if not type_key(keys.pop(0)):
        break
while zx.lib.zx_tstates(zx.z) - t0 < limit:
    st = state(frames=250)
    if st == 'ask':                                     # the keys have run out: cursor down, STOP
        zx.keystroke('DOWN')
    elif st == 'done':                                  # back at BASIC's editor: the program has finished
        done = True
        break
if a.scr:                                               # the screen memory too, for comparing pictures
    open(a.scr, 'wb').write(bytes(zx.read(0x4000, 6912)))
sys.stdout.reconfigure(encoding='latin-1', errors='replace')    # each byte the program printed as that byte
sys.stdout.write(transcript.answer(zx.printed()))        # without the text printed at a place: that's the screen's
if not done:
    sys.stderr.write(f'\nzxrun: still running after {minutes:g} minutes of Spectrum time (--minutes N for longer)\n')
    sys.exit(2)
report = zx.report()
if report.startswith('9 STOP statement'):               # a failure: its words are the output's last line
    sys.exit(1)
if not report.startswith('0 OK'):                       # a program goes back to BASIC with RET (0 OK), or after a
    sys.stderr.write(f'\nzxrun: BASIC reported {report}\n')     # failure with RST 8 (9 STOP): any other is the ROM's
    sys.exit(3)
