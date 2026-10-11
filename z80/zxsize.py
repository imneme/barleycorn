"""Where a Barley program's bytes go on the 48K: the generated code against
each library fragment gathered in.
"""
import argparse, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import z80gen, zxbuild

ap = argparse.ArgumentParser(prog='zxsize.py', description=__doc__)
ap.add_argument('program', metavar='PROGRAM.bly', help='the program')
ap.add_argument('input', metavar='INPUT', nargs='?', help='its input (it decides where the arena starts)')
a = ap.parse_args()
try:
    src, text = open(a.program).read(), open(a.input, 'rb').read() if a.input else b''
except OSError as err:
    sys.exit(f'zxsize.py: {err.filename}: {err.strerror}')
z80gen.B.EMBED_DIR = os.path.dirname(os.path.abspath(a.program))       # embed's files are beside it
try:
    tap, info = zxbuild.build(src, text)
except z80gen.B.BarleyError as err:
    sys.exit(str(err))                                  # the checker's words, as bly prints them
except (z80gen.GenError, ValueError) as err:
    sys.exit(f'Z80: {err}')
org = info['org']
asm = z80gen.compile_program(src, 'zx48', org=org, bss_at=org - info['slots']) + \
    f'\nbly_input_at equ {info["input_at"]}\n'
with tempfile.TemporaryDirectory() as d:
    p, l, b = (os.path.join(d, n) for n in ('p.asm', 'p.lst', 'p.bin'))
    open(p, 'w').write(asm)
    subprocess.run([zxbuild.SJASM, '--nologo', f'--raw={b}', f'--lst={l}', p], check=True, capture_output=True)
    lst = open(l, errors='replace').read().splitlines()
part, sizes = 'generated code', {}
for row in lst:
    f = re.search(r';\s*---- (\w+\.asm)', row)
    if f:
        part = f.group(1)
        continue
    if 'bly_code_end:' in row:
        break
    m = re.match(r'\s*\d+\+?\s+[0-9A-F]{4}\s+((?:[0-9A-F]{2} ?)+)', row)
    if m:
        sizes[part] = sizes.get(part, 0) + len(m.group(1).split())
total = sum(sizes.values())
print(f'{a.program}: {total} bytes of code ({info["code"]} by the builder), slots {info["slots"]} bytes '
      f'(the variables\' homes)')
for k, v in sorted(sizes.items(), key=lambda kv: -kv[1]):
    print(f'{v:6}  {100 * v / total:5.1f}%  {k}')
