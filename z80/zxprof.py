"""Where a Barley program spends its time on the 48K: build its tape, run it on
omse-ai, and from `--from` seconds on, for `--secs` seconds, sample the PC
every 997 T-states (prime, so it can't lock onto a loop). Each sample is
charged to the code it lands in: a library routine (the nearest bly_ label at
or below it), the generated code (by the Barley line its last `ld (bly_line)`
marker names, which is approximate: a marker sits before the first thing in a
statement that can fail), or the ROM. Prints the shares, biggest first.
"""
import argparse, bisect, collections, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import paths
paths.omse_ai()
import z80gen, zxbuild
from speccy import Speccy

ap = argparse.ArgumentParser(prog='zxprof.py', description=__doc__,
                             epilog="Run it with a Python that can import omse-ai: paths.py's OMSE_AI_PYTHON.")
ap.add_argument('prog', metavar='PROGRAM.bly', help='the program')
ap.add_argument('input', metavar='INPUT', nargs='?', help='its input')
ap.add_argument('--from', dest='start', type=float, default=20, metavar='SECONDS',
                help='start sampling this far into the run (default 20)')
ap.add_argument('--secs', type=float, default=30, metavar='SECONDS', help='sample for this long (default 30)')
ap.add_argument('--top', type=int, default=30, metavar='N', help='show the N biggest shares (default 30)')
a = ap.parse_args()
try:
    src, text = open(a.prog).read(), open(a.input, 'rb').read() if a.input else b''
except OSError as err:
    sys.exit(f'zxprof.py: {err.filename}: {err.strerror}')
tap, info = zxbuild.build(src, text)
org, bss_at, input_at = info['org'], info['org'] - info['slots'], info['input_at']
asm = z80gen.compile_program(src, 'zx48', org=org, bss_at=bss_at) + f'\nbly_input_at equ {input_at}\n'

# a listing, to know which Barley line each generated instruction belongs to
with tempfile.TemporaryDirectory() as d:
    p, l, s, b = (os.path.join(d, n) for n in ('p.asm', 'p.lst', 'p.sym', 'p.bin'))
    open(p, 'w').write(asm)
    subprocess.run([zxbuild.SJASM, '--nologo', f'--raw={b}', f'--sym={s}', f'--lst={l}', p], check=True,
                   capture_output=True)
    lst = open(l, errors='replace').read().splitlines()
    sym = {}
    for line in open(s):
        m = re.match(r'(\S+):\s+EQU\s+0x([0-9A-Fa-f]+)', line)
        if m:
            sym[m.group(1)] = int(m.group(2), 16)
lib_start = None                             # the library starts at the first gathered fragment's first byte
for i, row in enumerate(lst):
    if re.search(r';\s*---- \w+\.asm', row):
        for nxt in lst[i + 1:]:
            m = re.match(r'\s*\d+\+?\s+([0-9A-F]{4})\s+[0-9A-F]{2}', nxt)
            if m:
                lib_start = int(m.group(1), 16)
                break
        break
owner = {}                                   # address -> what it's charged to, for the generated code
line_no, func = 0, '?'
for row in lst:
    m = re.match(r'\s*\d+\+?\s+([0-9A-F]{4})\s+((?:[0-9A-F]{2} ?)+)?\s*(.*)', row)
    if not m:
        continue
    addr, body = int(m.group(1), 16), m.group(3)
    f = re.match(r'(f_\w+):', body)
    if f:
        func = f.group(1)
    n = re.match(r'ld hl,(\d+)\s*$', body.strip())
    if n:
        pending = int(n.group(1))
    if 'ld (bly_line),hl' in body and n is None:
        line_no = pending
    if m.group(2) and addr < lib_start:
        for k in range(len(m.group(2).split())):
            owner[addr + k] = f'{func} line {line_no}'
libs = sorted((v, k) for k, v in sym.items() if lib_start <= v < sym['bly_code_end'] and k.startswith('bly_'))
lib_addrs = [v for v, k in libs]

zx = Speccy()
zx.wait_ready(); zx.insert_tape(tap); zx.type('LOAD ""\n')
t0 = zx.seconds
zx.run(frames=int(a.start * 50))
counts = collections.Counter()
n = int(a.secs * 3_500_000 / 997)
for _ in range(n):
    zx.lib.zx_run_tstates(zx.z, 997)
    pc = zx.pc
    if pc < 0x4000:
        counts['ROM'] += 1
    elif pc >= lib_start and pc < sym['bly_code_end']:
        counts[libs[bisect.bisect_right(lib_addrs, pc) - 1][1]] += 1
    elif pc in owner:
        counts[owner[pc]] += 1
    else:
        counts[f'other {pc:04X}'] += 1
total = sum(counts.values())
gen = sum(c for k, c in counts.items() if k.startswith('f_'))
lib = sum(c for k, c in counts.items() if k.startswith('bly_'))
print(f'{a.prog}: {total} samples over {a.secs:.0f} s from {a.start:.0f} s; generated code {100 * gen / total:.1f}%, '
      f'library {100 * lib / total:.1f}%, ROM {100 * counts["ROM"] / total:.1f}%')
for k, c in counts.most_common(a.top):
    print(f'{100 * c / total:6.1f}%  {k}')
