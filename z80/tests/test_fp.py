"""fp.asm on a real ROM: floats through the Spectrum's calculator, against Python and the interpreter's words.

Every routine is called on omse-ai's 48K through fprig.Rig, which also checks after every call that BASIC's state
survived (IY, HL', ERR_SP, ERR_NR, X_PTR, an empty calculator stack, MEM). The model is Python: exact Fractions
where the routine is exact (compare, trunc, floor, round, conversions, negate, abs), floats with a tolerance where
the ROM computes (arithmetic, the functions). Each tolerance is printed with the worst error seen, so the notes can
say what held. Failure messages are compared word for word with the interpreter's (barley.py's farith, its function
and cast messages), with the value printed as the ROM prints it.

usage: $OMSE_AI_PYTHON test_fp.py [--lib DIR] [--seed N] [--quick] [--costs]
  --lib DIR   gather the library from DIR instead of z80/lib (for breaking a copy on purpose)
"""
import math
import os
import random
import sys
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
import z80gen as G                                    # noqa: E402
from fprig import Rig                                 # noqa: E402

args = sys.argv[1:]
LIB = args[args.index('--lib') + 1] if '--lib' in args else None
SEED = int(args[args.index('--seed') + 1]) if '--seed' in args else 1
QUICK = '--quick' in args
N = 150 if QUICK else 800
rnd = random.Random(SEED)
MAXF = float(G.rom_value(bytes([255, 0x7F, 255, 255, 255])))     # the ROM's biggest: about 1.7e38
MINF = float(G.rom_value(bytes([1, 0, 0, 0, 0])))                # its smallest: 2^-128
TYPES = ['byte', 'word', 'int', 'long', 'quad']
RANGE = {'byte': (0, 255), 'word': (0, 65535), 'int': (-32768, 32767), 'long': (-2**31, 2**31 - 1),
         'quad': (-2**63, 2**63 - 1)}
WIDTH = {'byte': 1, 'word': 2, 'int': 2, 'long': 4, 'quad': 8}

ROUTINES = ['bly_fadd', 'bly_fsub', 'bly_fmul', 'bly_fdiv', 'bly_fpow', 'bly_fneg', 'bly_fabs', 'bly_fcmp',
            'bly_fsqrt', 'bly_fsin', 'bly_fcos', 'bly_ftan', 'bly_fasin', 'bly_facos', 'bly_fatan', 'bly_fln',
            'bly_fexp', 'bly_ftrunc', 'bly_ffloor', 'bly_fround', 'bly_f_from_u16', 'bly_f_from_i16',
            'bly_f_from_i64', 'bly_f_to_int', 'bly_pr_f']
wrong = 0
worst = {}                                            # routine -> the worst error seen, against its tolerance


def check(what, ok, *detail):
    global wrong
    if not ok:
        wrong += 1
        if wrong <= 25:
            print('WRONG', what, *detail)


def val(b):
    return G.rom_value(bytes(b))


def rand_float(lo=-30, hi=30, ints=0.2):
    """a float the ROM can hold exactly: a random 32-bit mantissa at a random scale, sometimes a short-form integer"""
    if rnd.random() < ints:
        return float(rnd.randint(-65535, 65535))
    m = rnd.randint(1 << 31, (1 << 32) - 1)
    x = math.ldexp(m, rnd.randint(lo, hi) - 32)
    return -x if rnd.random() < 0.5 else x


def full_form(x):
    """x in the full form even when it's a short-form whole number (both are legal, and the ROM makes both)"""
    if x == 0:
        return bytes(5)
    m, e = math.frexp(abs(x))
    mi = int(m * 2 ** 32)
    return bytes([e + 128, ((mi >> 24) & 0x7F) | (0x80 if x < 0 else 0), (mi >> 16) & 255, (mi >> 8) & 255, mi & 255])


def form(x):
    return full_form(x) if x == int(x) and abs(x) <= 65535 and rnd.random() < 0.3 else G.rom5(x)


def rel_err(got, want, floor=0.0):
    return abs(got - want) / max(abs(want), floor, 1e-300)


def note(name, err, tol, case=''):
    w = worst.setdefault(name, [0.0, tol, ''])
    if err > w[0]:
        w[0], w[2] = err, case


def rom_print(rig, b):
    return rig.call('bly_pr_f', hl=rig.X, mem={rig.X: bytes(b)}).out


# -- arithmetic -------------------------------------------------------------------------------------------------
def py_op(op, a, b):
    if op == '+':
        return a + b
    if op == '-':
        return a - b
    if op == '*':
        return a * b
    if op == '/':
        return a / b
    return math.pow(a, b)


ARITH = {'+': 'bly_fadd', '-': 'bly_fsub', '*': 'bly_fmul', '/': 'bly_fdiv', '**': 'bly_fpow'}
TOL = {'+': 1e-9, '-': 1e-9, '*': 1e-9, '/': 1e-9, '**': 1e-9}   # ** is exp(b ln a): scaled by b ln a below


def arith_case(rig, op, a, b, ab=None, bb=None):
    ab, bb = ab or form(a), bb or form(b)
    a, b = float(val(ab)), float(val(bb))
    r = rig.call(ARITH[op], hl=rig.X, de=rig.Y, bc=rig.R, mem={rig.X: ab, rig.Y: bb, rig.R: b'\xAA' * 8})
    try:
        want = py_op(op, a, b)
        err = None
    except ZeroDivisionError:
        err = 'division by zero'
    except OverflowError:
        err = 'float overflow'
    except ValueError:
        err = f'float {op} has no answer'
    if err is None and abs(want) > MAXF:
        err = 'float overflow'
    if err:
        check(f'{a!r} {op} {b!r} fails', r.failed and r.out == err + '\n', repr(r.out))
        return r
    if r.failed and abs(want) > MAXF * 0.999999:
        return r                                           # at the very edge the ROM may round over
    check(f'{a!r} {op} {b!r}', not r.failed, repr(r.out))
    if r.failed:
        return r
    got = r.mem(rig.R, 8)
    check(f'{a!r} {op} {b!r} writes 5 bytes only', got[5:] == b'\xAA' * 3, got.hex())
    g = float(val(got[:5]))
    if abs(want) < MINF * 2:                               # underflow: the ROM gives 0
        check(f'{a!r} {op} {b!r} underflows', abs(g) < MINF * 4, g)
        return r
    e = rel_err(g, want, max(abs(a), abs(b)) if op in '+-' else 0.0)   # + and -: to the operands' precision
    tol = TOL[op]
    if op == '**':                       # exp(b ln a): ln a's error, times b, becomes exp's relative error
        tol = 1e-9 + 2 * COND * abs(b * math.log(abs(a))) if a else 1e-9
    note(op, e / tol, 1.0, f'{a!r} {op} {b!r} = {want!r}, got {g!r}')
    check(f'{a!r} {op} {b!r} = {want!r}', e <= tol, f'got {g!r}, error {e:.2e}')
    check(f'{a!r} {op} {b!r}: no slipped -65536', bytes(got[:5]) != bytes([0, 0xFF, 0, 0, 0]))
    return r


def test_arith(rig):
    print('arithmetic: + - * / ** against Python')
    for op in '+-*/':
        for _ in range(N):
            arith_case(rig, op, rand_float(), rand_float())
        for _ in range(N // 8):                             # near each other: cancellation, and short forms
            a = rand_float(ints=0.5)
            arith_case(rig, op, a, a * (1 + rnd.choice([0, 1e-9, -1e-9, 2 ** -31])))
        for _ in range(N // 8):                             # overflow and underflow
            arith_case(rig, op, rand_float(100, 126), rand_float(100, 126))
            arith_case(rig, op, rand_float(-126, -100), rand_float(100, 126))
    for a, b in [(-65535.0, 1.0), (-65535.0, -1.0), (65535.0, 1.0), (-65536.0, 1.0), (32767.0, 32769.0),
                 (-1.0, -65535.0), (0.0, 0.0), (1.0, 0.0), (-0.0, 5.0)]:
        for op in '+-*/':
            arith_case(rig, op, a, b)
    arith_case(rig, '-', -65535.0, 1.0)                      # the ROM's own slip: 00 FF 00 00 00
    for _ in range(N // 2):
        arith_case(rig, '**', abs(rand_float(-10, 10)), rand_float(-3, 4))
    for a, b in [(0.0, 0.0), (0.0, 2.0), (0.0, -1.0), (2.0, 0.0), (-2.0, 2.0), (-2.0, 3.0), (-8.0, 1 / 3),
                 (-2.0, 0.5), (-1.0, 1e30), (-3.0, -2.0), (-3.0, -3.0), (10.0, 38.0), (10.0, 39.0), (2.0, 127.0),
                 (2.0, 126.5), (-2.0, 127.0), (-2.0, 128.0), (-1.5, 2 ** 40), (1.0, 1e38)]:
        arith_case(rig, '**', a, b)
    for _ in range(N // 4):                                  # negative bases with whole exponents
        arith_case(rig, '**', -abs(rand_float(-3, 3)), float(rnd.randint(-12, 12)))


# -- compare, negate, abs ---------------------------------------------------------------------------------------
def test_cmp(rig):
    print('compare, negate, abs: exact')
    cases = []
    for _ in range(N):
        a = rand_float(-126, 126, ints=0.3)
        b = rnd.choice([a, -a, rand_float(-126, 126, ints=0.3), a * (1 + 2 ** -31)])
        cases.append((a, b))
    cases += [(0.0, 0.0), (0.0, -1.0), (-1.0, 0.0), (1.0, 1.0), (65535.0, 65536.0), (-65535.0, -65536.0),
              (-65536.0, -65535.0), (MINF, 0.0), (-MINF, 0.0), (MAXF, -MAXF), (1.0, -1.0), (-1.0, 1.0)]
    for a, b in cases:
        ab, bb = (rnd.choice([form, full_form, G.rom5])(x) for x in (a, b))
        va, vb = val(ab), val(bb)
        r = rig.call('bly_fcmp', hl=rig.X, de=rig.Y, mem={rig.X: ab, rig.Y: bb})
        want = 0xFF if va < vb else (0 if va == vb else 1)
        check(f'cmp {ab.hex()} {bb.hex()}', r.a == want, f'got {r.a}, want {want}')
    slip = bytes([0, 0xFF, 0, 0, 0])                         # the ROM's -65536, if one ever got through
    r = rig.call('bly_fcmp', hl=rig.X, de=rig.Y, mem={rig.X: slip, rig.Y: G.rom5(-65535.0)})
    check('cmp: the slipped -65536 is below -65535', r.a == 0xFF, r.a)
    for a, _ in cases:
        ab = rnd.choice([form, full_form])(a)
        for name, fn in (('bly_fneg', lambda v: -v), ('bly_fabs', abs)):
            r = rig.call(name, hl=rig.X, bc=rig.R, mem={rig.X: ab, rig.R: b'\xAA' * 8})
            got = r.mem(rig.R, 8)
            check(f'{name} {ab.hex()}', val(got[:5]) == fn(val(ab)) and got[5:] == b'\xAA' * 3, got.hex())
            check(f'{name} {ab.hex()}: no slipped -65536', got[:5] != slip)
    for a in (3.5, -2.0, 0.0, -65535.0):                      # in place: r is x
        r = rig.call('bly_fneg', hl=rig.X, bc=rig.X, mem={rig.X: G.rom5(a)})
        check(f'fneg {a} in place', val(r.mem(rig.X, 5)) == -F(a), r.mem(rig.X, 5).hex())


# -- trunc, floor, round ----------------------------------------------------------------------------------------
def test_whole(rig):
    print('trunc, floor, round: exact (round is floor(x + 0.5))')
    xs = [rand_float(-40, 70, ints=0.2) for _ in range(N)]
    xs += [k + h for k in (-65537, -65536, -65535, -3, -2, -1, 0, 1, 2, 65535, 65536) for h in (-0.5, 0, 0.25, 0.5, 0.75)]
    xs += [2.0 ** 31 - 0.5, 2.0 ** 31 + 1, -(2.0 ** 31) - 0.5, 2.0 ** 32 - 1, 0.5 - 2 ** -33, -0.5 + 2 ** -33,
           MINF, -MINF, MAXF, -MAXF, 0.5, -0.5, 1.5, -1.5, 2.5, -2.5]
    for x in xs:
        xb = rnd.choice([form, full_form])(x) if x == int(x) and abs(x) <= 65535 else G.rom5(x)
        v = val(xb)
        for name, fn in (('bly_ftrunc', math.trunc), ('bly_ffloor', math.floor), ('bly_fround', lambda q: math.floor(q + F(1, 2)))):
            r = rig.call(name, hl=rig.X, bc=rig.R, mem={rig.X: xb, rig.R: b'\xAA' * 8})
            got = r.mem(rig.R, 8)
            check(f'{name}({float(v)!r}) [{xb.hex()}]', val(got[:5]) == fn(v) and got[5:] == b'\xAA' * 3,
                  f'got {float(val(got[:5]))!r} ({got[:5].hex()}), want {fn(v)}')
            check(f'{name}({float(v)!r}): no slipped -65536', got[:5] != bytes([0, 0xFF, 0, 0, 0]))


# -- conversions -------------------------------------------------------------------------------------------------
def test_conv(rig):
    print('conversions: every integer type to a float, and back with the range check')
    for n in [0, 1, 255, 256, 65535, rnd.randint(0, 65535)] + [rnd.randint(0, 65535) for _ in range(N // 8)]:
        r = rig.call('bly_f_from_u16', hl=n, bc=rig.R, mem={rig.R: b'\xAA' * 8})
        got = r.mem(rig.R, 8)
        check(f'from_u16 {n}', got[:5] == G.rom5(float(n)) and got[5:] == b'\xAA' * 3, got.hex())
    for n in [0, 1, -1, 32767, -32768, -32767] + [rnd.randint(-32768, 32767) for _ in range(N // 8)]:
        r = rig.call('bly_f_from_i16', hl=n & 0xFFFF, bc=rig.R, mem={rig.R: b'\xAA' * 8})
        got = r.mem(rig.R, 8)
        check(f'from_i16 {n}', got[:5] == G.rom5(float(n)) and got[5:] == b'\xAA' * 3, got.hex())
    qs = [0, 1, -1, 65535, -65535, 65536, -65536, 65537, -65537, 2**31 - 1, -2**31, 2**32 - 1, 2**32, 2**32 + 1,
          2**32 + 2, 2**33 - 1, 2**33 + 1, 2**33 + 2, 2**63 - 1, -2**63, -2**63 + 1, (1 << 40) + (1 << 7),
          (1 << 40) + (1 << 8) - 1]
    qs += [rnd.randint(-2**63, 2**63 - 1) >> rnd.randint(0, 62) for _ in range(N)]
    for q in qs:
        r = rig.call('bly_f_from_i64', hl=rig.X, bc=rig.R, mem={rig.X: (q & (2**64 - 1)).to_bytes(8, 'little'),
                                                                rig.R: b'\xAA' * 8})
        got = r.mem(rig.R, 8)
        want = G.rom5(q)                                     # exact: a Fraction of the int, rounded half up
        check(f'from_i64 {q}', got[:5] == want and got[5:] == b'\xAA' * 3, got[:5].hex(), want.hex())
        check(f'from_i64 {q} is near', abs(val(got[:5]) - q) <= abs(q) * F(1, 2**32))
    # back: truncating, and the range check at every type's edges
    for t in TYPES:
        lo, hi = RANGE[t]
        xs = [lo, hi, lo - 1, hi + 1, lo - 0.5, hi + 0.5, lo + 0.5, hi - 0.5, 0, -0.5, 0.5, -1, 1, -0.99, 255.9,
              -32768.5, -32769, 2.0 ** 63, -2.0 ** 63, 2.0 ** 64, MAXF, -MAXF, MINF]
        xs += [rand_float(-5, 70) for _ in range(N // 4)]
        for x in xs:
            xb = G.rom5(float(x))
            v = val(xb)
            tv = math.trunc(v)
            r = rig.call('bly_f_to_int', hl=rig.X, a=TYPES.index(t), de=rig.R, mem={rig.X: xb, rig.R: b'\xAA' * 9})
            if lo <= tv <= hi:
                got = r.mem(rig.R, 9)
                n = WIDTH[t]
                check(f'{t}({float(v)!r})', not r.failed and int.from_bytes(got[:n], 'little', signed=t not in ('byte', 'word')) == tv
                      and got[n:] == b'\xAA' * (9 - n), r.out, got.hex())
            else:
                shown = rom_print(rig, xb)
                check(f'{t}({float(v)!r}) fails', r.failed and r.out == f"{shown} doesn't fit in {'an' if t[0] in 'aeiou' else 'a'} {t}\n", repr(r.out))


# -- the functions -------------------------------------------------------------------------------------------------
# The ROM's exp carries about 2^-32 of its argument's size as an absolute error, which it turns into a relative one:
# so exp is allowed 6e-10 times |x| more than 1e-9, and sqrt (exp(ln x / 2)) and ** (exp(b ln a)) twice that times
# their exponent, ln's own error riding along. The trig functions reduce their argument with 32 bits, so they're
# allowed 3e-9 times |x| (and tan its slope); asin and acos (by atan(x / sqrt(1 - x^2))) lose 1 - x^2 near +-1.
COND = 4e-10
FUNCS = {  # name: (python, the domain to draw from, the tolerance for x and the right answer)
    'sqrt': (math.sqrt, lambda: abs(rand_float(-60, 60)), lambda x, w: abs(w) * (1e-9 + 2 * COND * abs(math.log(x) / 2))),
    'sin': (math.sin, lambda: rand_float(-8, 7), lambda x, w: 3e-9 * max(1, abs(x))),
    'cos': (math.cos, lambda: rand_float(-8, 7), lambda x, w: 3e-9 * max(1, abs(x))),
    'tan': (math.tan, lambda: rand_float(-8, 2), lambda x, w: (3e-9 * max(1, abs(x)) + 1e-8 * abs(w)) * (1 + w * w)),
    'asin': (math.asin, lambda: rnd.uniform(-1, 1), lambda x, w: 3e-9 + 2e-10 / math.sqrt(max(1 - x * x, 1e-18))),
    'acos': (math.acos, lambda: rnd.uniform(-1, 1), lambda x, w: 3e-9 + 2e-10 / math.sqrt(max(1 - x * x, 1e-18))),
    'atan': (math.atan, lambda: rand_float(-20, 20), lambda x, w: 3e-9),
    'ln': (math.log, lambda: abs(rand_float(-120, 120)), lambda x, w: 3e-9 + 1e-9 * abs(w)),
    'exp': (math.exp, lambda: rnd.uniform(-88, 88), lambda x, w: abs(w) * (1e-9 + 1.5 * COND * abs(x))),
}


def test_funcs(rig):
    print('functions: the ROM against Python, and every failure')
    for name, (fn, draw, tolf) in FUNCS.items():
        xs = [draw() for _ in range(N // 3)]
        for x in xs:
            xb = G.rom5(x)
            x = float(val(xb))
            r = rig.call('bly_f' + name, hl=rig.X, bc=rig.R, mem={rig.X: xb, rig.R: b'\xAA' * 8})
            want = fn(x)
            got = r.mem(rig.R, 8)
            check(f'{name}({x!r})', not r.failed, repr(r.out))
            if r.failed:
                continue
            g = float(val(got[:5]))
            tol = tolf(x, want)
            err = abs(g - want) / max(tol, 1e-300)                            # in units of the tolerance
            note(name, err, 1.0, f'{name}({x!r}) = {want!r}, got {g!r}')
            check(f'{name}({x!r}) = {want!r}', err <= 1, f'got {g!r}', f'{err:.2f} tolerances')
            check(f'{name}({x!r}) writes 5 bytes', got[5:] == b'\xAA' * 3)
    bad = [('sqrt', -1.0), ('sqrt', -1e-30), ('ln', 0.0), ('ln', -2.0), ('asin', 1.0000001), ('asin', -2.0),
           ('acos', 2.0), ('acos', -1.5), ('exp', 89.0), ('exp', 1000.0), ('tan', math.pi / 2)]
    for name, x in bad:
        xb = G.rom5(x)
        r = rig.call('bly_f' + name, hl=rig.X, bc=rig.R, mem={rig.X: xb})
        shown = rom_print(rig, xb)
        check(f'{name}({x}) fails', r.failed and r.out == f'{name}({shown}) has no answer\n', repr(r.out))
    for name, x in [('sqrt', 0.0), ('ln', 1.0), ('exp', 0.0), ('asin', 1.0), ('acos', -1.0), ('sin', 0.0)]:
        r = rig.call('bly_f' + name, hl=rig.X, bc=rig.R, mem={rig.X: G.rom5(x)})
        check(f'{name}({x}) is fine', not r.failed, repr(r.out))


# -- printing ------------------------------------------------------------------------------------------------------
def test_print(rig):
    print("printing: the ROM's PRINT-FP, caught and sent on through bly_out")
    col = rig.sym['bly_col']
    for x in [0.0, 1.0, -1.0, 0.5, -0.5, 1 / 3, 3.5, 1e10, 123456789.0, 1e-5, 0.0001, MAXF, MINF, -65536.0, 65535.0]\
            + [rand_float(-126, 126) for _ in range(N // 4)]:
        xb = G.rom5(x)
        rig.poke16(col, 7)
        r = rig.call('bly_pr_f', hl=rig.X, mem={rig.X: xb})
        s = r.out
        check(f'print {x!r}: one line of number', s and '\n' not in s and ' ' not in s, repr(s))
        try:
            p = float(s.replace('E', 'e'))
        except ValueError:
            check(f'print {x!r} is a number', False, repr(s))
            continue
        check(f'print {x!r}: 8 digits', rel_err(p, float(val(xb)), 1e-38) <= 6e-8, repr(s))
        check(f'print {x!r}: the column moves on', rig.zx.peek16(col) == 7 + len(s), rig.zx.peek16(col))


# -- literals: the generator's rom5 ------------------------------------------------------------------------------
def test_literals(rig):
    print("literals: z80gen's rom5 is the nearest 5 bytes (half away from zero), and the ROM reads them back")
    check('0.1 is 7D 4C CC CC CD', G.rom5(0.1).hex() == '7d4ccccccd', G.rom5(0.1).hex())   # (the ROM's own 1/10: ...CC)
    check('1.5 is 81 40 00 00 00', G.rom5(1.5).hex() == '8140000000', G.rom5(1.5).hex())
    check('-65535 is short', G.rom5(-65535.0).hex() == '00ff010000', G.rom5(-65535.0).hex())
    check('-65536 is in full', G.rom5(-65536.0).hex() == '9180000000', G.rom5(-65536.0).hex())
    for _ in range(N * 4):
        x = rnd.choice([rnd.uniform(-1e6, 1e6), math.ldexp(rnd.random(), rnd.randint(-120, 120)) * rnd.choice([1, -1])])
        b = G.rom5(x)
        v = val(b)
        if b[0] == 0:
            check(f'rom5({x!r}) short only for whole numbers', v == x and x == int(x), b.hex())
            continue
        ulp = F(2) ** (b[0] - 128 - 32)
        err = abs(v - F(x))
        check(f'rom5({x!r}) is the nearest', err < ulp / 2 or (err == ulp / 2 and abs(v) > abs(F(x))), b.hex(), float(err / ulp))
    for x in (1.7e38, 1e-38, 1e-39, 3e-39):
        try:
            b = G.rom5(x)
            check(f'rom5({x}) in range', 1 <= b[0] or x < MINF, b.hex())
        except G.GenError:
            check(f'rom5({x}) is too big', x > MAXF)
    try:
        G.rom5(1e39)
        check('rom5(1e39) refuses', False)
    except G.GenError as e:
        check('rom5(1e39) says why', 'too big for the Spectrum' in str(e), str(e))
    for x in (0.1, 1 / 3, 1e10, -2.5e-20, 123.456):                  # the ROM agrees: it prints them as near
        p = float(rom_print(rig, G.rom5(x)).replace('E', 'e'))
        check(f'the ROM reads rom5({x!r})', rel_err(p, x) <= 6e-8, p)


# -- costs ---------------------------------------------------------------------------------------------------------
def costs(rig):
    print('\ncosts (T-states, interrupts off, the call included):')
    rows = [('bly_fadd', 1.5, 2.25), ('bly_fadd', 12345.678, 0.001), ('bly_fsub', 1e10, 3.0),
            ('bly_fmul', 1.5, 2.25), ('bly_fmul', 3.14159, 2.71828), ('bly_fdiv', 1.0, 3.0), ('bly_fdiv', 22.0, 7.0),
            ('bly_fpow', 2.0, 10.0), ('bly_fpow', 1.5, 2.5), ('bly_fpow', -2.0, 3.0)]
    out = []
    for name, a, b in rows:
        r = rig.call(name, hl=rig.X, de=rig.Y, bc=rig.R, mem={rig.X: G.rom5(a), rig.Y: G.rom5(b)})
        out.append((f'{name} {a:g}, {b:g}', r.t))
    for name, x in [('bly_fsqrt', 2.0), ('bly_fsqrt', 71503.5), ('bly_fsin', 1.0), ('bly_fcos', 1.0),
                    ('bly_ftan', 1.0), ('bly_fasin', 0.5), ('bly_facos', 0.5), ('bly_fatan', 1.0), ('bly_fln', 10.0),
                    ('bly_fexp', 1.0), ('bly_ftrunc', -2.5), ('bly_ffloor', -2.5), ('bly_fround', 1234.5678),
                    ('bly_ffloor', 13.15), ('bly_fneg', 1.5), ('bly_fabs', -1.5)]:
        r = rig.call(name, hl=rig.X, bc=rig.R, mem={rig.X: G.rom5(x)})
        out.append((f'{name} {x:g}', r.t))
    for a, b in [(1.5, 2.25), (100.0, 100.0), (-3.0, 2.0)]:
        r = rig.call('bly_fcmp', hl=rig.X, de=rig.Y, mem={rig.X: G.rom5(a), rig.Y: G.rom5(b)})
        out.append((f'bly_fcmp {a:g}, {b:g}', r.t))
    r = rig.call('bly_f_from_u16', hl=1234, bc=rig.R)
    out.append(('bly_f_from_u16', r.t))
    r = rig.call('bly_f_from_i16', hl=(-1234) & 0xFFFF, bc=rig.R)
    out.append(('bly_f_from_i16', r.t))
    for q in (71530, 940200, 2**40 + 12345, -2**62):
        r = rig.call('bly_f_from_i64', hl=rig.X, bc=rig.R, mem={rig.X: (q & (2**64 - 1)).to_bytes(8, 'little')})
        out.append((f'bly_f_from_i64 {q}', r.t))
    for t, x in [('int', 13.15), ('quad', 13.15), ('quad', 4.5e15), ('byte', 300.0)]:
        r = rig.call('bly_f_to_int', hl=rig.X, a=TYPES.index(t), de=rig.R, mem={rig.X: G.rom5(x)})
        out.append((f'bly_f_to_int {t} {x:g}' + (' (fails)' if r.failed else ''), r.t))
    for x in (3.5, 1 / 3, 123456789.0, -1.2345e-20):
        r = rig.call('bly_pr_f', hl=rig.X, mem={rig.X: G.rom5(x)})
        out.append((f'bly_pr_f {x:g} -> {r.out}', r.t))
    for k, t in out:
        print(f'  {k:42} {t:8,}')


def main():
    rig = Rig(ROUTINES, lib_dir=LIB)
    s = rig.sym
    print(f"fp.asm: {s['bly_pr_f.buf'] + 16 - s['bly_fadd']} bytes (code and its scratch)")
    for t in (test_literals, test_cmp, test_whole, test_conv, test_arith, test_funcs, test_print):
        t(rig)
    if '--costs' in args:
        costs(rig)
    print('\nworst errors (tolerance in brackets):')
    for k, (e, tol, case) in worst.items():
        print(f'  {k:6} {e:.3g}  [{tol:g}]' if tol != 1.0 else f'  {k:6} {e:.3g} of its tolerance', '  ', case)
    print(f'{wrong} wrong')
    sys.exit(1 if wrong else 0)


if __name__ == '__main__':
    main()
