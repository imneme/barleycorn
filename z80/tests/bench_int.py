"""The integer library's costs: T-states on representative operands, and bytes per fragment (for z80/lib/NOTES.md).

    $OMSE_AI_PYTHON z80/tests/bench_int.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from harness import Runner, assemble          # noqa: E402
from link import gather, load                 # noqa: E402

A, B, R, Q = 0xE000, 0xE010, 0xE020, 0xE030
MINE = ('int16.asm', 'intarith.asm', 'intbits.asm', 'intdiv.asm', 'intfail.asm', 'intmisc.asm', 'intmul32.asm',
        'intmul64.asm', 'intquad.asm')
enc = lambda v, n: (v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little')

# (routine, label, operands): ints for 16-bit routines (HL, DE), or values put at A and B for the wider ones
CASES = [
    ('bly_mul_u16', '1234 * 56', (1234, 56)), ('bly_mul_u16', '40000 * 3', (40000, 3)),
    ('bly_mul_u16', '65535 * 65535 (worst)', (65535, 65535)),
    ('bly_mul_i16', '-123 * 45', (-123, 45)), ('bly_mul_i16', '181 * 181 (worst)', (181, 181)),
    ('bly_divmod_u16', '12345 / 7', (12345, 7)), ('bly_divmod_u16', '1000 / 7', (1000, 7)),
    ('bly_divmod_u16', '65535 / 300', (65535, 300)), ('bly_divmod_u16', '65535 / 1 (worst)', (65535, 1)),
    ('bly_divmod_i16', '-12345 / 7', (-12345, 7)), ('bly_divmod_i16', '-32768 / 1 (worst)', (-32768, 1)),
    ('bly_rem_i16', '-12345 % 7', (-12345, 7)),
    ('bly_add_i32', 'any', (5, 7)), ('bly_sub_i32', 'any', (5, 7)), ('bly_neg_i32', 'any', (5,)),
    ('bly_cmp_i32', 'differ at the top', (1 << 30, 5)), ('bly_cmp_i32', 'equal (worst)', (12345, 12345)),
    ('bly_add_i64', 'any', (5, 7)), ('bly_sub_i64', 'any', (5, 7)), ('bly_neg_i64', 'any', (5,)),
    ('bly_cmp_i64', 'differ at the top', (1 << 60, 5)), ('bly_cmp_i64', 'equal (worst)', (12345, 12345)),
    ('bly_and_i32', 'any', (5, 7)), ('bly_and_i64', 'any', (5, 7)), ('bly_not_i32', 'any', (5,)),
    ('bly_not_i64', 'any', (5,)),
    ('bly_shl_i32', '<< 1', (12345, 1)), ('bly_shl_i32', '<< 8', (12345, 8)), ('bly_shl_i32', '<< 31 (worst)', (1, 31)),
    ('bly_shr_i32', '>> 1', (-12345, 1)), ('bly_shr_i32', '>> 31 (worst)', (-12345, 31)),
    ('bly_shl_i64', '<< 1', (12345, 1)), ('bly_shl_i64', '<< 63 (worst)', (1, 63)),
    ('bly_shr_i64', '>> 1', (-12345, 1)), ('bly_shr_i64', '>> 63 (worst)', (-12345, 63)),
    ('bly_mul_i32', '123456 * 7', (123456, 7)), ('bly_mul_i32', '40000 * 50000', (40000, 50000)),
    ('bly_mul_i32', '-46340 * 46340', (-46340, 46340)), ('bly_mul_i32', '2^23 * 255 (worst)', ((1 << 23) - 1, 255)),
    ('bly_mul_i64', '10^12 * 7', (10 ** 12, 7)), ('bly_mul_i64', '10^9 * 10^9', (10 ** 9, 10 ** 9)),
    ('bly_mul_i64', '2^31 * 2^31', ((1 << 31) - 1, (1 << 31) - 1)),
    ('bly_mul_i64', '(2^47-1) * (2^15-1) (wide)', ((1 << 47) - 1, (1 << 15) - 1)),
    ('bly_mul_i64', '(2^35-1) * (2^27-1) (worst)', ((1 << 35) - 1, (1 << 27) - 1)),
    ('bly_divmod_i32', '10^9 / 7 (by a byte)', (10 ** 9, 7)), ('bly_divmod_i32', '10^9 / 10000 (two bytes)', (10 ** 9, 10000)),
    ('bly_divmod_i32', '10^9 / 100000 (three)', (10 ** 9, 100000)), ('bly_divmod_i32', '2^31-1 / 2^24+1 (four)', ((1 << 31) - 1, (1 << 24) + 1)),
    ('bly_divmod_i32', '2^31-1 / 65537 (worst)', ((1 << 31) - 1, 65537)),
    ('bly_rem_i32', '10^9 % 10000', (10 ** 9, 10000)),
    ('bly_divmod_i64', '10^18 / 7 (by a byte)', (10 ** 18, 7)), ('bly_divmod_i64', '10^18 / 10000 (two bytes)', (10 ** 18, 10000)),
    ('bly_divmod_i64', '10^12 / 10000 (two bytes)', (10 ** 12, 10000)),
    ('bly_divmod_i64', '10^18 / 10^6 (three)', (10 ** 18, 10 ** 6)), ('bly_divmod_i64', '10^18 / 10^9 (four)', (10 ** 18, 10 ** 9)),
    ('bly_divmod_i64', '10^18 / 10^12 (five)', (10 ** 18, 10 ** 12)),
    ('bly_divmod_i64', '10^18 / 10^15 (seven)', (10 ** 18, 10 ** 15)),
    ('bly_divmod_i64', '2^63-1 / 2^32+1 (five, worst)', ((1 << 63) - 1, (1 << 32) + 1)),
    ('bly_divmod_i64', '2^63-1 / 65537 (worst)', ((1 << 63) - 1, 65537)),
    ('bly_rem_i64', '10^18 % 10007', (10 ** 18, 10007)),
    ('bly_mod_i64', '-10^12 mod 10007', (-10 ** 12, 10007)),
    ('bly_gcd_i64', 'gcd(360, 84)', (360, 84)), ('bly_gcd_i64', 'gcd(10^12, 20000)', (10 ** 12, 20000)),
    ('bly_gcd_i64', 'gcd(2^40+15, 2^39+7) (both wide)', ((1 << 40) + 15, (1 << 39) + 7)),
    ('bly_gcd_i64', 'gcd(F92, F91) (worst kind)', (7540113804746346429, 4660046610375530309)),
    ('bly_lcm_i64', 'lcm(13 * 10^9, 20021)', (13 * 10 ** 9, 20021)), ('bly_lcm_i64', 'lcm(12, 18)', (12, 18)),
    ('bly_abs_i64', '-5', (-5,)), ('bly_fit_i64', 'to long', (123456,)),
]


def cost(r, routine, ops):
    if routine.endswith('16'):
        return r.call(routine, regs={'hl': ops[0] & 0xFFFF, 'de': ops[1] & 0xFFFF}).t
    n = 4 if routine.endswith('i32') else 8
    mem = {A: enc(ops[0], n)}
    regs = {'hl': A, 'bc': R}
    if routine.startswith('bly_shl') or routine.startswith('bly_shr'):
        regs['de'] = ops[1]
    elif len(ops) > 1:
        mem[B] = enc(ops[1], n)
        regs['de'] = B
    if routine.startswith('bly_divmod'):
        regs.update(bc=Q, ix=R)
    if routine == 'bly_fit_i64':
        regs = {'hl': A, 'a': 3, 'de': R}
    res = r.call(routine, regs=regs, mem=mem)
    assert not res.failed, (routine, ops, res.out)
    return res.t


def sizes():
    """bytes per fragment, and how many of them are scratch (ds)"""
    mine = [f for f in load() if f.name in MINE]
    syms = [s for f in mine for s in f.provides]
    frags, _ = gather(syms, 'test')
    text = '        org 8000h\nbly_test_halt: nop\n'
    for i, f in enumerate(frags):
        text += f'bly_zz_mark{i}:\n' + f.text + '\n'
    text += f'bly_zz_mark{len(frags)}:\n'
    _, sym = assemble(text)
    out = {}
    for i, f in enumerate(frags):
        scratch = sum(int(m) for m in re.findall(r'^\S*\s*ds\s+(\d+)', f.text, re.M))
        out[f.name] = (sym[f'bly_zz_mark{i + 1}'] - sym[f'bly_zz_mark{i}'], scratch)
    return out


def main():
    r = Runner(sorted({c[0] for c in CASES}))
    rows = [(routine, label, cost(r, routine, ops)) for routine, label, ops in CASES]
    for routine, label, t in rows:
        print(f'{routine:16} {label:36} {t:7} T')
    print()
    for name, (n, scratch) in sizes().items():
        print(f'{name:16} {n:5} bytes' + (f' ({scratch} of them scratch)' if scratch else ''))


if __name__ == '__main__':
    main()
