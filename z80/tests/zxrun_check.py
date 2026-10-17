#!/usr/bin/env python3
"""zxrun.py types a program's keys as a patient person would: a program that
reads only through ask() and works for seconds before its next question still
gets the next line, typed ahead (bly zx and bly all pass --wait-ask for it).
Without that, the 48K pressed the line while the program was busy, and it was
lost: claw_d13 ended "STOP in ask" at its second question. Run with omse-ai's
Python, or any: it goes through bly.
"""
import argparse
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
argparse.ArgumentParser(prog='zxrun_check.py', description=__doc__,
                        formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
PROG = '''func main()
  var n = ask("how many? ")
  var t: long = 0
  for i in 0..20 do
    for j in 0..3000 do
      t += j
    end
  end
  var m = ask("again? ")
  print n; " and "; m; ", "; t
end
'''
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, 'asktwice.bly')
    open(p, 'w').write(PROG)
    r = subprocess.run([os.path.join(ROOT, 'bly'), 'zx', p], input='7\n42\n', capture_output=True, text=True,
                       timeout=600)
    ok = r.returncode == 0 and r.stdout.rstrip().endswith('7 and 42, 89970000')
print(f"zxrun: a second question after two seconds' work {'gets its typed-ahead line' if ok else 'LOST it: ' + repr((r.stdout + r.stderr)[-120:])}")
sys.exit(0 if ok else 1)
