#!/usr/bin/env python3
"""A tape with several inputs runs the program on each in turn, as Melissa's
robots tape loaded each floor after the last was solved: three inputs of
different sizes, the largest not the first, and the program prints each one's
first line and how many lines it has, three runs in order, and BASIC ends with
0 OK. Run with omse-ai's Python, or any: it goes through bly zx.
"""
import argparse
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
argparse.ArgumentParser(prog='multi_input_check.py', description=__doc__,
                        formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
PROG = '''func main()
  var n = 0
  for line in lines() do
    if n == 0 then print line; " ";
    end
    n += 1
  end
  print n
end
'''
INPUTS = ['apple\nbanana\n', 'cherry\n' * 400, 'damson\nelder\nfig\n']
WANT = 'apple 2\ncherry 400\ndamson 3\n'
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, 'firsts.bly')
    open(p, 'w').write(PROG)
    files = []
    for k, text in enumerate(INPUTS):
        files.append(os.path.join(d, f'in{k}.txt'))
        open(files[-1], 'w').write(text)
    r = subprocess.run([os.path.join(ROOT, 'bly'), 'zx', p] + files, capture_output=True, text=True, timeout=600)
    ok = r.returncode == 0 and r.stdout == WANT
print('multi-input tape: ' + ('three runs, an input each, in order' if ok else
                              'WRONG: ' + repr((r.stdout + r.stderr)[-200:])))
sys.exit(0 if ok else 1)
