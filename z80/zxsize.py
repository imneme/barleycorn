"""Where a Barley program's bytes go on the 48K: the generated code against each library fragment gathered in.
usage: zxsize.py PROGRAM.bly INPUT.txt"""
import os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import z80gen, zxbuild

src, text = open(sys.argv[1]).read(), open(sys.argv[2], 'rb').read()
tap, info = zxbuild.build(src, text)
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
print(f'{sys.argv[1]}: {total} bytes of code ({info["code"]} by the builder), slots {info["slots"]}')
for k, v in sorted(sizes.items(), key=lambda kv: -kv[1]):
    print(f'{v:6}  {100 * v / total:5.1f}%  {k}')
