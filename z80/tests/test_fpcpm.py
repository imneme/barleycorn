"""fp_cpm.asm against its model, fp5.py: floats where there's no ROM (CP/M),
on the bare Z80.

+ - * / come out correctly rounded (nearest, ties away from zero, as
z80gen.rom5 rounds a literal), so they're held to fp5's exact Fractions
byte for byte, in the full form; printing is held to fp5.show text for
text (PRINT-FP's layout, its 8 digits exactly rounded). Cases: random over
the whole exponent range; the edges where rounding and alignment break
(exponents 0, 1, 31-33 and 63-65 apart, equal magnitudes, powers of two,
all-ones mantissas, ties, the short form, zero); answers whose exponent
lands at its edges; and the failures word for word (float overflow,
division by zero). --mutants breaks fp_cpm.asm on purpose (a copy of the
library) and checks these tests notice. Run it with omse-ai's Python
($OMSE_AI_PYTHON).
"""
import argparse
import os
import random
import sys
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(HERE, '..'), os.path.join(HERE, '..', '..'), os.path.join(HERE, '..', '..', 'interp')):
    sys.path.insert(0, p)
import fp5                                     # noqa: E402
import harness                                 # noqa: E402
import link                                    # noqa: E402
import paths                                   # noqa: E402
from harness import Runner                     # noqa: E402

ap = argparse.ArgumentParser(prog='test_fpcpm.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--seed', type=int, default=1, help="the random cases' seed (default 1)")
ap.add_argument('--quick', action='store_true', help='fewer random cases')
ap.add_argument('--lib', metavar='DIR', help='a mutated copy of the library to test instead')
ap.add_argument('--mutants', action='store_true',
                help='break fp_cpm.asm on purpose, and check these tests notice')
ARGS = ap.parse_args()
if ARGS.lib:
    _lib = ARGS.lib
    harness.gather = lambda symbols, target: link.gather(symbols, target, lib=_lib)
N = 300 if ARGS.quick else 2000
rnd = random.Random(ARGS.seed)
A, B, R = 0xE000, 0xE008, 0xE010
run = Runner(['bly_fadd', 'bly_fsub', 'bly_fmul', 'bly_fdiv', 'bly_fsqrt', 'bly_pr_f', 'bly_str_float',
              'bly_fexp', 'bly_fln', 'bly_fsin', 'bly_fcos', 'bly_ftan', 'bly_fatan', 'bly_fasin',
              'bly_facos'])
wrong = checks = 0
costs = {}


def say_wrong(*what):
    global wrong
    wrong += 1
    if wrong <= 25:
        print('WRONG', *what)


def rand_float():
    k = rnd.random()
    if k < 0.08:
        return bytes(5)
    if k < 0.2:                                 # the short form
        n = rnd.randint(-65535, 65535)
        return bytes([0, 0xFF if n < 0 else 0, n & 0xFF, (n >> 8) & 0xFF, 0])
    e = rnd.choice([rnd.randint(1, 255), rnd.randint(110, 150)])
    m = rnd.choice([rnd.randint(0, 0x7FFFFFFF), 0, 0x7FFFFFFF, 0x7FFFFF00, 0x00000001])
    return bytes([e, (m >> 24) | (0x80 if rnd.random() < 0.5 else 0), (m >> 16) & 0xFF, (m >> 8) & 0xFF, m & 0xFF])


def edge_pair(op):
    """a and b whose answer's exponent byte lands at its edges: 0 (just under), 1, 255, 256 (just over)"""
    target = rnd.choice([-1, 0, 1, 2, 254, 255, 256])
    ea = rnd.randint(1, 255)
    eb = target - ea + 128 if op == 'bly_fmul' else ea - target + 128
    if not 1 <= eb <= 255:
        eb = rnd.randint(1, 255)
    m = lambda: rnd.choice([rnd.randint(0, 0x7FFFFFFF), 0, 0x7FFFFFFF])
    mk = lambda e, mm: bytes([e, (mm >> 24) | (0x80 if rnd.random() < 0.5 else 0), (mm >> 16) & 255, (mm >> 8) & 255,
                              mm & 255])
    return mk(ea, m()), mk(eb, m())


def near(a):
    """b a chosen number of binary places below a: the alignment's edges"""
    va = fp5.value(a)
    if va == 0:
        return rand_float()
    d = rnd.choice([0, 1, 2, 7, 8, 9, 31, 32, 33, 34, 62, 63, 64, 65, 70])
    m = rnd.choice([rnd.randint(1 << 31, (1 << 32) - 1), 1 << 31, (1 << 32) - 1, (1 << 31) + 1])
    x = F(m, 1 << 32) * F(2) ** (fp5.ilog2(abs(va)) + 1 - d) * rnd.choice([1, -1])
    try:
        return fp5.pack(x)
    except fp5.Overflow:
        return rand_float()


def model(op, a, b):
    try:
        return {'bly_fadd': fp5.add, 'bly_fsub': fp5.sub, 'bly_fmul': fp5.mul, 'bly_fdiv': fp5.div}[op](a, b), None
    except fp5.Overflow:
        return None, b'float overflow\n'
    except ZeroDivisionError:
        return None, b'division by zero\n'


def case(op, a, b):
    global checks
    checks += 1
    want, err = model(op, a, b)
    res = run.call(op, regs={'hl': A, 'de': B, 'bc': R}, mem={A: a, B: b, R: b'\xAA' * 8})
    got = bytes(res.mem[R:R + 8])
    if res.t is not None and not res.failed:
        costs.setdefault(op, []).append(res.t)
    if err is not None:
        if not (res.failed and res.out == err):
            say_wrong(op, a.hex(), b.hex(), 'should fail', err, 'got', res.out, got.hex())
        return
    if res.failed or got[:5] != want or got[5:] != b'\xAA' * 3:
        say_wrong(op, a.hex(), b.hex(), 'gave', got.hex(), repr(res.out), 'want', want.hex(),
                  float(fp5.value(a)), float(fp5.value(b)))


MUTANTS = [   # (the text, what it becomes, what that breaks)
    ('        jr nc,.rd\n        inc l', '        jr .rd\n        inc l', 'never rounds up'),
    ('.packc: ld a,(.w+3)', '.packc: ld a,(.w+2)', 'rounds on the wrong bit'),
    ('.sub:   ld a,(bly_fc.lost)', '.sub:   xor a', '- forgets the bits b lost'),
    ('        jp nc,bly_fc.pack\n        ld hl,bly_fc.w+7', '        jp bly_fc.pack\n        ld hl,bly_fc.w+7',
     '+ forgets its carry out'),
    ('        jr nc,.bnl', '        jr .bnl', "the bit shift's lost bits unseen"),
    ('        ld de,-8\n        add hl,de\n        ld (bly_fc.ex),hl', '        ld de,-7\n        add hl,de\n        ld (bly_fc.ex),hl',
     'normalising by bytes counts 7'),
    ('        ld de,-128\n        add hl,de\n        ld (bly_fc.ex),hl\n        ld hl,bly_fc.w              ; the 64',
     '        ld de,-127\n        add hl,de\n        ld (bly_fc.ex),hl\n        ld hl,bly_fc.w              ; the 64',
     '* with the bias off by one'),
    ('        inc (ix+4)\n        ret nz\n        inc (ix+5)', '        inc (ix+4)\n        ret nz\n        nop\n        nop\n        nop',
     "*'s partial product carries one byte"),
    ('        ld a,0\n        rra\n        ld (bly_fc.w+3),a\n        ld hl,bly_fc.q',
     '        ld a,0\n        and a\n        ld (bly_fc.w+3),a\n        ld hl,bly_fc.q', "/ forgets the quotient's last bit"),
    ('        ld b,32\n        ld hl,(bly_fc.ex)', '        ld b,33\n        ld hl,(bly_fc.ex)', '/ takes one bit too many'),
    ('.movf:  db "float overflow",0', '.movf:  db "float overflov",0', 'the message misspelt'),
    ('        jr z,.zero                  ; under', '        jr z,.range                 ; under', 'underflow as overflow'),
    ('        cp 5\n        jr c,.nr', '        cp 6\n        jr c,.nr', 'print: rounds up only from 6'),
    ('.frac:  cp 0FFh', '.frac:  cp 0FEh', 'print: 0. for k = -2, not -1'),
    ('        cp 13\n        jr nc,.sci', '        cp 12\n        jr nc,.sci', 'print: E notation from 10^7'),
    ("        cp '0'\n        jr nz,.lay", "        cp '1'\n        jr nz,.lay", 'print: strips the wrong digit'),
    ('        call .cmp4\n        jr nz,.dg0', '        call .cmp4\n        jr .dg0', 'print: 99999999.5 left as 10^8'),
    ('        ld hl,.t9+3\n        call .cmp4\n        jr nc,.kup', '        ld hl,.t9+3\n        call .cmp4\n        nop\n        nop',
     "print: k's guess never moves up"),
    ("        ld b,'0'-1", "        ld b,'0'", "print: the exponent's tens one high"),
    ('        ld a,0\n        rra\n        ld (bly_fc.w+3),a\n        ld hl,.q\n',
     '        ld a,0\n        and a\n        ld (bly_fc.w+3),a\n        ld hl,.q\n', "sqrt: the root's last bit forgotten"),
    ('        rra\n        jr nc,.even', '        rra\n        jr .even', 'sqrt: an odd exponent not shifted'),
    ('        ld de,-127\n        add hl,de\n        sra h', '        ld de,-126\n        add hl,de\n        sra h',
     "sqrt: the exponent's half miscounted"),
    ('        cp 2\n        call nz,.xdn', '        cp 1\n        call nz,.xdn', "read: a fraction's leading zeros don't count"),
    ('        cp 40\n        ld a,2', '        cp 30\n        ld a,2', 'read: keeps 30 digits, not 40'),
    ('        jr nz,.wn\n        call .xup', '        jr .wn\n        call .xup', "read: a dropped whole digit doesn't count"),
    ('        jr z,.sup                   ; 34 or more', '        jr .sok                     ; 34 or more',
     "read: s's guess taken as it is"),
    ('        ld hl,161', '        ld hl,160', "read: a small number's exponent one low"),
    ('        ld hl,(.k)\n        add hl,de', '        ld hl,(.k)\n        inc hl\n        add hl,de', 'exp: 2^k one too many'),
    ('        db 1,4,10,2,5,3,11,6', '        db 1,4,10,2,5,3,11,5', "ln: its series one term short, shifted"),
    ('        ld hl,.q\n        add a,(hl)', '        ld hl,.q\n        add a,0', 'sin: the quadrant forgotten'),
    ('        ld a,1\n        ld (.far),a', '        ld a,0\n        ld (.far),a', "atan: the far reduction's pi/6 forgotten"),
    ('; The one trick:', '; The trick:', 'CONTROL: a comment'),
]


def mutants():
    import shutil, subprocess, tempfile
    lib = os.path.join(HERE, '..', 'lib')
    missed = 0
    for old, new_, why in MUTANTS:
        with tempfile.TemporaryDirectory(dir=paths.build_dir('fpcpm-tests')) as d:
            for name in os.listdir(lib):
                if name.endswith('.asm'):
                    shutil.copy(os.path.join(lib, name), d)
            f = os.path.join(d, 'fp_cpm.asm')
            text = open(f).read()
            if text.count(old) != 1:
                print(f'MISS {why}: its text is found {text.count(old)} times')
                missed += 1
                continue
            open(f, 'w').write(text.replace(old, new_))
            p = subprocess.run([sys.executable, __file__, '--quick', '--lib', d], capture_output=True, text=True)
            if 'sjasmplus' in p.stderr:
                print('BAD MUTANT (it does not assemble):', why)
                missed += 1
                continue
            caught = p.returncode != 0
            control = why.startswith('CONTROL')
            ok = caught != control
            missed += not ok
            first = next((l for l in p.stdout.splitlines() if l.startswith('WRONG')), p.stdout.strip()[-80:])
            print(f'{"ok  " if ok else "MISS"} {why:40} {first[:90]}')
    print('mutants:', 'every one caught' if not missed else f'{missed} not caught')
    return missed


def main():
    global checks
    if ARGS.mutants:
        sys.exit(1 if mutants() else 0)
    ops = ['bly_fadd', 'bly_fsub', 'bly_fmul', 'bly_fdiv']
    print('+ - * / against fp5, bit for bit')
    fixed = [(fp5.pack(1), fp5.pack(1)), (fp5.pack(1), fp5.pack(-1)), (fp5.pack(F(1, 3)), fp5.pack(3)),
             (bytes([255, 0x7F, 255, 255, 255]), bytes([255, 0x7F, 255, 255, 255])),
             (bytes([1, 0, 0, 0, 0]), bytes([1, 0, 0, 0, 0])), (bytes([0, 0, 1, 0, 0]), bytes(5)),
             (bytes([0, 0xFF, 0xFF, 0xFF, 0]), bytes([0, 0, 1, 0, 0])), (fp5.pack(2 ** 31 + 1), fp5.pack(F(1, 2)))]
    for a, b in fixed:
        for op in ops:
            case(op, a, b)
            case(op, b, a)
    for _ in range(N):
        a = rand_float()
        b = near(a) if rnd.random() < 0.5 else rand_float()
        for op in ops:
            case(op, a, b)
    for _ in range(N // 2):
        for op in ('bly_fmul', 'bly_fdiv'):
            case(op, *edge_pair(op))
    print('sqrt against fp5, bit for bit')
    roots = [rand_float() for _ in range(N)] + [fp5.pack(F(n * n)) for n in (1, 2, 3, 255, 256, 65535, 65536, 3037000499)]
    roots += [fp5.pack(F(n * n, 4 ** k)) for n, k in ((3, 1), (5, 7), (12345, 20))]
    for x in roots:
        checks += 1
        v = fp5.value(x)
        res = run.call('bly_fsqrt', regs={'hl': A, 'bc': R}, mem={A: x, R: b'\xAA' * 8})
        got = bytes(res.mem[R:R + 8])
        if v < 0:
            want = f'sqrt({fp5.show(x)}) has no answer\n'.encode()
            if not (res.failed and res.out == want):
                say_wrong('sqrt', x.hex(), 'should fail', want, 'got', res.out, got.hex())
            continue
        if res.t is not None:
            costs.setdefault('bly_fsqrt', []).append(res.t)
        want = fp5.sqrt(x)
        if res.failed or got[:5] != want or got[5:] != b'\xAA' * 3:
            say_wrong('sqrt', x.hex(), 'gave', got.hex(), repr(res.out), 'want', want.hex(), float(v))
    print('reading (s.float()) against fp5.read, bit for bit')
    import re
    pat = re.compile(rb'\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)')
    texts = [b'0', b'1', b'-1', b'3.25', b'-3.25e2xyz', b'5.', b'.5', b'-.5', b'+.5e-1', b'1e', b'1e+', b'3east',
             b'\t 42 and more', b'-0', b'1E+05', b'007.50', b'0.1', b'0.3', b'123456789012', b'1.7e38', b'1.7014118e38',
             b'1.8e38', b'3.4e38', b'1e-38', b'1.5e-39', b'1.4e-39', b'1e-39', b'2.9e-39', b'1e-40', b'0e999', b'1e-9999',
             b'0.000000000000000000000000000000000000000000000012', b'12345678901234567890123456789012345678901234',
             b'1' * 40, b'1' * 41 + b'e-10', b'9' * 45 + b'e-30', b'0.' + b'0' * 30 + b'1' * 45, b'4294967295',
             b'4294967296', b'65535', b'65536', b'2.5 3', b'5. 3', b'1.5e3 3', b'99999999999e-11', b'1e+00000005',
             b'1.00000000023283064365386962890625', b'-1.00000000023283064365386962890625']   # a tie, 33 digits
    for _ in range(N):
        w = rnd.choice([b'', b' ', b'  \t'])
        n = rnd.choice([f'{rnd.uniform(-1e6, 1e6):.{rnd.randint(0, 9)}f}', f'{rnd.randint(0, 99)}.{rnd.randint(0, 99):02d}',
                        f'{rnd.uniform(1, 10):.{rnd.randint(1, 12)}f}e{rnd.randint(-45, 45)}', str(rnd.randint(-10**12, 10**12)),
                        f'.{rnd.randint(0, 10**9)}', '0' * rnd.randint(1, 50) + str(rnd.randint(1, 10**15))])
        texts.append(w + n.encode() + rnd.choice([b'', b' ', b',', b'x', b'e', b'.', b' 7', b'e+']))
    S = 0xE100
    for t in texts:
        checks += 1
        m = pat.match(t)
        if not m:
            want, err = None, b'"' + t + b'" doesn\'t start with a number\n'
        else:
            try:
                want, err = fp5.read(m.group(1).decode()), None
            except fp5.Overflow:
                want, err = None, m.group(1) + b" doesn't fit in a float\n"
        res = run.call('bly_str_float', regs={'hl': A, 'de': R},
                       mem={A: S.to_bytes(2, 'little') + len(t).to_bytes(2, 'little'), S: t + b'Z#', R: b'\xAA' * 8})
        got = bytes(res.mem[R:R + 8])
        if err is not None:
            if not (res.failed and res.out == err):
                say_wrong('read', t, 'should fail', err, 'got', res.out, got.hex())
            continue
        if res.t is not None:
            costs.setdefault('bly_str_float', []).append(res.t)
        if res.failed or got[:5] != want or got[5:] != b'\xAA' * 3:
            say_wrong('read', t, 'gave', got.hex(), repr(res.out), 'want', want.hex())
    for t in [b'', b'.', b'-', b'abc', b' +x', b'e5', b'.e5']:
        checks += 1
        res = run.call('bly_str_float', regs={'hl': A, 'de': R},
                       mem={A: S.to_bytes(2, 'little') + len(t).to_bytes(2, 'little'), S: t + b'Z#'})
        want = b'"' + t + b'" doesn\'t start with a number\n'
        if not (res.failed and res.out == want):
            say_wrong('read', t, 'should fail', want, 'got', res.out)
    print('the functions against Python, within a tolerance, and their failures word for word')
    import math
    FUNCS = {'bly_fexp': ('exp', math.exp, lambda: F(rnd.uniform(-89.6, 88.2)).limit_denominator(1 << 40), 2e-9),
             'bly_fln': ('ln', math.log, lambda: F(abs(float(fp5.value(rand_float()))) or 1), 2e-9),
             'bly_fsin': ('sin', math.sin, lambda: F(rnd.uniform(-300, 300)), None),
             'bly_fcos': ('cos', math.cos, lambda: F(rnd.uniform(-300, 300)), None),
             'bly_ftan': ('tan', math.tan, lambda: F(rnd.uniform(-10, 10)), None),
             'bly_fatan': ('atan', math.atan, lambda: F(fp5.value(rand_float())), None),
             'bly_fasin': ('asin', math.asin, lambda: F(rnd.uniform(-1.02, 1.02)), None),
             'bly_facos': ('acos', math.acos, lambda: F(rnd.uniform(-1.02, 1.02)), None)}
    ABS = {   # an absolute tolerance, for x and the right answer (test_fp's shapes for the ROM, its constants tighter)
        'sin': lambda x, w: 1e-9 * max(1, abs(x)), 'cos': lambda x, w: 1e-9 * max(1, abs(x)),
        'tan': lambda x, w: (1e-9 * max(1, abs(x)) + 3e-9 * abs(w)) * (1 + w * w), 'atan': lambda x, w: 1e-9,
        'asin': lambda x, w: 1e-9 + 2e-10 / math.sqrt(max(1 - x * x, 1e-18)),
        'acos': lambda x, w: 1e-9 + 2e-10 / math.sqrt(max(1 - x * x, 1e-18))}
    tol0 = 2e-9                                     # ABS errors are scaled to this: under it is within
    for name, (word, fn, draw, tol) in FUNCS.items():
        tol = tol or tol0
        xs = [fp5.pack(draw()) for _ in range(N // 2)] + [fp5.pack(F(v)) for v in (1, 2, F(1, 2), 10, -1, 0, 88, 89, -89, -90)]
        if word in ('asin', 'acos'):
            xs = [x for x in xs if abs(fp5.value(x)) <= 2]
        for x in xs:
            checks += 1
            v = float(fp5.value(x))
            res = run.call(name, regs={'hl': A, 'bc': R}, mem={A: x, R: b'\xAA' * 8})
            got = bytes(res.mem[R:R + 8])
            try:
                want = fn(v)
                ok_domain = not (name == 'bly_fln' and v <= 0) and abs(want) < 1.70141183e38
                if word in ('asin', 'acos') and abs(v) > 1:
                    ok_domain = False
            except (ValueError, OverflowError):
                ok_domain = False
            if not ok_domain:
                msg = f'{word}({fp5.show(x)}) has no answer\n'.encode()
                if not (res.failed and res.out == msg):
                    say_wrong(word, x.hex(), v, 'should fail', msg, 'got', res.out, got.hex())
                continue
            if res.failed or got[5:] != b'\xAA' * 3:
                say_wrong(word, x.hex(), v, 'failed or wrote past', repr(res.out), got.hex())
                continue
            if res.t is not None:
                costs.setdefault(name, []).append(res.t)
            g = float(fp5.value(got[:5]))
            if word in ABS:
                err = abs(g - want) / ABS[word](v, want) * tol0
            elif abs(want) < 2.94e-39:                  # under the smallest 5-byte float: 0 is right
                err = 0.0 if g == 0 else abs(g - want) / abs(want)
            else:
                err = abs(g - want) / abs(want)
            worst = costs.setdefault('worst ' + word, [0.0, ''])
            if err > worst[0]:
                worst[0], worst[1] = err, f'{v!r}'
            if err > tol:
                say_wrong(word, x.hex(), v, 'gave', g, 'want', want, f'error {err:.2e}')
    for word in ('exp', 'ln', 'sin', 'cos', 'tan', 'atan', 'asin', 'acos'):
        w = costs.pop('worst ' + word)
        if word in ABS:
            print(f'  {word}: worst {w[0] / tol0:.3g} of its tolerance, at {w[1]}')
        else:
            print(f'  {word}: worst relative error {w[0]:.3g} at {w[1]}')
    print('printing against fp5.show, text for text')
    import z80gen as G
    shown = [0.5, 0.01, 1e-5, 1.2345678e-5, 1e-6, 99999999.0, 1e8, 123456789.0, 999999999.0, 12345.678, 1234.5,
             65536.0, -65536.0, 1 / 3, 2 / 3, 3.14159265, 1e-38, 4294967295.0, 9.9999e-05, 0.0, -1.0, 1e38,
             99999999.5, 9999999.95, 0.099999999, 9.99999995e-6, 0.0000099999999, 1.7e38, -2.9e-39]
    cases = [G.rom5(x) for x in shown] + [bytes([0, 0, 1, 0, 0]), bytes([0, 0xFF, 0xFF, 0xFF, 0])]
    cases += [rand_float() for _ in range(N)]
    for b in cases:
        checks += 1
        want = fp5.show(b).encode()
        res = run.call('bly_pr_f', regs={'hl': A}, mem={A: b})
        if res.t is not None:
            costs.setdefault('bly_pr_f', []).append(res.t)
        if res.failed or res.out != want:
            say_wrong('print', b.hex(), 'gave', res.out, 'want', want)
    for op in ops + ['bly_fsqrt', 'bly_str_float', 'bly_fexp', 'bly_fln', 'bly_fsin', 'bly_fcos', 'bly_ftan',
                     'bly_fatan', 'bly_fasin', 'bly_facos', 'bly_pr_f']:
        t = costs[op]
        print(f'  {op:9} {len(t)} cases, {min(t):,} to {max(t):,} T, mean {sum(t) // len(t):,}')
    print(f'{checks} checks, {wrong} wrong')
    sys.exit(1 if wrong else 0)


if __name__ == '__main__':
    main()
