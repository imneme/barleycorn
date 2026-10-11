#!/usr/bin/env python3
"""bly c's --wrap and -o, held to what they say.

--wrap builds the C with BLY_WRAP: a signed number that doesn't fit wraps
round, as two's complement does, instead of stopping the program. Held to
Python's own arithmetic for int, long and quad (+, -, *, /, unary -), and the
same program without --wrap must still stop, at the right line. Indexes and
division by zero are still checked under --wrap. -o keeps the executable and
doesn't run it: it must run on its own, and an input given to the build is
refused. Every run has a time limit: a program that relies on an overflow to
stop runs for ever under --wrap.
"""
import argparse
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLY = os.path.join(ROOT, 'bly')

argparse.ArgumentParser(prog='test_wrap.py', description=__doc__,
                        formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()


def wrap(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


I16, I32, I64 = 32767, 2147483647, 9223372036854775807
ARITH = '''func main()
  var a: int = 32767
  var b: long = 2147483647
  var c: quad = 9223372036854775807
  print a + 1; " "; b + 1; " "; c + 1
  var d: int = -a - 1
  var e: long = -b - 1
  var f: quad = -c - 1
  print -d; " "; d - 1; " "; d * 2; " "; a * a; " "; d / -1
  print -e; " "; e - 1; " "; e * 3; " "; b * b; " "; e / -1
  print -f; " "; f - 1; " "; f * 3; " "; c * c; " "; f / -1
end
'''
d, e, f = -I16 - 1, -I32 - 1, -I64 - 1
WANT = '\n'.join([
    f'{wrap(I16 + 1, 16)} {wrap(I32 + 1, 32)} {wrap(I64 + 1, 64)}',
    f'{wrap(-d, 16)} {wrap(d - 1, 16)} {wrap(d * 2, 16)} {wrap(I16 * I16, 16)} {wrap(-d, 16)}',
    f'{wrap(-e, 32)} {wrap(e - 1, 32)} {wrap(e * 3, 32)} {wrap(I32 * I32, 32)} {wrap(-e, 32)}',
    f'{wrap(-f, 64)} {wrap(f - 1, 64)} {wrap(f * 3, 64)} {wrap(I64 * I64, 64)} {wrap(-f, 64)}']) + '\n'
STILL = {'index': ('var arr: byte[3]\n\nfunc main()\n  var i = 3\n  print arr[i]\nend\n', 'at line 5'),
         'division by zero': ('func main()\n  var z = 0\n  print 10 / z\nend\n', 'division by zero at line 3')}

wrong = checks = 0


def check(what, ok, got=''):
    global wrong, checks
    checks += 1
    if not ok:
        wrong += 1
        print('WRONG', what, repr(got)[:300])


def bly(*args, run=None):
    r = subprocess.run([BLY, 'c'] + list(args), capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


with tempfile.TemporaryDirectory() as tmp:
    prog = os.path.join(tmp, 'arith.bly')
    open(prog, 'w').write(ARITH)
    code, out = bly('--wrap', prog)
    check('--wrap: int, long and quad wrap round, as Python says', code == 0 and out == WANT, out)
    code, out = bly(prog)
    check('without --wrap: int overflow stops it at line 5', code != 0 and out.rstrip().endswith('int overflow at line 5'),
          out)
    for name, (src, words) in STILL.items():
        p = os.path.join(tmp, name.replace(' ', '_') + '.bly')
        open(p, 'w').write(src)
        code, out = bly('--wrap', p)
        check(f'--wrap still checks {name}', code != 0 and words in out, out)
    exe = os.path.join(tmp, 'arith')
    code, out = bly('--wrap', '-o', exe, prog)
    check("-o keeps the executable and doesn't run it", code == 0 and out == exe + '\n' and os.access(exe, os.X_OK), out)
    r = subprocess.run([exe], capture_output=True, text=True, timeout=60)
    check('the kept executable runs on its own', r.returncode == 0 and r.stdout == WANT, r.stdout)
    code, out = bly('-o', exe, prog, prog)
    check('-o refuses an input', code != 0 and 'the input goes to the executable' in out, out)
print(f'{checks} checks of bly c --wrap and -o, {wrong} wrong')
sys.exit(1 if wrong else 0)
