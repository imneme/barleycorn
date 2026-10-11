"""core.asm against its meaning: printing numbers, zones, the failure messages, the arena."""
import os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from harness import Runner

r = Runner(['bly_pr_u16', 'bly_pr_i16', 'bly_zone', 'bly_fail_index_i16', 'bly_alloc', 'bly_pr_bool', 'bly_pr_str'])
bad = 0
for v in [0, 1, 9, 10, 99, 100, 1000, 9999, 10000, 32767, 32768, 65535] + random.sample(range(65536), 300):
    got = r.call('bly_pr_u16', regs={'hl': v}).out.decode()
    if got != str(v):
        bad += 1; print('pr_u16', v, got)
    s = v - 65536 if v >= 32768 else v
    got = r.call('bly_pr_i16', regs={'hl': v}).out.decode()
    if got != str(s):
        bad += 1; print('pr_i16', s, got)
res = r.call('bly_fail_index_i16', regs={'de': 0xFFFF, 'bc': 3})
want = 'index -1 is outside 0..3\n'               # bly_line is 0 here, so no " at line"
if res.out.decode() != want or not res.failed:
    bad += 1; print('fail_index', res.out, res.failed)
res = r.call('bly_alloc', regs={'hl': 100})
if res.regs['hl'] != 0xA000 or res.failed:
    bad += 1; print('alloc', hex(res.regs['hl']))
res = r.call('bly_alloc', regs={'hl': 0x5000})
if res.out.decode() != 'arena full\n' or not res.failed:
    bad += 1; print('alloc full', res.out)
for a, w in ((0, 'false'), (1, 'true')):
    if r.call('bly_pr_bool', regs={'a': a}).out.decode() != w:
        bad += 1; print('bool', a)
res = r.call('bly_pr_str', regs={'hl': 0xE000}, mem={0xE000: bytes([4, 0xE0, 5, 0]), 0xE004: b'hello'})
if res.out != b'hello':
    bad += 1; print('pr_str', res.out)
res = r.call('bly_pr_str', regs={'hl': 0xE000}, mem={0xE000: bytes(4)})
if res.out != b'':
    bad += 1; print('pr_str empty', res.out)
# a line in an included file: (file << 12) | its line, " of NAME" from the table bly_files points at, as the
# interpreter's where() says it (barley.py)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'interp'))
import barley as B                                                  # noqa: E402
names = ['lib/a.bly', 'dice.bly', 'inc/faces.bly']
table = bytes([0, 0]) + b''.join((0xE110 + 16 * k).to_bytes(2, 'little') for k in range(len(names)))
mem = {0xE100: table, **{0xE110 + 16 * k: n.encode() + b'\0' for k, n in enumerate(names)}}
B.FILES[:] = [None] + [(n, '.', n) for n in names]
for k, n in ((0, 7), (0, 4095), (1, 1), (2, 4095), (3, 77)):
    line = k << 12 | n
    res = r.call('bly_fail_index_i16', regs={'de': 0xFFFF, 'bc': 3}, mem=mem,
                 set16={'bly_line': line, 'bly_files': 0xE100})
    want = str(B.BarleyError('index -1 is outside 0..3', line)) + '\n'
    if res.out.decode() != want or not res.failed:
        bad += 1; print('line of a file', k, n, res.out, want)
print('core:', 'all right' if not bad else f'{bad} wrong', f'(pr_u16 of 65535: {r.call("bly_pr_u16", regs={"hl": 65535}).t} T)')
sys.exit(1 if bad else 0)                               # ./check goes by this: the words alone aren't a failure
