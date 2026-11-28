#!/usr/bin/env python3
"""Operand homes (z80/homes.py) and RUN: a variable whose home is an instruction's operand lives in the code, which
RUN again doesn't reload, so the homes of globals that rely on starting at zero are zeroed at every start, as the
slots are. Three programs on omse-ai's 48K, each run, then run again by typing RUN: a global with no value counted
up, one read through a function so its home is elsewhere, and a global with a value. Each run must print the same.
Without the zeroing, the second run of the first two would carry on from the first's count.

Run it with omse-ai's Python (paths.py's OMSE_AI_PYTHON).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'z80'))
import paths                                            # noqa: E402
paths.omse_ai()
from speccy import Speccy                               # noqa: E402
import zxbuild                                          # noqa: E402

PROGRAMS = {
    'a global with no value, counted up': """
var count: word
func main()
  for i in 0..10 do count += 1 end
  print count
end
""",
    'read through a function': """
var hits: byte
func bump(): byte
  hits += 1
  return hits
end
func main()
  var last: byte = 0
  for i in 0..5 do last = bump() end
  print last; " "; hits
end
""",
    'a global with a value': """
var total: int = 100
func main()
  for i in 0..3 do total += i end
  print total
end
""",
}
WANT = {'a global with no value, counted up': '10', 'read through a function': '5 5', 'a global with a value': '103'}


def until_done(zx):
    for _ in range(600):
        zx.run(frames=50)
        r = zx.report()
        if ',' in r and ':' in r:
            return r
    return '(still running)'


bad = 0
for name, src in PROGRAMS.items():
    asm = zxbuild.z80gen.compile_program(src, 'zx48')
    homed = asm.count('; the home of ')
    tap, _ = zxbuild.build(src, b'')
    zx = Speccy()
    zx.wait_ready()
    zx.insert_tape(tap)
    zx.type('LOAD ""\n')
    until_done(zx)
    whole = zx.printed()
    t1 = whole.split('Bytes: program   \n', 1)[-1].strip()
    zx.type('RUN\n')
    until_done(zx)
    t2 = zx.printed()[len(whole):].strip()
    ok = t1 == t2 == WANT[name] and homed > 0
    bad += not ok
    print(f'{"ok  " if ok else "FAIL"} {name}: {t1!r}, then {t2!r} ({homed} home{"s" if homed != 1 else ""})')
print(f'{len(PROGRAMS) - bad} of {len(PROGRAMS)} run again by RUN the same, with their variables in operands')
sys.exit(1 if bad else 0)
