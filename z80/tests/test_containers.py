"""The containers against their meaning: the interpreter's own BList, BQueue, BHeap, BMap, BSet and BGrid,
driven through its own e_new, e_dot, e_index, store and walk, so every failure message is the interpreter's, compared
byte for byte. Long random sequences of operations are run on one container at a time, with the arena carried from
call to call, and after every step the Z80's container is read back through ABI.md's layouts and compared: the items
in walking order, the length, ver going up or not, and every failure.

    $OMSE_AI_PYTHON z80/tests/test_containers.py [--quick] [--seed N] [--cost]
"""
import os, random, struct, sys
from types import SimpleNamespace as NS

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'interp'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import paths                                  # noqa: E402
import harness                                # noqa: E402
import link                                   # noqa: E402
from harness import Runner                     # noqa: E402
import barley as B                             # noqa: E402

if '--lib' in sys.argv:                        # a mutated copy of the library (see --mutants)
    _lib = sys.argv[sys.argv.index('--lib') + 1]
    harness.gather = lambda symbols, target: link.gather(symbols, target, lib=_lib)

ARENA, OPS = 0xA000, 0xE000

# ---- test-only element routines. Each cmp trashes BC, DE, HL and IX before it returns, as a generated one may.
EXTRA = r'''
tst_res:                        ; flags after an unsigned compare (C less, Z equal) -> A and flags as ABI.md 2
        ld a,0
        jr z,.eq
        ld a,1
        jr nc,.eq
        ld a,0FFh
.eq:    ld bc,0DEADh
        ld de,0BEEFh
        ld hl,0F00Dh
        ld ix,0CAFEh
        or a
        ret
tst_cmp_u8:
        ld a,(de)
        ld b,a
        ld a,(hl)
        cp b
        jr tst_res
tst_i16f:                       ; C if (HL) < (DE) as ints, Z if equal
        ld c,(hl)
        inc hl
        ld b,(hl)
        ex de,hl
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld h,b
        ld l,c
        ld a,h
        xor 80h
        ld h,a
        ld a,d
        xor 80h
        ld d,a
        or a
        sbc hl,de
        ret
tst_cmp_i16:
        call tst_i16f
        jr tst_res
tst_cmp_rec:                    ; record R(x int, y byte)
        push hl
        push de
        call tst_i16f
        pop de
        pop hl
        jr nz,tst_res
        inc hl
        inc hl
        inc de
        inc de
        jr tst_cmp_u8
tst_cmp_pos:                    ; pos(r int, c int)
        push hl
        push de
        call tst_i16f
        pop de
        pop hl
        jr nz,tst_res
        inc hl
        inc hl
        inc de
        inc de
        jr tst_cmp_i16
tst_cmp_i64:
        ld bc,7
        add hl,bc
        ex de,hl
        add hl,bc
        ex de,hl
        ld a,(de)
        xor 80h
        ld b,a
        ld a,(hl)
        xor 80h
        cp b
        jr nz,tst_res
        ld b,7
.l:     dec hl
        dec de
        ld a,(de)
        ld c,a
        ld a,(hl)
        cp c
        jr nz,tst_res
        djnz .l
        jr tst_res
tst_pr_u8:
        ld l,(hl)
        ld h,0
        jp bly_pr_u16
tst_pr_i16:
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        jp bly_pr_i16
tst_pr_pos:                     ; (r, c)
        push hl
        ld a,'('
        call bly_out
        pop hl
        push hl
        call tst_pr_i16
        ld hl,tst_comma
        call bly_pr_cstr
        pop hl
        inc hl
        inc hl
        call tst_pr_i16
        ld a,')'
        jp bly_out
tst_pr_rec:                     ; R(x, y)
        push hl
        ld hl,tst_r
        call bly_pr_cstr
        pop hl
        push hl
        call tst_pr_i16
        ld hl,tst_comma
        call bly_pr_cstr
        pop hl
        inc hl
        inc hl
        call tst_pr_u8
        ld a,')'
        jp bly_out
tst_pr_hex64:                   ; 16 hex digits, the top first (the test's own way to show a quad)
        ld bc,7
        add hl,bc
        ld b,8
.l:     ld a,(hl)
        push hl
        push bc
        push af
        rrca
        rrca
        rrca
        rrca
        call .dig
        pop af
        call .dig
        pop bc
        pop hl
        dec hl
        djnz .l
        ret
.dig:   and 15
        add a,'0'
        cp '9'+1
        jr c,.out
        add a,'a'-'9'-1
.out:   jp bly_out
tst_deep:                       ; call the routine at (tst_target) with SP three bytes deeper, so nothing
        dec sp                  ; can lean on where the stack happens to be
        dec sp
        dec sp
        push ix
        ld ix,(tst_target)
        ld (tst_deep_call+1),ix
        pop ix
tst_deep_call:
        call 0
        inc sp
        inc sp
        inc sp
        ret
tst_target: dw 0
tst_comma: db ", ",0
tst_r:     db "R(",0
'''

QH = B.IntT('quad', 64, True)                  # a quad the test's printer shows in hex
REC = B.RecordT('R')
REC.set_fields([('x', B.INT), ('y', B.BYTE)])


class Shim(B.Interp):
    """the interpreter, with each expression a value already: its own e_* code then runs on our operands"""
    def __init__(self):
        self.col, self.out = 0, None

    def ev(self, e, env):
        return e.v

    def show(self, v, t):
        return format(v & (1 << 64) - 1, '016x') if t is QH else super().show(v, t)


SHIM = Shim()


def lit(v, ty=None):
    return NS(v=v, ty=ty, cval=None, k='lit')


def model(fn):
    """run an interpreter step: (result, None) or (None, its message)"""
    try:
        return fn(), None
    except B.BarleyError as e:
        return None, e.msg


def dot(obj, ty, name, *args):
    return model(lambda: SHIM.e_dot(NS(obj=lit(obj, ty), name=name, args=[lit(a) for a in args], line=None, ty=None), {}))


def new(kind, ty, *args):
    return model(lambda: SHIM.e_new(NS(args=[lit(a) for a in args], ty=ty, kind=kind, line=None), {}))


class Kind:
    def __init__(self, name, fmt, cmp, pr, ty, gen):
        self.name, self.fmt, self.cmp, self.pr, self.ty, self.gen = name, fmt, cmp, pr, ty, gen
        self.size = struct.calcsize(fmt)

    def pack(self, v):
        return struct.pack(self.fmt, *(v if isinstance(v, tuple) else (v,)))

    def unpack(self, b):
        t = struct.unpack(self.fmt, bytes(b))
        return t if len(t) > 1 else t[0]


def gen_i64(rng):
    return rng.choice([rng.randrange(-5, 5), rng.randrange(-2**63, 2**63), rng.randrange(-300, 300) << rng.randrange(55)])


U8 = Kind('byte', '<B', 'tst_cmp_u8', 'tst_pr_u8', B.BYTE, lambda r: r.randrange(256))
I16 = Kind('int', '<h', 'tst_cmp_i16', 'tst_pr_i16', B.INT, lambda r: r.choice([r.randrange(-40, 40), r.randrange(-32768, 32768)]))
RECK = Kind('R', '<hB', 'tst_cmp_rec', 'tst_pr_rec', REC, lambda r: (r.randrange(-3, 3), r.randrange(256)))
POSK = Kind('pos', '<hh', 'tst_cmp_pos', 'tst_pr_pos', B.POS, lambda r: (r.randrange(-3, 3), r.randrange(-3, 3)))
I64 = Kind('quad', '<q', 'tst_cmp_i64', 'tst_pr_hex64', QH, gen_i64)
ELEMS = [U8, I16, RECK, POSK, I64]

NEEDS = ['bly_list_new', 'bly_list_push', 'bly_list_pop', 'bly_list_ref', 'bly_list_clear', 'bly_list_sort', 'bly_sort',
         'bly_queue_new', 'bly_queue_put', 'bly_queue_get', 'bly_queue_at', 'bly_heap_new', 'bly_heap_push',
         'bly_heap_pop', 'bly_map_new', 'bly_map_has', 'bly_map_put', 'bly_map_ref', 'bly_map_getd', 'bly_map_del',
         'bly_map_find', 'bly_grid_new', 'bly_grid_ref', 'bly_grid_has', 'bly_grid_find', 'bly_grid_chk16',
         'bly_changed', 'bly_cn_mul', 'bly_cn_cmul']
R = Runner(NEEDS, EXTRA)
SYM = R.build('bly_list_new')[1]


def w(m, a):
    return m[a] | m[a + 1] << 8


def quad(v):
    return struct.pack('<q', v)


STATS = {}


def stat(k):
    STATS[k] = STATS.get(k, 0) + 1


class Fails:
    def __init__(self):
        self.bad, self.checks = 0, 0

    def check(self, ok, *what):
        self.checks += 1
        if not ok:
            self.bad += 1
            if self.bad <= 30:
                print('WRONG:', *what)
        return ok


F = Fails()


class Z80:
    """one container's world: the arena carried from call to call (only constructors allocate)"""
    def __init__(self):
        self.arena = bytes(0x4000)
        self.mem = None

    def call(self, routine, regs, ops=None):
        mem = {ARENA: self.arena}
        if ops:
            for a, data in ops.items():
                mem[a] = data
        res = R.call(routine, regs=regs, mem=mem)
        self.arena, self.mem = res.mem[ARENA:ARENA + 0x4000], res.mem
        return res


def deep(z, routine, regs, rng):
    """call it directly, or (half the time) through tst_deep, three bytes further down the stack"""
    if rng.random() < 0.5:
        return z.call(routine, regs)
    tgt = SYM['tst_target']
    return z.call('tst_deep', regs, {tgt: SYM[routine].to_bytes(2, 'little')})


def same_failure(res, msg, *what):
    """the Z80 failed exactly when the interpreter did, with the same words"""
    got = res.out.decode('latin-1') if res.failed else None
    want = msg + '\n' if msg is not None else None
    if got is None and want is None and res.out:
        return F.check(False, what, 'printed', res.out)
    return F.check(got == want, what, 'got', repr(got), 'want', repr(want))


# ---- constructors: the capacity checks, the arena, the headers

def header_size(kind, cap, k):
    """bytes a constructor takes from the arena, or None if it can't be counted (cap above 8192 for a map)"""
    if kind == 'list':
        return 10 + cap * k[0]
    if kind == 'queue':
        return 12 + cap * k[0]
    if kind == 'heap':
        return 12 + (cap + 1) * k[0]
    if cap > 8192:
        return None
    size = 4
    while size < 2 * cap:
        size *= 2
    return 27 + cap * (k[0] + k[1] + 1) + 2 * size


def test_constructors(rng):
    caps = [0, 1, 2, 3, -1, -2**63, 2**63 - 1, 65535, 65536, 65537, 2**32, 2**32 + 5, -65535, 100, 8192, 8193, 4000]
    caps += [rng.randrange(-2**63, 2**63) for _ in range(30)] + [rng.randrange(1, 3000) for _ in range(60)]
    for cap in caps:
        for kind in ('list', 'queue', 'heap', 'map', 'set'):
            el = rng.choice(ELEMS)
            if kind in ('map', 'set'):
                key = rng.choice([U8, I16, POSK, I64])
                vs = 0 if kind == 'set' else rng.choice([I16, RECK, I64]).size
                ty = B.Gen(kind, key.ty) if kind == 'set' else B.Gen(kind, key.ty, I16.ty)
                block = quad(cap) + struct.pack('<HHHB', key.size, vs, SYM[key.pr], kind == 'set')
                sizes = (key.size, vs)
                routine = 'bly_map_new'
            else:
                ty = B.Gen(kind, el.ty)
                block = quad(cap) + struct.pack('<HH', el.size, SYM[el.cmp])
                sizes = (el.size,)
                routine = f'bly_{kind}_new'
            _, msg = new(kind, ty, cap)
            size = header_size(kind, cap, sizes) if msg is None else 0
            if msg is None and (size is None or size > 0x4000):
                msg = 'arena full'
            z = Z80()
            res = z.call(routine, {'hl': OPS}, {OPS: block})
            if not same_failure(res, msg, routine, cap) or res.failed:
                continue
            m, h = res.mem, res.regs['hl']
            F.check(h == ARENA and w(m, SYM['bly_atop']) == ARENA + size, routine, cap, 'allocated', hex(h),
                    hex(w(m, SYM['bly_atop'])), 'want', hex(ARENA + size))
            if kind == 'list':
                F.check([w(m, h + i) for i in (0, 2, 4, 6, 8)] == [0, cap, 0, el.size, h + 10], 'list header', cap)
            elif kind == 'queue':
                F.check([w(m, h + i) for i in (0, 2, 4, 6, 8, 10)] == [0, 0, cap, 0, el.size, h + 12], 'queue header')
            elif kind == 'heap':
                F.check([w(m, h + i) for i in (0, 2, 4, 6, 8, 10)] == [0, cap, 0, el.size, h + 12 + el.size,
                                                                     SYM[el.cmp]], 'heap header')
            else:
                ks, vs = sizes
                isz = (w(m, h + 8) + 1)
                k = h + 25
                want = [0, 0, cap, 0, k, k + cap * ks, k + cap * (ks + vs), k + cap * (ks + vs + 1), SYM[key.pr]]
                got = [w(m, h + i) for i in (0, 2, 4, 6, 14, 16, 18, 20, 22)]
                F.check(got == want and m[h + 24] == (kind == 'set') and w(m, h + 10) == ks and w(m, h + 12) == vs
                        and isz & (isz - 1) == 0 and isz >= 2 * cap and isz >= 4 and (isz == 4 or isz // 2 < 2 * cap)
                        and set(m[want[7]:want[7] + 2 * isz]) == {0xFF} and w(m, want[7] + 2 * isz) == 0xFFFD,
                        'map header', kind, cap, got, want)


# ---- list, queue, heap: random sequences against the interpreter

FAIL_RATE = 0.03


def pick(rng, ops, fails):
    """an op; one the interpreter would fail on only now and then, so sequences run long and still end every way"""
    for _ in range(20):
        op = rng.choice(ops)
        if not fails(op) or rng.random() < FAIL_RATE:
            return op
    return op


def make(kind, el, cap, ty):
    """construct on both sides; returns (model, z80 world, header address)"""
    m, msg = new(kind, ty, cap)
    z = Z80()
    res = z.call(f'bly_{kind}_new', {'hl': OPS}, {OPS: quad(cap) + struct.pack('<HH', el.size, SYM[el.cmp])})
    assert msg is None and not res.failed, (kind, cap, msg, res.out)
    return m, z, res.regs['hl']


def untouched(z, used, what):
    """nothing beyond the container's own block in the arena was written"""
    return F.check(not any(z.arena[used:]), what, 'wrote past its block')


def poke(z, addr, data):
    o = addr - ARENA
    assert 0 <= o and o + len(data) <= 0x4000, hex(addr)
    z.arena = z.arena[:o] + data + z.arena[o + len(data):]


def list_seq(rng, el, steps):
    cap = rng.choice([1, 2, 3, 5, 8, 20, 60])
    ty = B.Gen('list', el.ty)
    m, z, h = make('list', el, cap, ty)
    used = 10 + cap * el.size
    for step in range(steps):
        op = pick(rng, ['push'] * 5 + ['pop'] * 3 + ['clear', 'sort', 'sort', 'set', 'set'],
                  lambda op: op == 'push' and len(m.items) >= cap or op == 'pop' and not m.items)
        ver0, zver0 = m.ver, w(z.arena, h - ARENA + 4)
        what = ('list', el.name, cap, step, op)
        if op == 'push':
            v = el.gen(rng)
            _, msg = dot(m, ty, 'push', v)
            res = z.call('bly_list_push', {'hl': h, 'de': OPS}, {OPS: el.pack(v)})
        elif op == 'pop':
            want, msg = dot(m, ty, 'pop')
            res = z.call('bly_list_pop', {'hl': h, 'de': OPS + 0x100})
            if not res.failed:
                F.check(el.unpack(res.mem[OPS + 0x100:OPS + 0x100 + el.size]) == want, what, 'popped')
        elif op == 'clear':
            _, msg = dot(m, ty, 'clear')
            res = z.call('bly_list_clear', {'hl': h, 'de': 0x1234, 'bc': 0x5678, 'ix': 0x9ABC})
            F.check((res.regs['de'], res.regs['bc'], res.regs['ix']) == (0x1234, 0x5678, 0x9ABC), what, 'clobbers')
        elif op == 'sort':
            _, msg = dot(m, ty, 'sort')
            res = z.call('bly_list_sort', {'hl': h, 'de': SYM[el.cmp]})
        else:                                   # l[i] = v, through bly_list_ref: ver mustn't move
            if not m.items:
                continue
            i, v = rng.randrange(len(m.items)), el.gen(rng)
            _, msg = model(lambda: SHIM.store(NS(k='index', obj=lit(m, ty), idx=[lit(i)], line=None), v, {}))
            res = z.call('bly_list_ref', {'hl': h, 'de': i})
            a = w(z.arena, h - ARENA + 8)
            F.check(res.regs['hl'] == a + i * el.size, what, 'ref', hex(res.regs['hl']))
            poke(z, res.regs['hl'], el.pack(v))
        if not same_failure(res, msg, *what) or res.failed:
            stat(f'list ended by {msg}')
            break
        stat('list steps')
        n, a = w(z.arena, h - ARENA), w(z.arena, h - ARENA + 8)
        items = [el.unpack(z.arena[a - ARENA + i * el.size:a - ARENA + (i + 1) * el.size]) for i in range(n)]
        F.check(items == m.items, what, 'items', items, m.items)
        zver = w(z.arena, h - ARENA + 4)
        F.check((zver - zver0) & 0xFFFF == m.ver - ver0, what, 'ver moved', zver - zver0, 'want', m.ver - ver0)
        untouched(z, used, what)


def queue_seq(rng, el, steps):
    cap = rng.choice([1, 2, 3, 4, 7, 16, 33])
    ty = B.Gen('queue', el.ty)
    m, z, h = make('queue', el, cap, ty)
    used = 12 + cap * el.size
    o = h - ARENA
    for step in range(steps):
        op = pick(rng, ['put'] * 5 + ['get'] * 4 + ['at'] * 2,
                  lambda op: op == 'put' and len(m.items) >= cap or op == 'get' and not m.items)
        ver0, zver0 = m.ver, w(z.arena, o + 6)
        what = ('queue', el.name, cap, step, op)
        if op == 'put':
            v = el.gen(rng)
            _, msg = dot(m, ty, 'put', v)
            res = z.call('bly_queue_put', {'hl': h, 'de': OPS}, {OPS: el.pack(v)})
        elif op == 'get':
            want, msg = dot(m, ty, 'get')
            res = z.call('bly_queue_get', {'hl': h, 'de': OPS + 0x100})
            if not res.failed:
                F.check(el.unpack(res.mem[OPS + 0x100:OPS + 0x100 + el.size]) == want, what, 'got')
        else:                                   # for walks it through bly_queue_at; and q[i] = v leaves ver alone
            if not m.items:
                continue
            i, msg = rng.randrange(len(m.items)), None
            res = z.call('bly_queue_at', {'hl': h, 'de': i})
            a = res.regs['hl']
            F.check(el.unpack(z.arena[a - ARENA:a - ARENA + el.size]) == m.items[i], what, 'at', i)
            v = el.gen(rng)
            m.items[i] = v
            poke(z, a, el.pack(v))
        if not same_failure(res, msg, *what) or res.failed:
            stat(f'queue ended by {msg}')
            break
        stat('queue steps')
        head, n, a = w(z.arena, o), w(z.arena, o + 2), w(z.arena, o + 10)
        items = [el.unpack(z.arena[a - ARENA + (head + i) % cap * el.size:][:el.size]) for i in range(n)]
        F.check(items == list(m.items) and head < cap, what, 'items', items, list(m.items))
        zver = w(z.arena, o + 6)
        F.check((zver - zver0) & 0xFFFF == m.ver - ver0, what, 'ver moved', zver - zver0, 'want', m.ver - ver0)
        untouched(z, used, what)


def heap_seq(rng, el, steps):
    cap = rng.choice([1, 2, 3, 6, 15, 16, 40, 100])
    ty = B.Gen('heap', el.ty)
    m, z, h = make('heap', el, cap, ty)
    used = 12 + (cap + 1) * el.size
    o = h - ARENA
    for step in range(steps):
        op = pick(rng, ['push'] * 6 + ['pop'] * 4,
                  lambda op: op == 'push' and len(m.items) >= cap or op == 'pop' and not m.items)
        zver0 = w(z.arena, o + 4)
        what = ('heap', el.name, cap, step, op)
        if op == 'push':
            v = el.gen(rng)
            _, msg = dot(m, ty, 'push', v)
            res = z.call('bly_heap_push', {'hl': h, 'de': OPS}, {OPS: el.pack(v)})
        else:
            want, msg = dot(m, ty, 'pop')
            res = deep(z, 'bly_heap_pop', {'hl': h, 'de': OPS + 0x100}, rng)
            if not res.failed:
                F.check(el.unpack(res.mem[OPS + 0x100:OPS + 0x100 + el.size]) == want, what, 'popped', 'want', want)
        if not same_failure(res, msg, *what) or res.failed:
            stat(f'heap ended by {msg}')
            break
        stat('heap steps')
        n, a = w(z.arena, o), w(z.arena, o + 8)
        items = [el.unpack(z.arena[a - ARENA + i * el.size:][:el.size]) for i in range(n)]
        F.check(sorted(items) == sorted(m.items), what, 'items', items, m.items)
        F.check(all(items[(i - 1) // 2] <= items[i] for i in range(1, n)), what, 'not a heap', items)
        # the interpreter's heap never counts (no for can walk a heap); ABI.md and bly_heap.h count each push and pop
        F.check((w(z.arena, o + 4) - zver0) & 0xFFFF == 1, what, 'ver')
        untouched(z, used, what)


# ---- maps and sets

KEYS = [U8, I16, POSK, I64]
VALS = [I16, RECK, I64]
def map_walk(z, h):
    """the entries as the code generator walks them: 0..ne-1, skipping the dead"""
    o = h - ARENA
    ne, ks, vs = w(z.arena, o), w(z.arena, o + 10), w(z.arena, o + 12)
    k, v, alive = w(z.arena, o + 14) - ARENA, w(z.arena, o + 16) - ARENA, w(z.arena, o + 18) - ARENA
    out = []
    cap = w(z.arena, o + 4)
    flags = z.arena[alive:alive + cap]
    F.check(set(flags[:ne]) <= {0, 1} and not any(flags[ne:]), 'alive bytes are 0 or 1, and 0 from ne on',
            flags.hex())
    for e in range(ne):
        if z.arena[alive + e]:
            out.append((bytes(z.arena[k + e * ks:k + (e + 1) * ks]), bytes(z.arena[v + e * vs:v + (e + 1) * vs])))
    return out


def map_seq(rng, steps, is_set=None):
    key = rng.choice(KEYS)
    is_set = rng.random() < 0.35 if is_set is None else is_set
    val = None if is_set else rng.choice(VALS)
    cap = rng.choice([1, 2, 3, 4, 5, 8, 13, 31, 64])
    if key is U8:
        cap = min(cap, 200)
    universe = list({key.pack(key.gen(rng)): 0 for _ in range(cap * 2 + 2)})
    kind = 'set' if is_set else 'map'
    ty = B.Gen('set', key.ty) if is_set else B.Gen('map', key.ty, val.ty)
    m, msg = new(kind, ty, cap)
    z = Z80()
    vs = 0 if is_set else val.size
    res = z.call('bly_map_new', {'hl': OPS}, {OPS: quad(cap) + struct.pack('<HHHB', key.size, vs, SYM[key.pr], is_set)})
    assert not res.failed and msg is None
    h, o = res.regs['hl'], res.regs['hl'] - ARENA
    used = w(res.mem, SYM['bly_atop']) - ARENA
    ops = ['put'] * 6 + ['del'] * 4 + ['has'] * 2 + ([] if is_set else ['ref', 'refset', 'getd', 'getd'])
    for step in range(steps):
        kb = rng.choice(universe) if rng.random() < 0.9 else key.pack(key.gen(rng))
        k = key.unpack(kb)
        op = pick(rng, ops, lambda op: op == 'put' and k not in m.d and len(m.d) >= cap
                  or op in ('ref', 'refset') and k not in m.d)
        fresh = k not in m.d
        ver0, zver0, ne0 = m.ver, w(z.arena, o + 6), w(z.arena, o)
        what = (kind, key.name, val and val.name, cap, step, op, k)
        if op == 'put':
            if is_set:
                _, msg = dot(m, ty, 'add', k)
                res = z.call('bly_map_put', {'hl': h, 'de': OPS, 'bc': 0}, {OPS: kb})
            else:
                v = val.gen(rng)
                _, msg = model(lambda: SHIM.store(NS(k='index', obj=lit(m, ty), idx=[lit(k)], line=None), v, {}))
                res = z.call('bly_map_put', {'hl': h, 'de': OPS, 'bc': OPS + 0x10}, {OPS: kb, OPS + 0x10: val.pack(v)})
            if not res.failed and fresh and ne0 == cap:
                stat('compactions')
        elif op == 'del':
            _, msg = dot(m, ty, 'del', k)
            res = z.call('bly_map_del', {'hl': h, 'de': OPS}, {OPS: kb})
        elif op == 'has':
            want, msg = model(lambda: SHIM.e_bin(NS(op='in', a=lit(k), b=lit(m)), {}))
            res = z.call('bly_map_has', {'hl': h, 'de': OPS}, {OPS: kb})
            F.check(res.regs['a'] == want, what, 'has', res.regs['a'])
        elif op in ('ref', 'refset'):
            want, msg = model(lambda: SHIM.e_index(NS(obj=lit(m, ty), slice=False, idx=[lit(k)], line=None), {}))
            res = z.call('bly_map_ref', {'hl': h, 'de': OPS}, {OPS: kb})
            if not res.failed:
                a = res.regs['hl']
                F.check(val.unpack(z.arena[a - ARENA:a - ARENA + vs]) == want, what, 'ref')
                if op == 'refset':              # m[k] = v for a present key, through the reference
                    v = val.gen(rng)
                    model(lambda: SHIM.store(NS(k='index', obj=lit(m, ty), idx=[lit(k)], line=None), v, {}))
                    poke(z, a, val.pack(v))
            else:
                stat('missing keys')
        else:
            d = val.gen(rng)
            want, msg = dot(m, ty, 'get', k, d)
            res = z.call('bly_map_getd', {'hl': h, 'de': OPS, 'bc': OPS + 0x10, 'ix': OPS + 0x20},
                         {OPS: kb, OPS + 0x10: val.pack(d), OPS + 0x20: b'\x5a' * 16})
            F.check(val.unpack(res.mem[OPS + 0x20:OPS + 0x20 + vs]) == want and res.mem[OPS + 0x20 + vs] == 0x5A,
                    what, 'getd', res.mem[OPS + 0x20:OPS + 0x28].hex())
        if not same_failure(res, msg, *what) or res.failed:
            if res.failed:
                stat(f'{kind} ended by {msg.split()[0]} {msg.split()[1]}')
            break
        walk = map_walk(z, h)
        want = [(key.pack(kk), b'' if is_set else val.pack(vv)) for kk, vv in m.d.items()]
        F.check(walk == want, what, 'walk', [(key.unpack(a), b.hex()) for a, b in walk], list(m.d.items()))
        F.check(w(z.arena, o + 2) == len(m.d), what, 'live', w(z.arena, o + 2), len(m.d))
        zver = w(z.arena, o + 6)
        F.check((zver - zver0) & 0xFFFF == m.ver - ver0, what, 'ver moved', zver - zver0, 'want', m.ver - ver0)
        untouched(z, used, what)
        stat('map steps')
    else:
        stat(f'{kind} ran its course')


# ---- grids

def grid_block(rows, cols, el, fill_addr):
    return quad(rows) + quad(cols) + struct.pack('<HHHH', el.size, SYM[el.cmp], SYM[el.pr], fill_addr)


def test_grid_new(rng):
    sides = [0, 1, 2, 3, 7, -1, -32768, 32767, 32768, 65536, 2**40, -2**63, 2**63 - 1, 127, 128, 255, 256]
    for _ in range(400):
        rows = rng.choice(sides + [rng.randrange(0, 60)] * 4)
        cols = rng.choice(sides + [rng.randrange(0, 60)] * 4)
        el = rng.choice(ELEMS)
        fill = el.gen(rng) if rng.random() < 0.7 else el.unpack(bytes(el.size))
        ty = B.Gen('grid', el.ty)
        cells = rows * cols * el.size
        if 0 <= rows <= 32767 and 0 <= cols <= 32767 and cells > 20000:
            msg = 'arena full'                  # the interpreter would make it; the test arena can't hold it
            g = None
        else:
            g, msg = new('grid', ty, rows, cols, fill)
            if msg is None and cells + 12 > 0x4000:
                msg = 'arena full'
        z = Z80()
        res = z.call('bly_grid_new', {'hl': OPS}, {OPS: grid_block(rows, cols, el, OPS + 0x40), OPS + 0x40: el.pack(fill)})
        what = ('grid new', rows, cols, el.name, fill)
        if not same_failure(res, msg, *what) or res.failed:
            stat(f'grid new failed: {msg}')
            continue
        stat('grid new')
        h = res.regs['hl']
        F.check([w(res.mem, h + i) for i in range(0, 12, 2)] == [rows, cols, el.size, h + 12, SYM[el.cmp], SYM[el.pr]]
                and w(res.mem, SYM['bly_atop']) == h + 12 + cells, what, 'header')
        got = [el.unpack(res.mem[h + 12 + i * el.size:][:el.size]) for i in range(rows * cols)]
        F.check(got == [v for row in g.cells for v in row], what, 'cells')


def small_grid(rng, el, rows=None, cols=None, universe=None):
    """a grid made on both sides, its cells then set at random (as generated code would, through bly_grid_ref)"""
    rows = rng.randrange(0, 12) if rows is None else rows
    cols = rng.randrange(0, 12) if cols is None else cols
    ty = B.Gen('grid', el.ty)
    fill = el.gen(rng)
    g, msg = new('grid', ty, rows, cols, fill)
    z = Z80()
    res = z.call('bly_grid_new', {'hl': OPS}, {OPS: grid_block(rows, cols, el, OPS + 0x40), OPS + 0x40: el.pack(fill)})
    assert msg is None and not res.failed
    h = res.regs['hl']
    universe = universe or [el.gen(rng) for _ in range(4)]
    for r in range(rows):
        for c in range(cols):
            if rng.random() < 0.8:
                v = rng.choice(universe)
                g.cells[r][c] = v
                poke(z, h + 12 + (r * cols + c) * el.size, el.pack(v))
    return g, ty, z, h, universe


def test_grid_ops(rng):
    for _ in range(60):
        el = rng.choice(ELEMS)
        g, ty, z, h, universe = small_grid(rng, el)
        rows, cols = g.rows, g.cols
        for _ in range(25):                     # ref: the cell's address
            if not rows or not cols:
                break
            r, c = rng.randrange(rows), rng.randrange(cols)
            res = z.call('bly_grid_ref', {'hl': h, 'de': r, 'bc': c})
            F.check(res.regs['hl'] == h + 12 + (r * cols + c) * el.size, 'grid ref', rows, cols, r, c)
        edge = [-32768, -1, 0, 1, 32767] + [rows - 1, rows, cols - 1, cols]
        for _ in range(40):                     # has, and chk16
            r = rng.choice(edge + [rng.randrange(-3, rows + 3)] * 3)
            c = rng.choice(edge + [rng.randrange(-3, cols + 3)] * 3)
            want, _ = dot(g, ty, 'has', (r, c))
            res = z.call('bly_grid_has', {'hl': h, 'de': OPS}, {OPS: struct.pack('<hh', r, c)})
            F.check(res.regs['a'] == want, 'grid has', rows, cols, r, c, res.regs['a'])
            _, msg = model(lambda: g.check(r, c, None))
            res = z.call('bly_grid_chk16', {'hl': h, 'de': r & 0xFFFF, 'bc': c & 0xFFFF, 'ix': 0x4321})
            if same_failure(res, msg, 'grid chk16', rows, cols, r, c) and not res.failed:
                F.check((res.regs['hl'], res.regs['de'], res.regs['bc'], res.regs['ix']) == (h, r & 0xFFFF, c & 0xFFFF,
                        0x4321), 'chk16 clobbered', res.regs)
        for _ in range(6):                      # find: present, absent
            v = rng.choice(universe + [el.gen(rng)])
            want, msg = dot(g, ty, 'find', v)
            res = z.call('bly_grid_find', {'hl': h, 'de': OPS, 'bc': OPS + 0x10}, {OPS: el.pack(v)})
            if same_failure(res, msg, 'grid find', el.name, rows, cols, v) and not res.failed:
                F.check(struct.unpack('<hh', res.mem[OPS + 0x10:OPS + 0x14]) == want, 'grid find', v, want)
            stat('grid find ' + ('missing' if msg else 'found'))
    # a wide one-byte grid, for find's CPIR path along long rows
    for rows, cols in ((3, 300), (40, 40), (1, 1), (2, 5000)):
        g, ty, z, h, universe = small_grid(rng, U8, rows, cols, [7, 9])
        for v in (7, 9, 200, g.cells[-1][-1]):
            want, msg = dot(g, ty, 'find', v)
            res = z.call('bly_grid_find', {'hl': h, 'de': OPS, 'bc': OPS + 0x10}, {OPS: U8.pack(v)})
            if same_failure(res, msg, 'grid find wide', rows, cols, v) and not res.failed:
                F.check(struct.unpack('<hh', res.mem[OPS + 0x10:OPS + 0x14]) == want, 'grid find wide', v, want)


# ---- sorting a fixed array, and bly_changed

def test_sort(rng):
    sizes = [0, 1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 100] + [rng.randrange(0, 400) for _ in range(40)]
    for n in sizes:
        el = rng.choice(ELEMS)
        pool = [el.gen(rng) for _ in range(rng.choice([1, 2, 5, 1000]))]
        vals = [rng.choice(pool) for _ in range(n)]
        if rng.random() < 0.2:
            vals.sort(reverse=rng.random() < 0.5)
        data = b''.join(el.pack(v) for v in vals)
        z = Z80()
        z.arena = data + bytes(0x4000 - len(data))
        res = deep(z, 'bly_sort', {'hl': ARENA, 'de': n, 'bc': el.size, 'ix': SYM[el.cmp]}, rng)
        got = [el.unpack(z.arena[i * el.size:][:el.size]) for i in range(n)]
        F.check(got == sorted(vals) and not res.failed and not any(z.arena[len(data):]), 'sort', el.name, n)
        stat('sorts')


def test_changed():
    s = NS(line=None, names=['x'])
    for code, kind in enumerate(('list', 'queue', 'heap', 'map', 'set')):
        if kind == 'heap':                      # no for can walk a heap; the words follow the others
            msg = 'the heap changed while for was walking it'
        else:
            it = {'list': B.BList, 'queue': B.BQueue, 'map': B.BMap, 'set': B.BSet}[kind](5)
            walk = SHIM.walk(it, B.Gen(kind, B.INT), s)
            if kind in ('list', 'queue'):
                it.items.append(1)
            else:
                it.d[1] = 1
            next(walk)
            it.ver += 1                         # the change, as push, put, add or del would count it
            _, msg = model(lambda: next(walk))
        res = R.call('bly_changed', regs={'a': code})
        same_failure(res, msg, 'changed', kind)


# ---- watching the tests fail: each mutant plants one bug, and the suite must notice. The last is a control: a
# different hash is no bug at all (the hash is the map's own business), so that one must pass.
MUTANTS = [
    ('map.asm', 'or a                        ; (carry is set here: live < cap)', 'nop', 'compaction one late'),
    ('map.asm', 'jr z,.absent                ; FFFFh: the end of the chain', 'jr .absent', 'a tombstone ends the chain'),
    ('map.asm', 'inc (ix+6)                  ; ver\n        ret nz', 'nop\n        ret nz', 'del leaves ver'),
    ('map.asm', 'ld (hl),1                   ; alive', 'ld (hl),2', 'alive is 2'),
    ('map.asm', 'jr z,.cmoved                ; already in place', 'nop\n        nop', 'compaction copies in place'),
    ('heap.asm', "jp p,.place                 ; v >= parent: the hole is v's place", 'jp m,.place',
     'push compares backwards'),
    ('heap.asm', 'jp p,.one\n', 'jp m,.one\n', 'pop takes the bigger child'),
    ('heap.asm', 'cmp(last, parent)\n        or a\n        jp p,.place', 'cmp(last, parent)\n        or a\n        jp .place',
     'pop never climbs'),
    ('heap.asm', 'push de                     ; the path', 'push hl', 'pop climbs the wrong path'),
    ('list.asm', 'or a\n        sbc hl,bc\n        jr nc,.full', 'scf\n        sbc hl,bc\n        jr nc,.full',
     'list full one early'),
    ('queue.asm', 'jr z,.wrap                  ; head + 1 = cap: back to 0', 'jr nz,.wrap', 'get wraps wrongly'),
    ('queue.asm', 'jr nc,.in\n', 'jr c,.in\n', 'the ring index'),
    ('sort.asm', 'jp m,.one\n', 'nop\n        nop\n        nop\n', 'sort takes the smaller child'),
    ('sort.asm', 'jp m,.place                 ; tmp <= parent: here', 'nop', 'sort climbs too far'),
    ('sort.asm', 'ld (.base),sp', 'nop', 'sort climbs past its subtree'),
    ('sort.asm', 'sbc hl,bc\n        add hl,sp\n        ld sp,hl', 'sbc hl,bc\n        add hl,sp\n        nop',
     'tmp is not given room'),
    ('map.asm', 'ld l,(ix+20)                ; FFFDh', 'ld l,(ix+18)                ; FFFDh', 'the wrap goes astray'),
    ('sort.asm', '        ld (.tmp4+1),hl\n', '        ld (.tmp4+1),hl\n        ld (.sp0-1),hl\n',
     'a patch lands on the saved SP'),
    ('heap.asm', '        ld (.sp),sp ', '        ld (.sp),sp\n        ld (.sp+1),a\n        nop ', 'pop saves SP wrongly'),
    ('cont.asm', 'ld b,6\n        xor a', 'ld b,5\n        xor a', 'a cap of 65536..16M passes'),
    ('cont.asm', 'db "list",0,"queue",0', 'db "list",0,"queeu",0', 'a misspelled kind'),
    ('cont.asm', '.nw:    dec a', '.nw:    nop', 'the wide multiply loops on'),
    ('grid.asm', 'ld a,e\n        sub (hl)', 'ld a,e\n        scf\n        sbc a,(hl)', 'chk16 lets r = rows by'),
    ('grid.asm', 'ld a,c\n        sub (hl)\n        inc hl\n        ld a,b\n        sbc a,(hl)                  ; c - cols\n        ld a,0',
     'ld a,c\n        scf\n        sbc a,(hl)\n        inc hl\n        ld a,b\n        sbc a,(hl)\n        ld a,0',
     'has lets c = cols by'),
    ('grid.asm', 'scf\n        sbc hl,bc                   ; c = cols - left - 1', 'or a\n        sbc hl,bc',
     'find on bytes: c one out'),
    ('grid.asm', 'jr nz,.fillit', 'jr .done', 'fill is never written'),
    ('map.asm', 'add hl,bc\n        pop de\n        ld a,h', 'add hl,hl\n        pop de\n        ld a,h',
     'CONTROL: another hash (must pass)'),
]


def mutants():
    import shutil, subprocess, tempfile
    lib = os.path.join(HERE, '..', 'lib')
    missed = 0
    for f, old, new_, why in MUTANTS:
        with tempfile.TemporaryDirectory(dir=paths.build_dir('container-tests')) as d:
            for name in os.listdir(lib):
                if name.endswith('.asm'):
                    shutil.copy(os.path.join(lib, name), d)
            text = open(os.path.join(d, f)).read()
            assert text.count(old) == 1, (f, old, text.count(old))
            open(os.path.join(d, f), 'w').write(text.replace(old, new_))
            p = subprocess.run([sys.executable, __file__, '--quick', '--lib', d], capture_output=True, text=True)
            if 'sjasmplus' in p.stderr:
                print('BAD MUTANT (it does not assemble):', why)
                missed += 1
                continue
            caught = p.returncode != 0
            control = why.startswith('CONTROL')
            ok = caught != control
            missed += not ok
            first = next((l for l in p.stdout.splitlines() if l.startswith(('WRONG', 'containers'))), p.stderr[-200:])
            print(f'{"ok  " if ok else "MISS"} {why:34} {first[:110]}')
    print('mutants:', 'every one caught' if not missed else f'{missed} not caught')
    return missed


# ---- what it costs: T-states on shapes like AoC's, and bytes per fragment

def frag_bytes():
    """each fragment assembled alone, its needs stubbed: code plus its scratch words"""
    out = {}
    for f in link.load():
        if f.name not in ('cont.asm', 'list.asm', 'queue.asm', 'heap.asm', 'sort.asm', 'map.asm', 'grid.asm'):
            continue
        stubs = ''.join(f'{n} equ 0\n' for n in f.needs)
        code, _ = harness.assemble('        org 8000h\n' + stubs + f.text)
        out[f.name] = len(code)
    return out


def cost():
    rng = random.Random(7)
    rows = []

    def row(name, ts, note=''):
        ts = [t for t in ts if t is not None]
        rows.append((name, round(sum(ts) / len(ts)), max(ts), note))

    for el, n in ((U8, 1), (I16, 2), (POSK, 4), (I64, 8)):
        cap = 200
        m, z, h = make('list', el, cap, B.Gen('list', el.ty))
        ts = [z.call('bly_list_push', {'hl': h, 'de': OPS}, {OPS: el.pack(el.gen(rng))}).t for _ in range(cap)]
        row(f'list_push, esize {n}', ts)
        row(f'list_ref, esize {n}', [z.call('bly_list_ref', {'hl': h, 'de': i}).t for i in (0, 1, 100, 199, 255 % cap)])
        row(f'list_pop, esize {n}', [z.call('bly_list_pop', {'hl': h, 'de': OPS}).t for _ in range(cap)])
    m, z, h = make('list', I16, 10, B.Gen('list', I16.ty))
    row('list_clear', [z.call('bly_list_clear', {'hl': h}).t])
    m, z, h = make('list', I16, 300, B.Gen('list', I16.ty))
    ts = [z.call('bly_list_ref', {'hl': h, 'de': i}).t for i in (256, 299)]
    row('list_ref, esize 2, i >= 256', ts)
    for el, n in ((U8, 1), (POSK, 4)):
        cap = 100
        m, z, h = make('queue', el, cap, B.Gen('queue', el.ty))
        ts = []
        for _ in range(3):
            ts += [z.call('bly_queue_put', {'hl': h, 'de': OPS}, {OPS: el.pack(el.gen(rng))}).t for _ in range(60)]
            tg = [z.call('bly_queue_get', {'hl': h, 'de': OPS + 0x10}).t for _ in range(60)]
        row(f'queue_put, esize {n}', ts)
        row(f'queue_get, esize {n}', tg)
        z.call('bly_queue_put', {'hl': h, 'de': OPS}, {OPS: el.pack(el.gen(rng))})
        row(f'queue_at, esize {n}', [z.call('bly_queue_at', {'hl': h, 'de': 0}).t])
    for el, n, cmpcost in ((I16, 2, 'tst_cmp_i16'), (POSK, 4, 'tst_cmp_pos')):
        cap = 1000 if n == 2 else 500
        m, z, h = make('heap', el, cap, B.Gen('heap', el.ty))
        tp = [z.call('bly_heap_push', {'hl': h, 'de': OPS}, {OPS: el.pack(el.gen(rng))}).t for _ in range(cap)]
        to = [z.call('bly_heap_pop', {'hl': h, 'de': OPS + 0x10}).t for _ in range(cap)]
        row(f'heap_push, {el.name}, {cap} random', tp, f'calls {cmpcost}')
        row(f'heap_pop, {el.name}, {cap} random', to)
    cmp_t = [R.call('tst_cmp_i16', regs={'hl': OPS, 'de': OPS + 2}, mem={OPS: b'\x05\x00\x07\x00'}).t]
    row('(the test cmp for ints, for scale)', cmp_t)
    # maps: pos keys from a diamond on a grid (a BFS's visited set), int keys, quad keys; cap 1000, half full or less
    keysets = [
        ('pos', POSK, I16, [(r, c) for r in range(141) for c in range(141) if abs(r - 70) + abs(c - 70) <= 22][:1000]),
        ('int', I16, I16, rng.sample(range(-32768, 32768), 1000)),
        ('quad', I64, I16, [rng.randrange(1 << 40) for _ in range(800)]),
    ]
    for name, key, val, keys in keysets:
        cap = len(keys)
        z = Z80()
        res = z.call('bly_map_new', {'hl': OPS}, {OPS: quad(cap) + struct.pack('<HHHB', key.size, val.size, SYM[key.pr], 0)})
        h = res.regs['hl']
        row(f'map_new, {name} keys, cap {cap}', [res.t])
        tput = [z.call('bly_map_put', {'hl': h, 'de': OPS, 'bc': OPS + 8}, {OPS: key.pack(k), OPS + 8: b'\1\0'}).t
                for k in keys]
        row(f'map_put, {name}, a new key', tput, f'{cap} keys into cap {cap}')
        thas = [z.call('bly_map_has', {'hl': h, 'de': OPS}, {OPS: key.pack(k)}).t for k in keys]
        row(f'map_has, {name}, present', thas)
        others = [key.gen(rng) for _ in range(300)]
        row(f'map_has, {name}, absent', [z.call('bly_map_has', {'hl': h, 'de': OPS}, {OPS: key.pack(k)}).t
                                         for k in others if k not in set(keys)])
        row(f'map_ref, {name}', [z.call('bly_map_ref', {'hl': h, 'de': OPS}, {OPS: key.pack(k)}).t for k in keys[:300]])
        row(f'map_put, {name}, an old key', [z.call('bly_map_put', {'hl': h, 'de': OPS, 'bc': OPS + 8},
                                                    {OPS: key.pack(k), OPS + 8: b'\2\0'}).t for k in keys[:300]])
        row(f'map_getd, {name}', [z.call('bly_map_getd', {'hl': h, 'de': OPS, 'bc': OPS + 8, 'ix': OPS + 16},
                                         {OPS: key.pack(k), OPS + 8: b'\0\0'}).t for k in keys[:300]])
        tdel = [z.call('bly_map_del', {'hl': h, 'de': OPS}, {OPS: key.pack(k)}).t for k in keys[::2]]
        row(f'map_del, {name}', tdel)
        tc = z.call('bly_map_put', {'hl': h, 'de': OPS, 'bc': OPS + 8}, {OPS: key.pack(others[0]), OPS + 8: b'\1\0'}).t
        row(f'map_put, {name}, compacting {cap} to {cap // 2}', [tc])
    for el, n in ((U8, 1), (POSK, 4)):
        z = Z80()
        res = z.call('bly_grid_new', {'hl': OPS}, {OPS: grid_block(100, 30 if n == 4 else 100, el, OPS + 0x40),
                                                   OPS + 0x40: el.pack((1, 1) if n == 4 else 46)})
        h = res.regs['hl']
        row(f'grid_new, {100}x{30 if n == 4 else 100}, esize {n}, filled', [res.t])
        ts = [z.call('bly_grid_ref', {'hl': h, 'de': r, 'bc': c}).t for r, c in ((0, 0), (1, 5), (50, 20), (99, 29), (77, 3))]
        row(f'grid_ref, esize {n}', ts)
        if n == 1:
            row('grid_chk16 (in range)', [z.call('bly_grid_chk16', {'hl': h, 'de': r, 'bc': c}).t for r, c in ((5, 5), (99, 99))])
            row('grid_has', [z.call('bly_grid_has', {'hl': h, 'de': OPS}, {OPS: struct.pack('<hh', r, c)}).t
                             for r, c in ((5, 5), (-1, 5), (99, 99), (100, 0))])
            poke(z, h + 12 + 9999, b'S')
            row('grid_find, 100x100 bytes, the last cell', [z.call('bly_grid_find', {'hl': h, 'de': OPS, 'bc': OPS + 8},
                                                                    {OPS: b'S'}).t], 'CPIR, a row at a time')
        else:
            poke(z, h + 12 + 2999 * 4, POSK.pack((7, 7)))
            row('grid_find, 100x30 pos, the last cell', [z.call('bly_grid_find', {'hl': h, 'de': OPS, 'bc': OPS + 8},
                                                                 {OPS: POSK.pack((7, 7))}).t], 'cmp on each cell')
    for n in (100, 1000):
        vals = [rng.randrange(-32768, 32768) for _ in range(n)]
        z = Z80()
        z.arena = b''.join(I16.pack(v) for v in vals) + bytes(0x4000 - 2 * n)
        t = z.call('bly_sort', {'hl': ARENA, 'de': n, 'bc': 2, 'ix': SYM['tst_cmp_i16']}).t
        row(f'sort, {n} random ints', [t], f'{t / n:.0f} T an element')
    sizes = frag_bytes()
    print(f'{"routine":44} {"typical":>9} {"worst":>9}  note')
    for name, typ, worst, note in rows:
        print(f'{name:44} {typ:9,} {worst:9,}  {note}')
    print()
    for f, b in sizes.items():
        print(f'{f:12} {b:5} bytes')


def test_mul(rng):
    """the containers' multiplies, including the 16-bit path no element size reaches in the sequences"""
    vals = [0, 1, 2, 3, 255, 256, 257, 4095, 32767, 32768, 65535]
    for _ in range(600):
        b = rng.choice(vals + [rng.randrange(65536)] * 3 + [rng.randrange(300)] * 2)
        d = rng.choice(vals + [rng.randrange(65536)] * 3 + [rng.randrange(300)] * 2)
        res = R.call('bly_cn_mul', regs={'bc': b, 'de': d})
        F.check(res.regs['hl'] == b * d & 0xFFFF and not res.failed, 'cn_mul', b, d, res.regs['hl'])
        res = R.call('bly_cn_cmul', regs={'bc': b, 'de': d})
        carry = res.regs['f'] & 1
        F.check(res.regs['bc'] == b and carry == (b * d > 0xFFFF) and (carry or res.regs['hl'] == b * d),
                'cn_cmul', b, d, res.regs)


def main():
    args = sys.argv[1:]
    if '--mutants' in args:
        return mutants()
    if '--cost' in args:
        return cost()
    seed = int(args[args.index('--seed') + 1]) if '--seed' in args else 1
    quick = '--quick' in args
    rng = random.Random(seed)
    test_constructors(rng)
    test_mul(rng)
    test_changed()
    test_grid_new(rng)
    test_grid_ops(rng)
    test_sort(rng)
    reps, steps = (2, 120) if quick else (8, 300)
    for el in ELEMS:
        for _ in range(reps):
            list_seq(rng, el, steps)
            queue_seq(rng, el, steps)
            heap_seq(rng, el, steps)
    for _ in range(reps * 12):
        map_seq(rng, steps + 100)
    print('containers:', 'all right' if not F.bad else f'{F.bad} wrong', f'({F.checks} checks, seed {seed})')
    for k in sorted(STATS):
        print(f'  {STATS[k]:6}  {k}')
    return F.bad


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
