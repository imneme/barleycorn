"""num.asm, num_read.asm and num_chk.asm against their meaning: numbers to and from text, and the 64-bit checks.

The model is the interpreter itself wherever it has the code: Interp.e_dot for s.int() and s.int(k), Interp.walk
for the message of `for v in s.ints()`, Interp.e_index for indices and slices, BGrid.check, ints_in, and str() for
printing (Interp.show prints an integer with str). Every failure message is compared byte for byte.

usage: test_num.py [--lib DIR] [--seed N] [--quick]
  --lib DIR   gather the library from DIR instead of z80/lib (for breaking a copy on purpose)
"""
import os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'interp'))
import harness, link                          # noqa: E402
from harness import Runner                    # noqa: E402
import barley                                 # noqa: E402
from barley import BarleyError, INTS, STR, FLEX, Gen, Range, BGrid, ints_in   # noqa: E402

args = sys.argv[1:]
if '--lib' in args:
    LIB = args[args.index('--lib') + 1]
    harness.gather = lambda syms, target: link.gather(syms, target, lib=LIB)
SEED = int(args[args.index('--seed') + 1]) if '--seed' in args else 1
QUICK = '--quick' in args
N = 300 if QUICK else 1500
rnd = random.Random(SEED)

TYPES = ['byte', 'word', 'int', 'long', 'quad']
WIDTH = {'byte': 1, 'word': 2, 'int': 2, 'long': 4, 'quad': 8}
STR_AT, DEST, K_AT, STATE = 0xE000, 0xE010, 0xE020, 0xE030
TEXT = 0xE100                                   # strings: up to EFFFh
FILL = 0xAA


# -- the model: the interpreter's own code, called through small stand-ins ---------------------------------------

class Box:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Ev:
    """stands in for the Interp in e_dot and e_index: every operand is a Box holding its value"""
    def ev(self, x, env):
        return x.val


def interp_str_int(s, tname, k=None):
    """s.int() or s.int(k) read into a tname: the value, or the failure's words"""
    e = Box(obj=Box(val=s, ty=STR), name='int', args=[] if k is None else [Box(val=k)], line=None, ty=INTS[tname])
    try:
        return barley.Interp.e_dot(Ev(), e, None), None
    except BarleyError as err:
        return None, str(err)


def interp_ints(s, tname):
    """for v: tname in s.ints(): the values, then the failure's words if one doesn't fit"""
    vals = []
    try:
        for v in barley.Interp.walk(None, iter(ints_in(s)), Gen('iter', FLEX), Box(vtys=[INTS[tname]], line=None)):
            vals.append(v)
    except BarleyError as err:
        return vals, str(err)
    return vals, None


def interp_index(i, n):
    e = Box(obj=Box(val=b'x' * n, ty=STR), slice=False, idx=[Box(val=i)], line=None)
    try:
        barley.Interp.e_index(Ev(), e, None)
        return None
    except BarleyError as err:
        return str(err)


def interp_slice(a, b, n):
    e = Box(obj=Box(val=b'x' * n, ty=STR), slice=True, idx=[Box(val=Range(a, b, False))], line=None)
    try:
        barley.Interp.e_index(Ev(), e, None)
        return None
    except BarleyError as err:
        return str(err)


def interp_grid(r, c, rows, cols):
    g = BGrid.__new__(BGrid)                    # the real check, without making rows x cols cells
    g.rows, g.cols = rows, cols
    try:
        g.check(r, c, None)
        return None
    except BarleyError as err:
        return str(err)


# -- helpers --------------------------------------------------------------------------------------------------------

def le(v, n):
    return (v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little')


def sle(b):
    return int.from_bytes(b, 'little', signed=True)


def str_mem(s, at=STR_AT, text=TEXT, p0=False):
    """a str at `at` whose bytes are at `text`; p0: an empty str with p = 0, as the ABI allows"""
    p = 0 if (p0 and not s) else text
    return {at: le(p, 2) + le(len(s), 2), text: s}


def rand_val(bits):
    """a random signed value, its bit length drawn first, so every magnitude gets tried"""
    n = rnd.randint(0, bits - 1)
    v = rnd.getrandbits(n) if n else 0
    return -v - rnd.randint(0, 1) if rnd.random() < 0.5 else v


bad = 0
counts = {}


def check(what, ok, *detail):
    global bad
    counts[what] = counts.get(what, 0) + 1
    if not ok:
        bad += 1
        if bad <= 40:
            print('WRONG', what, *detail)


def expect_fail(res, msg, line=0):
    """a failure prints the message, " at line N" when bly_line isn't 0, and a newline"""
    want = msg + (f' at line {line}' if line else '') + '\n'
    return res.failed and res.out == want.encode('latin-1')


def col_ok(res):
    """print's column follows what was printed (no newline in a number)"""
    col = int.from_bytes(res.mem[res.sym['bly_col']:res.sym['bly_col'] + 2], 'little')
    return col == len(res.out)


# -- printing --------------------------------------------------------------------------------------------------------

def test_printing(r):
    for v in range(256):                                   # every byte
        res = r.call('bly_pr_u8', regs={'a': v})
        check('pr_u8', res.out == str(v).encode() and not res.failed and col_ok(res), v, res.out)
    edges32 = [0, 1, -1, 9, 10, -10, 65535, 65536, -65535, -65536, 99999, 100000, -100000, 999999999, 10**9,
               -10**9, 2**31 - 1, -2**31, -2**31 + 1, 1234567890, -1234567890, 2**31 - 10**9]
    edges32 += [s * (10**k + d) for k in range(10) for d in (-1, 0, 1) for s in (1, -1) if 10**k + d < 2**31]
    vals = edges32 + [rand_val(32) for _ in range(N)]
    for v in vals:
        res = r.call('bly_pr_i32', regs={'hl': DEST}, mem={DEST: le(v, 4)})
        check('pr_i32', res.out == str(v).encode() and not res.failed and col_ok(res), v, res.out)
    edges64 = [0, 1, -1, 2**32 - 1, 2**32, -2**32, 2**63 - 1, -2**63, -2**63 + 1, 10**18, 10**18 - 1, -10**18,
               10**18 + 1, 9 * 10**18, 9 * 10**18 - 1, 2**60, 10**9 * 2**32, 4 * 10**9, 4 * 10**9 + 999999999,
               2**32 * 10**9 + 10**9 - 1, 10**17, 10**9 * 10**9 - 1]
    edges64 += [s * (10**k + d) for k in range(19) for d in (-1, 0, 1) for s in (1, -1)]
    edges64 += [s * (t * 10**18 + q * 10**9 + rr) for t in (0, 1, 9) for q in (0, 5, 999999999)
                for rr in (0, 1, 999999999) for s in (1, -1) if t * 10**18 + q * 10**9 + rr < 2**63]
    vals = edges64 + [rand_val(64) for _ in range(N)]
    for v in vals:
        res = r.call('bly_pr_i64', regs={'hl': DEST}, mem={DEST: le(v, 8)})
        check('pr_i64', res.out == str(v).encode() and not res.failed and col_ok(res), v, res.out)
        check('pr_i64 keeps v', res.mem[DEST:DEST + 8] == le(v, 8), v)


# -- reading ---------------------------------------------------------------------------------------------------------

def num_case(r, digits, neg, tname):
    """bly_num on a run of digits: against s.int() of the same digits with the same sign"""
    code = TYPES.index(tname) | (0x80 if neg else 0)
    res = r.call('bly_num', regs={'hl': TEXT, 'bc': len(digits), 'a': code, 'de': DEST},
                 mem={TEXT: digits, DEST: bytes([FILL]) * 8})
    v, err = interp_str_int((b'-' if neg else b'') + digits, tname)
    w = WIDTH[tname]
    if err:
        check('num ' + tname, expect_fail(res, err), digits, neg, res.out, res.failed)
    else:
        got = res.mem[DEST:DEST + 8]
        check('num ' + tname, not res.failed and res.out == b'' and got == le(v, w) + bytes([FILL]) * (8 - w),
              digits, neg, got.hex(), res.out)
    return res


def rand_digits():
    x = rnd.random()
    n = rnd.randint(1, 6) if x < 0.4 else rnd.randint(1, 21) if x < 0.9 else rnd.randint(22, 300)
    z = rnd.choice([0, 0, 0, 1, 2, 5])
    return b'0' * z + bytes(rnd.choice(b'0123456789') for _ in range(n))


def test_num(r):
    for tname in TYPES:
        t = INTS[tname]
        near = set()
        for b in (t.lo, t.hi, 0, 2**63, 2**64, 10**19, 2**31, 2**32, 65536, 32768, 256, 10**9, 10**10):
            near.update(range(b - 3, b + 4))
        for v in sorted(near):
            for z in (0, 1, 3):
                for neg in (False, True):
                    if v >= 0:
                        num_case(r, b'0' * z + str(v).encode(), neg, tname)
    for _ in range(N * 2):
        num_case(r, rand_digits(), rnd.random() < 0.4, rnd.choice(TYPES))
    for neg in (False, True):                              # a run the type can't hold, as long as the output allows
        for tname in TYPES:
            num_case(r, b'9' * 900, neg, tname)


WS = b' \t\n\r\x0b\x0c'


def rand_text(alphabet, n):
    return bytes(rnd.choice(alphabet) for _ in range(n))


def rand_str_int():
    parts = [rand_text(WS + b'x', rnd.choice([0, 0, 1, 3]))]
    parts.append(rnd.choice([b'', b'', b'-', b'+', b'--', b'+-', b'x']))
    parts.append(rand_digits() if rnd.random() < 0.85 else b'')
    parts.append(rand_text(b'0123456789 -+x,', rnd.choice([0, 0, 2, 6])))
    return b''.join(parts)[:400]


def str_int_case(r, s, tname, line=0, p0=False):
    mem = str_mem(s, p0=p0)
    mem[DEST] = bytes([FILL]) * 8
    routine = 'tst_str_int42' if line else 'bly_str_int'         # (bly_test_init zeroes bly_line, so set16 can't)
    res = r.call(routine, regs={'hl': STR_AT, 'a': TYPES.index(tname), 'de': DEST}, mem=mem)
    v, err = interp_str_int(s, tname)
    w = WIDTH[tname]
    if err:
        check('str_int', expect_fail(res, err, line), s, tname, res.out)
    else:
        got = res.mem[DEST:DEST + 8]
        check('str_int', not res.failed and got == le(v, w) + bytes([FILL]) * (8 - w), s, tname, got.hex(), res.out)


def test_str_int(r):
    fixed = [b'', b' ', b'\t\n\r\x0b\x0c 42', b'-', b'+', b'-0', b'+0', b'00', b'-007', b'+12abc', b' - 5', b'--5',
             b'x12', b'12-3', b'255', b'256', b'-1', b'-32768', b'-32769', b'32767', b'32768', b'2147483648',
             b'-2147483648', b'9223372036854775807', b'-9223372036854775808', b'9223372036854775808',
             b'99999999999999999999999', b'-00000000000000000000000000001', b'\xa0 5', b'\x00 5', b'\x1c5']
    for s in fixed:
        for tname in TYPES:
            str_int_case(r, s, tname)
    str_int_case(r, b'', 'long', p0=True)
    str_int_case(r, b'nothing here', 'int', line=42)
    str_int_case(r, b'70000', 'word', line=42)
    for _ in range(N):
        str_int_case(r, rand_str_int(), rnd.choice(TYPES))


def rand_ints_text():
    n = rnd.choice([0, 1, 3, 8, 20, 60])
    alpha = rnd.choice([b'0123456789-', b'0123456789 -,x', b'0123456789-+=:; \t', b'-x9', b'0-'])
    s = rand_text(alpha, n)
    if rnd.random() < 0.3:
        s += b'-' + rand_digits()[:25]
    if rnd.random() < 0.2:
        s = rand_digits()[:25] + s
    return s


INTS_DRIVER = '''
tst_ints:                           ; HL = &str, A = type: every value in 8-byte slots from 0A000h, the count at 0EFFEh
        ld (tst_type),a
        ex de,hl
        ld hl,tst_state
        call bly_ints_init
        ld hl,0A000h
        ld (tst_out),hl
        ld hl,0
        ld (0EFFEh),hl
.loop:  ld hl,tst_state
        call bly_ints_next
        ret z
        ld hl,(0EFFEh)
        inc hl
        ld (0EFFEh),hl
        ld a,(tst_type)
        ld de,(tst_out)
        ld hl,tst_state
        call bly_ints_val
        ld hl,(tst_out)
        ld de,8
        add hl,de
        ld (tst_out),hl
        jr .loop
tst_str_int42:                      ; bly_str_int at line 42
        push hl
        ld hl,42
        ld (bly_line),hl
        pop hl
        jp bly_str_int
tst_type:  db 0
tst_out:   dw 0
tst_state: ds 12
'''


def ints_case(r, s, tname, p0=False):
    mem = str_mem(s, p0=p0)
    res = r.call('tst_ints', regs={'hl': STR_AT, 'a': TYPES.index(tname)}, mem=mem)
    vals, err = interp_ints(s, tname)
    n = int.from_bytes(res.mem[0xEFFE:0xF000], 'little')
    w = WIDTH[tname]
    got = [sle(res.mem[0xA000 + 8 * i:0xA000 + 8 * i + w]) for i in range(len(vals))]
    if tname in ('byte', 'word'):
        got = [g & ((1 << (8 * w)) - 1) for g in got]
    if err:
        ok = expect_fail(res, err) and n == len(vals) + 1 and got == vals
    else:
        ok = not res.failed and res.out == b'' and n == len(vals) and got == vals
    check('ints', ok, s, tname, vals, err, got, n, res.out)


def test_ints(r):
    fixed = [b'', b'2-4', b'2-4,6-8', b'x=-3', b'-5', b'--5', b'a-5', b'5-', b'-', b'0-0', b'-0', b'1 -2 --3 4-5-6',
             b'move 3 from 1 to 2', b'-255 255 256', b'99999999999999999999', b'-x9', b'9-x-9']
    for s in fixed:
        for tname in TYPES:
            ints_case(r, s, tname)
    ints_case(r, b'', 'long', p0=True)
    long_s = b'-' + b' -'.join(str(rnd.randint(0, 10**6)).encode() for _ in range(200))   # far apart: st - p >= 256
    ints_case(r, long_s, 'long')
    ints_case(r, b'x' * 300 + b'-12' + b'y' * 300 + b'7-8', 'int')
    for _ in range(N):
        ints_case(r, rand_ints_text(), rnd.choice(TYPES))


def str_intk_case(r, s, k, tname, p0=False):
    mem = str_mem(s, p0=p0)
    mem[DEST] = bytes([FILL]) * 8
    mem[K_AT] = le(k, 8)
    res = r.call('bly_str_intk', regs={'hl': STR_AT, 'bc': K_AT, 'a': TYPES.index(tname), 'de': DEST}, mem=mem)
    v, err = interp_str_int(s, tname, k)
    w = WIDTH[tname]
    if err:
        check('str_intk', expect_fail(res, err), s, k, tname, res.out)
    else:
        got = res.mem[DEST:DEST + 8]
        check('str_intk', not res.failed and got == le(v, w) + bytes([FILL]) * (8 - w), s, k, tname, got.hex())


def test_str_intk(r):
    str_intk_case(r, b'', 0, 'long', p0=True)
    for k in (0, 1, 2, 3, -1, 65536, -2**63, 2**63 - 1, 2**16 + 1, 2**32):
        for s in (b'move 3 from 1 to 2', b'', b'no numbers', b'2-4,6-8', b'x=-300'):
            str_intk_case(r, s, k, rnd.choice(TYPES))
    for _ in range(N):
        s = rand_ints_text()
        m = len(ints_in(s))
        k = rnd.choice([rnd.randint(0, max(m - 1, 0)), m, rnd.randint(-3, m + 3), rand_val(64)])
        str_intk_case(r, s, k, rnd.choice(TYPES))


# -- the checks --------------------------------------------------------------------------------------------------------

def rand_index():
    x = rnd.random()
    return rnd.randint(-3, 70000) if x < 0.6 else rand_val(64) if x < 0.9 else rnd.choice([-2**63, 2**63 - 1, 65535, 65536, -65536])


def test_checks(r):
    for _ in range(N):
        n = rnd.choice([0, 1, 2, 10, 255, 256, 65534, 65535, rnd.randint(0, 65535)])
        i = rnd.choice([rand_index(), rnd.randint(-2, n + 2), n - 1, n])
        res = r.call('bly_chk_index64', regs={'hl': K_AT, 'de': n}, mem={K_AT: le(i, 8)})
        err = interp_index(i, n)
        if err:
            check('chk_index64', expect_fail(res, err), i, n, res.out)
        else:
            check('chk_index64', not res.failed and res.regs['de'] == i and res.regs['hl'] == K_AT, i, n)
    for _ in range(N):
        n = rnd.choice([0, 1, 5, 65535, rnd.randint(0, 65535)])
        a = rnd.choice([rand_index(), rnd.randint(-2, n + 2), 0, n])
        b = rnd.choice([rand_index(), rnd.randint(-2, n + 2), a, a + 1, a - 1, n, n + 1])
        b = max(-2**63, min(2**63 - 1, b))       # still a quad
        res = r.call('bly_chk_slice64', regs={'hl': K_AT, 'de': DEST, 'bc': n}, mem={K_AT: le(a, 8), DEST: le(b, 8)})
        err = interp_slice(a, b, n)
        if err:
            check('chk_slice64', expect_fail(res, err), a, b, n, res.out)
        else:
            check('chk_slice64', not res.failed and res.regs['de'] == a and res.regs['bc'] == b, a, b, n)
    G = 0xE040
    for _ in range(N):
        rows, cols = rnd.choice([0, 1, 7, 32767, rnd.randint(0, 32767)]), rnd.choice([0, 1, 9, 32767, rnd.randint(0, 32767)])
        rr = rnd.choice([rand_index(), rnd.randint(-2, rows + 2), rows - 1, rows])
        cc = rnd.choice([rand_index(), rnd.randint(-2, cols + 2), cols - 1, cols])
        hdr = le(rows, 2) + le(cols, 2) + le(1, 2) + le(0xA000, 2) + le(0, 4)
        res = r.call('bly_grid_chk64', regs={'hl': G, 'de': K_AT, 'bc': DEST}, mem={G: hdr, K_AT: le(rr, 8), DEST: le(cc, 8)})
        err = interp_grid(rr, cc, rows, cols)
        if err:
            check('grid_chk64', expect_fail(res, err), rr, cc, rows, cols, res.out)
        else:
            check('grid_chk64', not res.failed and (res.regs['de'], res.regs['bc'], res.regs['hl']) == (rr, cc, G),
                  rr, cc, rows, cols)


def test_preserves(r):
    """what a header says it keeps, it keeps (IY and the alternate set aren't visible here; no fragment names them)"""
    S = 0x1234
    for v in (0, 7, 255):
        res = r.call('bly_pr_u8', regs={'a': v, 'ix': S})
        check('keeps', res.regs['ix'] == S, 'pr_u8 ix')
    res = r.call('bly_ints_init', regs={'hl': STATE, 'de': STR_AT, 'ix': S}, mem=str_mem(b'1 2'))
    check('keeps', res.regs['ix'] == S, 'ints_init ix')
    res = r.call('bly_chk_index64', regs={'hl': K_AT, 'de': 10, 'bc': 0x5678, 'ix': S}, mem={K_AT: le(3, 8)})
    check('keeps', (res.regs['bc'], res.regs['hl'], res.regs['ix']) == (0x5678, K_AT, S), 'chk_index64')
    res = r.call('bly_chk_slice64', regs={'hl': K_AT, 'de': DEST, 'bc': 9, 'ix': S}, mem={K_AT: le(2, 8), DEST: le(5, 8)})
    check('keeps', res.regs['ix'] == S, 'chk_slice64 ix')
    G = 0xE040
    res = r.call('bly_grid_chk64', regs={'hl': G, 'de': K_AT, 'bc': DEST, 'ix': S},
                 mem={G: le(5, 2) + le(6, 2), K_AT: le(4, 8), DEST: le(5, 8)})
    check('keeps', res.regs['ix'] == S and res.regs['hl'] == G, 'grid_chk64')
    res = r.call('bly_n_q2w', regs={'hl': K_AT, 'bc': 0x5678, 'ix': S}, mem={K_AT: le(-1, 8)})
    check('keeps', (res.regs['bc'], res.regs['ix'], res.regs['f'] & 0x40) == (0x5678, S, 0), 'n_q2w')


def main():
    r = Runner(['bly_pr_u8', 'bly_pr_i32', 'bly_pr_i64', 'bly_num', 'bly_str_int', 'bly_str_intk', 'bly_ints_init',
                'bly_ints_next', 'bly_ints_val', 'bly_chk_index64', 'bly_chk_slice64', 'bly_grid_chk64', 'bly_n_q2w'],
               extra=INTS_DRIVER)
    for t in (test_printing, test_num, test_str_int, test_ints, test_str_intk, test_checks, test_preserves):
        t(r)
    print('num:', 'all right' if not bad else f'{bad} wrong', '(' + ', '.join(f'{k} {v}' for k, v in counts.items()) + ')')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
