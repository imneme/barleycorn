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
print('core:', 'all right' if not bad else f'{bad} wrong', f'(pr_u16 of 65535: {r.call("bly_pr_u16", regs={"hl": 65535}).t} T)')
