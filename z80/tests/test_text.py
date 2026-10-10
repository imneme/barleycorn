"""Text and input, against the interpreter: text.asm, text_chr.asm, intern.asm, input.asm,
input_grid.asm and elem_byte.asm.

The model is the interpreter's own code, reached through small hand-made nodes: e_dot for the str methods
(split, find, starts, trim, lines' next), e_index for slices, e_call for intern, name, chr, grid and input, and
Interp.__init__ for splitting the input into lines. Every failure is compared byte for byte, " at line 7"
included: the drivers below set bly_line to 7 first.

    $OMSE_AI_PYTHON z80/tests/test_text.py [--quick] [--cost]
BLY_LIB=<dir> runs it against another copy of lib/ (to watch it catch a broken routine).
"""
import functools
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'interp'))
import harness                                # noqa: E402
import link                                   # noqa: E402
import barley as B                            # noqa: E402

if os.environ.get('BLY_LIB'):
    harness.gather = functools.partial(link.gather, lib=os.environ['BLY_LIB'])

QUICK = '--quick' in sys.argv
N = 300 if QUICK else 2000                    # random cases per routine
LINE = 7
rng = random.Random(int(os.environ.get('SEED', '4')))

# -- the model: the interpreter's own code ---------------------------------------------------------------------

IP = B.Interp(None, b'', None)                # __init__ only keeps the checker and splits the input


def lit(v, ty=None):
    return B.N('lit', LINE, cval=v, ty=ty)


def method(s, name, *args, ty=B.STR):
    return IP.e_dot(B.N('dot', LINE, obj=lit(s, ty), name=name, args=[lit(a) for a in args]), {})


def builtin(ip, name, *args):
    return ip.e_call(B.N('call', LINE, builtin=name, args=[lit(a) for a in args]), {})


def m_cmp(a, b):
    return -1 if B.compare('<', a, b) else 1 if B.compare('>', a, b) else 0


def m_slice(s, a, b):
    return IP.e_index(B.N('index', LINE, obj=lit(s, B.STR), idx=[lit(B.Range(a, b, False))], slice=True), {})


def ask(fn):
    """('ok', value), or ('fail', the message as the Z80 prints it)"""
    try:
        return 'ok', fn()
    except B.BarleyError as e:
        return 'fail', str(e) + '\n'


# -- the Z80 side ----------------------------------------------------------------------------------------------

DRIVERS = r'''
; ---- test_text.py's drivers
t_line7:                ; bly_line = 7, so failures end " at line 7"; keeps every register
        push hl
        ld hl,7
        ld (bly_line),hl
        pop hl
        ret

w_cmp_str:  call t_line7
        jp bly_cmp_str
w_find:     call t_line7
        jp bly_find
w_starts:   call t_line7
        jp bly_starts
w_trim:     call t_line7
        jp bly_trim
w_slice:    call t_line7
        jp bly_slice
w_name:     call t_line7
        jp bly_name

t_split:                ; HL = &s, DE = &sep, BC = &out -> HL = the pieces, written as strs at out
        call t_line7
        ld (.out),bc
        ld bc,0
        ld (.cnt),bc
        ld b,d
        ld c,e
        ex de,hl
        ld hl,.state
        call bly_split_init
.loop:  ld hl,.state
        ld de,.piece
        call bly_split_next
        or a
        jr z,.end
        ld hl,.piece
        ld de,(.out)
        ld bc,4
        ldir
        ld (.out),de
        ld hl,(.cnt)
        inc hl
        ld (.cnt),hl
        jr .loop
.end:   ld hl,.state            ; once it has said no, it keeps saying no
        ld de,.piece
        call bly_split_next
        ld (t_again),a
        ld hl,(.cnt)
        ret
.state: db 0EEh,0EEh,0EEh,0EEh,0EEh,0EEh,0EEh,0EEh,0EEh,0EEh,0EEh
.piece: ds 4
.out:   dw 0
.cnt:   dw 0
t_again: db 0

t_nest:                 ; HL = &s, DE = &outer sep, BC = &inner sep, IX = &out: for each outer piece, its inner
        call t_line7    ; pieces and then FFFFh FFFFh; a find between the inner pieces stirs the shared scratch
        ld (.isep),bc
        ld (.osep),de
        ld (.out),ix
        ld b,d
        ld c,e
        ex de,hl
        ld hl,.st1
        call bly_split_init
.outer: ld hl,.st1
        ld de,.p1
        call bly_split_next
        or a
        ret z
        ld hl,.st2
        ld de,.p1
        ld bc,(.isep)
        call bly_split_init
.inner: ld hl,.st2
        ld de,.p2
        call bly_split_next
        or a
        jr z,.idone
        ld hl,.p2
        ld de,(.osep)
        call bly_find
        ld hl,.p2
        ld de,(.out)
        ld bc,4
        ldir
        ld (.out),de
        jr .inner
.idone: ld hl,(.out)
        ld b,4
.mark:  ld (hl),0FFh
        inc hl
        djnz .mark
        ld (.out),hl
        jr .outer
.st1:   ds 11
.st2:   ds 11
.p1:    ds 4
.p2:    ds 4
.isep:  dw 0
.osep:  dw 0
.out:   dw 0

t_intern:               ; HL = a table of str addresses (words), BC = how many, DE = &ids (words)
        call t_line7
.loop:  ld a,b
        or c
        ret z
        push bc
        push de
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        push hl
        ex de,hl
        call bly_intern
        ex de,hl
        pop hl
        ex (sp),hl
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ex de,hl
        pop hl
        pop bc
        dec bc
        jr .loop

t_ask:  dw 0
t_inames:               ; as t_intern, then name(0) .. name(t_ask - 1) as strs at IX
        push ix
        call t_intern
        pop de
        ld hl,0
.loop:  ld bc,(t_ask)
        or a
        sbc hl,bc
        add hl,bc
        ret z
        push hl
        push de
        call bly_name
        pop hl
        ld de,4
        add hl,de
        ex de,hl
        pop hl
        inc hl
        jr .loop

t_input:                ; HL = a bly_alimit to use, or 0 to keep the test platform's
        ld a,h
        or l
        jr z,.go
        ld (bly_alimit),hl
.go:    jp bly_split_input

t_lines2:               ; split the input; two lines() iterators; HL = &script (0: the first, 1: the second),
        push hl         ; BC = its length, DE = &out: each .next() as a str
        push de
        push bc
        call bly_split_input
        call t_line7
        call bly_lines_new
        ld (.a),hl
        call bly_lines_new
        ld (.b),hl
        pop bc
        pop de
        pop hl
.loop:  ld a,b
        or c
        ret z
        push bc
        push hl
        push de
        ld a,(hl)
        ld hl,(.a)
        or a
        jr z,.go
        ld hl,(.b)
.go:    call bly_lines_next
        pop hl
        ld de,4
        add hl,de
        ex de,hl
        pop hl
        inc hl
        pop bc
        dec bc
        jr .loop
.a:     dw 0
.b:     dw 0

t_grid:                 ; split the input, then grid(); HL = a bly_alimit to use, or 0 to keep the platform's
        ld a,h
        or l
        jr z,.go
        ld (bly_alimit),hl
.go:    call bly_split_input
        call t_line7
        jp bly_grid_input

t_atop: dw 0A000h
t_fn:   dw 0
t_direct:               ; for timing: bly_atop = t_atop (bly_test_init reset it), then on to the routine at t_fn
        push hl         ; with every register as given. 81 T of overhead, CALL included.
        ld hl,(t_atop)
        ld (bly_atop),hl
        pop hl
        ld ix,(t_fn)
        jp (ix)
'''

NEEDS = ['bly_alloc_raw', 'bly_cmp_str', 'bly_slice', 'bly_find', 'bly_starts', 'bly_trim', 'bly_chr', 'bly_split_init',
         'bly_split_next', 'bly_intern', 'bly_name', 'bly_split_input', 'bly_lines_new', 'bly_lines_next',
         'bly_input', 'bly_grid_input', 'bly_cmp_byte', 'bly_pr_byte', 'bly_line']
R = harness.Runner(NEEDS, extra=DRIVERS)

LO, HI = 0x4000, 0x8000                       # free RAM in the bare machine, for long strings and texts
OPS = 0xE000                                  # small operands
IXV = 0x5A5A                                  # IX going in, to see it kept

bad = 0
counts = {}


def wrong(what, *info):
    global bad
    bad += 1
    if bad <= 40:
        print('WRONG', what, *[repr(x)[:300] for x in info])


def count(what, k=1):
    counts[what] = counts.get(what, 0) + k


def w16(v):
    return (v & 0xFFFF).to_bytes(2, 'little')


def rd16(m, a):
    return m[a] | m[a + 1] << 8


def rdstr(m, a):
    p, n = rd16(m, a), rd16(m, a + 2)
    return p, n, (bytes(m[p:p + n]) if n else b'')


class Space:
    """lays out strs: bytes, then the (p, n) that points at them"""

    def __init__(self, base, end):
        self.base, self.at, self.end, self.img = base, base, end, bytearray(end - base)

    def put(self, data):
        a = self.at
        self.img[a - self.base:a - self.base + len(data)] = data
        self.at += len(data)
        assert self.at <= self.end, 'test space full'
        return a

    def str(self, s, zero_p=False):
        p = self.put(s)
        if not s and zero_p:
            p = 0
        return self.put(w16(p) + w16(len(s))), p

    def mem(self):
        return {self.base: bytes(self.img[:self.at - self.base])}


def untouched(res, mem, keep):
    """every byte the test put in memory is still there, apart from the ranges in keep"""
    for base, data in mem.items():
        if res.mem[base:base + len(data)] == data:
            continue
        for i, b in enumerate(data):
            a = base + i
            if res.mem[a] != b and not any(lo <= a < hi for lo, hi in keep):
                return a
    return None


def failed_as(res, want):
    return res.failed and res.out.decode('latin-1') == want


# -- cmp, starts, find, trim, slice -------------------------------------------------------------------------------

def rand_bytes(alpha, lo, hi):
    return bytes(rng.choice(alpha) for _ in range(rng.randint(lo, hi)))


ALPHAS = [b'ab', b'abc', b'\x00\x7f\x80\xff', bytes(range(256)), b'a', b' \tab']


def pairs():
    hand = [(b'', b''), (b'', b'a'), (b'a', b''), (b'a', b'a'), (b'a', b'b'), (b'b', b'a'), (b'ab', b'a'),
            (b'a', b'ab'), (b'\x80', b'\x7f'), (b'\x7f', b'\x80'), (b'\xff', b'\x00'), (b'\x00', b'\xff'),
            (b'abc', b'abd'), (b'x' * 300, b'x' * 300), (b'x' * 300, b'x' * 299 + b'y'), (b'x' * 256, b'x' * 257),
            (b'\x00', b''), (b'', b'\x00')]
    for a, b in hand:
        yield a, b
    for _ in range(N):
        alpha = rng.choice(ALPHAS)
        a = rand_bytes(alpha, 0, rng.choice([3, 8, 20, 300]))
        k = rng.random()
        if k < 0.3:
            b = a
        elif k < 0.5:
            b = a[:rng.randint(0, len(a))]
        elif k < 0.6:
            b = a + rand_bytes(alpha, 1, 3)
        else:
            b = rand_bytes(alpha, 0, rng.choice([3, 8, 20, 300]))
        if rng.random() < 0.5:
            a, b = b, a
        yield a, b


def test_two_str():
    """cmp_str, starts and find, on the same pairs"""
    for a, b in pairs():
        sp = Space(LO, HI)
        sa, _ = sp.str(a, zero_p=rng.random() < 0.5)
        sb, _ = sp.str(b, zero_p=rng.random() < 0.5)
        mem = sp.mem()
        regs = {'hl': sa, 'de': sb, 'ix': IXV}
        # cmp
        res = R.call('w_cmp_str', regs=regs, mem=mem)
        want = m_cmp(a, b)
        f = res.regs['f']
        if res.failed or res.regs['a'] != want & 0xFF or bool(f & 0x40) != (want == 0) or bool(f & 0x80) != (want < 0) \
                or res.regs['ix'] != IXV or untouched(res, mem, []):
            wrong('cmp_str', a, b, want, res.regs, res.out)
        count('cmp_str')
        # starts
        res = R.call('w_starts', regs=regs, mem=mem)
        want = method(a, 'starts', b)
        if res.failed or res.regs['a'] != int(want) or res.regs['ix'] != IXV or untouched(res, mem, []):
            wrong('starts', a, b, want, res.regs)
        count('starts')
        # find
        res = R.call('w_find', regs=regs, mem=mem)
        kind, want = ask(lambda: method(a, 'find', b))
        if kind == 'fail' or res.failed or res.regs['hl'] != want & 0xFFFF or res.regs['ix'] != IXV \
                or untouched(res, mem, []):
            wrong('find', a, b, want, res.regs, res.out)
        count('find')


def test_find_more():
    """find with the needle cut from the haystack, near misses, and the int overflow past 32767"""
    for _ in range(N):
        alpha = rng.choice([b'ab', b'abc', b'aab', bytes(range(256))])
        s = rand_bytes(alpha, 0, rng.choice([10, 60, 600]))
        if s and rng.random() < 0.7:
            i = rng.randrange(len(s))
            t = s[i:i + rng.randint(1, 6)]
            if rng.random() < 0.3 and t:          # the same, but its last byte changed: a near miss
                t = t[:-1] + bytes([t[-1] ^ 1])
        else:
            t = rand_bytes(alpha, 0, 4)
        sp = Space(LO, HI)
        if s and t and rng.random() < 0.3:         # memory goes on past s with the rest of t
            k = rng.randint(1, len(t))
            s2 = s + t[k:] if s.endswith(t[:k]) else s
            pp = sp.put(s2 + t)
            ss = sp.put(w16(pp) + w16(len(s)))
        else:
            ss, _ = sp.str(s)
        st, _ = sp.str(t)
        res = R.call('w_find', regs={'hl': ss, 'de': st}, mem=sp.mem())
        kind, want = ask(lambda: method(s, 'find', t))
        if res.failed or res.regs['hl'] != want & 0xFFFF:
            wrong('find', s, t, want, res.regs['hl'])
        count('find')
    # Long strs: (p = 0, n) runs over the ROM (zeros, and ED 45 at 0072h), the empty RAM, and on into the code at
    # 8000h, which starts with CDh. The model reads the same memory back from the run.
    for n, pat, where in ((0x8000, b'\xcd', 'absent'), (0x8001, b'\xcd', 32768), (0x9000, b'\xcd', 32768),
                          (0x8000, b'\x00\x00\x00', 0), (0x7000, b'\xed\x45', 0x72)):
        mem = {OPS: w16(0) + w16(n) + w16(OPS + 8) + w16(len(pat)) + pat}
        res = R.call('w_find', regs={'hl': OPS, 'de': OPS + 4}, mem=mem)
        hay = bytes(res.mem[0:n])
        kind, want = ask(lambda: method(hay, 'find', pat))
        ok = failed_as(res, want) if kind == 'fail' else (not res.failed and res.regs['hl'] == want & 0xFFFF)
        if not ok:
            wrong('find long', n, pat, want, res.out, res.regs['hl'])
        count('find')
    # exactly at 32767, which fits: the pattern placed in the empty RAM
    mem = {OPS: w16(0) + w16(0x8000) + w16(OPS + 8) + w16(2) + b'\x55\x66', 0x7FFF: b'\x55'}
    res = R.call('w_find', regs={'hl': OPS, 'de': OPS + 4}, mem=mem)
    mem2 = {OPS: w16(0) + w16(0x8000) + w16(OPS + 8) + w16(1) + b'\x55', 0x7FFF: b'\x55'}
    res2 = R.call('w_find', regs={'hl': OPS, 'de': OPS + 4}, mem=mem2)
    if res.regs['hl'] != 0xFFFF or res2.regs['hl'] != 32767 or res2.failed:
        wrong('find at 32767', res.regs['hl'], res2.regs['hl'])
    count('find', 2)


def test_trim_slice():
    hand = [b'', b' ', b'\t', b' \t ', b'a', b' a', b'a ', b'\ta\t', b' a b ', b'\na\n', b'\x0b a', b'a\x0c',
            b' ' * 300 + b'x' + b'\t' * 300]
    cases = hand + [rand_bytes(rng.choice([b' \tab', b' \t', b' \t\n\r\x0bx', bytes(range(256))]), 0,
                               rng.choice([4, 12, 40])) for _ in range(N)]
    for s in cases:
        sp = Space(LO, HI)
        ss, p = sp.str(s, zero_p=rng.random() < 0.5)
        dest = sp.put(b'\xee' * 4)
        mem = sp.mem()
        res = R.call('w_trim', regs={'hl': ss, 'de': dest, 'ix': IXV}, mem=mem)
        want = method(s, 'trim')
        q, n, got = rdstr(res.mem, dest)
        if res.failed or got != want or (n and q != p + s.index(want)) or res.regs['ix'] != IXV \
                or untouched(res, mem, [(dest, dest + 4)]):
            wrong('trim', s, want, got)
        count('trim')
    for _ in range(N):
        s = rand_bytes(bytes(range(256)), 0, rng.choice([5, 50, 300]))
        a = rng.randint(0, len(s))
        b = rng.randint(a, len(s))
        sp = Space(LO, HI)
        ss, p = sp.str(s, zero_p=rng.random() < 0.5)
        dest = sp.put(b'\xee' * 4)
        mem = sp.mem()
        res = R.call('w_slice', regs={'hl': ss, 'de': a, 'bc': b, 'ix': dest}, mem=mem)
        want = m_slice(s, a, b)
        q, n, got = rdstr(res.mem, dest)
        if res.failed or got != want or (n and q != p + a) or res.regs['de'] != a or res.regs['bc'] != b \
                or res.regs['ix'] != dest or untouched(res, mem, [(dest, dest + 4)]):
            wrong('slice', s, a, b, want, got, res.regs)
        count('slice')


def test_chr():
    seen = {}
    for b in list(range(256)) + [rng.randrange(256) for _ in range(50)]:
        res = R.call('bly_chr', regs={'a': b, 'de': OPS, 'bc': 0x1234, 'ix': IXV})
        p, n, got = rdstr(res.mem, OPS)
        want = builtin(IP, 'chr', b)
        atop = rd16(res.mem, res.sym['bly_atop'])
        if res.failed or got != want or seen.setdefault(b, p) != p or atop != 0xA000 or res.regs['bc'] != 0x1234 \
                or res.regs['ix'] != IXV:
            wrong('chr', b, got, p, hex(atop))
        count('chr')
    if len(set(seen.values())) != 256:
        wrong('chr: 256 different places', len(set(seen.values())))


# -- split ----------------------------------------------------------------------------------------------------

SEPS = [b',', b', ', b'ab', b'aa', b'aaa', b' -> ', b'\x00', b'\xff\xfe', b'abcab']


def split_case():
    sep = rng.choice(SEPS + [rand_bytes(b'ab,', 1, 3)])
    parts = [rand_bytes(rng.choice([b'ab', b'xyz', b'a,b ', bytes(range(256))]), 0, rng.choice([0, 2, 6, 30]))
             for _ in range(rng.randint(1, 6))]
    s = sep.join(parts)
    if rng.random() < 0.2:
        s = sep + s
    if rng.random() < 0.2:
        s = s + sep
    if rng.random() < 0.1:
        s = sep * rng.randint(1, 4)
    if rng.random() < 0.1:
        s = s[:rng.randint(0, len(s))]              # a separator cut short at the end
    return s, sep


def test_split():
    hand = [(b'', b','), (b',', b','), (b',,', b','), (b'a', b','), (b'a,', b','), (b',a', b','), (b'a,b', b','),
            (b'aaa', b'aa'), (b'aaaa', b'aa'), (b'a', b'ab'), (b'ab', b'ab'), (b'xabx', b'ab'), (b'', b''),
            (b'abc', b''), (b'a,b', b'a,b,c'), (b'1 -> 2 -> 3', b' -> '), (b'x' * 300 + b',' + b'y', b',')]
    cases = hand + [split_case() for _ in range(N)]
    cases += [(b'a,', b', '), (b'x,', b', '), (b',', b', '), (b'aa', b'aaa'), (b'a -', b' -> ')] * 4
    for s, sep in cases:
        sp = Space(LO, HI)
        if s and rng.random() < 0.3:               # memory goes on past s with the separator: nothing may read it
            p = sp.put(s + sep[1:] + sep)
            ss = sp.put(w16(p) + w16(len(s)))
        else:
            ss, p = sp.str(s, zero_p=rng.random() < 0.5)
        ssep, _ = sp.str(sep, zero_p=rng.random() < 0.5)
        out = sp.at
        mem = sp.mem()
        res = R.call('t_split', regs={'hl': ss, 'de': ssep, 'bc': out}, mem=mem)
        kind, want = ask(lambda: method(s, 'split', sep))
        if kind == 'fail':
            if not failed_as(res, want):
                wrong('split fail', s, sep, want, res.out)
            count('split')
            continue
        got, ok, off = [], True, 0
        for i in range(min(res.regs['hl'], len(want) + 1) if not res.failed else 0):
            q, n, piece = rdstr(res.mem, out + 4 * i)
            got.append(piece)
            if n and q != p + off:
                ok = False
            off += n + len(sep)
        if res.failed or got != want or not ok or res.mem[res.sym['t_again']] != 0 \
                or untouched(res, mem, [(out, out + 4 * len(want))]):
            wrong('split', s, sep, want, got, res.out)
        count('split')
    # one split inside another, with a find between the inner pieces
    for _ in range(N // 4):
        inner = [[rand_bytes(b'xy', 0, 3) for _ in range(rng.randint(1, 4))] for _ in range(rng.randint(1, 4))]
        osep, isep = rng.choice([(b';', b','), (b'; ', b', '), (b'ab', b'a'), (b'|', b'||')])
        if osep == b'ab':
            inner = [[x.replace(b'x', b'c') for x in row] for row in inner]
        s = osep.join(isep.join(row) for row in inner)
        sp = Space(LO, HI)
        ss, _ = sp.str(s)
        so, _ = sp.str(osep)
        si, _ = sp.str(isep)
        out = sp.at
        res = R.call('t_nest', regs={'hl': ss, 'de': so, 'bc': si, 'ix': out}, mem=sp.mem())
        want = []
        for piece in method(s, 'split', osep):
            want += method(piece, 'split', isep) + [None]
        got, a = [], out
        for _ in want:
            q, n, piece = rdstr(res.mem, a)
            got.append(None if (q, n) == (0xFFFF, 0xFFFF) else piece)
            a += 4
        if res.failed or got != want:
            wrong('split nested', s, osep, isep, want, got)
        count('split nested')


# -- intern and name ------------------------------------------------------------------------------------------

def intern_run(names, ask_n):
    """intern the names in order, then name(0 .. ask_n - 1); the strs go at 4000h, ids at E000h, names at E800h"""
    sp = Space(LO, HI)
    strs = [sp.str(s, zero_p=rng.random() < 0.5)[0] for s in names]
    table = sp.put(b''.join(w16(a) for a in strs))
    res = R.call('t_inames', regs={'hl': table, 'bc': len(names), 'de': OPS, 'ix': 0xE800}, mem=sp.mem(),
                 set16={'t_ask': ask_n})
    ip = B.Interp(None, b'', None)
    kind, want_ids = ask(lambda: [builtin(ip, 'intern', s) for s in names])
    got_ids = [rd16(res.mem, OPS + 2 * i) for i in range(len(names))]
    want_names, fail = [], None
    for i in range(ask_n):
        k, v = ask(lambda: builtin(ip, 'name', i))
        if k == 'fail':
            fail = v
            break
        want_names.append(v)
    got_names = [rdstr(res.mem, 0xE800 + 4 * i) for i in range(len(want_names))]
    ok = kind == 'ok' and got_ids == want_ids and [g[2] for g in got_names] == want_names
    ok = ok and all(not n or 0xA000 <= q < 0xE000 for q, n, _ in got_names)       # copies, in the arena
    ok = ok and (failed_as(res, fail) if fail else not res.failed)
    return ok, res, want_ids, got_ids


def test_intern():
    hand = [([], 1), ([b''], 1), ([b'', b''], 2), ([b'a', b'b', b'a', b''], 4), ([b'AAA', b'BBB', b'AAA'], 3),
            ([b'x'], 0), ([], 0)]
    for names, ask_n in hand:
        ok, res, w, g = intern_run(names, ask_n)
        if not ok:
            wrong('intern', names, ask_n, w, g, res.out)
        count('intern')
    # many names, through several doublings (16, 32 ... 512), with repeats; and name() past the end
    for size, rounds in ((20, N // 20), (100, N // 100), (500, 3)):
        for _ in range(max(rounds, 2)):
            pool = list({rand_bytes(rng.choice([b'ABCDEFGHIJKLMNOPQRSTUVWXYZ', b'ab', bytes(range(256))]), 0,
                                    rng.choice([3, 6, 12])) for _ in range(size)})
            names = [rng.choice(pool) for _ in range(size * 2)]
            distinct = len(set(names))
            ok, res, w, g = intern_run(names, distinct + rng.choice([0, 1]))
            if not ok:
                wrong('intern many', size, w[:20] if isinstance(w, list) else w, g[:20], res.out)
            count('intern', len(names))
    # name() of numbers that aren't there
    for n in (0, 1, 2, 3, 100, 32767, 32768, 65535):
        res = R.call('w_name', regs={'hl': n, 'de': OPS})
        k, want = ask(lambda: builtin(B.Interp(None, b'', None), 'name', n))
        if not failed_as(res, want):
            wrong('name of nothing', n, want, res.out)
        count('name')
    # the arena running out: AoC-shaped 3-letter names, until the 16K test arena can't hold the table
    pool = [bytes(rng.choice(b'ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(3)) for _ in range(5000)]
    names = list(dict.fromkeys(pool))[:1200]
    ok, res, w, g = intern_run(names, 0)
    stuck = next(i for i, x in enumerate(g) if x != i)
    if not failed_as(res, 'arena full at line 7\n') or stuck < 500:
        wrong('intern arena full', res.out, stuck)
    count('intern', len(names))
    return stuck


# -- input: lines, lines(), input(), grid() --------------------------------------------------------------------

ENDS = [b'\n', b'\r\n', b'\r']


def text_case():
    k = rng.random()
    alpha = rng.choice([b'abc', b'#.', b'a\tb\x0c\x00\xff ', bytes(range(256))])
    lines = [rand_bytes(alpha, 0, rng.choice([0, 3, 20, 80])) for _ in range(rng.randint(0, 30))]
    if k < 0.5:
        end = rng.choice(ENDS)
        text = b''.join(ln + end for ln in lines)
    else:
        text = b''.join(ln + rng.choice(ENDS) for ln in lines)
    if text and rng.random() < 0.4:
        text = text.rstrip(b'\r\n') if rng.random() < 0.5 else text + rng.choice(ENDS)
    return text


def edge_texts():
    yield from [b'', b'\n', b'\r', b'\r\n', b'\n\r', b'\r\r\n', b'\n\n', b'\r\n\r\n', b'\r\r', b'a', b'a\n', b'a\r',
                b'a\r\n', b'\na', b'a\n\nb', b'a\r\rb', b'a\r\n\nb', b'a\n\r\nb', b'\r\na', b'a\x00b\nc', b'\t\n\t']
    for n in (254, 255, 256, 257, 511, 512, 513, 1024):     # the scan's counter rolls over at 256
        for tail in (b'', b'\n', b'\r', b'\r\n'):
            yield b'x' * (n - len(tail)) + tail
            yield (b'ab\r\n' * n)[:n - len(tail)] + tail


def split_text(text, alimit=0):
    mem = {LO: text} if text else {}
    return R.call('t_input', regs={'hl': alimit}, mem=mem, set16={'bly_text': LO, 'bly_tlen': len(text)})


def test_split_input():
    cases = list(edge_texts()) + [text_case() for _ in range(N)]
    cases.append(b''.join(rand_bytes(b'.#', 0, 140) + rng.choice(ENDS) for _ in range(200)))   # about 14K
    cases.append(b''.join(rand_bytes(b'ab', 0, 3) + rng.choice(ENDS) for _ in range(1500)))   # 1500 lines
    for text in cases:
        res = split_text(text)
        want = B.Interp(None, text, None).input_lines
        lns, nln = rd16(res.mem, res.sym['bly_lns']), rd16(res.mem, res.sym['bly_nln'])
        got, ok, off = [], True, 0
        for i in range(min(nln, len(want) + 1)):
            q, n, line = rdstr(res.mem, lns + 4 * i)
            got.append(line)
            if n and q != LO + text.find(line, off):      # in place, a slice of the text
                ok = False
            off = q - LO + n if n else off
        atop = rd16(res.mem, res.sym['bly_atop'])
        if res.failed or got != want or not ok or lns != 0xA000 or atop != lns + 4 * nln:
            wrong('split_input', text[:80], want[:5], got[:5], res.out)
        count('split_input')
    # the arena too small for the lines: exactly enough, and one short (at start-up bly_line is 0)
    text = b'ab\n' * 50
    for room, fails in ((200, False), (199, True), (197, True), (196, True), (203, False), (0, True)):
        res = split_text(text, 0xA000 + room)
        if (failed_as(res, 'arena full\n') if fails else not res.failed and rd16(res.mem, res.sym['bly_nln']) == 50) \
                is False:
            wrong('split_input arena', room, res.out)
        count('split_input')


def test_lines():
    many = b''.join(b'%d\n' % i for i in range(700))        # past 256 lines, for the iterator's high byte
    for text in list(edge_texts())[:21] + [text_case() for _ in range(N // 4)] + [many]:
        ip = B.Interp(None, text, None)
        its = [builtin(ip, 'lines'), builtin(ip, 'lines')]
        nln = len(ip.input_lines)
        script = bytes(rng.choice([0, 0, 1]) for _ in range(rng.randint(0, nln * 2 + 2)))
        if text is many:
            script = bytes(701)                     # every line, then one too many
        want, fail = [], None
        for w in script:
            k, v = ask(lambda: method(its[w], 'next', ty=B.LINES))
            if k == 'fail':
                fail = v
                break
            want.append(v)
        sp = Space(0xEC00, 0xF000)
        sc = sp.put(script)
        mem = {LO: text, **sp.mem()} if text else sp.mem()
        res = R.call('t_lines2', regs={'hl': sc, 'bc': len(script), 'de': OPS}, mem=mem,
                     set16={'bly_text': LO, 'bly_tlen': len(text)})
        got = [rdstr(res.mem, OPS + 4 * i)[2] for i in range(len(want))]
        if got != want or not (failed_as(res, fail) if fail else not res.failed):
            wrong('lines', text[:60], script, want, got, res.out)
        count('lines', len(script))
    for text in (b'', b'abc', b'a\r\nb\n', bytes(range(256)) * 4):
        res = R.call('bly_input', regs={'de': OPS, 'ix': IXV}, mem={LO: text} if text else {},
                     set16={'bly_text': LO, 'bly_tlen': len(text)})
        p, n, got = rdstr(res.mem, OPS)
        want = builtin(B.Interp(None, text, None), 'input')
        if res.failed or got != want or p != LO or res.regs['ix'] != IXV:
            wrong('input', text[:40], got[:40])
        count('input')


def grid_text():
    rows, cols = rng.randint(0, 12), rng.randint(0, 15)
    lines = [rand_bytes(rng.choice([b'.#', b'0123456789', bytes(range(256))]), cols, cols) for _ in range(rows)]
    if lines and rng.random() < 0.4:              # ragged: one line a different length
        r = rng.randrange(len(lines))
        lines[r] = rand_bytes(b'.#', 0, cols + 3)
    end = rng.choice(ENDS)
    text = b''.join(ln + (end if rng.random() < 0.8 else rng.choice(ENDS)) for ln in lines)
    if rng.random() < 0.3:
        text = text.rstrip(b'\r\n')
    return text


def test_grid():
    hand = [b'', b'\n', b'\n\n', b'abc', b'abc\n', b'ab\ncd\n', b'ab\ncde\n', b'abc\nde\n', b'ab\r\ncd\ref\n',
            b'a\n\nb\n', b'\nab\n', b'ab\n\n']
    cases = hand + [grid_text() for _ in range(N)] + [b''.join(rand_bytes(b'.#', 140, 140) + b'\n'
                                                               for _ in range(40))]
    cases += [b'x' * 300 + b'\n' + b'y' * 300,                # rows of 256 and more
              b'x' * 300 + b'\n' + b'y' * 44,                 # lengths 256 apart
              b'x' * 44 + b'\n' + b'y' * 300 + b'\n',
              b'x' * 44 + b'\n' + b'y' * 44 + b'\n' + b'z' * 556 + b'\n',
              b''.join(b'%03d\n' % i for i in range(300)),   # 300 rows
              b''.join(b'%03d\n' % i for i in range(300)) + b'1234\n']
    for text in cases:
        res = R.call('t_grid', regs={'hl': 0}, mem={LO: text} if text else {},
                     set16={'bly_text': LO, 'bly_tlen': len(text)})
        kind, want = ask(lambda: builtin(B.Interp(None, text, None), 'grid'))
        if kind == 'fail':
            if not failed_as(res, want):
                wrong('grid ragged', text[:60], want, res.out)
            count('grid')
            continue
        g = res.regs['hl']
        rows, cols, esize, a = (rd16(res.mem, g + k) for k in (0, 2, 4, 6))
        cmp, pr = rd16(res.mem, g + 8), rd16(res.mem, g + 10)
        cells = bytes(res.mem[a:a + rows * cols])
        if res.failed or (rows, cols, esize) != (want.rows, want.cols, 1) or cells != bytes(sum(want.cells, [])) \
                or cmp != res.sym['bly_cmp_byte'] or pr != res.sym['bly_pr_byte'] or not 0xA000 <= g < 0xE000:
            wrong('grid', text[:60], (want.rows, want.cols), (rows, cols, esize), res.out)
        count('grid')


def test_alloc_raw():
    """bly_alloc_raw: the block is where bly_atop was, bly_atop moves past it, nothing is zeroed, and when it
    doesn't fit bly_alloc says so"""
    junk = bytes(rng.randrange(1, 256) for _ in range(0x4000))
    for size in (0, 1, 2, 100, 0x3FFF, 0x4000, 0x4001, 0x5FFF, 0x6000, 0xFFFF, 0x8000) + \
            tuple(rng.randrange(0x4100) for _ in range(N // 10)):
        res = R.call('bly_alloc_raw', regs={'hl': size, 'bc': 0x1234, 'ix': IXV}, mem={0xA000: junk})
        atop = rd16(res.mem, res.sym['bly_atop'])
        if size <= 0x4000:
            ok = not res.failed and res.regs['hl'] == 0xA000 and atop == 0xA000 + size \
                and bytes(res.mem[0xA000:0xE000]) == junk and res.regs['bc'] == 0x1234 and res.regs['ix'] == IXV
        else:
            ok = failed_as(res, 'arena full\n') and atop == 0xA000
        if not ok:
            wrong('alloc_raw', size, res.out, hex(atop), hex(res.regs['hl']))
        count('alloc_raw')
    # through grid(): 100 x 100 cells after 100 strs of lines and a 12-byte header, in an arena cut to fit or not
    text = b''.join(rand_bytes(b'.#', 100, 100) + b'\n' for _ in range(100))
    for room, fits in ((400 + 12 + 10000, True), (400 + 12 + 9999, False), (400 + 11, False)):
        res = R.call('t_grid', regs={'hl': 0xA000 + room}, mem={LO: text}, set16={'bly_text': LO, 'bly_tlen': len(text)})
        if (not res.failed) != fits or (not fits and res.out != b'arena full at line 7\n'):
            wrong('grid arena', room, res.out)
        count('alloc_raw')


def test_clobbers():
    """what each header says it keeps, it keeps: IX unless it's listed, and the rest where the header is short"""
    sp = Space(LO, HI)
    ss, _ = sp.str(b'a,b,c')
    sep, _ = sp.str(b',')
    seps, _ = sp.str(b', ')
    name, _ = sp.str(b'AAA')
    state = sp.put(bytes(11))
    mem = sp.mem()
    keeps = {   # routine: (regs in, the registers it must give back unchanged)
        'bly_split_init': ({'hl': state, 'de': ss, 'bc': sep}, ['ix']),
        'bly_intern': ({'hl': name}, ['ix']),
        'bly_lines_new': ({}, ['ix', 'hl_not']),
        'bly_input': ({'de': OPS, 'bc': 0x1234, 'a': 0x77}, ['ix', 'bc', 'a']),
        'bly_alloc_raw': ({'hl': 10, 'bc': 0x1234}, ['ix', 'bc']),
    }
    for routine, (regs, keep) in keeps.items():
        regs = dict({'bc': 0x1111, 'de': 0x2222, 'hl': 0x3333, 'ix': IXV, 'a': 0x44}, **regs)
        res = R.call(routine, regs=regs, mem=mem)
        for k in keep:
            if k == 'hl_not':
                continue
            if res.failed or res.regs[k] != regs[k]:
                wrong('clobbers', routine, k, hex(res.regs[k]), hex(regs[k]))
        count('clobbers')
    # bly_split_next, bly_name and bly_lines_next need state: give it to them directly
    for k, sepn, sepp in ((1, 1, LO + 5), (2, 2, LO + 5)):
        st = bytes([0]) + w16(LO) + w16(LO + 5) + w16(sepn) + w16(sepp) + b'\x00\x00'
        res = R.call('bly_split_next', regs={'hl': OPS, 'de': OPS + 16, 'ix': IXV},
                     mem={LO: b'a,b,c, ', OPS: st})
        if res.regs['ix'] != IXV or res.regs['a'] != 1:
            wrong('clobbers split_next', k, res.regs)
        count('clobbers')
    res = R.call('bly_name', regs={'hl': 0, 'de': OPS, 'ix': IXV}, mem={0xE100: w16(LO) + w16(3), LO: b'abc'},
                 set16={'bly_intern.count': 1, 'bly_intern.names': 0xE100})
    if res.regs['ix'] != IXV or rdstr(res.mem, OPS)[2] != b'abc':
        wrong('clobbers name', res.regs)
    res = R.call('bly_lines_next', regs={'hl': OPS + 8, 'de': OPS, 'ix': IXV},
                 mem={OPS + 8: w16(0), 0xE100: w16(LO) + w16(3), LO: b'abc'}, set16={'bly_lns': 0xE100, 'bly_nln': 1})
    if res.regs['ix'] != IXV or rdstr(res.mem, OPS)[2] != b'abc':
        wrong('clobbers lines_next', res.regs)
    count('clobbers', 2)


def test_byte_elems():
    pairs = [(a, b) for a in (0, 1, 127, 128, 254, 255) for b in (0, 1, 127, 128, 254, 255)]
    pairs += [(rng.randrange(256), rng.randrange(256)) for _ in range(N)]
    for a, b in pairs:
        res = R.call('bly_cmp_byte', regs={'hl': OPS, 'de': OPS + 1, 'bc': 0x1234, 'ix': IXV}, mem={OPS: bytes([a, b])})
        want = m_cmp(a, b)
        f = res.regs['f']
        if res.regs['a'] != want & 0xFF or bool(f & 0x40) != (want == 0) or bool(f & 0x80) != (want < 0) \
                or res.regs['bc'] & 0xFF != 0x34 or res.regs['de'] != OPS + 1 or res.regs['hl'] != OPS \
                or res.regs['ix'] != IXV:
            wrong('cmp_byte', a, b, res.regs)
        count('cmp_byte')
    for v in range(256):
        res = R.call('bly_pr_byte', regs={'hl': OPS}, mem={OPS: bytes([v])})
        if res.out.decode() != IP.show(v, B.BYTE):
            wrong('pr_byte', v, res.out)
        count('pr_byte')


# -- costs ----------------------------------------------------------------------------------------------------

def costs():
    """T-states (CALL and RET included) for typical and worst cases, for NOTES.md"""
    rows = []

    def t(routine, regs, mem=None, set16=None):
        res = R.call(routine, regs=regs, mem=mem, set16=set16)
        assert not res.failed, (routine, res.out)
        return res.t

    def direct(routine, regs, mem, set16, atop=0xA000):
        set16 = dict(set16, t_fn=R.build('t_direct')[1][routine], t_atop=atop)
        return t('t_direct', regs, mem, set16) - 81

    def row(name, case, tt):
        rows.append((name, case, tt))

    def strs(*ss):
        sp = Space(LO, HI)
        return [sp.str(x)[0] for x in ss], sp.mem()

    (a, b), m = strs(b'abcdefgh', b'abcdXfgh')
    row('bly_cmp_str', '8 bytes, differing at the 5th', t('bly_cmp_str', {'hl': a, 'de': b}, m))
    (a, b), m = strs(b'', b'abc')
    row('bly_cmp_str', 'with ""', t('bly_cmp_str', {'hl': a, 'de': b}, m))
    (a, b), m = strs(b'x' * 100, b'x' * 100)
    t1 = t('bly_cmp_str', {'hl': a, 'de': b}, m)
    (a, b), m = strs(b'x' * 1000, b'x' * 1000)
    t2 = t('bly_cmp_str', {'hl': a, 'de': b}, m)
    row('bly_cmp_str', f'two equal 1000-byte strs ({(t2 - t1) / 900:.0f} T a byte)', t2)
    (a,), m = strs(b'0123456789')
    row('bly_slice', 'any', t('bly_slice', {'hl': a, 'de': 2, 'bc': 5, 'ix': OPS}, m))
    (a, b), m = strs(b'Game 12: 3 blue, 4 red; 1 red, 2 green, 6 blue', b':')
    row('bly_find', '":" at 7 in a 47-byte line', t('bly_find', {'hl': a, 'de': b}, m))
    (a, b), m = strs(b'Game 12: 3 blue, 4 red; 1 red, 2 green, 6 blue', b'green')
    row('bly_find', '"green" at 32 in the same', t('bly_find', {'hl': a, 'de': b}, m))
    (a, b), m = strs(b'a' * 1000, b'b')
    row('bly_find', 'a byte that isn\'t in 1000', t('bly_find', {'hl': a, 'de': b}, m))
    (a, b), m = strs(b'a' * 1000, b'aaab')
    row('bly_find', 'worst: "aaab" in 1000 a\'s', t('bly_find', {'hl': a, 'de': b}, m))
    (a, b), m = strs(b'move 3 from 1 to 2', b'move ')
    row('bly_starts', '5 bytes, true', t('bly_starts', {'hl': a, 'de': b}, m))
    (a,), m = strs(b'  some words\t')
    row('bly_trim', '2 blanks before, 1 after', t('bly_trim', {'hl': a, 'de': OPS}, m))
    (a,), m = strs(b'words')
    row('bly_trim', 'nothing to trim', t('bly_trim', {'hl': a, 'de': OPS}, m))
    row('bly_chr', 'any', t('bly_chr', {'a': 65, 'de': OPS}))
    (a, b), m = strs(b'3 blue, 4 red, 1 green', b', ')
    row('bly_split_init', 'any', t('bly_split_init', {'hl': OPS, 'de': a, 'bc': b}, m))
    sp = Space(LO, HI)
    p = sp.put(b'3 blue, 4 red, 1 green')
    q = sp.put(b', ')
    r = sp.put(b',')

    def state(done, cur, sep, k):                 # bly_split_next's state, as text.asm lays it out
        return {**sp.mem(), OPS: bytes([done]) + w16(cur) + w16(p + 22) + w16(k) + w16(sep) + b'\x00\x00'}
    row('bly_split_next', 'a 6-byte piece, then ", "', t('bly_split_next', {'hl': OPS, 'de': OPS + 16},
                                                          state(0, p, q, 2)))
    row('bly_split_next', 'a 6-byte piece, then ","', t('bly_split_next', {'hl': OPS, 'de': OPS + 16},
                                                         state(0, p, r, 1)))
    row('bly_split_next', 'the last piece, 7 bytes, by ", "', t('bly_split_next', {'hl': OPS, 'de': OPS + 16},
                                                                state(0, p + 15, q, 2)))
    row('bly_split_next', 'the last piece, 7 bytes, by ","', t('bly_split_next', {'hl': OPS, 'de': OPS + 16},
                                                               state(0, p + 15, r, 1)))
    row('bly_split_next', 'after the last', t('bly_split_next', {'hl': OPS, 'de': OPS + 16}, state(1, p, q, 2)))

    # intern, against a real table: intern k names, keep the arena and the variables, then time one more call
    pool = list(dict.fromkeys(bytes(rng.choice(b'ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(3))
                              for _ in range(3000)))
    keys = ('names', 'slots', 'mask', 'cap', 'count', 'sp', 'sn', 'h', 'i')

    def table(k):
        sp = Space(LO, HI)
        ss = [sp.str(x)[0] for x in pool[:k]]
        tab = sp.put(b''.join(w16(x) for x in ss))
        res = R.call('t_intern', regs={'hl': tab, 'bc': k, 'de': OPS}, mem=sp.mem())
        assert not res.failed
        return ({0xA000: bytes(res.mem[0xA000:0xE000])}, {'bly_intern.' + v: rd16(res.mem, res.sym['bly_intern.' + v])
                                                          for v in keys}, rd16(res.mem, res.sym['bly_atop']))

    def one_more(k, names, tab=None):
        mem, vars_, atop = tab or table(k)
        ts = []
        for name in names:
            m = dict(mem)
            m[OPS] = w16(OPS + 4) + w16(len(name)) + name
            ts.append(direct('bly_intern', {'hl': OPS}, m, vars_, atop))
        return f'{sum(ts) / len(ts):.0f} (from {min(ts)} to {max(ts)})'

    t500 = table(500)
    row('bly_intern', 'a 3-letter name among 500, found (40 of them)', one_more(500, pool[100:140], t500))
    row('bly_intern', 'a new 3-letter name, the 501st (40 of them)', one_more(500, pool[600:640], t500))
    row('bly_intern', 'the 257th: the table doubles to 512', one_more(256, pool[600:601]))
    row('bly_intern', 'a new 12-letter name among 100', one_more(100, [b'ABCDEFGHIJKL']))
    mem, vars_, atop = table(100)
    row('bly_name', 'any', direct('bly_name', {'hl': 42, 'de': OPS}, mem, vars_, atop))
    tot = R.call('t_intern', regs={'hl': 0, 'bc': 0, 'de': OPS}).t
    sp = Space(LO, HI)
    ss = [sp.str(x)[0] for x in pool[:500]]
    tab = sp.put(b''.join(w16(x) for x in ss))
    tot = R.call('t_intern', regs={'hl': tab, 'bc': 500, 'de': OPS}, mem=sp.mem()).t - tot - 500 * 177
    row('bly_intern', '500 new 3-letter names, on average (doublings included)', tot // 500)

    # input
    grid = b''.join(rand_bytes(b'.#', 140, 140) + b'\n' for _ in range(100))
    lines = b''.join(rand_bytes(b'0123456789 ', 20, 20) + b'\n' for _ in range(700))
    for name, text in (('a 100 x 140 grid, LF (14,100 bytes)', grid), ('700 lines of 20, LF (14,700 bytes)', lines),
                       ('the same with CR LF (15,400 bytes)', lines.replace(b'\n', b'\r\n')),
                       ('one 14,700-byte line, no line end', b'x' * 14700)):
        row('bly_split_input', name, t('t_input', {'hl': 0}, {LO: text}, {'bly_text': LO, 'bly_tlen': len(text)}))
    res = R.call('t_grid', regs={'hl': 0}, mem={LO: grid}, set16={'bly_text': LO, 'bly_tlen': len(grid)})
    tsplit = t('t_input', {'hl': 0}, {LO: grid}, {'bly_text': LO, 'bly_tlen': len(grid)})
    row('bly_grid_input', 'the 100 x 140 grid (the split not counted)', res.t - tsplit - 50)
    arr = b''.join(w16(LO + 3 * i) + w16(2) for i in range(10))
    row('bly_lines_next', 'any', t('bly_lines_next', {'hl': OPS, 'de': OPS + 8}, {OPS: w16(4), OPS + 16: arr},
                                   {'bly_lns': OPS + 16, 'bly_nln': 10}))
    row('bly_lines_new', 'any', t('bly_lines_new', {}))
    row('bly_input', 'any', t('bly_input', {'de': OPS}))
    row('bly_cmp_byte', 'any', t('bly_cmp_byte', {'hl': OPS, 'de': OPS + 1}, {OPS: b'\x05\x09'}))
    row('bly_pr_byte', '3 digits', t('bly_pr_byte', {'hl': OPS}, {OPS: b'\xc8'}))
    return rows


def sizes():
    """bytes of each routine: from its label to the next global label in the same fragment (data included)"""
    out = {}
    for frag in ('text.asm', 'text_chr.asm', 'intern.asm', 'input.asm', 'input_grid.asm', 'elem_byte.asm',
                 'alloc_raw.asm'):
        f = [x for x in link.load() if x.name == frag][0]
        syms = f.provides
        code, sym = harness.assemble('        org 8000h\n' + f.text + '\nbly__end:\n'
                                     + ''.join(f'{s}: equ 0\n' for s in f.needs))
        labels = sorted((sym[s], s) for s in syms if s in sym) + [(sym['bly__end'], None)]
        for (a, s), (b, _) in zip(labels, labels[1:]):
            out[s] = b - a
        out[frag] = sym['bly__end'] - 0x8000
    return out


if __name__ == '__main__':
    test_two_str()
    test_find_more()
    test_trim_slice()
    test_chr()
    test_split()
    stuck = test_intern()
    test_split_input()
    test_lines()
    test_grid()
    test_alloc_raw()
    test_clobbers()
    test_byte_elems()
    print('text:', 'all right' if not bad else f'{bad} wrong', '| cases:',
          ', '.join(f'{k} {v}' for k, v in counts.items()))
    print(f'intern filled the 16K test arena at name {stuck} (3-letter names)')
    if '--cost' in sys.argv:
        for r in costs():
            print('cost', r)
        for k, v in sizes().items():
            print('size', k, v)
    sys.exit(1 if bad else 0)
