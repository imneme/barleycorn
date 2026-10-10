#!/usr/bin/env python3
"""Barley's Z80 backend. It began deliberately dumb, then took back, one
measured step at a time, the answers Barley's first compiler had measured
(HISTORY.md): where values live, and what a call costs.

The front end is the reference interpreter's own parser and checker. Every
variable, parameter and temporary lives at a fixed address (a slot): a
function's slots are one block, its frame.
- A variable is read in place, except where something later could change it: a
  global in a statement that calls a user function, and whatever a `for` holds
  across its body or a self-call writes over (snapshots).
- Conditions are branches, with phase one's inline compares for 8 and 16 bits.
- Failure paths (index checks, int overflow, a slice's general check) are cold
  code after the function's ret.
- Unsigned arithmetic by constants is inline (shifts, masks, shift-and-add).
- A call into the caller's own cycle saves only what's live after it (the save
  rule: live_after ∩ clobber(callee), with liveness from the AST), as pushes
  of byte runs.
- peephole.py runs phase one's register cache (HL, DE, A) over each function
  and drops stores to temps nobody reads.

8- and 16-bit arithmetic is inline (int's overflow is the V flag of ADC or
SBC); anything wider is a call into the library (ABI.md), by address.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'interp'))
sys.path.insert(0, HERE)
import barley as B                                                     # noqa: E402
from link import gather                                                # noqa: E402
import peephole                                                        # noqa: E402
PEEP = os.environ.get('BLY_PEEP', '1') != '0'        # BLY_PEEP=0 turns the register cache off, to compare

TYPE_CODE = {B.BYTE: 0, B.WORD: 1, B.INT: 2, B.LONG: 3, B.QUAD: 4, B.DWORD: 5}
CMP_ROUTINE = {'<': 'bly_lt', '<=': 'bly_le', '>': 'bly_gt', '>=': 'bly_ge', '==': 'bly_eq', '!=': 'bly_ne'}
NEG = {'<': '>=', '>=': '<', '>': '<=', '<=': '>', '==': '!=', '!=': '=='}
SWAP = {'>': '<', '<=': '>='}                          # a > b is b < a; a <= b is b >= a
UCOND = {'<': 'c', '>=': 'nc', '==': 'z', '!=': 'nz'}  # after an unsigned compare (or a biased signed one)
SCOND = {'<': 'm', '>=': 'p', '==': 'z', '!=': 'nz'}   # after a comparer: A = FFh/0/1, flags as after OR A
KIND_CODE = {'list': 0, 'queue': 1, 'heap': 2, 'map': 3, 'set': 4}


class GenError(Exception):
    pass


FLOATS = {'on': False}                 # floats exist on the Spectrum only: compile_program sets this per target


def rom5(x):
    """a float as the Spectrum ROM's 5 bytes (ABI.md section 11): the short form 00 s lo hi 00 for a whole number in
    -65535..65535, else e m3 m2 m1 m0 with the 32-bit mantissa rounded half away from zero, as bly_f_from_i64 does.
    Too small is zero (as the ROM's own underflow); too big for the ROM (1.7e38) is an error."""
    from fractions import Fraction
    if x != x or x in (float('inf'), float('-inf')):
        raise GenError(f'{x} is not a number the Spectrum has')
    f = Fraction(x)
    if f.denominator == 1 and -65535 <= f <= 65535:
        n = int(f)
        return bytes([0, 0xFF if n < 0 else 0, n & 0xFF, (n >> 8) & 0xFF, 0])
    neg, f = f < 0, abs(f)
    e = f.numerator.bit_length() - f.denominator.bit_length()      # 2^e is near f: settle it to 0.5 <= f/2^e < 1
    while f >= Fraction(2) ** e:
        e += 1
    while f < Fraction(2) ** (e - 1):
        e -= 1
    m = f / Fraction(2) ** (e - 32)                                  # in [2^31, 2^32)
    mi = int(m)
    if m - mi >= Fraction(1, 2):
        mi += 1
    if mi == 1 << 32:
        mi, e = 1 << 31, e + 1
    if e + 128 > 255:
        raise GenError(f'{x:.10g} is too big for the Spectrum: its floats stop at about 1.7e38')
    if e + 128 < 1:
        return bytes(5)
    return bytes([e + 128, ((mi >> 24) & 0x7F) | (0x80 if neg else 0), (mi >> 16) & 0xFF, (mi >> 8) & 0xFF, mi & 0xFF])


def rom_value(b):
    """the exact value (a Fraction) of the ROM's 5 bytes"""
    from fractions import Fraction
    if b[0] == 0:
        v = b[2] | (b[3] << 8)
        return Fraction(v - 65536 if b[1] == 0xFF else v)
    m = ((b[1] | 0x80) << 24) | (b[2] << 16) | (b[3] << 8) | b[4]
    v = Fraction(m) * Fraction(2) ** (b[0] - 128 - 32)
    return -v if b[1] & 0x80 else v


def imm_bits(v, t):
    """a constant as the integer whose little-endian bytes are its memory: a float's are the ROM's 5 bytes"""
    if t is B.FLOAT:
        return int.from_bytes(rom5(v if isinstance(v, int) else float(v)), 'little')     # an int exactly
    return v


def size(t):
    if t in (B.BYTE, B.BOOL, B.BIT):
        return 1
    if t in (B.WORD, B.INT):
        return 2
    if t is B.LONG or t is B.DWORD or t is B.STR:
        return 4
    if t is B.QUAD:
        return 8
    if isinstance(t, B.RecordT):
        return sum(size(ft) for _, ft in t.fields)
    if t is B.LINES or (isinstance(t, B.Gen) and t.kind in ('list', 'queue', 'heap', 'map', 'set', 'grid')):
        return 2
    if isinstance(t, B.Gen) and t.kind == 'array':
        if t.n is not None and t.args[0] is B.BIT:
            return (t.n + 7) // 8                                    # bits pack eight to a byte
        return size(t.args[0]) * t.n if t.n is not None else 4      # a parameter is a view: pointer, length
    if t is B.FLOAT:
        if FLOATS['on']:
            return 5                                    # the ROM's own form (ABI.md section 11)
        raise GenError('floats are not on the Z80 yet: the CP/M target has no ROM calculator')
    raise GenError(f'no size for {t!r}')


def field_offset(rt, name):
    off = 0
    for f, ft in rt.fields:
        if f == name:
            return off, ft
        off += size(ft)
    raise GenError(f'no field {name}')


class Op:
    """an operand: 'mem' (val is an address expression) or 'imm' (val is the value). fresh: a temp this generator
    made, which nothing else can change; otherwise a 'mem' Op may be a variable, read in place"""

    def __init__(self, kind, val, ty, fresh=False):
        self.kind, self.val, self.ty, self.fresh = kind, val, ty, fresh

    def at(self, k=0):
        return f'{self.val}+{k}' if k else self.val


class Gen:
    def __init__(self, ck, target):
        self.ck, self.target = ck, target
        self.code = []
        self.nlabel = 0
        self.strings = {}
        self.calls = set(['bly_start', 'bly_exit', 'bly_fail'])
        self.helpers = {}                    # name -> lines: generated cmp and print routines
        self.cur_line = None
        self.func = None
        self.fsize = 0
        self.gsize = 0
        self.equs = []
        self.loops = []
        self.cold_code = []
        self.dead_args = []
        self.fail_stubs = {}
        self.stmt_calls = True
        self.uses_input = False
        self.scc = self.cycles()

    # -- the call graph's cycles ---------------------------------------------------------------------------------
    def cycles(self):
        funcs = {d.name: d for d in self.ck.decls if d.k == 'func'}
        edges = {n: set() for n in funcs}

        def walk(x, into):
            if isinstance(x, B.N):
                if x.k == 'call' and hasattr(x, 'func'):
                    into.add(x.func.name)
                for k, v in x.__dict__.items():
                    if k not in ('func', 'var', 'ty', 'record', 'cast'):     # a function's own tree only
                        walk(v, into)
            elif isinstance(x, (list, tuple)):
                for v in x:
                    walk(v, into)
        for n, f in funcs.items():
            walk(f.body, edges[n])
        index, low, stack, on, comp, counter = {}, {}, [], set(), {}, [0]

        def strong(v):
            index[v] = low[v] = counter[0]
            counter[0] += 1
            stack.append(v)
            on.add(v)
            for w in edges[v]:
                if w not in index:
                    strong(w)
                    low[v] = min(low[v], low[w])
                elif w in on:
                    low[v] = min(low[v], index[w])
            if low[v] == index[v]:
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp[w] = v
                    if w == v:
                        break
        sys.setrecursionlimit(10000)
        for v in funcs:
            if v not in index:
                strong(v)
        self.edges = edges
        return comp

    def recursive_call(self, caller, callee):
        return self.scc.get(caller) == self.scc.get(callee) and (callee in self.edges[callee] or caller != callee
                                                                 or callee in self.edges.get(callee, ()))

    # -- emitting ------------------------------------------------------------------------------------------------
    def emit(self, s):
        self.code.append('        ' + s)

    def label(self, name=None):
        if name is None:
            self.nlabel += 1
            name = f'L{self.nlabel}'
        return name

    def place(self, name):
        self.code.append(name + ':')
        self.cur_line = None

    def call(self, routine):
        self.calls.add(routine)
        self.emit(f'call {routine}')

    def jp(self, routine, cond=None):
        self.calls.add(routine)
        self.emit(f'jp {cond + "," if cond else ""}{routine}')

    def cold(self, gen):
        """emit gen()'s code out of line (after the function's ret) and return its label: for failure paths, which
        never come back, so the hot path doesn't pay for them"""
        lab, saved, line = self.label(), self.code, self.cur_line
        self.code = []
        self.place(lab)
        gen()
        self.cold_code += self.code
        self.code, self.cur_line = saved, line
        return lab

    def fail_jp(self, cond, routine, line):
        """jp cond to a failure routine that takes no arguments in HL, setting the line only on the way there"""
        self.calls.add(routine)
        key = (routine, line)                               # one stub for each failure and line, in a function
        if key not in self.fail_stubs:
            self.fail_stubs[key] = self.cold(lambda: (self.line(line), self.jp(routine)))
        self.emit(f'jp {cond},{self.fail_stubs[key]}')

    def line(self, n):
        if n and n != self.cur_line:
            self.emit(f'ld hl,{n}')
            self.emit('ld (bly_line),hl')
            self.cur_line = n

    def slot(self, t, n=None):
        """a fresh slot in the current frame (or the globals when there's no function)"""
        sz = n if n is not None else size(t)
        sz = max(sz, 1)
        if self.func is None:
            name = f'gs+{self.gsize}'
            self.gsize += sz
        else:
            name = f'fr_{self.func.name}+{self.fsize}'
            self.fsize += sz
        return name

    def temp(self, t):
        name = self.slot(t)
        if self.func is not None:                           # the peephole may drop stores to it nobody reads
            self.temps[name] = (f'fr_{self.func.name}', self.fsize - max(size(t) if t is not None else 1, 1),
                                max(size(t) if t is not None else 1, 1))
        return Op('mem', name, t, fresh=True)

    def snap(self, op):
        """op as a value nothing later can change: a variable read in place is copied into a temp"""
        if op is None or op.kind == 'imm' or op.fresh or isinstance(op.ty, B.Gen) and op.ty.kind == 'array':
            return op
        return self.copy_to_temp(op.val, op.ty)

    def liveness(self, f):
        """for the save rule: each statement's own local names (in its own expressions), the names of every
        statement after it in the text, and every name anywhere inside each loop. Sound without a CFG: there's no
        backward flow except loops, and a block's var is set again before it's read"""
        order, own, inside = [], {}, {}

        def names(*xs):
            acc = set()

            def walk(x):
                if isinstance(x, B.N):
                    if x.k == 'name' and getattr(x, 'var', None) is not None and x.var.where != 'global' \
                            and not x.var.const:
                        acc.add(x.name)
                    for k, v in x.__dict__.items():
                        if k not in ('func', 'var', 'ty', 'record', 'cast', 'body', 'else_', 'arms', 'whens', 'opnode'):
                            walk(v)
                elif isinstance(x, (list, tuple)):
                    for v in x:
                        walk(v)
            for x in xs:
                walk(x)
            return acc

        def visit(st):
            k = st.k
            order.append(st)
            heads = {'var': lambda: [st.e], 'assign': lambda: [st.target, st.e], 'expr': lambda: [st.e],
                     'return': lambda: [st.e], 'assert': lambda: [st.e], 'print': lambda: [st.items],
                     'if': lambda: [c for c, _ in st.arms], 'while': lambda: [st.cond], 'for': lambda: [st.it],
                     'case': lambda: [st.e] + [w for vals, _ in st.whens for w in vals]}.get(k, lambda: [])
            own[id(st)] = names(*heads())
            start = len(order)
            for body in ([b for _, b in st.arms] + [st.else_] if k == 'if' else
                         [st.body] if k in ('while', 'for') else
                         [b for _, b in st.whens] + [st.else_] if k == 'case' else []):
                for t in body:
                    visit(t)
            if k in ('while', 'for'):
                inside[id(st)] = set(own[id(st)]).union(*[own[id(t)] for t in order[start:]])
        for st in f.body:
            visit(st)
        after, acc = {}, set()
        for st in reversed(order):
            after[id(st)] = set(acc)
            acc |= own[id(st)]
        return own, after, inside

    def live_slots(self, dead=()):
        """what a call into our own cycle must save: (address, size), by the save rule"""
        own, after, inside = self.live
        cur = self.cur_stmt
        names = set(own.get(id(cur), ())) | after.get(id(cur), set()) if cur is not None else set(self.locals)
        for lp in self.loop_stmts:
            names |= inside.get(id(lp), set())
        out = {}
        for n in names:
            if n in self.locals:
                out[self.locals[n]] = self.lsize[n]
        for lo, hi in self.machinery:                           # enclosing loops' own slots
            for k in range(lo, hi):
                out[f'fr_{self.func.name}+{k}'] = 1
        for i, (name, (_, _, n)) in enumerate(self.temps.items()):     # this statement's values so far,
            if i >= self.temp_mark and not any(lo <= i < hi for lo, hi in dead):   # but not calls' arguments
                out[name] = n
        return out

    def coalesce(self, slots):
        """{address: size} -> runs of adjacent bytes in the frame, so neighbouring bytes are saved as words (phase
        one's packed saves: memory ranges, not variables)"""
        offs = set()
        for a, n in slots.items():
            base, off = a.rsplit('+', 1)
            offs.update(range(int(off), int(off) + n))
        runs, base = [], f'fr_{self.func.name}'
        for o in sorted(offs):
            if runs and runs[-1][1] == o:
                runs[-1][1] = o + 1
            else:
                runs.append([o, o + 1])
        return [(f'{base}+{lo}', hi - lo) for lo, hi in runs]

    def has_call(self, *nodes):
        """does evaluating these expressions call a user function (which could change a global)?"""
        def walk(x):
            if isinstance(x, B.N):
                if x.k == 'call' and hasattr(x, 'func'):
                    return True
                return any(walk(v) for k, v in x.__dict__.items()
                           if k not in ('func', 'var', 'ty', 'record', 'cast', 'body', 'else_', 'arms', 'whens',
                                        'opnode'))
            if isinstance(x, (list, tuple)):
                return any(walk(v) for v in x)
            return False
        return any(walk(n) for n in nodes)

    def string(self, b):
        if b not in self.strings:
            self.strings[b] = f'S{len(self.strings)}'
        return Op('mem', self.strings[b], B.STR)

    # -- moving values ----------------------------------------------------------------------------------------------
    def load_hl(self, op):
        """a 16-bit (or narrower, zero- or sign-extended per its type) value into HL"""
        t = op.ty
        if op.kind == 'imm':
            self.emit(f'ld hl,{op.val & 0xFFFF}')
        elif size(t) == 1:
            self.emit(f'ld a,({op.val})')
            self.emit('ld l,a')
            self.emit('ld h,0')
        else:
            self.emit(f'ld hl,({op.val})')

    def load_de(self, op):
        if op.kind == 'imm':
            self.emit(f'ld de,{op.val & 0xFFFF}')
        elif size(op.ty) == 1:
            self.emit(f'ld a,({op.val})')
            self.emit('ld e,a')
            self.emit('ld d,0')
        else:
            self.emit(f'ld de,({op.val})')

    def load_a(self, op):
        if op.kind == 'imm':
            self.emit(f'ld a,{op.val & 0xFF}')
        else:
            self.emit(f'ld a,({op.val})')

    def addr(self, op):
        """the address of a value in memory. A constant must have been made memory (mem()) before anything was
        loaded into a register: materialising it here would clobber them."""
        if op.kind == 'imm':
            raise GenError('internal: a constant reached addr(); call mem() before loading registers')
        return op.val

    def mem(self, op, t=None):
        """op in memory: a constant is stored in a fresh temp now, before any registers are loaded"""
        return self.materialize(op, t) if op.kind == 'imm' else op

    def materialize(self, op, t=None):
        t = t or op.ty
        dst = self.temp(t)
        self.store_imm(dst.val, imm_bits(op.val, t), size(t))
        return dst

    def store_imm(self, dst, v, n):
        v &= (1 << (8 * n)) - 1
        k = 0
        while k + 2 <= n:
            self.emit(f'ld hl,{(v >> (8 * k)) & 0xFFFF}')
            self.emit(f'ld ({dst}+{k}),hl')
            k += 2
        if k < n:
            self.emit(f'ld a,{(v >> (8 * k)) & 0xFF}')
            self.emit(f'ld ({dst}+{k}),a')

    def copy(self, dst, src, n):
        """n bytes from address expression src to address expression dst"""
        if n <= 6:
            k = 0
            while k + 2 <= n:
                self.emit(f'ld hl,({src}+{k})')
                self.emit(f'ld ({dst}+{k}),hl')
                k += 2
            if k < n:
                self.emit(f'ld a,({src}+{k})')
                self.emit(f'ld ({dst}+{k}),a')
        else:
            self.emit(f'ld hl,{src}')
            self.emit(f'ld de,{dst}')
            self.emit(f'ld bc,{n}')
            self.emit('ldir')

    def put(self, dst, op, t):
        """store op (already of type t) at address expression dst"""
        if op.kind == 'imm':
            self.store_imm(dst, imm_bits(op.val, t), size(t))
        else:
            self.copy(dst, op.val, size(t))

    def put_ptr(self, ptr_in_hl_note, op, t):
        """store op at the address in HL: a constant of up to 2 bytes as it is, a memory op of 1 or 2 bytes through
        A or DE, anything else by LDIR (the caller materialises bigger constants first)"""
        n = size(t)
        if op.kind == 'imm':
            v = imm_bits(op.val, t)
            for k in range(n):
                if k:
                    self.emit('inc hl')
                self.emit(f'ld (hl),{(v >> (8 * k)) & 0xFF}')
            return
        if n == 1:
            self.emit(f'ld a,({op.val})')
            self.emit('ld (hl),a')
            return
        if n == 2:
            self.emit(f'ld de,({op.val})')
            self.emit('ld (hl),e')
            self.emit('inc hl')
            self.emit('ld (hl),d')
            return
        self.emit('ex de,hl')
        self.emit(f'ld hl,{op.val}')
        self.emit(f'ld bc,{n}')
        self.emit('ldir')

    def get_ptr(self, t):
        """copy the value at the address in HL into a fresh temp"""
        dst = self.temp(t)
        if size(t) == 1:
            self.emit('ld a,(hl)')
            self.emit(f'ld ({dst.val}),a')
            return dst
        if size(t) == 2:
            self.emit('ld e,(hl)')
            self.emit('inc hl')
            self.emit('ld d,(hl)')
            self.emit(f'ld ({dst.val}),de')
            return dst
        self.emit(f'ld de,{dst.val}')
        self.emit(f'ld bc,{size(t)}')
        self.emit('ldir')
        return dst

    def conv(self, op, to):
        """op, widened (or the same) as type to; constants just change type"""
        frm = op.ty
        if frm is B.BIT:
            frm = B.BOOL
        if to is B.BIT:
            to = B.BOOL
        if frm is to or frm == to:
            return op
        if op.kind == 'imm':
            return Op('imm', op.val, to)
        if frm is B.FLEX:
            raise GenError('an unsettled constant')
        if not (frm in TYPE_CODE and to in TYPE_CODE):
            return Op(op.kind, op.val, to)
        n0, n1 = size(frm), size(to)
        if n1 <= n0:                                        # narrowing (casts): the low bytes
            return Op('mem', op.val, to)
        dst = self.temp(to)
        self.copy(dst.val, op.val, n0)
        if frm.signed:
            self.emit(f'ld a,({op.val}+{n0 - 1})')
            self.emit('rla')
            self.emit('sbc a,a')
        else:
            self.emit('xor a')
        for k in range(n0, n1):
            self.emit(f'ld ({dst.val}+{k}),a')
        return dst

    # -- the program ---------------------------------------------------------------------------------------------
    def program(self):
        ck = self.ck
        funcs = [d for d in ck.decls if d.k == 'func' and d.name in ck.reachable]    # only what this target can reach
        out = []
        bodies = []
        for f in funcs:
            self.func, self.fsize, self.code = f, 0, []
            self.temps = {}
            self.live, self.cur_stmt, self.temp_mark, self.dead_args = self.liveness(f), None, 0, []
            self.loop_stmts, self.machinery, self.lsize = [], [], {}
            self.params = {}
            for (pn, _), pt in zip(f.params, f.ptys):
                self.params[pn] = self.slot(pt)
                self.lsize[pn] = max(size(pt), 1)
            self.place(f'f_{f.name}')
            self.locals = dict(self.params)
            self.block(f.body)
            self.emit('ret')
            if PEEP:
                self.code = peephole.optimise(self.code, self.cold_code, self.temps)
            bodies += self.code + self.cold_code + ['']
            self.cold_code, self.fail_stubs = [], {}
            self.equs.append(f'fsz_{f.name} equ {max(self.fsize, 1)}')
            self.fsizes = getattr(self, 'fsizes', {})
            self.fsizes[f.name] = max(self.fsize, 1)
        self.func, self.code = None, []
        self.place('bly_init_globals')
        self.globals_ = self.globals_names()
        for d in ck.decls:
            if d.k == 'var' and d.e is not None:
                v = self.conv(self.ex(d.e), d.ty)
                self.put(self.globals_[d.name], v, d.ty)
        self.emit('ret')
        init = self.code + self.cold_code
        self.cold_code, self.fail_stubs = [], {}
        out.append('        org 100h' if self.target == 'cpm' else f'        org {getattr(self, "org", 0x8000)}')
        out.append('        jp bly_start')
        out.append('bly_program:')
        out.append('        call bly_init_globals')
        if self.uses_input:
            out.append('        call bly_split_input')
            self.calls.add('bly_split_input')
        out.append('        call f_main')
        out.append('        ld hl,0')
        out.append('        ld (bly_line),hl')
        out.append('        jp bly_exit')
        out += init + [''] + bodies
        for name, lines in self.helpers.items():
            out += lines + ['']
        for b, name in self.strings.items():
            data = ', '.join(str(x) for x in b) if b else ''
            out.append(f'{name}: dw {name}d, {len(b)}')
            out.append(f'{name}d:' + (f' db {data}' if data else ''))
        _, lib = gather(sorted(c for c in self.calls if c not in self.helpers), self.target)
        out.append(lib)
        bss_at = getattr(self, 'bss_at', None)
        out.append('bly_bss:' if bss_at is None else f'bly_code_end:\nbly_bss equ {bss_at}')
        off = 0
        gbase = 0
        out.append(f'gs equ bly_bss')
        off = self.gsize
        for f in funcs:
            out.append(f'fr_{f.name} equ bly_bss+{off}')
            off += self.fsizes[f.name]
            out.append(f'rv_{f.name} equ bly_bss+{off}')
            off += size(f.rty) if f.rty is not B.VOID else 0
        out += self.equs
        out.append(f'bly_bss_end equ bly_bss+{off}')
        return '\n'.join(out) + '\n'

    # -- names -------------------------------------------------------------------------------------------------
    def var_addr(self, e):
        v = e.var
        if v.where == 'global':
            return self.globals_names()[e.name]
        return self.locals[e.name]

    def globals_names(self):
        if not hasattr(self, '_gnames'):
            self._gnames = {}
            off = 0
            for d in self.ck.decls:
                if d.k == 'var':
                    self._gnames[d.name] = f'gs+{off}'
                    off += max(size(d.ty), 1)
            self.gsize = max(self.gsize, off)
        return self._gnames

    # -- statements ------------------------------------------------------------------------------------------------
    def block(self, stmts):
        for s in stmts:
            self.stmt(s)

    def stmt(self, s):
        k = s.k
        heads = {'var': lambda: [s.e], 'assign': lambda: [s.target, s.e], 'expr': lambda: [s.e],
                 'return': lambda: [s.e], 'assert': lambda: [s.e], 'print': lambda: [s.items],
                 'for': lambda: [s.it], 'case': lambda: [s.e]}.get(k)
        self.stmt_calls = self.has_call(*heads()) if heads else True
        self.cur_stmt, self.temp_mark, self.dead_args = s, len(self.temps), []
        if k == 'var':
            t = s.ty
            self.lsize[s.name] = max(size(t), 1)
            v = self.conv(self.ex(s.e), t) if s.e is not None else None
            if v is not None and v.kind == 'mem' and v.fresh and size(v.ty) == size(t):
                self.locals[s.name] = v.val                   # a fresh temp nobody else holds: it becomes the variable
                return
            a = self.slot(t)
            self.locals[s.name] = a
            if v is None:
                self.store_imm(a, 0, size(t)) if size(t) <= 8 else self.zero(a, size(t))
            else:
                self.put(a, v, t)
        elif k == 'assign':
            self.assign(s)
        elif k == 'expr':
            self.ex(s.e)
        elif k == 'if':
            self.if_(s.arms, s.else_, s)
        elif k == 'while':
            top, end = self.label(), self.label()
            self.place(top)
            self.stmt_calls = self.has_call(s.cond)
            self.cur_stmt, self.temp_mark, self.dead_args = s, len(self.temps), []
            self.branch(s.cond, end, False)
            self.loop_enter((top, end), s, self.fsize)
            self.block(s.body)
            self.loop_exit()
            self.emit(f'jp {top}')
            self.place(end)
        elif k == 'for':
            self.for_(s)
        elif k == 'case':
            v = self.ex(s.e)
            end = self.label()
            for vals, body in s.whens:
                nxt, hit = self.label(), self.label()
                for w in vals:
                    self.cmp_jump('==', v, Op('imm', w.cval, s.e.ty if s.e.ty is not B.FLEX else w.ty), s.e.ty, hit,
                                  True, s.line)
                self.emit(f'jp {nxt}')
                self.place(hit)
                self.block(body)
                self.emit(f'jp {end}')
                self.place(nxt)
            self.block(s.else_)
            self.place(end)
        elif k == 'break':
            self.emit(f'jp {self.loops[-1][1]}')
        elif k == 'continue':
            self.emit(f'jp {self.loops[-1][0]}')
        elif k == 'return':
            f = self.func
            if s.e is not None:
                v = self.conv(self.ex(s.e), f.rty)
                self.put(f'rv_{f.name}', v, f.rty)
            self.emit('ret')
        elif k == 'assert':
            ok = self.label()
            self.branch(s.e, ok, True)
            self.line(s.line)
            self.jp('bly_assert')
            self.place(ok)
        elif k == 'print' and getattr(s, 'stream', 2) == 4:    # #4: FZX text (zxfzx.asm)
            if self.target != 'zx48':
                raise GenError('print #4 is Spectrum-only: put it inside if ZX then ... end')
            for kind, e in s.items:
                if kind == 'at':
                    y, x = self.conv(self.ex(e[0]), B.INT), self.conv(self.ex(e[1]), B.INT)
                    self.line(s.line)
                    self.load_hl(x)
                    self.emit('ex de,hl')
                    self.load_hl(y)
                    self.call('bly_zx_fzx_at')
                else:
                    v = self.ex(e)
                    self.line(s.line)
                    self.call('bly_zx_fzx_on')
                    self.pr(v, e.ty)
                    self.call('bly_zx_fzx_off')
            if s.newline:
                self.line(s.line)
                self.call('bly_zx_fzx_on')
                self.call('bly_nl')
                self.call('bly_zx_fzx_off')
        elif k == 'print' and getattr(s, 'stream', 2) != 2:    # #0, #1: the lower screen's (zxlower.asm)
            if self.target != 'zx48':
                raise GenError(f'print #{s.stream} is Spectrum-only: put it inside if ZX then ... end')

            def piece(f):                                    # each piece on channel K, worked out before
                self.line(s.line)
                self.call('bly_zx_lower')
                f()
                self.call('bly_zx_upper')
            for kind, e in s.items:
                if kind == 'zone':
                    piece(lambda: self.call('bly_zone'))
                elif kind == 'at':
                    r, c = self.conv(self.ex(e[0]), B.INT), self.conv(self.ex(e[1]), B.INT)
                    self.line(s.line)
                    self.load_hl(c)
                    self.emit('ex de,hl')
                    self.load_hl(r)
                    self.call('bly_zx_lat')
                else:
                    v = self.ex(e)
                    piece(lambda: self.pr(v, e.ty))
            if s.newline:
                piece(lambda: self.call('bly_nl'))
        elif k == 'print':
            placed = False                                   # from the first at on: the screen's alone (bracketed)
            on = lambda: placed and self.call('bly_zx_scr_on')
            off = lambda: placed and self.call('bly_zx_scr_off')
            for kind, e in s.items:
                if kind == 'zone':
                    on()
                    self.call('bly_zone')
                    off()
                elif kind == 'at':
                    if self.target != 'zx48':
                        raise GenError('print at is Spectrum-only: put it inside if ZX then ... end')
                    r, c = self.conv(self.ex(e[0]), B.INT), self.conv(self.ex(e[1]), B.INT)
                    self.line(s.line)
                    self.load_hl(c)
                    self.emit('ex de,hl')
                    self.load_hl(r)
                    self.call('bly_zx_at')
                    placed = True
                else:
                    v = self.ex(e)                           # worked out first: a failure here isn't at-text
                    on()
                    self.pr(v, e.ty)
                    off()
            if s.newline:
                on()
                self.call('bly_nl')
                off()
        else:
            raise GenError(f'no Z80 for statement {k}')

    def zero(self, a, n):
        self.emit(f'ld hl,{a}')
        self.emit(f'ld de,{a}+1')
        self.emit(f'ld bc,{n - 1}')
        self.emit('ld (hl),0')
        self.emit('ldir')

    def if_(self, arms, else_, st=None):
        end = self.label()
        for cond, body in arms:
            if cond.cval is not None:                       # a constant (if ZX, say): only the branch it takes
                if cond.cval:
                    self.block(body)
                    self.place(end)
                    return
                continue
            nxt = self.label()
            self.stmt_calls = self.has_call(cond)
            self.cur_stmt, self.temp_mark, self.dead_args = st, len(self.temps), []
            self.branch(cond, nxt, False)
            self.block(body)
            self.emit(f'jp {end}')
            self.place(nxt)
        self.block(else_)
        self.place(end)

    def pr(self, op, t):
        if t is B.FLEX:
            t = B.INT
        if t in (B.BYTE, B.WORD):
            self.load_hl(op)
            self.call('bly_pr_u16')
        elif t is B.INT:
            self.load_hl(op)
            self.call('bly_pr_i16')
        elif t is B.BOOL:
            self.load_a(op)
            self.call('bly_pr_bool')
        else:
            op = self.mem(op)                                # (a constant float, say)
            self.emit(f'ld hl,{self.addr(op)}')
            self.call(self.printer(t))

    # -- per-type helpers: printing and comparing through a pointer ----------------------------------------------------
    def printer(self, t):
        """a routine that prints the value at HL"""
        lib = {B.LONG: 'bly_pr_i32', B.QUAD: 'bly_pr_i64', B.STR: 'bly_pr_str', B.FLOAT: 'bly_pr_f',
               B.DWORD: 'bly_pr_u32p'}.get(t)
        if lib:
            self.calls.add(lib)
            return lib
        if t is B.STR:
            return 'bly_pr_str'
        name = 'ppr_' + self.tname(t)
        if name in self.helpers:
            return name
        lines = [f'{name}:']
        if t in (B.BYTE, B.WORD, B.INT, B.BOOL, B.BIT):
            if size(t) == 1:
                lines += ['        ld a,(hl)']
                if t in (B.BOOL, B.BIT):
                    lines += ['        jp bly_pr_bool']
                    self.calls.add('bly_pr_bool')
                else:
                    lines += ['        ld l,a', '        ld h,0', '        jp bly_pr_u16']
                    self.calls.add('bly_pr_u16')
            else:
                lines += ['        ld e,(hl)', '        inc hl', '        ld d,(hl)', '        ex de,hl',
                          f'        jp {"bly_pr_i16" if t is B.INT else "bly_pr_u16"}']
                self.calls.add('bly_pr_i16' if t is B.INT else 'bly_pr_u16')
        elif isinstance(t, B.RecordT):
            self.helpers[name] = []                          # reserve the name (records nest, never cycle)
            lines += [f'        ld ({name}_p),hl']
            opener = '(' if t is B.POS else t.name + '('
            lines += [f'        ld hl,{name}_open', '        call bly_pr_cstr']
            off = 0
            for i, (f, ft) in enumerate(t.fields):
                if i:
                    lines += [f'        ld hl,{name}_sep', '        call bly_pr_cstr']
                lines += [f'        ld hl,({name}_p)', f'        ld de,{off}', '        add hl,de',
                          f'        call {self.printer(ft)}']
                off += size(ft)
            lines += [f'        ld hl,{name}_close', '        jp bly_pr_cstr',
                      f'{name}_p: dw 0', f'{name}_open: db "{opener}",0', f'{name}_sep: db ", ",0',
                      f'{name}_close: db ")",0']
            self.calls.add('bly_pr_cstr')
        else:
            raise GenError(f'no printer for {t!r}')
        self.helpers[name] = lines
        return name

    def comparer(self, t):
        """a routine comparing the values at HL and DE: A = FFh/0/1, flags as after OR A"""
        lib = {B.LONG: 'bly_cmp_i32', B.QUAD: 'bly_cmp_i64', B.STR: 'bly_cmp_str', B.FLOAT: 'bly_fcmp',
               B.DWORD: 'bly_cmp_u32'}.get(t)
        if lib:
            self.calls.add(lib)
            return lib
        if t is B.STR:
            return 'bly_cmp_str'
        name = 'pcmp_' + self.tname(t)
        if name in self.helpers:
            return name
        lines = [f'{name}:']
        if t in (B.BYTE, B.BOOL, B.BIT):
            lines += ['        ld a,(de)', '        ld e,a', '        ld a,(hl)', '        jp bly_cmp_u8']
            self.calls.add('bly_cmp_u8')
        elif t in (B.WORD, B.INT):
            r = 'bly_cmp_i16' if t is B.INT else 'bly_cmp_u16'
            lines += ['        ld a,(de)', '        ld c,a', '        inc de', '        ld a,(de)', '        ld b,a',
                      '        ld e,(hl)', '        inc hl', '        ld d,(hl)', '        ex de,hl',
                      '        ld d,b', '        ld e,c', f'        jp {r}']
            self.calls.add(r)
        elif isinstance(t, B.RecordT):
            self.helpers[name] = []
            lines += [f'        ld ({name}_a),hl', f'        ld ({name}_b),de']
            off = 0
            for f, ft in t.fields:
                lines += [f'        ld hl,({name}_b)', f'        ld de,{off}', '        add hl,de', '        push hl',
                          f'        ld hl,({name}_a)', '        add hl,de', '        pop de',
                          f'        call {self.comparer(ft)}', '        ret nz']
                off += size(ft)
            lines += ['        xor a', '        ret', f'{name}_a: dw 0', f'{name}_b: dw 0']
        else:
            raise GenError(f'no comparer for {t!r}')
        self.helpers[name] = lines
        return name

    def tname(self, t):
        if t in (B.BIT,):
            return 'bool'
        return t.name

    # -- expressions -----------------------------------------------------------------------------------------------
    def ex(self, e):
        if e.k == 'name' and e.var.const:
            if isinstance(e.var.ty, B.Gen):
                return Op('mem', self.const_array(e.name, e.var), e.ty)
            if e.ty is B.FLOAT:
                size(B.FLOAT)                            # (on CP/M: floats aren't here)
                return Op('imm', float(e.cval), B.FLOAT)
            return Op('imm', int(e.cval), e.ty if e.ty is not B.FLEX else B.INT)
        if e.cval is not None and e.k != 'name':
            t = e.ty
            if t is B.FLEX:
                t = next(x for x in (B.INT, B.LONG, B.QUAD) if x.lo <= e.cval <= x.hi)
            if t is B.FLOAT:
                size(B.FLOAT)
                rom5(float(e.cval))                      # too big for the ROM: say so now
                return Op('imm', float(e.cval), B.FLOAT)
            return Op('imm', int(e.cval), t)
        return getattr(self, 'x_' + e.k)(e)

    def const_array(self, name, var):
        """a constant array (dirs4, dirs8, or a table): its elements laid out in the code, as ABI.md section 1 lays
        values out in memory; returns its label"""
        lab = ('bly_' if name in ('dirs4', 'dirs8') else 'k_') + name
        if lab not in self.helpers:
            et = var.ty.args[0]
            lines = [f'{lab}:']
            if et is B.BYTE:                             # bytes, sixteen to a line (an embedded font is thousands)
                vals = var.cval
                lines += ['        db ' + ', '.join(str(v) for v in vals[i:i + 16]) for i in range(0, len(vals), 16)]
            for v in [] if et is B.BYTE else var.cval:
                lines += ['        ' + x for x in self.const_data(v, et)]
            self.helpers[lab] = lines
        return lab

    def const_data(self, v, t):
        """a constant value's bytes, as data lines"""
        if isinstance(t, B.RecordT):
            out = []
            for x, (_, ft) in zip(v, t.fields):
                out += self.const_data(x, ft)
            return out
        if t is B.STR:
            if not v:
                return ['dw 0, 0']
            return [f'dw {self.string(v).val}d, {len(v)}']
        if t is B.FLOAT:
            size(B.FLOAT)                                # (on CP/M: floats aren't here)
            return ['db ' + ', '.join(str(b) for b in rom5(float(v)))]
        if t is B.BOOL:
            return [f'db {1 if v else 0}']
        n = size(t)
        u = v & ((1 << (8 * n)) - 1)
        return ['db ' + ', '.join(str((u >> (8 * k)) & 0xFF) for k in range(n))]

    def x_str(self, e):
        return self.string(e.v)

    def x_name(self, e):
        t = e.ty
        a = self.var_addr(e)
        if isinstance(t, B.Gen) and t.kind == 'array' and t.n is not None:
            return Op('mem', a, t)                           # an array is used where it lives
        if e.var.where == 'global' and self.stmt_calls:       # a call later in the statement could change it:
            return self.copy_to_temp(a, t)                    # read it now
        return Op('mem', a, t)                                # in place: nothing in an expression changes a local

    def x_bin(self, e):
        op = e.op
        if op in ('and', 'or'):
            no, end, r = self.label(), self.label(), self.temp(B.BOOL)
            self.branch(e, no, False)
            self.emit('ld a,1')
            self.emit(f'jp {end}')
            self.place(no)
            self.emit('xor a')
            self.place(end)
            self.emit(f'ld ({r.val}),a')
            return r
        if op == 'in':
            k = self.ex(e.a)
            c = self.ex(e.b)
            k = self.mem(self.conv(k, e.b.ty.args[0]))
            self.load_hl(c)
            self.emit(f'ld de,{self.addr(k)}')
            self.call('bly_map_has')
            r = self.temp(B.BOOL)
            self.emit(f'ld ({r.val}),a')
            return r
        a = self.ex(e.a)
        b = self.ex(e.b)
        return self.binop(e, a, b)

    def common(self, ta, tb):
        if ta is B.FLEX:
            return tb
        if tb is B.FLEX:
            return ta
        if B.widens(ta, tb):
            return tb
        return ta

    def compare(self, op, a, b, t, line):
        """a compare as a bool value (0 or 1 in a temp): a branch, then the answer"""
        yes, end, r = self.label(), self.label(), self.temp(B.BOOL)
        self.cmp_jump(op, a, b, t, yes, True, line)
        self.emit('xor a')
        self.emit(f'jp {end}')
        self.place(yes)
        self.emit('ld a,1')
        self.place(end)
        self.emit(f'ld ({r.val}),a')
        return r

    def cmp_jump(self, op, a, b, t, target, when, line=None):
        """jump to target if (a op b) == when, else fall through: phase one's inline compares for 8 and 16 bits
        (codegen.py cmp), the comparer's flags (A = FFh/0/1, as after OR A) for everything else"""
        if t in (B.BIT,):
            t = B.BOOL
        if not when:
            op = NEG[op]
        a, b = self.conv(a, t), self.conv(b, t)
        if t in (B.BYTE, B.BOOL):
            if op in ('>', '<='):
                a, b, op = b, a, SWAP[op]
            if b.kind == 'imm':
                self.load_a(a)
                self.emit('or a' if b.val & 0xFF == 0 else f'cp {b.val & 0xFF}')
            else:
                self.load_a(b)
                self.emit('ld e,a')
                self.load_a(a)
                self.emit('cp e')
            self.emit(f'jp {UCOND[op]},{target}')
            return
        if t in (B.WORD, B.INT):
            if op in ('==', '!='):
                if a.kind == 'imm' and b.kind != 'imm':
                    a, b = b, a
                self.load_hl(a)
                if b.kind == 'imm' and b.val & 0xFFFF == 0:
                    self.emit('ld a,h')
                    self.emit('or l')
                else:
                    self.load_de(b)
                    self.emit('or a')
                    self.emit('sbc hl,de')
                self.emit(f'jp {UCOND[op]},{target}')
                return
            if op in ('>', '<='):
                a, b, op = b, a, SWAP[op]
            if t is B.INT:                                    # signed: flip both signs, compare unsigned
                if a.kind == 'imm':
                    self.emit(f'ld hl,{(a.val & 0xFFFF) ^ 0x8000}')
                else:
                    self.load_hl(a)
                    self.emit('ld a,h')
                    self.emit('xor 80h')
                    self.emit('ld h,a')
                if b.kind == 'imm':
                    self.emit(f'ld de,{(b.val & 0xFFFF) ^ 0x8000}')
                else:
                    self.load_de(b)
                    self.emit('ld a,d')
                    self.emit('xor 80h')
                    self.emit('ld d,a')
                self.emit('or a')
                self.emit('sbc hl,de')
            else:                                             # unsigned, without destroying HL
                self.load_hl(a)
                if b.kind == 'imm':
                    k = b.val & 0xFFFF
                    self.emit('ld a,l')
                    self.emit(f'sub {k & 0xFF}')
                    self.emit('ld a,h')
                    self.emit(f'sbc a,{k >> 8}')
                else:
                    self.load_de(b)
                    self.emit('ld a,l')
                    self.emit('sub e')
                    self.emit('ld a,h')
                    self.emit('sbc a,d')
            self.emit(f'jp {UCOND[op]},{target}')
            return
        a, b = self.mem(a), self.mem(b)
        self.line(line)
        self.emit(f'ld hl,{self.addr(a)}')
        self.emit(f'ld de,{self.addr(b)}')
        self.call(self.comparer(t))
        if op == '>':                                          # greater: not zero, and not minus
            skip = self.label()
            self.emit(f'jp z,{skip}')
            self.emit(f'jp p,{target}')
            self.place(skip)
        elif op == '<=':
            self.emit(f'jp m,{target}')
            self.emit(f'jp z,{target}')
        else:
            self.emit(f'jp {SCOND[op]},{target}')

    def branch(self, e, target, when):
        """jump to target if the bool e is `when`, else fall through: and, or and not as jumps, compares fused"""
        if e.cval is not None:
            if bool(e.cval) == when:
                self.emit(f'jp {target}')
            return
        if e.k == 'un' and e.op == 'not':
            self.branch(e.a, target, not when)
            return
        if e.k == 'bin' and e.op in ('and', 'or'):
            if (e.op == 'and') != when:                       # and->false, or->true: either side decides
                self.branch(e.a, target, when)
                self.branch(e.b, target, when)
            else:                                             # and->true, or->false: both must
                skip = self.label()
                self.branch(e.a, skip, not when)
                self.branch(e.b, target, when)
                self.place(skip)
            return
        if e.k == 'bin' and e.op in CMP_ROUTINE:
            a = self.ex(e.a)
            b = self.ex(e.b)
            ct = self.common(a.ty, b.ty) if a.ty in TYPE_CODE or b.ty in TYPE_CODE or a.ty is B.FLEX else a.ty
            self.cmp_jump(e.op, a, b, ct, target, when, e.line)
            return
        c = self.ex(e)
        self.load_a(c)
        self.emit('or a')
        self.emit(f'jp {"nz" if when else "z"},{target}')

    def binop(self, e, a, b):
        op, t, line = e.op, e.ty, e.line
        if op not in CMP_ROUTINE and not (t in (B.BYTE, B.WORD, B.INT, B.POS) and op in '+-&|^'):
            self.line(line)                                  # before any operand is loaded: it uses HL
        if op in CMP_ROUTINE:
            ct = self.common(a.ty, b.ty) if a.ty in TYPE_CODE or b.ty in TYPE_CODE or a.ty is B.FLEX else a.ty
            return self.compare(op, a, b, ct, line)
        if t is B.POS:
            a, b = self.mem(a), self.mem(b)
            r = self.temp(B.POS)
            for k in (0, 2):
                self.emit(f'ld hl,({self.addr(a)}+{k})')
                self.emit(f'ld de,({self.addr(b)}+{k})')
                self.emit('or a')
                self.emit('adc hl,de' if op == '+' else 'sbc hl,de')
                self.fail_jp('pe', 'bly_ovf_int', line)
                self.emit(f'ld ({r.val}+{k}),hl')
            return r
        a, b = self.conv(a, t), self.conv(b, t)
        r = self.temp(t)
        if op in ('<<', '>>'):
            return self.shift(op, a, b, t, r, line)
        if t is B.FLOAT:                                     # the ROM's calculator, by address (ABI.md section 11)
            a, b = self.mem(a), self.mem(b)
            self.emit(f'ld hl,{self.addr(a)}')
            self.emit(f'ld de,{self.addr(b)}')
            self.emit(f'ld bc,{r.val}')
            self.call({'+': 'bly_fadd', '-': 'bly_fsub', '*': 'bly_fmul', '/': 'bly_fdiv', '**': 'bly_fpow'}[op])
            return r
        if t in (B.BYTE, B.WORD, B.INT):
            if op in ('+', '-') and t is not B.INT and b.kind == 'imm':   # unsigned: wraps, so inc and dec
                m = 0xFF if t is B.BYTE else 0xFFFF
                k = (b.val if op == '+' else -b.val) & m
                if k <= 3 or m + 1 - k <= 3:
                    up, n = (True, k) if k <= 3 else (False, m + 1 - k)
                    reg = 'a' if t is B.BYTE else 'hl'
                    self.load_a(a) if t is B.BYTE else self.load_hl(a)
                    for _ in range(n):
                        self.emit(f'{"inc" if up else "dec"} {reg}')
                    self.emit(f'ld ({r.val}),{reg}')
                    return r
            if op in ('+', '-', '&', '|', '^'):
                if t is B.BYTE:
                    self.load_a(b)
                    self.emit('ld e,a')
                    self.load_a(a)
                    self.emit({'+': 'add a,e', '-': 'sub e', '&': 'and e', '|': 'or e', '^': 'xor e'}[op])
                    self.emit(f'ld ({r.val}),a')
                    return r
                self.load_hl(b)
                self.emit('ex de,hl')
                self.load_hl(a)
                if op in ('+', '-'):
                    if t is B.INT:
                        self.emit('or a')
                        self.emit('adc hl,de' if op == '+' else 'sbc hl,de')
                        self.fail_jp('pe', 'bly_ovf_int', line)
                    elif op == '+':
                        self.emit('add hl,de')
                    else:
                        self.emit('or a')
                        self.emit('sbc hl,de')
                else:
                    ins = {'&': 'and', '|': 'or', '^': 'xor'}[op]
                    self.emit('ld a,l')
                    self.emit(f'{ins} e')
                    self.emit('ld l,a')
                    self.emit('ld a,h')
                    self.emit(f'{ins} d')
                    self.emit('ld h,a')
                self.emit(f'ld ({r.val}),hl' if t is not B.BYTE else f'ld a,l')
                return r
            if self.const_arith(op, a, b, t, r, line):             # unsigned, by a constant: phase one's inline forms
                return r
            # * / %: 16-bit routines; a byte is done in 16 bits and keeps the low byte
            self.load_hl(b)
            self.emit('ex de,hl')
            self.load_hl(a)
            if op == '*':
                self.call('bly_mul_i16' if t is B.INT else 'bly_mul_u16')
            elif op == '%' and t is B.INT:
                self.call('bly_rem_i16')                    # -32768 % -1 is 0, where / would overflow
                self.emit('ex de,hl')
            else:
                self.call('bly_divmod_i16' if t is B.INT else 'bly_divmod_u16')
                if op == '%':
                    self.emit('ex de,hl')
            if t is B.BYTE:
                self.emit('ld a,l')
                self.emit(f'ld ({r.val}),a')
            else:
                self.emit(f'ld ({r.val}),hl')
            return r
        if t in (B.LONG, B.QUAD, B.DWORD) and op in ('&', '|', '^'):
            return self.wide_bits(op, a, b, t, r)
        if t is B.LONG and op in ('/', '%') and b.kind == 'imm' and 2 <= b.val <= 1 << 30 and b.val & (b.val - 1) == 0:
            return self.long_pow2(op, a, b.val.bit_length() - 1, r)
        # long, dword and quad: the library, by address
        a, b = self.mem(a), self.mem(b)
        n = {B.LONG: 'i32', B.QUAD: 'i64', B.DWORD: 'u32'}[t]
        if op == '%' and t is B.DWORD:                      # the remainder alone: no quotient wanted (BC = 0)
            self.emit(f'ld hl,{self.addr(a)}')
            self.emit(f'ld de,{self.addr(b)}')
            self.emit('ld bc,0')
            self.emit(f'ld ix,{r.val}')
            self.call('bly_divmod_u32')
            return r
        if op == '%':                                       # MIN % -1 is 0, where / would overflow
            self.emit(f'ld hl,{self.addr(a)}')
            self.emit(f'ld de,{self.addr(b)}')
            self.emit(f'ld bc,{r.val}')
            self.call(f'bly_rem_{n}')
            return r
        if op == '/':
            q, m = r, self.temp(t)
            self.emit(f'ld hl,{self.addr(a)}')
            self.emit(f'ld de,{self.addr(b)}')
            self.emit(f'ld bc,{q.val}')
            self.emit(f'ld ix,{m.val}')
            self.call(f'bly_divmod_{n}')
            return r
        name = {'+': 'add', '-': 'sub', '*': 'mul', '&': 'and', '|': 'or', '^': 'xor'}[op]
        self.emit(f'ld hl,{self.addr(a)}')
        self.emit(f'ld de,{self.addr(b)}')
        self.emit(f'ld bc,{r.val}')
        self.call(f'bly_{name}_{n}')
        return r

    def const_arith(self, op, a, b, t, r, line=0):
        """byte or word * / % by a constant, inline: powers of two as shifts and masks, other multipliers as
        shift-and-add (phase one's codegen). Unsigned only (int traps on overflow), and never / or % by 0 (the
        library says so). Returns False to leave it to the library."""
        if t is B.INT and op == '*' and (b.kind == 'imm' or a.kind == 'imm'):
            return self.int_times_const(a, b, r, line)
        if t not in (B.BYTE, B.WORD) or not (b.kind == 'imm' or op == '*' and a.kind == 'imm'):
            return False
        if b.kind != 'imm':
            a, b = b, a
        m = 0xFF if t is B.BYTE else 0xFFFF
        k = b.val & m
        pow2 = k and k & (k - 1) == 0
        n = k.bit_length() - 1
        if op in '/%' and not pow2:
            return False
        if t is B.BYTE:
            if op == '*' and not pow2:
                self.load_a(a)
                if k == 0:
                    self.emit('xor a')
                else:
                    self.emit('ld l,a')
                    self.emit('ld h,0')
                    self.mul_hl_const(k)
                    self.emit('ld a,l')
            else:
                self.load_a(a)
                if op == '*':
                    for _ in range(n):
                        self.emit('add a,a')
                elif op == '/':
                    for _ in range(n):
                        self.emit('srl a')
                else:
                    self.emit(f'and {k - 1}')
            self.emit(f'ld ({r.val}),a')
            return True
        self.load_hl(a)
        if op == '*':
            if k == 0:
                self.emit('ld hl,0')
            elif pow2:
                for _ in range(n):
                    self.emit('add hl,hl')
            else:
                self.mul_hl_const(k)
        elif op == '/':
            if n >= 8:
                self.emit('ld l,h')
                self.emit('ld h,0')
                n -= 8
                for _ in range(n):
                    self.emit('srl l')
            else:
                for _ in range(n):
                    self.emit('srl h')
                    self.emit('rr l')
        else:
            self.emit('ld a,l')
            self.emit(f'and {(k - 1) & 0xFF}')
            self.emit('ld l,a')
            self.emit('ld a,h')
            self.emit(f'and {(k - 1) >> 8}')
            self.emit('ld h,a')
        self.emit(f'ld ({r.val}),hl')
        return True

    def int_times_const(self, a, b, r, line):
        """int * k for a constant k from 1 to 32767, inline: shift-and-add with ADC, which sets P/V on signed overflow.
        Each step's value is x times a prefix of k's bits, no larger than x * k, so a step overflows only if the answer
        would: the trap is exactly the library's. Other k: the library"""
        if b.kind != 'imm':
            a, b = b, a
        k = b.val
        if not 1 <= k <= 32767:
            return False
        self.load_hl(a)
        if k > 1:
            if k & (k - 1):
                self.emit('ld b,h')
                self.emit('ld c,l')
            for bit in bin(k)[3:]:
                self.emit('or a')
                self.emit('adc hl,hl')
                self.fail_jp('pe', 'bly_ovf_int', line)
                if bit == '1':
                    self.emit('or a')
                    self.emit('adc hl,bc')
                    self.fail_jp('pe', 'bly_ovf_int', line)
        self.emit(f'ld ({r.val}),hl')
        return True

    def wide_bits(self, op, a, b, t, r):
        """& | ^ on a long or quad, a byte at a time: a constant byte of 00h or FFh is a store or a copy"""
        n = size(t)
        if a.kind == 'imm':
            a, b = b, a
        if a.kind == 'imm':
            a = self.mem(a)
        ins = {'&': 'and', '|': 'or', '^': 'xor'}[op]
        if b.kind == 'imm':
            v = imm_bits(b.val, t) & ((1 << (8 * n)) - 1)
            for k in range(n):
                byte = (v >> (8 * k)) & 0xFF
                if (op, byte) in (('&', 0), ('|', 0xFF)):
                    self.emit(f'ld a,{byte}')
                elif (op, byte) in (('&', 0xFF), ('|', 0), ('^', 0)):
                    self.emit(f'ld a,({a.val}+{k})')
                elif (op, byte) == ('^', 0xFF):
                    self.emit(f'ld a,({a.val}+{k})')
                    self.emit('cpl')
                else:
                    self.emit(f'ld a,({a.val}+{k})')
                    self.emit(f'{ins} {byte}')
                self.emit(f'ld ({r.val}+{k}),a')
            return r
        for k in range(n):
            self.emit(f'ld a,({b.val}+{k})')
            self.emit('ld c,a')
            self.emit(f'ld a,({a.val}+{k})')
            self.emit(f'{ins} c')
            self.emit(f'ld ({r.val}+{k}),a')
        return r

    def load_dehl(self, a):
        """a long into DE:HL (D the top byte)"""
        if a.kind == 'imm':
            v = imm_bits(a.val, B.LONG) & 0xFFFFFFFF
            self.emit(f'ld hl,{v & 0xFFFF}')
            self.emit(f'ld de,{v >> 16}')
        else:
            self.emit(f'ld hl,({a.val})')
            self.emit(f'ld de,({a.val}+2)')

    def shift_dehl(self, op, n, signed=True):
        """DE:HL shifted by 0 <= n < 32: << wraps, >> is arithmetic (as the interpreter's, on signed values), or
        brings zeros in for a dword"""
        nbytes, bits = divmod(n, 8)
        for _ in range(nbytes):
            if op == '<<':
                for ins in ('ld d,e', 'ld e,h', 'ld h,l', 'ld l,0'):
                    self.emit(ins)
            elif signed:
                for ins in ('ld l,h', 'ld h,e', 'ld e,d', 'ld a,d', 'rla', 'sbc a,a', 'ld d,a'):
                    self.emit(ins)
            else:
                for ins in ('ld l,h', 'ld h,e', 'ld e,d', 'ld d,0'):
                    self.emit(ins)
        for _ in range(bits):
            for ins in (('add hl,hl', 'rl e', 'rl d') if op == '<<' else
                        (('sra d' if signed else 'srl d'), 'rr e', 'rr h', 'rr l')):
                self.emit(ins)

    def const_shift(self, op, a, n, t, r):
        """a shift by a constant count, in registers: a byte in A, a word or int in HL, a long in DE:HL. Past the
        width, << gives 0, and >> gives 0, or -1 for a negative int or long"""
        if t is B.BYTE:
            self.load_a(a)
            if n >= 8:
                self.emit('xor a')
            for _ in range(n if n < 8 else 0):
                self.emit('add a,a' if op == '<<' else 'srl a')
            self.emit(f'ld ({r.val}),a')
            return r
        if t in (B.WORD, B.INT):
            self.load_hl(a)
            if n >= 16:
                if op == '>>' and t is B.INT:
                    for ins in ('ld a,h', 'rla', 'sbc a,a', 'ld h,a', 'ld l,a'):
                        self.emit(ins)
                else:
                    self.emit('ld hl,0')
            else:
                if n >= 8:
                    if op == '<<':
                        self.emit('ld h,l')
                        self.emit('ld l,0')
                    elif t is B.INT:
                        for ins in ('ld l,h', 'ld a,h', 'rla', 'sbc a,a', 'ld h,a'):
                            self.emit(ins)
                    else:
                        self.emit('ld l,h')
                        self.emit('ld h,0')
                    n -= 8
                for _ in range(n):
                    if op == '<<':
                        self.emit('add hl,hl')
                    else:
                        self.emit('sra h' if t is B.INT else 'srl h')
                        self.emit('rr l')
            self.emit(f'ld ({r.val}),hl')
            return r
        if n >= 32:                                          # a long or a dword, all the way out
            if op == '>>' and t is B.LONG:
                a = self.mem(a)
                self.emit(f'ld a,({a.val}+3)')
                self.emit('rla')
                self.emit('sbc a,a')
            else:
                self.emit('xor a')
            for k in range(4):
                self.emit(f'ld ({r.val}+{k}),a')
            return r
        self.load_dehl(a)
        self.shift_dehl(op, n, t.signed)
        self.emit(f'ld ({r.val}),hl')
        self.emit(f'ld ({r.val}+2),de')
        return r

    def long_pow2(self, op, a, n, r):
        """a long / or % 2^n (1 <= n <= 30), truncating as C does. q is the arithmetic shift of x + (2^n - 1) when x
        is negative (which turns the shift's floor into truncation), and x % 2^n is x - ((x + that bias) & ~mask)"""
        a = self.mem(a)
        bias = (1 << n) - 1
        pos = self.label()
        self.load_dehl(a)
        self.emit('bit 7,d')
        self.emit(f'jr z,{pos}')
        self.emit(f'ld bc,{bias & 0xFFFF}')
        self.emit('add hl,bc')
        self.emit('ex de,hl')
        self.emit(f'ld bc,{bias >> 16}')
        self.emit('adc hl,bc')
        self.emit('ex de,hl')
        self.place(pos)
        if op == '/':
            self.shift_dehl('>>', n)
            self.emit(f'ld ({r.val}),hl')
            self.emit(f'ld ({r.val}+2),de')
            return r
        keep = (~bias) & 0xFFFFFFFF                          # (x + bias) with its low n bits cleared
        for reg, k in (('l', 0), ('h', 1), ('e', 2), ('d', 3)):
            byte = (keep >> (8 * k)) & 0xFF
            if byte == 0:
                self.emit(f'ld {reg},0')
            elif byte != 0xFF:
                self.emit(f'ld a,{reg}')
                self.emit(f'and {byte}')
                self.emit(f'ld {reg},a')
        self.emit(f'ld ({r.val}),hl')                         # then x minus that
        self.emit(f'ld ({r.val}+2),de')
        self.emit(f'ld hl,({a.val})')
        self.emit(f'ld bc,({r.val})')
        self.emit('or a')
        self.emit('sbc hl,bc')
        self.emit(f'ld ({r.val}),hl')
        self.emit(f'ld hl,({a.val}+2)')
        self.emit(f'ld bc,({r.val}+2)')
        self.emit('sbc hl,bc')
        self.emit(f'ld ({r.val}+2),hl')
        return r

    def count_de(self, b):
        """a shift count into DE as a signed word, saturated to 64 when it's wider or a big word"""
        bt = b.ty
        if b.kind == 'imm':
            v = b.val
            self.emit(f'ld de,{(min(v, 64) if v >= 0 else -1) & 0xFFFF}')
            return
        if bt is B.BYTE:
            self.load_de(b)
            return
        if bt in (B.WORD, B.INT):                           # anything over 64 is 64 (a negative int stays negative)
            ok = self.label()
            self.load_de(b)
            if bt is B.INT:
                self.emit('bit 7,d')
                self.emit(f'jr nz,{ok}')
            self.emit('ld hl,64')
            self.emit('or a')
            self.emit('sbc hl,de')
            self.emit(f'jr nc,{ok}')
            self.emit('ld de,64')
            self.place(ok)
            return
        q = self.conv(b, B.QUAD)
        self.emit(f'ld hl,{self.addr(q)}')
        self.call('bly_count64')
        self.helpers.setdefault('bly_count64', COUNT64)

    def shift(self, op, a, b, t, r, line):
        if b.kind == 'imm' and b.val >= 0 and t in (B.BYTE, B.WORD, B.INT, B.LONG, B.DWORD):
            return self.const_shift(op, a, b.val, t, r)
        if t in (B.BYTE, B.WORD, B.INT):
            self.count_de(b)
            self.load_hl(a)
            routine = 'bly_shl16' if op == '<<' else ('bly_shr_i16' if t is B.INT else 'bly_shr_u16')
            self.call(routine)
            if t is B.BYTE:
                self.emit('ld a,l')
                self.emit(f'ld ({r.val}),a')
            else:
                self.emit(f'ld ({r.val}),hl')
            return r
        n = {B.LONG: 'i32', B.QUAD: 'i64', B.DWORD: 'i32'}[t]   # a dword's << is a long's (the same bits)
        if t is B.DWORD and op == '>>':
            n = 'u32'                                        # but >> brings zeros in
        a = self.mem(a)
        self.count_de(b)
        self.emit(f'ld hl,{self.addr(a)}')
        self.emit(f'ld bc,{r.val}')
        self.call(f'bly_{"shl" if op == "<<" else "shr"}_{n}')
        return r

    def x_un(self, e):
        a = self.ex(e.a)
        t = e.ty
        r = self.temp(t)
        if e.op == 'not':
            self.load_a(a)
            self.emit('xor 1')
            self.emit(f'ld ({r.val}),a')
            return r
        if e.op == '~':
            a = self.materialize(a) if a.kind == 'imm' else a
            for k in range(size(t)):
                self.emit(f'ld a,({a.val}+{k})')
                self.emit('cpl')
                self.emit(f'ld ({r.val}+{k}),a')
            return r
        if t not in (B.BYTE, B.WORD, B.INT):
            self.line(e.line)
        if t is B.BYTE:
            self.load_a(a)
            self.emit('neg')
            self.emit(f'ld ({r.val}),a')
        elif t in (B.WORD, B.INT):
            self.load_hl(a)
            self.emit('ex de,hl')
            self.emit('ld hl,0')
            self.emit('or a')
            self.emit('sbc hl,de')
            if t is B.INT:
                self.fail_jp('pe', 'bly_ovf_int', e.line)
            self.emit(f'ld ({r.val}),hl')
        elif t is B.FLOAT:
            a = self.mem(a)
            self.emit(f'ld hl,{self.addr(a)}')
            self.emit(f'ld bc,{r.val}')
            self.call('bly_fneg')
        else:
            a = self.mem(a)
            n = {B.LONG: 'i32', B.QUAD: 'i64', B.DWORD: 'u32'}[t]
            self.emit(f'ld hl,{self.addr(a)}')
            self.emit(f'ld bc,{r.val}')
            self.call(f'bly_neg_{n}')
        return r

    # -- indexing --------------------------------------------------------------------------------------------------
    def check_index(self, i, n_bc_already, line):
        """with the length in BC, check index op i and leave it in DE as a word"""
        it = i.ty
        if it in (B.BYTE, B.WORD) or i.kind == 'imm' and 0 <= i.val <= 65535:
            self.load_de(i)
            self.emit('ld h,d')
            self.emit('ld l,e')
            self.emit('or a')
            self.emit('sbc hl,bc')
            self.fail_jp('nc', 'bly_fail_index_u16', line)
        elif it is B.INT:
            self.load_de(i)
            self.emit('bit 7,d')
            self.fail_jp('nz', 'bly_fail_index_i16', line)
            self.emit('ld h,d')
            self.emit('ld l,e')
            self.emit('or a')
            self.emit('sbc hl,bc')
            self.fail_jp('nc', 'bly_fail_index_i16', line)
        else:
            self.line(line)
            q = self.conv(i, B.QUAD) if i.kind != 'imm' else self.materialize(Op('imm', i.val, B.QUAD))
            self.emit('ld d,b')
            self.emit('ld e,c')
            self.emit(f'ld hl,{q.val}')
            self.call('bly_chk_index64')

    def elem_addr(self, base_in_hl, esize):
        """HL = base (already in HL) + DE * esize"""
        if esize == 1:
            self.emit('add hl,de')
            return
        self.emit('push hl')
        self.emit('ld h,d')
        self.emit('ld l,e')
        self.mul_hl_const(esize)
        self.emit('pop de')
        self.emit('add hl,de')

    def mul_hl_const(self, k):
        if k == 1:
            return
        if k & (k - 1) == 0:
            while k > 1:
                self.emit('add hl,hl')
                k //= 2
            return
        self.emit('ld b,h')
        self.emit('ld c,l')
        bits = bin(k)[3:]
        for bit in bits:
            self.emit('add hl,hl')
            if bit == '1':
                self.emit('add hl,bc')

    def array_base(self, e):
        """an array expression: (address of the first element, the length as an Op)"""
        if e.k == 'name' and e.var.const:
            lab = self.const_array(e.name, e.var)
            return ('imm_addr', lab), Op('imm', len(e.var.cval), B.WORD)
        a = self.var_addr(e)
        if e.var.ty.n is not None:
            return ('imm_addr', a), Op('imm', e.var.ty.n, B.WORD)
        return ('ptr_at', a), Op('mem', f'{a}+2', B.WORD)

    def load_base(self, base):
        kind, a = base
        self.emit(f'ld hl,{a}' if kind == 'imm_addr' else f'ld hl,({a})')

    def array_elem_ptr(self, e, i, line):
        """HL = the address of array element i, checked"""
        base, n = self.array_base(e.obj)
        self.load_bc(n)
        self.check_index(i, True, line)
        self.load_base(base)
        self.elem_addr(None, size(e.obj.ty.args[0]))

    def bit_ptr(self, arr, i, line):
        """HL = the byte holding bit i of a bit array, A = its mask; i checked against the length"""
        base, n = self.array_base(arr)
        self.load_bc(n)
        self.check_index(i, True, line)                     # DE = i
        self.bit_addr(base)

    def bit_addr(self, base):
        """with DE = i: HL = base + i / 8, A = 1 << (i % 8), from a table of the eight masks"""
        self.helpers.setdefault('bly_bitmask', ['bly_bitmask: db 1, 2, 4, 8, 16, 32, 64, 128'])
        self.emit('ld a,e')
        self.emit('and 7')
        self.emit('ld c,a')
        for _ in range(3):
            self.emit('srl d')
            self.emit('rr e')
        self.load_base(base)
        self.emit('add hl,de')
        self.emit('ld b,0')
        self.emit('ex de,hl')
        self.emit('ld hl,bly_bitmask')
        self.emit('add hl,bc')
        self.emit('ld a,(hl)')
        self.emit('ex de,hl')

    def bit_read(self):
        """the bit at (HL) under mask A, as a bool (0 or 1) in a temp"""
        r = self.temp(B.BOOL)
        self.emit('and (hl)')
        self.emit('add a,255')                              # carry if it was set
        self.emit('sbc a,a')
        self.emit('and 1')
        self.emit(f'ld ({r.val}),a')
        return r

    def bit_write(self, v):
        """set or clear the bit at (HL) under mask A, as the bool v says"""
        if v.kind == 'imm':
            if v.val:
                self.emit('or (hl)')
            else:
                self.emit('cpl')
                self.emit('and (hl)')
            self.emit('ld (hl),a')
            return
        clear, done = self.label(), self.label()
        self.emit('ld c,a')
        self.emit(f'ld a,({v.val})')
        self.emit('or a')
        self.emit('ld a,c')
        self.emit(f'jr z,{clear}')
        self.emit('or (hl)')
        self.emit(f'jr {done}')
        self.place(clear)
        self.emit('cpl')
        self.emit('and (hl)')
        self.place(done)
        self.emit('ld (hl),a')

    def load_bc(self, op):
        if op.kind == 'imm':
            self.emit(f'ld bc,{op.val}')
        else:
            self.emit(f'ld bc,({op.val})')

    def x_index(self, e):
        ot, line = e.obj.ty, e.line
        if e.slice:
            s = self.ex(e.obj)
            rng = e.idx[0]
            vt = rng.ty.args[0] if isinstance(rng.ty, B.Gen) else None
            if vt in (B.BYTE, B.WORD, B.INT):                # 16-bit bounds: checked inline, the 64-bit check cold
                ra, rb = self.conv(self.ex(rng.a), vt), self.conv(self.ex(rng.b), vt)
                r = self.temp(B.STR)
                back = self.label()

                def slow():                                  # the general path: fails with the exact message
                    qa, qb = self.mem(self.conv(ra, B.QUAD)), self.mem(self.conv(rb, B.QUAD))
                    self.line(line)
                    self.emit(f'ld hl,({self.addr(s)}+2)')
                    self.emit('ld b,h')
                    self.emit('ld c,l')
                    self.emit(f'ld hl,{self.addr(qa)}')
                    self.emit(f'ld de,{self.addr(qb)}')
                    self.call('bly_chk_slice64')
                    self.emit(f'ld hl,{self.addr(s)}')
                    self.emit(f'ld ix,{r.val}')
                    self.call('bly_slice')
                    self.emit(f'jp {back}')
                cold = self.cold(slow)
                self.load_hl(rb)
                self.emit('ld b,h')
                self.emit('ld c,l')
                self.load_de(ra)
                if vt is B.INT:                              # either end negative
                    self.emit('ld a,d')
                    self.emit('or b')
                    self.emit(f'jp m,{cold}')
                self.emit('ld h,b')                          # b < a
                self.emit('ld l,c')
                self.emit('or a')
                self.emit('sbc hl,de')
                self.emit(f'jp c,{cold}')
                self.emit(f'ld hl,({self.addr(s)}+2)')       # n < b
                self.emit('or a')
                self.emit('sbc hl,bc')
                self.emit(f'jp c,{cold}')
                self.emit(f'ld hl,{self.addr(s)}')
                self.emit(f'ld ix,{r.val}')
                self.call('bly_slice')
                self.place(back)
                return r
            a = self.mem(self.conv(self.ex(rng.a), B.QUAD))
            b = self.mem(self.conv(self.ex(rng.b), B.QUAD))
            self.line(line)
            self.emit(f'ld hl,({self.addr(s)}+2)')
            self.emit('ld b,h')
            self.emit('ld c,l')
            self.emit(f'ld hl,{self.addr(a)}')
            self.emit(f'ld de,{self.addr(b)}')
            self.call('bly_chk_slice64')
            r = self.temp(B.STR)
            self.emit(f'ld hl,{self.addr(s)}')
            self.emit(f'ld ix,{r.val}')
            self.call('bly_slice')
            return r
        if ot is B.STR:
            s = self.ex(e.obj)
            i = self.ex(e.idx[0])
            self.emit(f'ld bc,({self.addr(s)}+2)')
            self.check_index(i, True, line)
            self.emit(f'ld hl,({self.addr(s)})')
            self.emit('add hl,de')
            self.emit('ld a,(hl)')
            r = self.temp(B.BYTE)
            self.emit(f'ld ({r.val}),a')
            return r
        et = B.BOOL if ot.args[-1] is B.BIT else ot.args[-1]
        if ot.kind == 'array' and ot.args[0] is B.BIT:
            i = self.ex(e.idx[0])
            self.bit_ptr(e.obj, i, line)
            return self.bit_read()
        if ot.kind == 'array':
            i = self.ex(e.idx[0])
            self.array_elem_ptr(e, i, line)
            return self.get_ptr(et)
        obj = self.ex(e.obj)
        if ot.kind == 'list':
            i = self.ex(e.idx[0])
            self.emit(f'ld hl,({obj.val})')
            self.emit('ld c,(hl)')
            self.emit('inc hl')
            self.emit('ld b,(hl)')
            self.check_index(i, True, line)
            self.emit(f'ld hl,({obj.val})')
            self.call('bly_list_ref')
            return self.get_ptr(et)
        if ot.kind == 'map':
            k = self.mem(self.conv(self.ex(e.idx[0]), ot.args[0]))
            self.line(line)
            self.emit(f'ld hl,({obj.val})')
            self.emit(f'ld de,{self.addr(k)}')
            self.call('bly_map_ref')
            return self.get_ptr(et)
        if ot.kind == 'grid':
            self.grid_ptr(obj, e, line)
            return self.get_ptr(et)
        raise GenError(f'no Z80 for indexing a {ot!r}')

    def grid_ptr(self, obj, e, line):
        """HL = the address of the grid cell e indexes, checked"""
        if len(e.idx) == 2:
            r, c = self.ex(e.idx[0]), self.ex(e.idx[1])
        else:
            p = self.mem(self.ex(e.idx[0]))
            pa = self.addr(p)
            r, c = Op('mem', pa, B.INT), Op('mem', f'{pa}+2', B.INT)
        self.line(line)
        if r.ty in (B.INT, B.BYTE) and c.ty in (B.INT, B.BYTE) or (r.kind == 'imm' and c.kind == 'imm'):
            r16, c16 = self.conv(r, B.INT), self.conv(c, B.INT)
            self.load_hl(c16)
            self.emit('push hl')
            self.load_hl(r16)
            self.emit('ex de,hl')
            self.emit('pop bc')
            self.emit(f'ld hl,({obj.val})')
            self.emit('push de')
            self.emit('push bc')
            self.call('bly_grid_chk16')
            self.emit('pop bc')
            self.emit('pop de')
        else:
            rq, cq = self.mem(self.conv(r, B.QUAD)), self.mem(self.conv(c, B.QUAD))
            self.emit(f'ld hl,({obj.val})')
            self.emit(f'ld de,{self.addr(rq)}')
            self.emit(f'ld bc,{self.addr(cq)}')
            self.call('bly_grid_chk64')
            self.emit(f'ld de,({self.addr(rq)})')
            self.emit(f'ld bc,({self.addr(cq)})')
        self.emit(f'ld hl,({obj.val})')
        self.call('bly_grid_ref')

    # -- dot: fields, properties and methods ------------------------------------------------------------------------
    def x_dot(self, e):
        ot, name, line = e.obj.ty, e.name, e.line
        if e.args is None:
            if isinstance(ot, B.Gen) and ot.kind == 'array':
                _, n = self.array_base(e.obj)
                r = self.temp(B.WORD)
                self.load_hl(n) if n.kind == 'mem' else self.emit(f'ld hl,{n.val}')
                self.emit(f'ld ({r.val}),hl')
                return r
            obj = self.ex(e.obj)
            if isinstance(ot, B.RecordT):
                off, ft = field_offset(ot, name)
                return Op('mem', f'{self.addr(obj)}+{off}', ft)
            r = self.temp(e.ty)
            if ot is B.STR:
                self.emit(f'ld hl,({obj.val}+2)')
            else:
                off = {'len': {'list': 0, 'queue': 2, 'heap': 0, 'map': 2, 'set': 2}.get(ot.kind),
                       'rows': 0, 'cols': 2}[name]
                self.emit(f'ld hl,({obj.val})')
                if off:
                    self.emit(f'ld de,{off}')
                    self.emit('add hl,de')
                self.emit('ld a,(hl)')
                self.emit('inc hl')
                self.emit('ld h,(hl)')
                self.emit('ld l,a')
            self.emit(f'ld ({r.val}),hl')
            return r
        if isinstance(ot, B.Gen) and ot.kind == 'array':
            if ot.args[0] is B.BIT:
                raise GenError("sorting a bit array isn't on the Z80 yet")
            base, n = self.array_base(e.obj)
            self.load_base(base)
            self.emit('push hl')
            self.load_hl(n) if n.kind == 'mem' else self.emit(f'ld hl,{n.val}')
            self.emit('ex de,hl')
            self.emit('pop hl')
            self.emit(f'ld bc,{size(ot.args[0])}')
            self.emit(f'ld ix,{self.comparer(ot.args[0])}')
            self.call('bly_sort')
            return None
        obj = self.ex(e.obj)
        args = [self.ex(a) for a in e.args]
        if isinstance(ot, B.Gen) and ot.kind in ('list', 'queue', 'heap', 'map', 'set', 'grid'):
            el0 = B.BOOL if ot.args[0] is B.BIT else ot.args[0]
            if args:                                      # the element, or the key, as the container's type
                args[0] = self.mem(self.conv(args[0], B.POS if (ot.kind == 'grid' and e.name == 'has') else el0))
            if len(args) > 1 and ot.kind == 'map':
                args[1] = self.mem(self.conv(args[1], ot.args[1]))
        self.line(line)
        if ot is B.STR:
            sa = self.addr(obj)
            if name == 'int':
                t = e.ty
                r = self.temp(t)
                if args:
                    k = self.conv(args[0], B.QUAD) if args[0].kind != 'imm' else self.materialize(Op('imm', args[0].val, B.QUAD))
                    self.emit(f'ld hl,{sa}')
                    self.emit(f'ld bc,{k.val}')
                    self.emit(f'ld a,{TYPE_CODE[t]}')
                    self.emit(f'ld de,{r.val}')
                    self.call('bly_str_intk')
                else:
                    self.emit(f'ld hl,{sa}')
                    self.emit(f'ld a,{TYPE_CODE[t]}')
                    self.emit(f'ld de,{r.val}')
                    self.call('bly_str_int')
                return r
            if name in ('find', 'starts'):
                ta = self.text(e.args[0], args[0] if e.args[0].ty is B.BYTE else self.mem(args[0]))
                self.emit(f'ld hl,{sa}')
                self.emit(f'ld de,{ta}')
                r = self.temp(e.ty)
                if name == 'find':
                    self.call('bly_find')
                    self.emit(f'ld ({r.val}),hl')
                else:
                    self.call('bly_starts')
                    self.emit(f'ld ({r.val}),a')
                return r
            if name == 'trim':
                r = self.temp(B.STR)
                self.emit(f'ld hl,{sa}')
                self.emit(f'ld de,{r.val}')
                self.call('bly_trim')
                return r
        if ot is B.LINES:
            r = self.temp(B.STR)
            self.emit(f'ld hl,({obj.val})')
            self.emit(f'ld de,{r.val}')
            self.call('bly_lines_next')
            return r
        k = ot.kind
        el = B.BOOL if ot.args[0] is B.BIT else ot.args[0]
        if k == 'list':
            if name == 'push':
                v = self.conv(args[0], el)
                self.emit(f'ld hl,({obj.val})')
                self.emit(f'ld de,{self.addr(v)}')
                self.call('bly_list_push')
                return None
            if name == 'pop':
                r = self.temp(el)
                self.emit(f'ld hl,({obj.val})')
                self.emit(f'ld de,{r.val}')
                self.call('bly_list_pop')
                return r
            if name == 'sort':
                self.emit(f'ld hl,({obj.val})')
                self.emit(f'ld de,{self.comparer(el)}')
                self.call('bly_list_sort')
                return None
            self.emit(f'ld hl,({obj.val})')
            self.call('bly_list_clear')
            return None
        if k in ('queue', 'heap'):
            if name in ('put', 'push'):
                v = self.conv(args[0], el)
                self.emit(f'ld hl,({obj.val})')
                self.emit(f'ld de,{self.addr(v)}')
                self.call(f'bly_{k}_{name}')
                return None
            r = self.temp(el)
            self.emit(f'ld hl,({obj.val})')
            self.emit(f'ld de,{r.val}')
            self.call(f'bly_{k}_{name}')
            return r
        if k == 'map':
            key = self.conv(args[0], ot.args[0])
            if name == 'get':
                d = self.conv(args[1], ot.args[1])
                r = self.temp(ot.args[1])
                self.emit(f'ld hl,({obj.val})')
                self.emit(f'ld de,{self.addr(key)}')
                self.emit(f'ld bc,{self.addr(d)}')
                self.emit(f'ld ix,{r.val}')
                self.call('bly_map_getd')
                return r
            self.emit(f'ld hl,({obj.val})')
            self.emit(f'ld de,{self.addr(key)}')
            self.call('bly_map_del')
            return None
        if k == 'set':
            key = self.conv(args[0], ot.args[0])
            self.emit(f'ld hl,({obj.val})')
            self.emit(f'ld de,{self.addr(key)}')
            self.call('bly_map_put' if name == 'add' else 'bly_map_del')
            return None
        if k == 'grid':
            if name == 'has':
                r = self.temp(B.BOOL)
                self.emit(f'ld hl,({obj.val})')
                self.emit(f'ld de,{self.addr(args[0])}')
                self.call('bly_grid_has')
                self.emit(f'ld ({r.val}),a')
                return r
            v = self.conv(args[0], el)
            r = self.temp(B.POS)
            self.emit(f'ld hl,({obj.val})')
            self.emit(f'ld de,{self.addr(v)}')
            self.emit(f'ld bc,{r.val}')
            self.call('bly_grid_find')
            return r
        raise GenError(f'no Z80 for .{name}() on a {ot!r}')

    def text(self, a, v):
        """a text argument (a byte or a str) as the address of a str"""
        if a.ty is B.BYTE:
            r = self.temp(B.STR)
            self.load_a(v)
            self.emit(f'ld de,{r.val}')
            self.call('bly_chr')
            return r.val
        return self.addr(v)

    # -- making things ---------------------------------------------------------------------------------------------
    def x_new(self, e):
        t, line = e.ty, e.line
        args = [self.ex(a) for a in e.args]
        self.line(line)
        if t.kind == 'grid':
            et = B.BOOL if t.args[0] is B.BIT else t.args[0]
            blk = self.temp(None, 24) if False else Op('mem', self.slot(None, 24), B.WORD)
            rows, cols = self.conv(args[0], B.QUAD), self.conv(args[1], B.QUAD)
            self.put(blk.val, rows, B.QUAD)
            self.put(f'{blk.val}+8', cols, B.QUAD)
            fill = self.conv(args[2], et) if len(args) == 3 else Op('imm', 0, et)
            fill = self.materialize(fill) if fill.kind == 'imm' else fill
            self.store_imm(f'{blk.val}+16', size(et), 2)
            self.emit(f'ld hl,{self.comparer(et)}')
            self.emit(f'ld ({blk.val}+18),hl')
            self.emit(f'ld hl,{self.printer(et)}')
            self.emit(f'ld ({blk.val}+20),hl')
            self.emit(f'ld hl,{fill.val}')
            self.emit(f'ld ({blk.val}+22),hl')
            self.emit(f'ld hl,{blk.val}')
            self.call('bly_grid_new')
        else:
            cap = self.conv(args[0], B.QUAD) if args[0].kind != 'imm' else Op('imm', args[0].val, B.QUAD)
            blk = Op('mem', self.slot(None, 16), B.WORD)
            self.put(blk.val, cap, B.QUAD)
            el = B.BOOL if t.args[0] is B.BIT else t.args[0]
            if t.kind in ('map', 'set'):
                vs = size(t.args[1]) if t.kind == 'map' else 0
                self.store_imm(f'{blk.val}+8', size(el), 2)
                self.store_imm(f'{blk.val}+10', vs, 2)
                self.emit(f'ld hl,{self.printer(el)}')
                self.emit(f'ld ({blk.val}+12),hl')
                self.store_imm(f'{blk.val}+14', 0 if t.kind == 'map' else 1, 1)
                self.emit(f'ld hl,{blk.val}')
                self.call('bly_map_new')
            else:
                self.store_imm(f'{blk.val}+8', size(el), 2)
                if t.kind == 'heap':
                    self.emit(f'ld hl,{self.comparer(el)}')
                    self.emit(f'ld ({blk.val}+10),hl')
                self.emit(f'ld hl,{blk.val}')
                self.call(f'bly_{t.kind}_new')
        r = self.temp(t)
        self.emit(f'ld ({r.val}),hl')
        return r

    def x_call(self, e):
        line = e.line
        if hasattr(e, 'func'):
            f = e.func
            arg_start = len(self.temps)
            args = [self.conv(self.ex(a), pt) for a, pt in zip(e.args, f.ptys)]
            caller = self.func.name if self.func else None
            if caller == f.name:
                args = [self.snap(a) for a in args]
            mine = (arg_start, len(self.temps))               # consumed by this call: dead once it's made
            save = caller is not None and self.scc.get(caller) == self.scc.get(f.name) and \
                (caller != f.name or f.name in self.edges[f.name])
            saved = []
            if save:                                          # the save rule: live after, and the callee can reach it
                for a, n in self.coalesce(self.live_slots(self.dead_args + [mine])):
                    for k in range(0, n, 2):
                        if n - k >= 2:
                            self.emit(f'ld hl,({a}+{k})')
                            self.emit('push hl')
                        else:
                            self.emit(f'ld a,({a}+{k})')
                            self.emit('push af')
                        saved.append((a, k, n - k >= 2))
            off = 0
            for a, pt in zip(args, f.ptys):
                if isinstance(pt, B.Gen) and pt.kind == 'array':
                    self.pass_array(a, f'fr_{f.name}+{off}')
                else:
                    self.put(f'fr_{f.name}+{off}', a, pt)
                off += max(size(pt), 1)
            self.emit(f'call f_{f.name}')
            self.dead_args.append(mine)
            self.cur_line = None
            for a, k, word in reversed(saved):
                self.emit('pop hl' if word else 'pop af')
                self.emit(f'ld ({a}+{k}),hl' if word else f'ld ({a}+{k}),a')
            if f.rty is B.VOID:
                return None
            r = self.temp(f.rty)
            self.copy(r.val, f'rv_{f.name}', size(f.rty))
            return r
        if hasattr(e, 'record'):
            rt = e.record
            r = self.temp(rt)
            vals = [self.conv(self.ex(a), ft) for a, (_, ft) in zip(e.args, rt.fields)]
            off = 0
            for v, (_, ft) in zip(vals, rt.fields):
                self.put(f'{r.val}+{off}', v, ft)
                off += size(ft)
            return r
        if hasattr(e, 'cast'):
            a = self.ex(e.args[0])
            to = e.cast
            if to is B.BOOL:
                r = self.temp(B.BOOL)
                a = self.materialize(a) if a.kind == 'imm' else a
                self.emit('xor a')
                for k in range(size(a.ty)):
                    self.emit(f'ld hl,{a.val}+{k}')
                    self.emit('or (hl)')
                end = self.label()
                self.emit(f'jr z,{end}')
                self.emit('ld a,1')
                self.place(end)
                self.emit(f'ld ({r.val}),a')
                return r
            if to is B.FLOAT or a.ty is B.FLOAT:
                return self.float_cast(a, to, line)
            if a.kind == 'imm':
                return Op('imm', B.wrap(a.val, to), to)
            if a.ty is B.BOOL:
                a = Op(a.kind, a.val, B.BYTE)
            if size(to) <= size(a.ty):
                r = self.temp(to)
                self.copy(r.val, a.val, size(to))
                return r
            return self.conv(a, to)
        name = e.builtin
        args = [self.ex(a) for a in e.args]
        t = e.ty
        self.line(line)
        if name in B.SCREEN_FUNCS:
            if self.target != 'zx48':
                raise GenError(f'{name}() is Spectrum-only: put it inside if ZX then ... end')
            return self.screen_call(name, args)
        if name in B.MACHINE_FUNCS:
            if self.target != 'zx48':
                raise GenError(f'{name}() is Spectrum-only: put it inside if ZX then ... end')
            return self.machine_call(name, args, line)
        if name in B.FLOAT_FUNCS or name in ('abs', 'sign') and args[0].ty is B.FLOAT:
            return self.float_fn(name, args[0], t, line)
        if name == 'lines':
            self.uses_input = True
            self.call('bly_lines_new')
            r = self.temp(B.LINES)
            self.emit(f'ld ({r.val}),hl')
            return r
        if name == 'input':
            self.uses_input = True
            r = self.temp(B.STR)
            self.emit(f'ld de,{r.val}')
            self.call('bly_input')
            return r
        if name == 'ask':                                   # zxask.asm on the 48K, cpmask.asm on CP/M
            p = self.mem(args[0]) if args else self.materialize(Op('imm', 0, B.LONG))     # no prompt: an empty str
            r = self.temp(B.STR)
            self.emit(f'ld hl,{self.addr(p)}')
            self.emit(f'ld de,{r.val}')
            self.call('bly_ask')
            return r
        if name == 'grid':
            self.uses_input = True
            self.call('bly_grid_input')
            r = self.temp(t)
            self.emit(f'ld ({r.val}),hl')
            return r
        if name == 'intern':
            args[0] = self.mem(args[0])
            self.emit(f'ld hl,{self.addr(args[0])}')
            self.call('bly_intern')
            r = self.temp(B.WORD)
            self.emit(f'ld ({r.val}),hl')
            return r
        if name == 'name':
            r = self.temp(B.STR)
            self.load_hl(self.conv(args[0], B.WORD))
            self.emit(f'ld de,{r.val}')
            self.call('bly_name')
            return r
        if name == 'chr':
            r = self.temp(B.STR)
            self.load_a(args[0])
            self.emit(f'ld de,{r.val}')
            self.call('bly_chr')
            return r
        if name in ('min', 'max'):
            r = self.temp(t)
            first = self.conv(args[0], t)
            self.put(r.val, first, t)
            for a in args[1:]:
                a = self.conv(a, t)
                skip = self.label()
                self.cmp_jump('<' if name == 'min' else '>', a, r, t, skip, False, line)
                self.put(r.val, a, t)
                self.place(skip)
            return r
        if name == 'sign':
            a = self.conv(args[0], t)
            r = self.temp(t)
            z = self.compare('>', a, Op('imm', 0, t), t, line)
            n = self.compare('<', a, Op('imm', 0, t), t, line)
            self.load_a(z)
            self.emit('ld b,a')
            self.load_a(n)
            self.emit('ld c,a')
            self.emit('ld a,b')
            self.emit('sub c')                              # 1, 0 or -1
            self.emit('ld l,a')
            self.emit('rla')
            self.emit('sbc a,a')
            self.emit('ld h,a')
            for k in range(size(t)):
                self.emit(f'ld a,{"l" if k == 0 else "h"}')
                self.emit(f'ld ({r.val}+{k}),a')
            return r
        if name == 'abs' and t in (B.BYTE, B.WORD, B.DWORD):    # unsigned: already its own size
            return self.conv(args[0], t)
        if name == 'abs' and t is B.INT:                    # a sign test, and a checked negate
            a = self.conv(args[0], t)
            r, done = self.temp(t), self.label()
            self.load_hl(a)
            self.emit('bit 7,h')
            self.emit(f'jr z,{done}')
            self.emit('ex de,hl')
            self.emit('ld hl,0')
            self.emit('or a')
            self.emit('sbc hl,de')
            self.fail_jp('pe', 'bly_ovf_int', line)
            self.place(done)
            self.emit(f'ld ({r.val}),hl')
            return r
        if name == 'abs' and t is B.LONG:                   # the sign byte decides: a copy, or the checked negate
            a = self.mem(self.conv(args[0], t))
            r, neg, done = self.temp(t), self.label(), self.label()
            self.emit(f'ld a,({self.addr(a)}+3)')
            self.emit('rla')
            self.emit(f'jr c,{neg}')
            self.copy(r.val, self.addr(a), 4)
            self.emit(f'jr {done}')
            self.place(neg)
            self.line(line)
            self.emit(f'ld hl,{self.addr(a)}')
            self.emit(f'ld bc,{r.val}')
            self.call('bly_neg_i32')
            self.place(done)
            return r
        if name in ('abs', 'gcd', 'lcm', 'mod'):
            qs = [self.conv(a, B.QUAD) if a.kind != 'imm' else self.materialize(Op('imm', a.val, B.QUAD)) for a in args]
            q = self.temp(B.QUAD)
            self.emit(f'ld hl,{qs[0].val}')
            if len(qs) > 1:
                self.emit(f'ld de,{qs[1].val}')
            self.emit(f'ld bc,{q.val}')
            self.call(f'bly_{name}_i64')
            r = self.temp(t)
            self.emit(f'ld hl,{q.val}')
            self.emit(f'ld a,{TYPE_CODE[t]}')
            self.emit(f'ld de,{r.val}')
            self.call('bly_fit_i64')
            return r
        raise GenError(f'no Z80 for {name}()')

    def float_cast(self, a, to, line):
        """float(x) from any integer type (or a bool), and the integer types from a float: truncating, and
        checked by bly_f_to_int ({x} doesn't fit in a {type})"""
        size(B.FLOAT)                                   # (on CP/M: floats aren't here)
        frm = B.BYTE if a.ty in (B.BOOL, B.BIT) else a.ty
        if to is B.FLOAT and frm is B.FLOAT:
            return a
        if to is B.FLOAT:
            if a.kind == 'imm':
                return Op('imm', int(a.val), B.FLOAT)    # exact: rom5 rounds the int itself
            r = self.temp(B.FLOAT)
            if frm in (B.BYTE, B.WORD, B.INT):
                self.load_hl(Op(a.kind, a.val, frm))
                self.emit(f'ld bc,{r.val}')
                self.call('bly_f_from_i16' if frm is B.INT else 'bly_f_from_u16')
            else:
                q = self.conv(Op(a.kind, a.val, frm), B.QUAD)
                self.emit(f'ld hl,{q.val}')
                self.emit(f'ld bc,{r.val}')
                self.call('bly_f_from_i64')
            return r
        a = self.mem(a)
        r = self.temp(to)
        self.line(line)
        self.emit(f'ld hl,{self.addr(a)}')
        self.emit(f'ld a,{TYPE_CODE[to]}')
        self.emit(f'ld de,{r.val}')
        self.call('bly_f_to_int')
        return r

    def float_fn(self, name, a, t, line):
        """sqrt and its friends, abs and sign of a float: ABI.md section 11"""
        a = self.mem(a)
        if name == 'sign':                               # bly_fcmp against 0 is the sign, as a byte: FFh, 0, 1
            z = self.materialize(Op('imm', 0.0, B.FLOAT))
            r = self.temp(t)
            self.emit(f'ld hl,{self.addr(a)}')
            self.emit(f'ld de,{z.val}')
            self.call('bly_fcmp')
            self.emit('ld l,a')
            self.emit('rla')
            self.emit('sbc a,a')
            self.emit('ld h,a')
            self.emit(f'ld ({r.val}),hl')
            return r
        r = self.temp(B.FLOAT)
        self.emit(f'ld hl,{self.addr(a)}')
        self.emit(f'ld bc,{r.val}')
        self.call('bly_f' + name)
        return r

    def to_bool_a(self, op):
        """A = 1 if op is true (a bool) or nonzero (a number), else 0"""
        if op.ty in (B.BOOL, B.BIT):
            self.load_a(op)
            return
        if op.kind == 'imm':
            self.emit(f'ld a,{1 if op.val else 0}')
            return
        self.emit('xor a')
        for k in range(size(op.ty)):
            self.emit(f'ld hl,{op.val}+{k}')
            self.emit('or (hl)')
        end = self.label()
        self.emit(f'jr z,{end}')
        self.emit('ld a,1')
        self.place(end)

    def machine_call(self, name, args, line):
        """peek, poke, inp and outp: the address or port checked as an index is (unless its type can't hold one out
        of range), then one LD, IN or OUT. A constant address needs nothing: poke(23692, 255) is ld a,255 / ld
        (23692),a"""
        v = self.conv(args[1], B.BYTE) if len(args) > 1 else None      # first, as converting may use HL
        a, port = args[0], name in ('inp', 'outp')
        if a.kind == 'imm' and 0 <= a.val <= 65535:
            if name == 'peek':
                self.emit(f'ld a,({a.val})')
            elif name == 'poke':
                self.load_a(v)
                self.emit(f'ld ({a.val}),a')
            else:
                self.emit(f'ld bc,{a.val}')
        else:
            if a.kind != 'imm' and a.ty in (B.BYTE, B.WORD):
                self.load_hl(a)
            elif a.kind != 'imm' and a.ty is B.INT:
                self.load_de(a)
                self.emit('bit 7,d')
                self.fail_jp('nz', f'bly_fail_{"port" if port else "addr"}_i16', line)
                self.emit('ex de,hl')
            else:
                q = self.conv(a, B.QUAD) if a.kind != 'imm' else self.materialize(Op('imm', a.val, B.QUAD))
                self.line(line)
                self.emit(f'ld hl,{q.val}')
                self.emit(f'ld a,{int(port)}')
                self.call('bly_zx_addr64')
            if name == 'peek':
                self.emit('ld a,(hl)')
            elif name == 'poke':
                self.load_a(v)
                self.emit('ld (hl),a')
            else:
                self.emit('ld b,h')
                self.emit('ld c,l')
        if name == 'inp':
            self.emit('in a,(c)')
        elif name == 'outp':
            self.load_a(v)
            self.emit('out (c),a')
        if name in ('peek', 'inp'):
            r = self.temp(B.BYTE)
            self.emit(f'ld ({r.val}),a')
            return r
        return None

    def screen_call(self, name, args):
        """the Spectrum's screen and sound (ABI.md section 10)"""
        ints = lambda i: self.conv(args[i], B.INT)
        routine = 'bly_zx_' + name
        if name == 'cls':
            self.call(routine)
        elif name in ('ink', 'paper', 'border', 'pause'):
            self.load_hl(ints(0))
            self.call(routine)
        elif name in ('bright', 'flash'):                # 0, 1 or 8 (true and false are 1 and 0), checked there
            if args[0].ty in (B.BOOL, B.BIT):
                self.to_bool_a(args[0])
                self.emit('ld l,a')
                self.emit('ld h,0')
            else:
                self.load_hl(ints(0))
            self.call(routine)
        elif name in ('inverse', 'over'):
            self.to_bool_a(args[0])
            self.call(routine)
        elif name in ('plot', 'point'):
            x, y = ints(0), ints(1)
            self.load_hl(y)
            self.emit('ex de,hl')
            self.load_hl(x)
            self.call(routine)
            if name == 'point':
                r = self.temp(B.BOOL)
                self.emit(f'ld ({r.val}),a')
                return r
        elif name in ('line', 'circle'):
            vals = [ints(i) for i in range(len(args))]
            blk = self.slot(None, 2 * len(vals))
            for i, v in enumerate(vals):
                self.put(f'{blk}+{2 * i}', v, B.INT)
            self.emit(f'ld hl,{blk}')
            self.call(routine)
        elif name == 'attr' and len(args) == 2:          # attr(r, c) reads a square back
            r, c = ints(0), ints(1)
            self.load_hl(c)
            self.emit('ex de,hl')
            self.load_hl(r)
            self.call('bly_zx_attr_read')
            t = self.temp(B.BYTE)
            self.emit(f'ld ({t.val}),a')
            return t
        elif name == 'attr':
            r, c, a = ints(0), ints(1), self.conv(args[2], B.BYTE)
            self.load_a(a)
            self.emit('ld c,a')
            self.load_hl(c)
            self.emit('ex de,hl')
            self.load_hl(r)
            self.call(routine)
        elif name == 'fzx':                              # the font: a constant table's address (zxfzx.asm)
            view = self.slot(None, 4)
            self.pass_array(args[0], view)
            self.emit(f'ld hl,({view})')
            self.call(routine)
        elif name == 'udg':
            view = self.slot(None, 4)
            self.pass_array(args[1], view)
            self.load_hl(ints(0))
            self.emit(f'ld de,{view}')
            self.call(routine)
        elif name in ('key', 'inkey'):
            self.call(routine)
            r = self.temp(B.BYTE)
            self.emit(f'ld ({r.val}),a')
            return r
        elif name == 'ticks':
            r = self.temp(B.LONG)
            self.emit(f'ld de,{r.val}')
            self.call(routine)
            return r
        elif name == 'beep':
            ms, st = ints(0), ints(1)
            self.load_hl(st)
            self.emit('ex de,hl')
            self.load_hl(ms)
            self.call(routine)
        return None

    def pass_array(self, a, dst):
        """an array argument: a view (address, length) in the parameter's 4 bytes"""
        if a.ty.n is None:                                      # passing a view on: copy it
            self.copy(dst, a.val, 4)
            return
        self.emit(f'ld hl,{a.val}')
        self.emit(f'ld ({dst}),hl')
        self.emit(f'ld hl,{a.ty.n}')
        self.emit(f'ld ({dst}+2),hl')

    def x_range(self, e):
        raise GenError('a range is walked by for, or slices a str')

    # -- assignment ------------------------------------------------------------------------------------------------
    def locate(self, e):
        """(read, write) makers for a target, its parts evaluated now, left to right (the interpreter's order)"""
        line = e.line
        t = e.ty
        if e.k == 'name':
            a = self.var_addr(e)
            return (lambda: self.copy_to_temp(a, t)), (lambda v: self.put(a, v, t))
        if e.k == 'dot':
            off, ft = field_offset(e.obj.ty, e.name)
            ptr = self.locate_ptr(e.obj)
            return ((lambda: (ptr(), self.add_hl(off), self.get_ptr(ft))[-1]),
                    (lambda v: (ptr(), self.add_hl(off), self.put_ptr(None, v, ft))))
        ptr = self.locate_ptr(e)
        if e.k == 'index' and e.obj.ty.kind == 'array' and e.obj.ty.args[0] is B.BIT:
            i = self.ex(e.idx[0])
            return ((lambda: (self.bit_ptr(e.obj, i, line), self.bit_read())[-1]),
                    (lambda v: (self.bit_ptr(e.obj, i, line), self.bit_write(v))))
        if e.k == 'index' and e.obj.ty.kind == 'map':
            obj, key = self._last_map
            et = e.obj.ty.args[1]

            def wr(v):
                v = self.materialize(v) if v.kind == 'imm' else v
                self.line(line)
                self.emit(f'ld hl,({obj.val})')
                self.emit(f'ld de,{self.addr(key)}')
                self.emit(f'ld bc,{v.val}')
                self.call('bly_map_put')
            return (lambda: (ptr(), self.get_ptr(et))[-1]), wr
        return (lambda: (ptr(), self.get_ptr(t))[-1]), (lambda v: (ptr(), self.put_ptr(None, v, t)))

    def add_hl(self, off):
        if off:
            self.emit(f'ld de,{off}')
            self.emit('add hl,de')

    def copy_to_temp(self, a, t):
        r = self.temp(t)
        self.copy(r.val, a, size(t))
        return r

    def locate_ptr(self, e):
        """evaluate a target's parts now; return a maker that emits, later, a checked HL = its address"""
        line = e.line
        if e.k == 'name':
            a = self.var_addr(e)
            return lambda: self.emit(f'ld hl,{a}')
        if e.k == 'dot':
            off, _ = field_offset(e.obj.ty, e.name)
            inner = self.locate_ptr(e.obj)
            return lambda: (inner(), self.add_hl(off))
        if e.k == 'index':
            ot = e.obj.ty
            if ot.kind == 'array':
                i = self.ex(e.idx[0])
                return lambda: self.array_elem_ptr(e, i, line)
            obj = self.ex(e.obj)
            if ot.kind == 'list':
                i = self.ex(e.idx[0])

                def mk():
                    self.emit(f'ld hl,({obj.val})')
                    self.emit('ld c,(hl)')
                    self.emit('inc hl')
                    self.emit('ld b,(hl)')
                    self.check_index(i, True, line)
                    self.emit(f'ld hl,({obj.val})')
                    self.call('bly_list_ref')
                return mk
            if ot.kind == 'map':
                key = self.mem(self.conv(self.ex(e.idx[0]), ot.args[0]))
                self._last_map = (obj, key)

                def mk():
                    self.line(line)
                    self.emit(f'ld hl,({obj.val})')
                    self.emit(f'ld de,{self.addr(key)}')
                    self.call('bly_map_ref')
                return mk
            if ot.kind == 'grid':
                parts = [self.ex(x) for x in e.idx]
                fake = B.N('index', line, obj=e.obj, idx=e.idx)

                def mk():
                    self.grid_ptr_from(obj, parts, line)
                return mk
        raise GenError(f"can't assign to {e.k}")

    def grid_ptr_from(self, obj, parts, line):
        if len(parts) == 2:
            r, c = parts
        else:
            pa = self.addr(self.mem(parts[0]))
            r, c = Op('mem', pa, B.INT), Op('mem', f'{pa}+2', B.INT)
        e = B.N('index', line, obj=None, idx=[])
        self._grid_rc(obj, r, c, line)

    def _grid_rc(self, obj, r, c, line):
        self.line(line)
        if r.ty in (B.INT, B.BYTE) and c.ty in (B.INT, B.BYTE):
            r16, c16 = self.conv(r, B.INT), self.conv(c, B.INT)
            self.load_hl(c16)
            self.emit('push hl')
            self.load_hl(r16)
            self.emit('ex de,hl')
            self.emit('pop bc')
            self.emit(f'ld hl,({obj.val})')
            self.emit('push de')
            self.emit('push bc')
            self.call('bly_grid_chk16')
            self.emit('pop bc')
            self.emit('pop de')
        else:
            rq, cq = self.mem(self.conv(r, B.QUAD)), self.mem(self.conv(c, B.QUAD))
            self.emit(f'ld hl,({obj.val})')
            self.emit(f'ld de,{self.addr(rq)}')
            self.emit(f'ld bc,{self.addr(cq)}')
            self.call('bly_grid_chk64')
            self.emit(f'ld de,({self.addr(rq)})')
            self.emit(f'ld bc,({self.addr(cq)})')
        self.emit(f'ld hl,({obj.val})')
        self.call('bly_grid_ref')

    def assign(self, s):
        rd, wr = self.locate(s.target)
        tt = s.target.ty
        if s.op is None:
            v = self.conv(self.ex(s.e), tt)
        else:
            old = rd()
            r = self.ex(s.e)
            v = self.conv(self.binop(s.opnode, old, r), tt)
        small = v.kind == 'imm' and size(tt) <= 2 and tt in (B.BYTE, B.WORD, B.INT, B.BOOL, B.BIT)
        wr(v if small or v.kind != 'imm' else self.materialize(v, tt))

    # -- for -------------------------------------------------------------------------------------------------------
    def loop_enter(self, labels, s, m0):
        self.loops.append(labels)
        self.loop_stmts.append(s)
        self.machinery.append((m0, self.fsize))

    def loop_exit(self):
        self.loops.pop()
        self.loop_stmts.pop()
        self.machinery.pop()

    def for_(self, s):
        it, t, line = s.it, s.it.ty, s.line
        names, vts = s.names, s.vtys
        m0 = self.fsize
        v0 = self.slot(vts[0])
        self.locals[names[0]] = v0
        self.lsize[names[0]] = max(size(vts[0]), 1)
        top, cont, end = self.label(), self.label(), self.label()
        if isinstance(t, B.Gen) and t.kind == 'range':
            rng = it.args[0] if it.k == 'call' else it
            vt = t.args[0]
            lo = self.conv(self.ex(rng.a), vt)
            hi = self.conv(self.ex(rng.b), vt)
            if size(vt) > 2:                                  # the library compares wide numbers in memory
                lo = self.materialize(lo) if lo.kind == 'imm' else lo
                hi = self.materialize(hi) if hi.kind == 'imm' else hi
            lo, hi = self.snap(lo), self.snap(hi)            # held across the body: the body can't move the bounds
            vop = Op('mem', v0, vt)
            if rng.rev:
                self.put(v0, hi, vt)
                self.place(top)
                self.cmp_jump('>', vop, lo, vt, end, False, line)
                self.step(vop, vt, -1)
                self.loop_enter((top, end), s, m0)
                self.block(s.body)
                self.loop_exit()
                self.emit(f'jp {top}')
                self.place(end)
                return
            self.put(v0, lo, vt)
            self.place(top)
            self.cmp_jump('<', vop, hi, vt, end, False, line)
            self.loop_enter((cont, end), s, m0)
            self.block(s.body)
            self.loop_exit()
            self.place(cont)
            self.step(vop, vt, 1)
            self.emit(f'jp {top}')
            self.place(end)
            return
        if isinstance(t, B.Gen) and t.kind == 'array' or t is B.STR:
            if t is B.STR:
                sv = self.snap(self.ex(it))
                base, n, es = ('ptr_at', sv.val), Op('mem', f'{sv.val}+2', B.WORD), 1
            else:
                base, n = self.array_base(it)
                es = size(t.args[0])
            bits = t is not B.STR and t.args[0] is B.BIT
            i = self.slot(B.WORD)
            self.store_imm(i, 0, 2)
            self.place(top)
            self.emit(f'ld hl,({i})')
            self.emit('ex de,hl')
            self.load_hl(n) if n.kind == 'mem' else self.emit(f'ld hl,{n.val}')
            self.emit('scf')
            self.emit('sbc hl,de')                           # n - i - 1 < 0: done
            self.emit(f'jp c,{end}')
            self.emit(f'ld de,({i})')
            if bits:                                          # the i-th bit, as a bool
                self.bit_addr(base)
                r = self.bit_read()
                self.copy(v0, r.val, 1)
            else:
                self.load_base(base)
                self.elem_addr(None, es)
                self.emit(f'ld de,{v0}')
                self.emit(f'ld bc,{es}')
                self.emit('ldir')
            self.loop_enter((cont, end), s, m0)
            self.block(s.body)
            self.loop_exit()
            self.place(cont)
            self.emit(f'ld hl,({i})')
            self.emit('inc hl')
            self.emit(f'ld ({i}),hl')
            self.emit(f'jp {top}')
            self.place(end)
            return
        if t is B.LINES:
            lv = self.snap(self.ex(it))
            self.uses_input = True
            self.place(top)
            self.emit(f'ld hl,({lv.val})')
            self.emit(f'ld de,{v0}')
            self.helpers.setdefault('bly_lines_more', LINES_MORE)
            self.calls.update(['bly_lns', 'bly_nln'])
            self.emit('call bly_lines_more')
            self.emit('or a')
            self.emit(f'jp z,{end}')
            self.loop_enter((top, end), s, m0)
            self.block(s.body)
            self.loop_exit()
            self.emit(f'jp {top}')
            self.place(end)
            return
        if isinstance(t, B.Gen) and t.kind == 'iter':
            obj = self.snap(self.mem(self.ex(it.obj)))
            st = self.slot(None, 16)
            if it.name == 'ints':
                self.emit(f'ld hl,{st}')
                self.emit(f'ld de,{self.addr(obj)}')
                self.call('bly_ints_init')
                self.place(top)
                self.emit(f'ld hl,{st}')
                self.call('bly_ints_next')
                self.emit('or a')
                self.emit(f'jp z,{end}')
                self.line(line)
                self.emit(f'ld hl,{st}')
                self.emit(f'ld a,{TYPE_CODE[vts[0]]}')
                self.emit(f'ld de,{v0}')
                self.call('bly_ints_val')
            else:
                sep = self.text(it.args[0], self.ex(it.args[0]))
                self.line(line)
                self.emit(f'ld hl,{st}')
                self.emit(f'ld de,{self.addr(obj)}')
                self.emit(f'ld bc,{sep}')
                self.call('bly_split_init')
                self.place(top)
                self.emit(f'ld hl,{st}')
                self.emit(f'ld de,{v0}')
                self.call('bly_split_next')
                self.emit('or a')
                self.emit(f'jp z,{end}')
            self.loop_enter((top, end), s, m0)
            self.block(s.body)
            self.loop_exit()
            self.emit(f'jp {top}')
            self.place(end)
            return
        if isinstance(t, B.Gen) and t.kind == 'grid':
            g = self.snap(self.ex(it))
            r, c = self.slot(B.INT), self.slot(B.INT)
            self.store_imm(r, 0, 2)
            self.store_imm(c, 0, 2)
            self.place(top)
            self.emit(f'ld hl,({g.val})')                   # rows, cols
            self.emit('ld e,(hl)')
            self.emit('inc hl')
            self.emit('ld d,(hl)')
            self.emit(f'ld hl,({r})')
            self.emit('or a')
            self.emit('sbc hl,de')
            self.emit(f'jp nc,{end}')
            self.emit(f'ld hl,({g.val})')
            self.emit('inc hl')
            self.emit('inc hl')
            self.emit('ld e,(hl)')
            self.emit('inc hl')
            self.emit('ld d,(hl)')
            self.emit('ld a,d')
            self.emit('or e')
            self.emit(f'jp z,{end}')                         # no columns: nothing to walk
            self.copy(v0, r, 2)
            self.copy(f'{v0}+2', c, 2)
            self.loop_enter((cont, end), s, m0)
            self.block(s.body)
            self.loop_exit()
            self.place(cont)
            self.emit(f'ld hl,({c})')
            self.emit('inc hl')
            self.emit(f'ld ({c}),hl')
            self.emit(f'ld hl,({g.val})')
            self.emit('inc hl')
            self.emit('inc hl')
            self.emit('ld e,(hl)')
            self.emit('inc hl')
            self.emit('ld d,(hl)')
            self.emit(f'ld hl,({c})')
            self.emit('or a')
            self.emit('sbc hl,de')
            self.emit(f'jp c,{top}')
            self.store_imm(c, 0, 2)
            self.emit(f'ld hl,({r})')
            self.emit('inc hl')
            self.emit(f'ld ({r}),hl')
            self.emit(f'jp {top}')
            self.place(end)
            return
        if isinstance(t, B.Gen) and t.kind in ('list', 'queue', 'map', 'set'):
            cv = self.snap(self.ex(it))
            i, ver = self.slot(B.WORD), self.slot(B.WORD)
            vo = {'list': 4, 'queue': 6, 'map': 6, 'set': 6}[t.kind]
            self.emit(f'ld hl,({cv.val})')
            self.add_hl(vo)
            self.emit('ld a,(hl)')
            self.emit('inc hl')
            self.emit('ld h,(hl)')
            self.emit('ld l,a')
            self.emit(f'ld ({ver}),hl')
            self.store_imm(i, 0, 2)
            self.place(top)
            self.line(line)
            self.emit(f'ld hl,({cv.val})')                  # changed under the walk?
            self.add_hl(vo)
            self.emit('ld a,(hl)')
            self.emit('inc hl')
            self.emit('ld h,(hl)')
            self.emit('ld l,a')
            self.emit(f'ld de,({ver})')
            self.emit('or a')
            self.emit('sbc hl,de')
            ok = self.label()
            self.emit(f'jr z,{ok}')
            self.emit(f'ld a,{KIND_CODE[t.kind]}')
            self.jp('bly_changed')
            self.place(ok)
            no = {'list': 0, 'queue': 2, 'map': 0, 'set': 0}[t.kind]   # n, or ne for maps
            self.emit(f'ld hl,({cv.val})')
            self.add_hl(no)
            self.emit('ld e,(hl)')
            self.emit('inc hl')
            self.emit('ld d,(hl)')
            self.emit(f'ld hl,({i})')
            self.emit('or a')
            self.emit('sbc hl,de')
            self.emit(f'jp nc,{end}')
            if t.kind in ('map', 'set'):
                self.emit(f'ld hl,({cv.val})')               # alive[i]?
                self.add_hl(18)
                self.emit('ld e,(hl)')
                self.emit('inc hl')
                self.emit('ld d,(hl)')
                self.emit(f'ld hl,({i})')
                self.emit('add hl,de')
                self.emit('ld a,(hl)')
                self.emit('or a')
                self.emit(f'jp z,{cont}')
                for which, dst, vt, hoff in ((0, v0, vts[0], 14),) + (((1, None, vts[1], 16),) if len(names) == 2 else ()):
                    if which == 1:
                        dst = self.slot(vt)
                        self.locals[names[1]] = dst
                        self.lsize[names[1]] = max(size(vt), 1)
                    self.emit(f'ld hl,({cv.val})')
                    self.add_hl(hoff)
                    self.emit('ld e,(hl)')
                    self.emit('inc hl')
                    self.emit('ld d,(hl)')
                    self.emit('push de')
                    self.emit(f'ld de,({i})')
                    self.emit('pop hl')
                    self.elem_addr(None, size(vt))
                    self.emit(f'ld de,{dst}')
                    self.emit(f'ld bc,{size(vt)}')
                    self.emit('ldir')
            else:
                self.emit(f'ld de,({i})')
                self.emit(f'ld hl,({cv.val})')
                self.call('bly_list_ref' if t.kind == 'list' else 'bly_queue_at')
                self.emit(f'ld de,{v0}')
                self.emit(f'ld bc,{size(vts[0])}')
                self.emit('ldir')
            self.loop_enter((cont, end), s, m0)
            self.block(s.body)
            self.loop_exit()
            self.place(cont)
            self.emit(f'ld hl,({i})')
            self.emit('inc hl')
            self.emit(f'ld ({i}),hl')
            self.emit(f'jp {top}')
            self.place(end)
            return
        raise GenError(f'no Z80 for walking a {t!r}')

    def step(self, vop, vt, d):
        """the loop variable += d, where it can't overflow"""
        if size(vt) == 1:
            self.emit(f'ld hl,{vop.val}')
            self.emit('inc (hl)' if d > 0 else 'dec (hl)')
        elif size(vt) == 2:
            self.emit(f'ld hl,({vop.val})')
            self.emit('inc hl' if d > 0 else 'dec hl')
            self.emit(f'ld ({vop.val}),hl')
        else:
            one = self.materialize(Op('imm', d, vt))
            n = {B.LONG: 'i32', B.QUAD: 'i64', B.DWORD: 'u32'}[vt]
            self.emit(f'ld hl,{vop.val}')
            self.emit(f'ld de,{one.val}')
            self.emit(f'ld bc,{vop.val}')
            self.call(f'bly_add_{n}')


LINES_MORE = ['bly_lines_more:                     ; HL = a lines iterator, DE = &dest: A = 1 and the next line, or 0',
              '        push de', '        ld e,(hl)', '        inc hl', '        ld d,(hl)',
              '        push hl', '        ld hl,(bly_nln)', '        or a', '        sbc hl,de', '        pop hl',
              '        jr nz,.more', '        pop de', '        xor a', '        ret',
              '.more:  inc de', '        ld (hl),d', '        dec hl', '        ld (hl),e', '        dec de',
              '        ex de,hl', '        add hl,hl', '        add hl,hl', '        ld de,(bly_lns)', '        add hl,de',
              '        pop de', '        ld bc,4', '        ldir', '        ld a,1', '        ret']

COUNT64 = ['bly_count64:                        ; HL = &count (quad) -> DE = it, saturated to -1..64',
           '        ld de,7', '        add hl,de', '        bit 7,(hl)', '        ld de,0FFFFh', '        ret nz',
           '        ld b,7', '        xor a', '.or:    or (hl)', '        dec hl', '        djnz .or',
           '        or a', '        ld de,64', '        ret nz', '        ld e,(hl)', '        ld d,0', '        ld a,e',
           '        cp 65', '        ret c', '        ld e,64', '        ret']


def compile_program(src, target='cpm', org=None, bss_at=None):
    """org and bss_at place the code and the slots (the Spectrum's builder puts code high, slots beneath it)"""
    FLOATS['on'] = target == 'zx48'
    decls = B.Parser(src).program()
    ck = B.Checker(decls, 'cpm' if target == 'cpm' else 'zx48')
    ck.check()
    g = Gen(ck, target)
    if org is not None:
        g.org = org
    if bss_at is not None:
        g.bss_at = bss_at
    g.globals_names()
    return g.program()


def main(argv):
    ap = argparse.ArgumentParser(prog='z80gen.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog='then, for CP/M: sjasmplus --raw=prog.com prog.asm (zxbuild.py makes tapes)')
    ap.add_argument('program', metavar='PROGRAM.bly', help='the program; its assembly goes to standard output')
    ap.add_argument('--target', choices=['cpm', 'zx48'], default='cpm', help='the machine (default cpm)')
    a = ap.parse_args(argv)
    try:
        B.EMBED_DIR = os.path.dirname(os.path.abspath(a.program))
        src = open(a.program).read()
    except OSError as err:
        sys.exit(f'z80gen.py: {a.program}: {err.strerror}')
    try:
        sys.stdout.write(compile_program(src, a.target))
    except B.BarleyError as err:
        print(err)
        sys.exit(1)
    except GenError as err:
        print(f'Z80: {err}')
        sys.exit(2)
    except ValueError as err:                          # the gatherer: a library part nobody has written yet
        print(f'Z80: {err}')
        sys.exit(2)

if __name__ == '__main__':
    main(sys.argv[1:])
