#!/usr/bin/env python3
"""bly --unchecked leaves 8- and 16-bit indexes unchecked on the Z80, and
nothing else changes: a program whose indexes are good prints the same with
it as without, in less code; one that reads past an array's end stops with
"index ... is outside" without it, and runs on with it (which is what
unchecked means, and why it's only for a program already proven checked).
Wider indexes (long, quad) stay checked. On CP/M, under tnylpo, through bly
(which can't pass a program's failure on as its exit status, so what each
prints is what's checked).
"""
import argparse
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
argparse.ArgumentParser(prog='unchecked_check.py', description=__doc__,
                        formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
GOOD = '''func main()
  var a: int[10]
  var b: byte[300]
  for i in 0..10 do a[i] = i * i end
  var w: word = 0
  while w < 300 do
    b[w] = byte(w & 255)
    w += 1
  end
  var s: long = 0
  for i in 0..10 do s += a[i] end
  w = 0
  while w < 300 do
    s += b[w]
    w += 1
  end
  var k: long = 9
  print s; " "; a[k]
end
'''
PAST = '''func main()
  var a: int[3]
  var guard: int[3]
  var k = 3
  print "before"
  print a[k] + guard[0] - guard[0]
  print "after"
end
'''
WIDE = '''func main()
  var a: int[3]
  var k: long = 5
  print a[k]
end
'''


def cpm(d, name, src, unchecked):
    p = os.path.join(d, name + '.bly')
    open(p, 'w').write(src)
    r = subprocess.run([os.path.join(ROOT, 'bly'), 'cpm', p] + (['--unchecked'] if unchecked else []),
                       capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def size(d, name, unchecked):
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'z80', 'z80gen.py'), os.path.join(d, name + '.bly')] +
                       (['--unchecked'] if unchecked else []), capture_output=True, text=True)
    return len(r.stdout)


bad = 0
with tempfile.TemporaryDirectory() as d:
    checked, unchecked = cpm(d, 'good', GOOD, False), cpm(d, 'good', GOOD, True)
    if checked != unchecked or 'outside' in checked[1]:
        bad += 1
        print(f'FAIL good indexes: checked {checked!r}, unchecked {unchecked!r}')
    if not size(d, 'good', True) < size(d, 'good', False):
        bad += 1
        print('FAIL unchecked code is no smaller')
    c, out = cpm(d, 'past', PAST, False)
    if 'index 3 is outside 0..3' not in out or 'after' in out:
        bad += 1
        print(f'FAIL a read past the end, checked, should stop: {c} {out!r}')
    c, out = cpm(d, 'past', PAST, True)
    if 'after' not in out or 'outside' in out:
        bad += 1
        print(f'FAIL a read past the end, unchecked, should run on: {c} {out!r}')
    c, out = cpm(d, 'wide', WIDE, True)
    if 'index 5 is outside 0..3' not in out:
        bad += 1
        print(f'FAIL a long index, unchecked, is still checked: {c} {out!r}')
print('unchecked: ' + ('indexes unchecked, and nothing else changed' if not bad else f'{bad} wrong'))
sys.exit(1 if bad else 0)
