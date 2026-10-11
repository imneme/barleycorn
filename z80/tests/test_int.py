"""The integer library against its meaning: interp/barley.py's own arith, fit,
wrap and the builtins.

Every routine gets hand-picked edges and random inputs; every failure is
compared byte for byte, " at line N" and all, with bly_line set to a random
line (through a test-only wrapper, since bly_test_init clears it after set16).
Results are written over guard bytes, and often onto an operand; nothing else
from A000h to EC3Fh may change, and every register a header's clobbers: leaves
out must come back as it went in.

Run it with omse-ai's Python ($OMSE_AI_PYTHON). In the environment,
ONLY=divide runs one section, and SEED=7 another seed.
"""
import argparse
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'interp'))
from harness import Runner                                     # noqa: E402
import barley                                                   # noqa: E402
from barley import BarleyError, arith, fit, wrap, BYTE, WORD, INT, LONG, QUAD, DWORD   # noqa: E402

ap = argparse.ArgumentParser(prog='test_int.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('count', type=int, nargs='?', default=1500, help='random cases per routine (default 1500)')
COUNT = ap.parse_args().count                  # read here: test_int_mutants imports this with its own count
SEED = int(os.environ.get('SEED', '1009'))
random.seed(SEED)

A, B, R, Q = 0xE000, 0xE010, 0xE020, 0xE030       # operands and results; each has room for guard bytes after it
GUARD = 0xA5


# -- the meaning -------------------------------------------------------------------------------------------------

def outcome(f):
    """('ok', value) or ('fail', the words the interpreter prints, " at line N" included)"""
    try:
        return 'ok', f()
    except BarleyError as e:
        return 'fail', str(e)


# the builtins live inside Interp.e_call, evaluated from the tree; these are its lines, word for word, with the
# arguments already evaluated (cross-checked below against whole Barley programs run by barley.run)
def b_mod(a, b, t, line):
    if b == 0:
        raise BarleyError('mod by zero', line)
    return a % b


def b_gcd(a, b, t, line):
    a, b = abs(a), abs(b)
    while b:
        a, b = b, a % b
    return fit(a, t, line)


def b_lcm(a, b, t, line):
    a, b = abs(a), abs(b)
    if a == 0 or b == 0:
        return 0
    g, x = a, b
    while x:
        g, x = x, g % x
    return fit(a // g * b, t, line)


def b_abs(a, t, line):
    return fit(abs(a), t, line)


def crosscheck_builtins(n=60):
    """the mirrored builtins against barley.run on whole programs: the same values, the same failures"""
    import io
    bad = 0
    names = {INT: 'int', LONG: 'long', QUAD: 'quad'}
    cases = []
    for _ in range(n):
        t = random.choice([INT, LONG, QUAD])
        a, b = rnd(t), rnd(t)
        if random.random() < 0.2:
            b = random.choice([0, 1, -1, t.lo, t.hi])
        if random.random() < 0.1:
            a = random.choice([0, t.lo, t.hi])
        cases.append((t, a, b))
    for t, a, b in cases:
        for fn, mirror in (('mod', b_mod), ('gcd', b_gcd), ('lcm', b_lcm), ('abs', None)):
            tn = names[t]
            lit = lambda v: f'({v + 1} - 1)' if v == t.lo else str(v)      # MIN has no literal of its own
            if fn == 'abs':
                src = f'func main()\n  var a: {tn} = {lit(a)}\n  print abs(a)\nend\n'
                want = outcome(lambda: b_abs(a, t, 3))
            else:
                src = f'func main()\n  var a: {tn} = {lit(a)}\n  var b: {tn} = {lit(b)}\n  print {fn}(a, b)\nend\n'
                want = outcome(lambda: mirror(a, b, t, 4))
            out = io.StringIO()
            try:
                barley.run(src, b'', out=out)
                got = ('ok', int(out.getvalue()))
            except BarleyError as e:
                got = ('fail', str(e))
            if got != want:
                bad += 1
                print('  MIRROR DIFFERS', fn, tn, a, b, got, want)
    return bad, len(cases) * 4


# -- values ------------------------------------------------------------------------------------------------------

def rnd(t):
    """a random value of type t, its bit length spread evenly so every width of operand is exercised"""
    bits = t.bits - (1 if t.signed else 0)
    n = random.randint(0, bits)
    v = random.getrandbits(n) if n else 0
    if n and random.random() < 0.3:
        v |= 1 << (n - 1)
    if t.signed and random.random() < 0.5:
        v = -v - (1 if random.random() < 0.05 else 0)
    return max(t.lo, min(t.hi, v))


def edges(t):
    out = {0, 1, 2, 3, 7, 10, 255, 256, 257, 65535, 65536, t.hi, t.hi - 1, t.lo, t.lo + 1}
    if t.signed:
        out |= {-1, -2, -3, -7, -10, -255, -256, -65536, -65535, t.hi // 2, t.lo // 2, (t.hi + 1) // 2 + 1}
        out |= {1 << (t.bits // 2 - 1), -(1 << (t.bits // 2 - 1)), (1 << (t.bits // 2)) - 1, 1 << (t.bits // 2)}
        out |= {46341, -46341, 3037000499, 3037000500, -3037000500}     # around the square roots of 2^31, 2^63
    return sorted(v for v in out if t.lo <= v <= t.hi)


def enc(v, n):
    return (v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little')


def dec(b, signed=True):
    return int.from_bytes(b, 'little', signed=signed)


# -- running and comparing ---------------------------------------------------------------------------------------

class Tally:
    all = []

    def __init__(self, name):
        self.name, self.n, self.bad, self.ts = name, 0, 0, []
        Tally.all.append(self)

    def check(self, ok, *info):
        self.n += 1
        if not ok:
            self.bad += 1
            if self.bad <= 6:
                print('  WRONG', self.name, *info)

    def summary(self):
        ts = sorted(self.ts)
        cost = f'T: median {ts[len(ts) // 2]}, worst seen {ts[-1]}' if ts else ''
        return f'{self.name:16} {self.n:6} cases  {"all right" if not self.bad else str(self.bad) + " WRONG":10}  {cost}'


# bly_test_init sets bly_line to 0 after the harness's set16 has poked it, so each routine is called through a
# test-only wrapper that stores the line first. Its cost is measured once and taken off every T-state count.
def wrappers(names):
    out = ['bly_t_line: dw 0', 'bly_t_ret: ret']
    for n in list(names) + ['bly_t_ret']:
        out += [f't_{n}:', ' push hl', ' ld hl,(bly_t_line)', ' ld (bly_line),hl', ' pop hl', f' jp {n}']
    return '\n'.join(out) + '\n'


def runner(names, extra=''):
    r = Runner(names, extra=wrappers(names) + extra)
    r.overhead = r.call('t_bly_t_ret').t - r.call('bly_t_ret').t
    return r


CHECKED = (0xA000, 0xEC40)       # the arena and the operands; from EC40h up, the bench paints the stack with A5h


def clobbers():
    """every routine's clobbers: from the headers in lib/, as a set of registers (A, F, B, C, D, E, H, L, IX)"""
    out, name = {}, None
    lib = os.path.join(HERE, '..', 'lib')
    for fn in sorted(os.listdir(lib)):
        if not fn.endswith('.asm'):
            continue
        for ln in open(os.path.join(lib, fn)):
            if not ln.startswith(';;'):
                break
            words = ln[2:].split()
            if words and words[0].startswith('bly_'):
                name = words[0]
            m = re.search(r'clobbers:\s*(.*)', ln)
            if m and name:
                regs = set()
                for w in m.group(1).split():
                    regs |= {'IX'} if w == 'IX' else set(w)
                out[name] = regs
    return out


CLOBBERS = clobbers()


def run(runner, routine, regs, mem, results, line):
    """call with every register not used for an input set at random; then check the untouched memory (all of
    CHECKED except the results' bytes) and the registers the header's clobbers: promises to keep"""
    lo, hi = CHECKED
    image = bytearray(hi - lo)                         # as it was loaded
    for addr, data in mem.items():
        image[addr - lo:addr - lo + len(data)] = data
    regs = dict(regs)
    for rp in ('hl', 'de', 'bc', 'ix'):
        regs.setdefault(rp, random.randrange(65536))
    regs.setdefault('a', random.randrange(256))
    res = runner.call('t_' + routine, regs=regs, mem=mem, set16={'bly_t_line': line})
    if res.t is not None:
        res.t -= runner.overhead
    after = bytearray(res.mem[lo:hi])
    for addr, n in results:
        if not res.failed:
            image[addr - lo:addr - lo + n] = after[addr - lo:addr - lo + n]
    res.stray = [hex(lo + i) for i in range(len(image)) if image[i] != after[i]][:4]
    res.lost = []
    kept = {'A', 'F', 'B', 'C', 'D', 'E', 'H', 'L', 'IX'} - CLOBBERS.get(routine, {'A', 'F', 'B', 'C', 'D', 'E', 'H', 'L', 'IX'})
    pairs = {'B': ('bc', 8), 'C': ('bc', 0), 'D': ('de', 8), 'E': ('de', 0), 'H': ('hl', 8), 'L': ('hl', 0)}
    for reg in kept:
        if reg == 'IX':
            same = res.regs['ix'] == regs['ix']
        elif reg == 'A':
            same = res.regs['a'] == regs['a']
        elif reg == 'F':
            same = True                                # the driver doesn't set F, so there's nothing to compare
        else:
            rp, sh = pairs[reg]
            same = (res.regs[rp] >> sh & 0xFF) == (regs[rp] >> sh & 0xFF)
        if not same:
            res.lost.append(reg)
    return res


def compare(tally, res, want, got_fn, info):
    """want: ('ok', value) or ('fail', words); got_fn(res) reads the value when the routine returned"""
    if want[0] == 'fail':
        ok = res.failed and res.out.decode() == want[1] + '\n'
        tally.check(ok, info, 'wanted', repr(want[1]), 'got', res.out, 'failed' if res.failed else 'returned')
        return
    if res.failed:
        tally.check(False, info, 'wanted', want[1], 'but it failed:', res.out)
        return
    got = got_fn(res)
    ok = got == want[1] and not res.out and not res.stray and not res.lost
    tally.check(ok, info, 'wanted', want[1], 'got', got, 'stray writes' if res.stray else '', res.stray, res.out,
                'lost ' + ' '.join(res.lost) if res.lost else '')
    if ok:
        tally.ts.append(res.t)


# -- 16-bit, in registers ------------------------------------------------------------------------------------------

def pairs16(t):
    es = edges(t)
    out = [(a, b) for a in es for b in es]
    out += [(rnd(t), rnd(t)) for _ in range(COUNT)]
    out += [(random.randint(t.lo, t.hi), random.randint(t.lo, t.hi)) for _ in range(COUNT // 3)]
    return out


def test16(r):
    s16 = lambda v: v - 65536 if v >= 32768 else v
    line = lambda: random.randint(1, 4095)                  # the program's own lines: (file << 12) | line
    for name, t in (('bly_mul_u16', WORD), ('bly_mul_i16', INT)):
        tl = Tally(name)
        for a, b in pairs16(t):
            L = line()
            res = run(r, name, {'hl': a & 0xFFFF, 'de': b & 0xFFFF}, {}, [], L)
            want = outcome(lambda: arith('*', a, b, t, L))
            conv = s16 if t.signed else (lambda v: v)
            compare(tl, res, want, lambda res: conv(res.regs['hl']),
                    (a, b))
    for name, t in (('bly_divmod_u16', WORD), ('bly_divmod_i16', INT), ('bly_rem_i16', INT)):
        tl = Tally(name)
        conv = s16 if t.signed else (lambda v: v)
        for a, b in pairs16(t):
            L = line()
            res = run(r, name, {'hl': a & 0xFFFF, 'de': b & 0xFFFF}, {}, [], L)
            if name == 'bly_rem_i16':
                if b == -1 and a == t.lo:
                    want = ('ok', (t.lo, 0))                  # the wrapped quotient, and the remainder 0
                else:
                    want = outcome(lambda: (arith('/', a, b, t, L), arith('%', a, b, t, L)))
            else:
                want = outcome(lambda: (arith('/', a, b, t, L), arith('%', a, b, t, L)))
            compare(tl, res, want,
                    lambda res: (conv(res.regs['hl']), conv(res.regs['de'])), (a, b))



# -- 32 and 64 bits, by address ------------------------------------------------------------------------------------

def line():
    return random.randint(1, 4095)


def pairs(t, count=None):
    count = COUNT if count is None else count
    es = edges(t)
    out = [(a, b) for a in es for b in es]
    out += [(rnd(t), rnd(t)) for _ in range(count)]
    out += [(random.randint(t.lo, t.hi), random.randint(t.lo, t.hi)) for _ in range(count // 3)]
    return out


def where(alias):
    """the result's address: its own, or (for x = x op y) one of the operands'"""
    return random.choice([R, A, B]) if alias else R


def binop(r, name, t, meaning, alias=True, cases=None):
    n = t.bits // 8
    tl = Tally(name)
    for a, b in cases or pairs(t):
        L, rr = line(), where(alias)
        mem = {A: enc(a, n) + bytes([GUARD] * (16 - n)), B: enc(b, n) + bytes([GUARD] * (16 - n)),
               R: bytes([GUARD] * 16)}
        res = run(r, name, {'hl': A, 'de': B, 'bc': rr}, mem, [(rr, n)], L)
        want = outcome(lambda: meaning(a, b, L))
        compare(tl, res, want, lambda res: dec(res.mem[rr:rr + n], t.signed),
                (a, b, hex(rr)))
    return tl


def unop(r, name, t, meaning, alias=True, values=None, regs=None):
    n = t.bits // 8
    tl = Tally(name)
    vals = values or (edges(t) + [rnd(t) for _ in range(COUNT)] + [random.randint(t.lo, t.hi) for _ in range(COUNT // 3)])
    for a in vals:
        L, rr = line(), (random.choice([R, A]) if alias else R)
        mem = {A: enc(a, n) + bytes([GUARD] * (16 - n)), R: bytes([GUARD] * 16)}
        res = run(r, name, dict({'hl': A, 'bc': rr}, **(regs or {})), mem, [(rr, n)], L)
        want = outcome(lambda: meaning(a, L))
        compare(tl, res, want, lambda res: dec(res.mem[rr:rr + n], t.signed),
                (a, hex(rr)))
    return tl


def cmpop(r, name, t):
    n = t.bits // 8
    tl = Tally(name)
    for a, b in pairs(t) + [(v, v) for v in edges(t)] + [(x, x) for x in (rnd(t) for _ in range(200))]:
        mem = {A: enc(a, n), B: enc(b, n)}
        res = run(r, name, {'hl': A, 'de': B}, mem, [], line())
        want = ('ok', (0xFF, 1, 0) if a < b else (0, 0, 1) if a == b else (1, 0, 0))
        compare(tl, res, want, lambda res: (res.regs['a'], res.regs['f'] >> 7 & 1, res.regs['f'] >> 6 & 1)
               , (a, b))


def test_arith(r):
    for t, w in ((LONG, 'i32'), (QUAD, 'i64')):
        binop(r, f'bly_add_{w}', t, lambda a, b, L: arith('+', a, b, t, L))
        binop(r, f'bly_sub_{w}', t, lambda a, b, L: arith('-', a, b, t, L))
        unop(r, f'bly_neg_{w}', t, lambda a, L: fit(-a, t, L))
        cmpop(r, f'bly_cmp_{w}', t)


def counts():
    fixed = [0, 1, 2, 7, 8, 9, 15, 16, 17, 23, 24, 31, 32, 33, 39, 40, 47, 48, 55, 56, 63, 64, 65, 100, 127, 128,
             129, 136, 192, 200, 254, 255, 256, 257, 1000, 32767, -1, -2, -64, -32768]
    return fixed + [random.randint(0, 80) for _ in range(40)] + [random.randint(-32768, 32767) for _ in range(5)]


def test_bits(r):
    for t, w in ((LONG, 'i32'), (QUAD, 'i64')):
        for op, nm in (('&', 'and'), ('|', 'or'), ('^', 'xor')):
            binop(r, f'bly_{nm}_{w}', t, lambda a, b, L: arith(op, a, b, t, L))
        unop(r, f'bly_not_{w}', t, lambda a, L: wrap(~a, t))
        for op, nm in (('<<', 'shl'), ('>>', 'shr')):
            vals = edges(t) + [rnd(t) for _ in range(COUNT // 8)]
            cases = [(a, c) for a in random.sample(vals, min(len(vals), 60)) for c in counts()]
            cases += [(rnd(t), random.choice([random.randint(0, 70), random.randint(-40000, 40000)]))
                      for _ in range(COUNT)]
            tl = Tally(f'bly_{nm}_{w}')
            n = t.bits // 8
            for a, c in cases:
                c = max(-32768, min(32767, c))
                L, rr = line(), random.choice([R, A])
                mem = {A: enc(a, n) + bytes([GUARD] * (16 - n)), R: bytes([GUARD] * 16)}
                res = run(r, f'bly_{nm}_{w}', {'hl': A, 'de': c & 0xFFFF, 'bc': rr}, mem, [(rr, n)], L)
                want = outcome(lambda: arith(op, a, c, t, L))
                compare(tl, res, want, lambda res: dec(res.mem[rr:rr + n]),
                        (a, c, hex(rr)))


def boundary_pairs(t, count):
    """products right at the edge of the type: b near MAX // a and MIN // a, with every sign"""
    out = []
    for _ in range(count):
        a = rnd(t)
        if a == 0:
            continue
        for lim in (t.hi, t.lo):
            q = abs(lim) // abs(a)
            for d in (-1, 0, 1):
                for sa, sb in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                    x, y = sa * abs(a), sb * (q + d)
                    if t.lo <= x <= t.hi and t.lo <= y <= t.hi:
                        out.append((x, y))
    out += [(t.lo, 1), (1, t.lo), (t.lo, -1), (-1, t.lo), (t.lo // 2, 2), (2, t.lo // 2), (t.lo // 2, -2),
            (-(1 << (t.bits // 2 - 1)), 1 << (t.bits // 2 - 1)), (1 << (t.bits // 2 - 1), 1 << (t.bits // 2 - 1))]
    return random.sample(out, min(len(out), count * 4)) + out[-9:]


def carry_pairs(t, count):
    """one operand a little past half the width, the other filling the rest: products from just past 2^(bits-1)
    to a few bits beyond the full width, where a long's high word carries (bly_mul_i32's Xlo*Y + Xhi*Y << 16)"""
    h = t.bits // 2
    out = []
    for _ in range(count):
        x = random.randint(1 << h, (1 << (h + random.randint(1, 4))) - 1)
        y = random.randint(1 << (h - 2), (1 << h) - 1)
        out.append((x * random.choice([1, -1]), y * random.choice([1, -1])))
    return [(a, b) if random.random() < 0.5 else (b, a) for a, b in out if t.lo <= a <= t.hi]


def test_mul(r):
    for t, w in ((LONG, 'i32'), (QUAD, 'i64')):
        binop(r, f'bly_mul_{w}', t, lambda a, b, L: arith('*', a, b, t, L),
              cases=pairs(t) + boundary_pairs(t, COUNT // 2) + carry_pairs(t, COUNT // 3))


def div_pairs(t):
    """every divisor width against every dividend width, plus the edges and the uniform ones"""
    out = pairs(t)
    n = t.bits // 8
    for _ in range(COUNT):
        nb = random.randint(1, n)
        b = random.getrandbits(8 * nb - (1 if nb == n else 0)) | (1 << (8 * nb - 9) if nb > 1 else 1)
        a = rnd(t)
        out.append((a * random.choice([1, -1]) if a != t.lo else a, b * random.choice([1, -1])))
    return out


def test_div(r):
    for t, w in ((LONG, 'i32'), (QUAD, 'i64')):
        n = t.bits // 8
        cases = div_pairs(t)
        tl = Tally(f'bly_divmod_{w}')
        for a, b in cases:
            L = line()
            q, rr = random.choice([(Q, R), (Q, R), (A, B), (B, A), (A, R), (Q, B)])
            mem = {A: enc(a, n) + bytes([GUARD] * (16 - n)), B: enc(b, n) + bytes([GUARD] * (16 - n)),
                   Q: bytes([GUARD] * 16), R: bytes([GUARD] * 16)}
            res = run(r, f'bly_divmod_{w}', {'hl': A, 'de': B, 'bc': q, 'ix': rr}, mem, [(q, n), (rr, n)], L)
            want = outcome(lambda: (arith('/', a, b, t, L), arith('%', a, b, t, L)))
            compare(tl, res, want, lambda res: (dec(res.mem[q:q + n]), dec(res.mem[rr:rr + n])), (a, b, hex(q), hex(rr)))
        binop(r, f'bly_rem_{w}', t, lambda a, b, L: arith('%', a, b, t, L), cases=cases)


def gcd_pairs(t, count):
    """shared factors, shared twos, one side small, both wide, and the products around 2^63 for lcm"""
    out = pairs(t, count // 2)
    for _ in range(count):
        g = rnd(t) or 1
        k = random.choice([0, 0, 1, 3, 9, 17, 40])
        x, y = rnd(t), rnd(t)
        a, b = g * x << k, g * y << k
        if t.lo <= a <= t.hi and t.lo <= b <= t.hi:
            out.append((a, b))
    for _ in range(count // 4):                        # lcm right at the edge
        x = random.randint(2, 1 << 32)
        y = t.hi // x + random.choice([-1, 0, 1, 2])
        out.append((x * random.choice([1, -1]), y * random.choice([1, -1])))
    out += [(t.lo, 0), (0, t.lo), (t.lo, t.lo), (t.lo, 1), (t.lo, -1), (t.lo, 2), (t.lo, t.lo // 2), (0, 0),
            (t.hi, t.hi), (t.hi, t.hi - 1), (1 << 62, 1 << 61), (3 << 40, 5 << 40)]
    return [(a, b) for a, b in out if t.lo <= a <= t.hi and t.lo <= b <= t.hi]


CODES = {BYTE: 0, WORD: 1, INT: 2, LONG: 3, QUAD: 4}


def test_quad(r):
    t, n = QUAD, 8
    cases = gcd_pairs(t, COUNT)
    for name, fn in (('bly_gcd_i64', b_gcd), ('bly_lcm_i64', b_lcm), ('bly_mod_i64', b_mod)):
        binop(r, name, t, lambda a, b, L: fn(a, b, t, L), cases=cases)
    unop(r, 'bly_abs_i64', t, lambda a, L: b_abs(a, t, L))
    tl = Tally('bly_fit_i64')
    vals = edges(QUAD) + [rnd(QUAD) for _ in range(COUNT)]
    for ty in (BYTE, WORD, INT, LONG):
        vals += [ty.lo, ty.hi, ty.lo - 1, ty.hi + 1, -ty.hi, -ty.hi - 1] + [rnd(ty) for _ in range(COUNT // 4)]
    for v in vals:
        ty = random.choice([BYTE, WORD, INT, LONG, QUAD])
        m, L = ty.bits // 8, line()
        dst = random.choice([R, A])
        mem = {A: enc(v, 8) + bytes([GUARD] * 8), R: bytes([GUARD] * 16)}
        res = run(r, 'bly_fit_i64', {'hl': A, 'a': CODES[ty], 'de': dst}, mem, [(dst, m)], L)
        want = outcome(lambda: fit(v, ty, L))
        compare(tl, res, want, lambda res: dec(res.mem[dst:dst + m], ty.signed), (v, ty.name, hex(dst)))


def test_widened(r):
    """the contract as generated code uses it: widen to quad, call, narrow with bly_fit_i64, against interp's
    builtins at the original type"""
    for t in (INT, LONG, QUAD):
        tl = Tally(f'via quad: {t.name}')
        for a, b in gcd_pairs(t, COUNT // 3):
            name, fn = random.choice([('bly_gcd_i64', b_gcd), ('bly_lcm_i64', b_lcm), ('bly_mod_i64', b_mod),
                                      ('bly_abs_i64', None)])
            L = line()
            mem = {A: enc(a, 8), B: enc(b, 8), R: bytes([GUARD] * 16)}
            res = run(r, name, {'hl': A, 'de': B, 'bc': R}, mem, [(R, 8)], L)
            want = outcome(lambda: fn(a, b, t, L) if fn else b_abs(a, t, L))
            if not res.failed:
                wide = res.mem[R:R + 8]
                res = run(r, 'bly_fit_i64', {'hl': R, 'a': CODES[t], 'de': Q}, {R: wide, Q: bytes([GUARD] * 16)},
                          [(Q, t.bits // 8)], L)
            compare(tl, res, want, lambda res: dec(res.mem[Q:Q + t.bits // 8]), (name, a, b))
        tl.ts = []                                     # two calls each: their costs are in the other tallies


def test_u32(r):
    """the dword's own routines (intu32.asm): unsigned 32 bits, wrapping, never trapping"""
    t, n = DWORD, 4
    binop(r, 'bly_add_u32', t, lambda a, b, L: arith('+', a, b, t, L))
    binop(r, 'bly_sub_u32', t, lambda a, b, L: arith('-', a, b, t, L))
    unop(r, 'bly_neg_u32', t, lambda a, L: wrap(-a, t))
    cmpop(r, 'bly_cmp_u32', t)
    wide = [(random.randint(1 << 16, t.hi), random.randint(1, t.hi)) for _ in range(COUNT // 2)]   # every cross term
    binop(r, 'bly_mul_u32', t, lambda a, b, L: arith('*', a, b, t, L), cases=pairs(t) + wide + [(b, a) for a, b in wide])
    cases = pairs(t) + [(rnd(t), random.getrandbits(8 * random.randint(1, 4)) | 1) for _ in range(COUNT)]
    tl = Tally('bly_divmod_u32')
    for a, b in cases:
        L = line()
        q, rr = random.choice([(Q, R), (Q, R), (A, B), (B, A), (A, R), (Q, B), (0, R), (Q, 0)])
        mem = {A: enc(a, n) + bytes([GUARD] * (16 - n)), B: enc(b, n) + bytes([GUARD] * (16 - n)),
               Q: bytes([GUARD] * 16), R: bytes([GUARD] * 16)}
        results = [(x, n) for x in (q, rr) if x]
        res = run(r, 'bly_divmod_u32', {'hl': A, 'de': B, 'bc': q, 'ix': rr}, mem, results, L)
        want = outcome(lambda: tuple(v for v, x in ((arith('/', a, b, t, L), q), (arith('%', a, b, t, L), rr)) if x))
        compare(tl, res, want, lambda res: tuple(dec(res.mem[x:x + n], False) for x in (q, rr) if x),
                (a, b, hex(q), hex(rr)))
    vals = edges(t) + [rnd(t) for _ in range(COUNT // 8)]
    shifts = [(a, c) for a in random.sample(vals, min(len(vals), 60)) for c in counts()]
    tl = Tally('bly_shr_u32')
    for a, c in shifts:
        c = max(-32768, min(32767, c))
        L, rr = line(), random.choice([R, A])
        mem = {A: enc(a, n) + bytes([GUARD] * (16 - n)), R: bytes([GUARD] * 16)}
        res = run(r, 'bly_shr_u32', {'hl': A, 'de': c & 0xFFFF, 'bc': rr}, mem, [(rr, n)], L)
        want = outcome(lambda: arith('>>', a, c, t, L))
        compare(tl, res, want, lambda res: dec(res.mem[rr:rr + n], False), (a, c, hex(rr)))
    tl = Tally('bly_pr_u32p')
    for a in vals:
        res = run(r, 'bly_pr_u32p', {'hl': A}, {A: enc(a, n)}, [], line())
        ok = not res.failed and res.out.decode('latin-1') == str(a) and not res.stray and not res.lost
        tl.check(ok, (a,), 'wanted', str(a), 'got', res.out)
        if ok:
            tl.ts.append(res.t)


SECTIONS = [('16-bit', ['bly_mul_u16', 'bly_mul_i16', 'bly_divmod_u16', 'bly_divmod_i16', 'bly_rem_i16'], test16),
            ('add, sub, neg, cmp', [f'bly_{o}_{w}' for o in ('add', 'sub', 'neg', 'cmp') for w in ('i32', 'i64')],
             test_arith),
            ('bits and shifts', [f'bly_{o}_{w}' for o in ('and', 'or', 'xor', 'not', 'shl', 'shr') for w in ('i32', 'i64')],
             test_bits),
            ('multiply', ['bly_mul_i32', 'bly_mul_i64'], test_mul),
            ('divide', ['bly_divmod_i32', 'bly_divmod_i64', 'bly_rem_i32', 'bly_rem_i64'], test_div),
            ('dword', ['bly_add_u32', 'bly_sub_u32', 'bly_neg_u32', 'bly_cmp_u32', 'bly_mul_u32', 'bly_divmod_u32',
                       'bly_shr_u32', 'bly_pr_u32p'], test_u32),
            ('quad functions', ['bly_gcd_i64', 'bly_lcm_i64', 'bly_mod_i64', 'bly_abs_i64', 'bly_fit_i64'], test_quad),
            ('widened', ['bly_gcd_i64', 'bly_lcm_i64', 'bly_mod_i64', 'bly_abs_i64', 'bly_fit_i64'], test_widened)]


def main():
    only = os.environ.get('ONLY')
    if not only or only in 'mirror':
        bad, n = crosscheck_builtins()
        print(f'the mirrored builtins against barley.run: {n} programs, ' + ('all the same' if not bad else f'{bad} DIFFER'))
        if bad:
            return bad
    for title, needs, fn in SECTIONS:
        if only and only not in title:
            continue
        print(f'{title}:')
        r = runner(needs)
        start = len(Tally.all)
        fn(r)
        for t in Tally.all[start:]:
            print('  ' + t.summary())
    bad = sum(t.bad for t in Tally.all)
    n = sum(t.n for t in Tally.all)
    print(f'integers: {n} cases, ' + ('all right' if not bad else f'{bad} WRONG') + f' (seed {SEED})')
    return bad


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
