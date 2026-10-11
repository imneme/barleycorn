"""gen.asm against its meaning."""
import os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from harness import Runner
r = Runner(['bly_cmp_u8', 'bly_cmp_u16', 'bly_cmp_i16', 'bly_lt', 'bly_le', 'bly_gt', 'bly_ge', 'bly_eq', 'bly_ne',
            'bly_shl16', 'bly_shr_u16', 'bly_shr_i16'])
bad = 0
sgn = lambda v: v - 65536 if v >= 32768 else v
cmp3 = lambda a, b: (a > b) - (a < b)
edge16 = [0, 1, 2, 0x7FFF, 0x8000, 0x8001, 0xFFFE, 0xFFFF, 100, 0x00FF, 0x0100]
pairs = [(a, b) for a in edge16 for b in edge16] + [(random.randrange(65536), random.randrange(65536)) for _ in range(400)]
for a, b in pairs:
    for name, want in (('bly_cmp_u16', cmp3(a, b)), ('bly_cmp_i16', cmp3(sgn(a), sgn(b)))):
        got = r.call(name, regs={'hl': a, 'de': b}).regs['a']
        if (got if got < 128 else got - 256) != want:
            bad += 1; print(name, a, b, got, want)
for a, b in [(random.randrange(256), random.randrange(256)) for _ in range(200)] + [(0, 0), (255, 0), (0, 255)]:
    got = r.call('bly_cmp_u8', regs={'a': a, 'de': b}).regs['a']
    if (got if got < 128 else got - 256) != cmp3(a, b):
        bad += 1; print('u8', a, b, got)
for name, f in (('bly_lt', lambda c: c < 0), ('bly_le', lambda c: c <= 0), ('bly_gt', lambda c: c > 0),
                ('bly_ge', lambda c: c >= 0), ('bly_eq', lambda c: c == 0), ('bly_ne', lambda c: c != 0)):
    for c in (-1, 0, 1):
        if r.call(name, regs={'a': c & 0xFF}).regs['a'] != int(f(c)):
            bad += 1; print(name, c)
for x in [0, 1, 0x8000, 0xFFFF, 0x1234] + [random.randrange(65536) for _ in range(60)]:
    for n in [0, 1, 7, 14, 15, 16, 17, 300] + [random.randrange(20) for _ in range(5)]:
        for name, want in (('bly_shl16', (x << n) & 0xFFFF), ('bly_shr_u16', x >> n),
                           ('bly_shr_i16', (sgn(x) >> n) & 0xFFFF)):
            got = r.call(name, regs={'hl': x, 'de': n})
            if got.regs['hl'] != want or got.failed:
                bad += 1; print(name, x, n, got.regs['hl'], want)
res = r.call('bly_shl16', regs={'hl': 1, 'de': 0xFFFF})
if res.out != b'negative shift count\n' or not res.failed:
    bad += 1; print('negative shift', res.out)
print('gen:', 'all right' if not bad else f'{bad} wrong')
sys.exit(1 if bad else 0)                               # ./check goes by this: the words alone aren't a failure
