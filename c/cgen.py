#!/usr/bin/env python3
"""Barley's C backend: the checked program, lowered to deliberately dumb C.

The front end is the reference interpreter's own (its parser and checker), so
the two can't disagree about what a program means. The C is as dumb as
possible on purpose:
  - every subexpression goes into its own temporary, in the interpreter's
    left-to-right order, so nothing depends on C's unspecified order of
    evaluation (not even which of two errors is reported first);
  - every operation is a call into rt/barley.h, which checks it and has no
    undefined behaviour;
  - control flow stays structured: Barley's if, while and for become C's, so
    break and continue mean the same;
  - generics are the preprocessor's: each container type is a template
    included once per element type.
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'interp'))
sys.path.insert(0, os.path.join(HERE, '..', 'z80'))
import barley as B                                                     # noqa: E402
import zxgfx                                                           # noqa: E402  the screen's meaning, and the font

INT_C = {B.BYTE: 'u8', B.WORD: 'u16', B.INT: 'i16', B.LONG: 'i32', B.QUAD: 'i64'}
CMP_OPS = ('==', '!=', '<', '>', '<=', '>=')
ARITH = {'+': 'add', '-': 'sub', '*': 'mul', '/': 'div', '%': 'rem'}
BITS = {'&': 'and', '|': 'or', '^': 'xor'}
LIMITS = {B.BYTE: ('0', '255'), B.WORD: ('0', '65535'), B.INT: ('INT16_MIN', 'INT16_MAX'),
          B.LONG: ('INT32_MIN', 'INT32_MAX'), B.QUAD: ('INT64_MIN', 'INT64_MAX')}


class CGenError(Exception):
    pass


class Gen:
    def __init__(self, ck):
        self.ck = ck
        self.out = []                     # the current block's lines
        self.depth = 1
        self.ntemp = 0
        self.strings = {}                 # bytes -> C array name
        self.insts = []                   # template instantiations, in the order they're first needed
        self.inst_set = set()
        self.arr_views = []
        self.func = None
        self.peeks = False                # the ROM's 16K go into the program only if something can see them

    # -- names and types -----------------------------------------------------------------------------------------
    def kind(self, t):
        """the element kind: the suffix of bly_cmp_, bly_pr_ and friends"""
        if t in INT_C:
            return INT_C[t]
        if t is B.BOOL or t is B.BIT:
            return 'b8'
        if t is B.FLOAT:
            return 'f64'
        if t is B.STR:
            return 'str'
        if t is B.POS:
            return 'pos'
        if isinstance(t, B.RecordT):
            return 'R_' + t.name
        raise CGenError(f'no element kind for {t!r}')

    def ctype(self, t):
        if t in INT_C:
            return INT_C[t]
        if t is B.BOOL or t is B.BIT:
            return 'b8'
        if t is B.FLOAT:
            return 'f64'
        if t is B.STR:
            return 'bly_str'
        if t is B.POS:
            return 'bly_pos'
        if isinstance(t, B.RecordT):
            return 'R_' + t.name
        if t is B.LINES:
            return 'bly_lines *'
        if isinstance(t, B.Gen):
            if t.kind == 'array':
                return self.arr_view(t.args[0])
            return self.gname(t) + ' *'
        raise CGenError(f'no C type for {t!r}')

    def arr_view(self, et):
        name = 'arr_' + self.kind(et)
        if name not in self.arr_views:
            self.arr_views.append(name)
        return name

    def gname(self, t):
        """the C name of a container type, instantiating its template (and what it needs) on first use"""
        k = t.kind
        if k == 'map':
            name = f'map_{self.kind(t.args[0])}_{self.kind(t.args[1])}'
            self.need(('map', name, t.args[0], t.args[1], 'map'))
            return name
        if k == 'set':
            name = f'set_{self.kind(t.args[0])}'
            self.need(('map', name, t.args[0], B.BOOL, 'set'))
            return name
        name = f'{k}_{self.kind(t.args[0])}'
        if k in ('list', 'grid', 'queue', 'heap'):
            self.need((k, name, t.args[0]))
            return name
        raise CGenError(f'no C name for {t!r}')

    def need(self, inst):
        if inst not in self.inst_set:
            self.inst_set.add(inst)
            self.insts.append(inst)

    def need_sort(self, et):
        self.need(('sort', self.kind(et), et))

    # -- emitting ------------------------------------------------------------------------------------------------
    def emit(self, line):
        self.out.append('    ' * self.depth + line)

    def temp(self, ct, expr):
        self.ntemp += 1
        name = f't{self.ntemp}'
        self.emit(f'{ct} {name} = {expr};')
        return name

    def open(self, head):
        self.emit(head + ' {')
        self.depth += 1

    def close(self, tail=''):
        self.depth -= 1
        self.emit('}' + tail)

    def string(self, b):
        if not b:
            return 'bly_s(bly_nothing, 0)'
        if b not in self.strings:
            self.strings[b] = f'S{len(self.strings)}'
        return f'bly_s({self.strings[b]}, {len(b)})'

    def c_init(self, v, t):
        """a constant value as a C initializer (a record's fields in order, a str as its bytes and length)"""
        if isinstance(t, B.RecordT):
            return '{' + ', '.join(self.c_init(x, ft) for x, (_, ft) in zip(v, t.fields)) + '}'
        if t is B.STR:
            if not v:
                return '{bly_nothing, 0}'
            if v not in self.strings:
                self.strings[v] = f'S{len(self.strings)}'
            return f'{{{self.strings[v]}, {len(v)}}}'
        return self.lit(v, t)

    def lit(self, v, t):
        if t is B.FLEX:
            t = next(x for x in (B.INT, B.LONG, B.QUAD) if x.lo <= v <= x.hi)
        if t is B.BOOL:
            return '1' if v else '0'
        if t is B.FLOAT:
            r = repr(float(v))
            return r if ('.' in r or 'e' in r) else r + '.0'
        if t is B.QUAD:
            return '(INT64_MIN)' if v == -2**63 else f'((i64){v}LL)'
        if t is B.LONG:
            return f'((i32){v}L)'
        if t in INT_C:
            return f'(({INT_C[t]}){v})'
        raise CGenError(f'no literal for a {t!r}')

    # -- the program ---------------------------------------------------------------------------------------------
    def program(self):
        ck = self.ck
        body = []
        # records, in an order where each field's record comes first
        done, order = set(), []

        def visit(rt):
            if rt.name in done:
                return
            done.add(rt.name)
            for _, ft in rt.fields:
                if isinstance(ft, B.RecordT):
                    visit(ft)
            order.append(rt)
        for rt in ck.records.values():
            visit(rt)
        globals_ = [d for d in ck.decls if d.k == 'var']
        funcs = [d for d in ck.decls if d.k == 'func']
        # functions first (they decide which templates are needed), then everything that has to precede them
        fbodies = []
        protos = []
        for f in funcs:
            protos.append(self.signature(f) + ';')
            self.out, self.depth, self.ntemp, self.func = [], 1, 0, f
            self.block(f.body)
            fbodies.append(self.signature(f) + ' {\n' + '\n'.join(self.out) + '\n}\n')
        self.out, self.depth, self.ntemp, self.func = [], 1, 0, None
        ginit = []
        gdecls = []
        for d in self.ck.decls:                                      # the tables: not const in C, as views take
            if getattr(d, 'table', False):                           # them, but the checker lets nothing write
                et, vals = d.ty.args[0], self.ck.globals[d.name].cval
                gdecls.append(f'static {self.ctype(et)} k_{d.name}[{len(vals)}] = '
                              f'{{{", ".join(self.c_init(v, et) for v in vals)}}};')
        for d in globals_:
            t = d.ty
            if isinstance(t, B.Gen) and t.kind == 'array':
                gdecls.append(f'static {self.ctype(t.args[0])} g_{d.name}[{t.n}];')
                continue
            gdecls.append(f'static {self.ctype(t)} g_{d.name};')
            if d.e is not None:
                self.out = []
                v = self.ex(d.e)
                ginit += self.out + ['    ' + f'g_{d.name} = {self.conv(v, d.e.ty, t)};']
        # now write it out
        # the ROM's font, read now, so the program carries its own; only a program that can see the screen needs it
        font = zxgfx.font() if B.uses_machine(self.ck.decls) else bytes(96 * 8)
        body.append('#define BLY_ZX_FONT {' + ','.join(str(b) for b in font) + '}')
        if self.peeks:
            body.append('#define BLY_ZX_ROM {' + ','.join(str(b) for b in zxgfx.rom()) + '}')
        body.append('#include "barley.h"\n')
        for rt in order:
            body.append(self.record_decl(rt))
        for b, name in self.strings.items():
            body.append(f'static const u8 {name}[] = {{{", ".join(str(x) for x in b)}}};')
        body.append('')
        body += self.instantiations()
        for name in self.arr_views:
            body.append(f'typedef struct {{ {self.view_elem[name]} *p; u16 n; }} {name};')
        body.append('')
        body += gdecls
        body.append('')
        body += protos
        body.append('')
        body.append('static void bly_init_globals(void) {')
        body += ginit
        body.append('}\n')
        body += fbodies
        body.append('int main(int argc, char **argv) {\n    bly_start(argc, argv);\n    bly_init_globals();\n'
                    '    f_main();\n    return bly_finish();\n}')
        return '\n'.join(body) + '\n'

    @property
    def view_elem(self):
        out = {}
        for rt_kind in self.arr_views:
            k = rt_kind[4:]
            out[rt_kind] = {'u8': 'u8', 'u16': 'u16', 'i16': 'i16', 'i32': 'i32', 'i64': 'i64', 'b8': 'b8',
                            'f64': 'f64', 'str': 'bly_str', 'pos': 'bly_pos'}.get(k, k)
        return out

    def record_decl(self, rt):
        n = 'R_' + rt.name
        fields = ' '.join(f'{self.ctype(ft)} {f};' for f, ft in rt.fields)
        cmp_body = ''.join(f'    if ((c = bly_cmp_{self.kind(ft)}(a.{f}, b.{f}))) return c;\n' for f, ft in rt.fields)
        pr_body = '    bly_pr_cstr("' + rt.name + '(");\n'
        for i, (f, ft) in enumerate(rt.fields):
            if i:
                pr_body += '    bly_pr_cstr(", ");\n'
            pr_body += f'    bly_pr_{self.kind(ft)}(v.{f});\n'
        pr_body += '    bly_pr_cstr(")");\n'
        return (f'typedef struct {n} {{ {fields} }} {n};\n'
                f'static inline int bly_cmp_{n}({n} a, {n} b) {{\n    int c;\n{cmp_body}    return 0;\n}}\n'
                f'static inline int bly_eq_{n}({n} a, {n} b) {{ return bly_cmp_{n}(a, b) == 0; }}\n'
                f'static void bly_pr_{n}({n} v) {{\n{pr_body}}}\n')

    def instantiations(self):
        out = []
        insts = [i for i in self.insts if i[0] == 'sort'] + [i for i in self.insts if i[0] != 'sort']
        for inst in insts:                              # sorts first: a list's sort calls its element's
            k = inst[0]
            if k == 'sort':
                out += [f'#define G_T {self.ctype(inst[2])}', f'#define G_X {inst[1]}', '#include "bly_sort.h"']
            elif k == 'map':
                _, name, kt, vt, kind = inst
                out += [f'#define G_NAME {name}', f'#define G_K {self.ctype(kt)}', f'#define G_KX {self.kind(kt)}',
                        f'#define G_V {self.ctype(vt)}', f'#define G_KIND "{kind}"', '#include "bly_map.h"']
            else:
                _, name, et = inst
                if k == 'list' and ('sort', self.kind(et), et) in self.inst_set:
                    out.append('#define G_SORTS')
                out += [f'#define G_NAME {name}', f'#define G_T {self.ctype(et)}', f'#define G_X {self.kind(et)}',
                        f'#include "bly_{k}.h"']
                if k == 'grid' and name == 'grid_u8':
                    out.append(GRID_INPUT)
        return out

    def signature(self, f):
        rt = 'void' if f.rty is B.VOID else self.ctype(f.rty)
        params = ', '.join(f'{self.ctype(pt)} v_{pn}' for (pn, _), pt in zip(f.params, f.ptys)) or 'void'
        return f'static {rt} f_{f.name}({params})'

    # -- statements ----------------------------------------------------------------------------------------------
    def block(self, stmts):
        for s in stmts:
            self.stmt(s)

    def stmt(self, s):
        k = s.k
        line = s.line
        if k == 'var':
            t = s.ty
            if isinstance(t, B.Gen) and t.kind == 'array':
                self.emit(f'{self.ctype(t.args[0])} v_{s.name}[{t.n}];')
                self.emit(f'memset(v_{s.name}, 0, sizeof v_{s.name});')
                return
            if s.e is None:
                self.emit(f'{self.ctype(t)} v_{s.name} = {self.zero(t)};')
            else:
                v = self.ex(s.e)
                self.emit(f'{self.ctype(t)} v_{s.name} = {self.conv(v, s.e.ty, t)};')
        elif k == 'assign':
            self.assign(s)
        elif k == 'expr':
            v = self.ex(s.e, discard=True)
            if v:
                self.emit(f'(void){v};')
        elif k == 'if':
            self.if_(s.arms, s.else_)
        elif k == 'while':
            self.open('for (;;)')
            c = self.ex(s.cond)
            self.emit(f'if (!{c}) break;')
            self.block(s.body)
            self.close()
        elif k == 'for':
            self.for_(s)
        elif k == 'case':
            v = self.ex(s.e)
            arms = [(' || '.join(f'{v} == {self.lit(w.cval, s.e.ty if s.e.ty is not B.FLEX else w.ty)}'
                                 for w in vals), body) for vals, body in s.whens]
            for i, (cond, body) in enumerate(arms):
                self.open(('if (' if i == 0 else 'else if (') + cond + ')')
                self.block(body)
                self.close()
            if s.else_:
                self.open('else' if arms else '')
                self.block(s.else_)
                self.close()
        elif k == 'break':
            self.emit('break;')
        elif k == 'continue':
            self.emit('continue;')
        elif k == 'return':
            if s.e is None:
                self.emit('return;')
            else:
                v = self.ex(s.e)
                self.emit(f'return {self.conv(v, s.e.ty, self.func.rty)};')
        elif k == 'assert':
            c = self.ex(s.e)
            self.emit(f'if (!{c}) bly_fail("assertion failed", {line});')
        elif k == 'print':                    # what print itself writes also lands on the screen: BLY_SHOW
            for kind, e in s.items:
                if kind == 'zone':
                    self.emit('BLY_SHOW(bly_zone());')
                elif kind == 'at':
                    r, c = (self.conv(self.ex(x), x.ty, B.INT) for x in e)
                    self.emit(f'bly_zx_at({r}, {c}, {line});')
                    self.emit(f'bly_col = {c};')
                else:
                    v = self.ex(e)
                    self.emit('BLY_SHOW(' + self.pr(v, e.ty) + ');')
            if s.newline:
                self.emit('BLY_SHOW(bly_nl());')
        else:
            raise CGenError(f'no C for statement {k}')

    def if_(self, arms, else_):
        cond, body = arms[0]
        c = self.ex(cond)
        self.open(f'if ({c})')
        self.block(body)
        self.close()
        if len(arms) > 1 or else_:
            self.open('else')
            if len(arms) > 1:
                self.if_(arms[1:], else_)
            else:
                self.block(else_)
            self.close()

    def pr(self, v, t):
        if t in INT_C or t is B.FLEX:
            return f'bly_pr_int((i64){v})'
        return f'bly_pr_{self.kind(t)}({v})'

    def zero(self, t):
        if t in INT_C or t is B.BOOL:
            return '0'
        if t is B.FLOAT:
            return '0.0'
        if t is B.STR:
            return 'bly_s(bly_nothing, 0)'
        if isinstance(t, B.RecordT):
            return f'(({self.ctype(t)}){{0}})'
        return '0'

    def conv(self, v, frm, to):
        """a value of type frm where a to is wanted (the checker allows only widening, or the same type)"""
        if frm is to or frm == to or frm is B.FLEX:
            return v if frm is not B.FLEX else f'(({self.ctype(to)}){v})'
        if to in INT_C or to is B.FLOAT:
            return f'(({self.ctype(to)}){v})'
        if isinstance(to, B.Gen) and to.kind == 'array':
            return v
        return v

    # -- assignment ----------------------------------------------------------------------------------------------
    def locate(self, e):
        """evaluate a target's parts, left to right; return (read, write) makers: read() emits a checked read and
        returns the value; write(v) emits the checked store"""
        line = e.line
        if e.k == 'name':
            name = ('g_' if e.var.where == 'global' else 'v_') + e.name
            ct = self.ctype(e.ty)                          # read now, into a temp: a call in the value can change it
            return (lambda: self.temp(ct, name)), (lambda v: self.emit(f'{name} = {v};'))
        if e.k == 'index':
            ot = e.obj.ty
            if isinstance(ot, B.Gen) and ot.kind == 'array':
                base, n = self.array(e.obj)
                i = self.index_temp(e.idx[0])
                et = self.ctype(ot.args[0])

                def rd():
                    self.emit(f'bly_chk_index({i}, {n}, {line});')
                    return self.temp(et, f'{base}[{i}]')

                def wr(v):
                    self.emit(f'bly_chk_index({i}, {n}, {line});')
                    self.emit(f'{base}[{i}] = {v};')
                return rd, wr
            obj = self.ex(e.obj)
            g = self.gname(ot)
            et = self.ctype(B.BOOL if ot.args[-1] is B.BIT else ot.args[-1])
            if ot.kind == 'list':
                i = self.ex(e.idx[0])
                return (lambda: self.temp(et, f'{g}_get({obj}, {i}, {line})'),
                        lambda v: self.emit(f'{g}_set({obj}, {i}, {v}, {line});'))
            if ot.kind == 'map':
                k = self.ex(e.idx[0])
                k = self.conv(k, e.idx[0].ty, ot.args[0])
                return (lambda: self.temp(et, f'{g}_get({obj}, {k}, {line})'),
                        lambda v: self.emit(f'{g}_put({obj}, {k}, {v}, {line});'))
            if ot.kind == 'grid':
                r, c = self.grid_rc(e)
                return (lambda: self.temp(et, f'{g}_get({obj}, {r}, {c}, {line})'),
                        lambda v: self.emit(f'{g}_set({obj}, {r}, {c}, {v}, {line});'))
        if e.k == 'dot':
            rd_base, wr_base, ref = self.locate_ref(e.obj)
            f = e.name

            def rd():
                return self.temp(self.ctype(e.ty), f'{ref()}.{f}')

            def wr(v):
                self.emit(f'{ref()}.{f} = {v};')
            return rd, wr
        raise CGenError(f"can't assign to {e.k}")

    def locate_ref(self, e):
        """a record-valued target, as a C lvalue made after its checks: (read, write, ref)"""
        line = e.line
        if e.k == 'name':
            name = ('g_' if e.var.where == 'global' else 'v_') + e.name
            return None, None, (lambda: name)
        if e.k == 'index':
            ot = e.obj.ty
            if isinstance(ot, B.Gen) and ot.kind == 'array':
                base, n = self.array(e.obj)
                i = self.index_temp(e.idx[0])

                def ref():
                    self.emit(f'bly_chk_index({i}, {n}, {line});')
                    return f'{base}[{i}]'
                return None, None, ref
            obj = self.ex(e.obj)
            g = self.gname(ot)
            if ot.kind == 'list':
                i = self.ex(e.idx[0])
                return None, None, (lambda: f'(*{g}_ref({obj}, {i}, {line}))')
            if ot.kind == 'map':
                k = self.conv(self.ex(e.idx[0]), e.idx[0].ty, ot.args[0])
                return None, None, (lambda: f'(*{g}_ref({obj}, {k}, {line}))')
            if ot.kind == 'grid':
                r, c = self.grid_rc(e)
                return None, None, (lambda: f'(*{g}_ref({obj}, {r}, {c}, {line}))')
        if e.k == 'dot':
            _, _, ref = self.locate_ref(e.obj)
            return None, None, (lambda: f'{ref()}.{e.name}')
        raise CGenError(f"can't assign through {e.k}")

    def assign(self, s):
        rd, wr = self.locate(s.target)
        tt = s.target.ty
        if s.op is None:
            v = self.ex(s.e)
            wr(self.conv(v, s.e.ty, tt))
            return
        old = rd()
        r = self.ex(s.e)
        v = self.binop(s.opnode, old, s.target.ty, r, s.e.ty)
        wr(self.conv(v, s.opnode.ty, tt))

    # -- for -----------------------------------------------------------------------------------------------------
    def for_(self, s):
        it, t, line = s.it, s.it.ty, s.line
        names, vts = s.names, s.vtys
        v0 = 'v_' + names[0]
        if isinstance(t, B.Gen) and t.kind == 'range':
            rng = it.args[0] if it.k == 'call' else it                  # rev(a..b) passes its range through
            lo, hi = self.ex(rng.a), self.ex(rng.b)
            ct = self.ctype(t.args[0])
            lo, hi = self.conv(lo, rng.a.ty, t.args[0]), self.conv(hi, rng.b.ty, t.args[0])
            if rng.rev:
                self.open(f'for ({ct} {v0} = {hi}; {v0} > {lo};)')
                self.emit(f'{v0}--;')
            else:
                self.open(f'for ({ct} {v0} = {lo}; {v0} < {hi}; {v0}++)')
            self.block(s.body)
            self.close()
            return
        if isinstance(t, B.Gen) and t.kind == 'array':
            base, n = self.array(it)
            self.ntemp += 1
            i = f't{self.ntemp}'
            self.open(f'for (u32 {i} = 0; {i} < (u32)({n}); {i}++)')
            self.emit(f'{self.ctype(vts[0])} {v0} = {base}[{i}];')
            self.block(s.body)
            self.close()
            return
        if t is B.STR:
            sv = self.ex(it)
            self.ntemp += 1
            i = f't{self.ntemp}'
            self.open(f'for (u32 {i} = 0; {i} < {sv}.n; {i}++)')
            self.emit(f'u8 {v0} = {sv}.p[{i}];')
            self.block(s.body)
            self.close()
            return
        if t is B.LINES:
            lv = self.ex(it)
            self.open('for (;;)')
            self.emit(f'if ({lv}->i >= bly_nln) break;')
            self.emit(f'bly_str {v0} = bly_lns[{lv}->i++];')
            self.block(s.body)
            self.close()
            return
        if isinstance(t, B.Gen) and t.kind == 'iter':
            obj = self.ex(it.obj)
            self.ntemp += 1
            st = f't{self.ntemp}'
            if it.name == 'ints':
                vt = vts[0]
                lo, hi = LIMITS[vt]
                self.emit(f'bly_ints_it {st};')
                self.emit(f'bly_ints_init(&{st}, {obj});')
                self.open(f'while (bly_ints_next(&{st}))')
                self.emit(f'{self.ctype(vt)} {v0} = ({self.ctype(vt)})bly_ints_val(&{st}, {lo}, {hi}, "{vt.name}", {line});')
            else:
                sep = self.text_arg(it.args[0])
                self.emit(f'bly_split_it {st};')
                self.emit(f'bly_split_init(&{st}, {obj}, {sep}, {line});')
                self.emit(f'bly_str {v0};')
                self.open(f'while (bly_split_next(&{st}, &{v0}))')
            self.block(s.body)
            self.close()
            return
        if isinstance(t, B.Gen) and t.kind == 'grid':
            g = self.ex(it)
            self.ntemp += 1
            i = f't{self.ntemp}'
            self.open(f'for (i32 {i} = 0; {i} < {g}->rows * {g}->cols; {i}++)')
            self.emit(f'bly_pos {v0} = bly_pos_make((i16)({i} / {g}->cols), (i16)({i} % {g}->cols));')
            self.block(s.body)
            self.close()
            return
        if isinstance(t, B.Gen) and t.kind in ('list', 'queue', 'map', 'set'):
            c = self.ex(it)
            self.gname(t)
            self.ntemp += 1
            i, ver = f't{self.ntemp}', f't{self.ntemp}v'
            self.emit(f'u32 {ver} = {c}->ver;')
            self.open(f'for (u32 {i} = 0; ; {i}++)')
            self.emit(f'if ({c}->ver != {ver}) bly_changed("{t.kind}", {line});')
            if t.kind in ('map', 'set'):
                self.emit(f'if ({i} >= {c}->ne) break;')
                self.emit(f'if (!{c}->alive[{i}]) continue;')
                self.emit(f'{self.ctype(vts[0])} {v0} = {c}->k[{i}];')
                if len(names) == 2:
                    self.emit(f'{self.ctype(vts[1])} v_{names[1]} = {c}->v[{i}];')
            else:
                self.emit(f'if ({i} >= {c}->n) break;')
                elem = f'{c}->a[{i}]' if t.kind == 'list' else f'{self.gname(t)}_at({c}, {i})'
                self.emit(f'{self.ctype(vts[0])} {v0} = {elem};')
            self.block(s.body)
            self.close()
            return
        raise CGenError(f"no C for walking a {t!r}")

    # -- expressions ---------------------------------------------------------------------------------------------
    def array(self, e):
        """an array-valued expression: (base pointer, length), both C expressions"""
        if e.k == 'name':
            if e.name in ('dirs4', 'dirs8') and e.var.const:
                return f'bly_{e.name}', e.name[-1]
            if e.var.const:                                          # a table
                return f'k_{e.name}', str(len(e.var.cval))
            name = ('g_' if e.var.where == 'global' else 'v_') + e.name
            n = e.var.ty.n
            if n is None:                                            # a parameter: a view
                return f'{name}.p', f'{name}.n'
            return name, str(n)
        raise CGenError('arrays are named')

    def index_temp(self, e):
        """an array index, always in a temporary (a literal index would be read by the C compiler's eye before
        the check that guards it)"""
        v = self.ex(e)
        return v if v.startswith('t') else self.temp('i64', f'(i64){v}')

    def text_arg(self, a):
        v = self.ex(a)
        return f'bly_chr({v})' if a.ty is B.BYTE else v

    def grid_rc(self, e):
        if len(e.idx) == 2:
            return self.ex(e.idx[0]), self.ex(e.idx[1])
        p = self.ex(e.idx[0])
        return f'{p}.r', f'{p}.c'

    def ex(self, e, discard=False):
        """emit what computing e takes; return a C expression for its value (a temporary, a literal or a name)"""
        if e.k == 'name' and e.var.const:
            if isinstance(e.var.ty, B.Gen):                          # a table, dirs4 or dirs8, passed: a view
                base, n = self.array(e)
                return f'(({self.ctype(e.ty)}){{{base}, (u16)({n})}})'
            return self.lit(e.cval, e.ty)
        if e.cval is not None and e.k != 'name':
            return self.lit(e.cval, e.ty)
        return getattr(self, 'x_' + e.k)(e, discard) if e.k in ('call', 'dot') else getattr(self, 'x_' + e.k)(e)

    def x_str(self, e):
        return self.string(e.v)

    def x_name(self, e):
        name = ('g_' if e.var.where == 'global' else 'v_') + e.name
        if isinstance(e.ty, B.Gen) and e.ty.kind == 'array':
            base, n = self.array(e)
            return f'(({self.ctype(e.ty)}){{{base}, (u16)({n})}})'
        return self.temp(self.ctype(e.ty), name)

    def x_bin(self, e):
        op = e.op
        if op in ('and', 'or'):
            a = self.ex(e.a)
            self.ntemp += 1
            r = f't{self.ntemp}'
            self.emit(f'b8 {r};')
            self.open(f'if ({"" if op == "and" else "!"}{a})')
            b = self.ex(e.b)
            self.emit(f'{r} = {b};')
            self.close(f' else {r} = {"0" if op == "and" else "1"};')
            return r
        if op == 'in':
            k = self.ex(e.a)
            c = self.ex(e.b)
            g = self.gname(e.b.ty)
            return self.temp('b8', f'{g}_has({c}, {self.conv(k, e.a.ty, e.b.ty.args[0])})')
        a = self.ex(e.a)
        b = self.ex(e.b)
        return self.binop(e, a, e.a.ty, b, e.b.ty)

    def binop(self, e, a, ta, b, tb):
        op, t, line = e.op, e.ty, e.line
        if op in CMP_OPS:
            if ta in (B.STR, B.POS) or isinstance(ta, B.RecordT):
                k = self.kind(ta)
                return self.temp('b8', f'bly_cmp_{k}({a}, {b}) {op} 0')
            if B.FLOAT in (ta, tb):
                return self.temp('b8', f'(f64){a} {op} (f64){b}')
            if ta in INT_C and tb in INT_C and ta is not tb:   # both sides in the wider type, as the checker has them:
                w = tb if B.widens(ta, tb) else ta             # word < 65536 is a long comparison, and C shouldn't
                a, b = f'(({self.ctype(w)}){a})', f'(({self.ctype(w)}){b})'   # see a u16 against 65536
            return self.temp('b8', f'{a} {op} {b}')
        if t is B.POS:
            return self.temp('bly_pos', f'bly_pos_{"add" if op == "+" else "sub"}({a}, {b}, {line})')
        if t is B.FLOAT:
            a, b = f'(f64){a}', f'(f64){b}'
            if op == '/':
                return self.temp('f64', f'bly_fdiv({a}, {b}, {line})')
            if op == '**':
                return self.temp('f64', f'bly_fpow({a}, {b}, {line})')
            return self.temp('f64', f'{a} {op} {b}')
        ct, n = self.ctype(t), INT_C[t]
        if op in ('<<', '>>'):
            return self.temp(ct, f'{"shl" if op == "<<" else "shr"}_{n}(({ct}){a}, (i64){b}, {line})')
        if op in BITS:
            return self.temp(ct, f'{BITS[op]}_{n}(({ct}){a}, ({ct}){b})')
        return self.temp(ct, f'{ARITH[op]}_{n}(({ct}){a}, ({ct}){b}, {line})')

    def x_un(self, e):
        a = self.ex(e.a)
        if e.op == 'not':
            return self.temp('b8', f'!{a}')
        if e.ty is B.FLOAT:
            return self.temp('f64', f'-{a}')
        ct, n = self.ctype(e.ty), INT_C[e.ty]
        if e.op == '-':
            return self.temp(ct, f'neg_{n}(({ct}){a}, {e.line})')
        return self.temp(ct, f'not_{n}(({ct}){a})')

    def x_index(self, e):
        ot, line = e.obj.ty, e.line
        if e.slice:
            s = self.ex(e.obj)
            rng = e.idx[0]
            a, b = self.ex(rng.a), self.ex(rng.b)
            return self.temp('bly_str', f'bly_slice({s}, (i64){a}, (i64){b}, {line})')
        if ot is B.STR:
            s = self.ex(e.obj)
            i = self.ex(e.idx[0])
            return self.temp('u8', f'bly_str_at({s}, (i64){i}, {line})')
        if isinstance(ot, B.Gen) and ot.kind == 'array':
            base, n = self.array(e.obj)
            i = self.index_temp(e.idx[0])
            self.emit(f'bly_chk_index((i64){i}, {n}, {line});')
            return self.temp(self.ctype(e.ty), f'{base}[{i}]')
        obj = self.ex(e.obj)
        g = self.gname(ot)
        if ot.kind == 'list':
            i = self.ex(e.idx[0])
            return self.temp(self.ctype(e.ty), f'{g}_get({obj}, (i64){i}, {line})')
        if ot.kind == 'map':
            k = self.conv(self.ex(e.idx[0]), e.idx[0].ty, ot.args[0])
            return self.temp(self.ctype(e.ty), f'{g}_get({obj}, {k}, {line})')
        if ot.kind == 'grid':
            r, c = self.grid_rc(e)
            return self.temp(self.ctype(e.ty), f'{g}_get({obj}, {r}, {c}, {line})')
        raise CGenError(f'no C for indexing a {ot!r}')

    def x_dot(self, e, discard=False):
        ot, name, line = e.obj.ty, e.name, e.line
        if e.args is None:
            if isinstance(ot, B.Gen) and ot.kind == 'array':
                _, n = self.array(e.obj)
                return self.temp('u16', f'(u16)({n})')
            obj = self.ex(e.obj)
            if isinstance(ot, B.RecordT):
                return self.temp(self.ctype(e.ty), f'{obj}.{name}')
            if name == 'len':
                if ot is B.STR:
                    return self.temp('u16', f'{obj}.n')
                self.gname(ot)
                return self.temp('u16', f'(u16){obj}->{"live" if ot.kind in ("map", "set") else "n"}')
            return self.temp('i16', f'(i16){obj}->{name}')
        if isinstance(ot, B.Gen) and ot.kind == 'array':
            base, n = self.array(e.obj)
            self.need_sort(ot.args[0])
            self.emit(f'bly_sort_{self.kind(ot.args[0])}({base}, {n});')
            return None
        obj = self.ex(e.obj)
        args = [self.ex(a) for a in e.args]
        if ot is B.STR:
            if name in ('int',):
                t = e.ty
                lo, hi = LIMITS[t]
                if args:
                    call = f'bly_str_intk({obj}, (i64){args[0]}, {lo}, {hi}, "{t.name}", {line})'
                else:
                    call = f'bly_str_int({obj}, {lo}, {hi}, "{t.name}", {line})'
                return self.temp(self.ctype(t), f'({self.ctype(t)}){call}')
            if name == 'find':
                return self.temp('i16', f'bly_find({obj}, {self.argtext(e.args[0], args[0])}, {line})')
            if name == 'starts':
                return self.temp('b8', f'bly_starts({obj}, {self.argtext(e.args[0], args[0])})')
            if name == 'trim':
                return self.temp('bly_str', f'bly_trim({obj})')
        if ot is B.LINES:
            return self.temp('bly_str', f'bly_lines_next({obj}, {line})')
        g = self.gname(ot)
        k = ot.kind
        conv_el = (lambda i: self.conv(args[i], e.args[i].ty, B.BOOL if ot.args[0] is B.BIT else ot.args[0]))
        if k == 'list':
            if name == 'push':
                self.emit(f'{g}_push({obj}, {conv_el(0)}, {line});')
                return None
            if name == 'pop':
                return self.temp(self.ctype(e.ty), f'{g}_pop({obj}, {line})')
            if name == 'sort':
                self.need_sort(ot.args[0])
                self.emit(f'{g}_sort({obj});')
                return None
            if name == 'clear':
                self.emit(f'{g}_clear({obj});')
                return None
        if k == 'queue':
            if name == 'put':
                self.emit(f'{g}_put({obj}, {conv_el(0)}, {line});')
                return None
            return self.temp(self.ctype(e.ty), f'{g}_get({obj}, {line})')
        if k == 'heap':
            if name == 'push':
                self.emit(f'{g}_push({obj}, {conv_el(0)}, {line});')
                return None
            return self.temp(self.ctype(e.ty), f'{g}_pop({obj}, {line})')
        if k == 'map':
            if name == 'get':
                d = self.conv(args[1], e.args[1].ty, ot.args[1])
                return self.temp(self.ctype(e.ty), f'{g}_getd({obj}, {conv_el(0)}, {d})')
            self.emit(f'{g}_del({obj}, {conv_el(0)});')
            return None
        if k == 'set':
            if name == 'add':
                self.emit(f'{g}_put({obj}, {conv_el(0)}, 1, {line});')
            else:
                self.emit(f'{g}_del({obj}, {conv_el(0)});')
            return None
        if k == 'grid':
            if name == 'has':
                return self.temp('b8', f'{g}_has({obj}, {args[0]})')
            return self.temp('bly_pos', f'{g}_find({obj}, {conv_el(0)}, {line})')
        raise CGenError(f'no C for .{name}() on a {ot!r}')

    def argtext(self, a, v):
        return f'bly_chr({v})' if a.ty is B.BYTE else v

    def x_new(self, e):
        t, line = e.ty, e.line
        g = self.gname(t)
        args = [self.ex(a) for a in e.args]
        if t.kind == 'grid':
            et = B.BOOL if t.args[0] is B.BIT else t.args[0]
            fill = self.conv(args[2], e.args[2].ty, et) if len(args) == 3 else self.zero(et)
            return self.temp(g + ' *', f'{g}_new((i64){args[0]}, (i64){args[1]}, {fill}, {line})')
        return self.temp(g + ' *', f'{g}_new((i64){args[0]}, {line})')

    def x_call(self, e, discard=False):
        line = e.line
        if hasattr(e, 'func'):
            f = e.func
            args = [self.conv(self.ex(a), a.ty, pt) for a, pt in zip(e.args, f.ptys)]
            call = f'f_{f.name}({", ".join(args)})'
            if f.rty is B.VOID:
                self.emit(call + ';')
                return None
            return self.temp(self.ctype(f.rty), call)
        if hasattr(e, 'record'):
            rt = e.record
            args = [self.conv(self.ex(a), a.ty, ft) for a, (_, ft) in zip(e.args, rt.fields)]
            if rt is B.POS:
                return self.temp('bly_pos', f'bly_pos_make({args[0]}, {args[1]})')
            return self.temp(self.ctype(rt), f'(({self.ctype(rt)}){{{", ".join(args)}}})')
        if hasattr(e, 'cast'):
            a = e.args[0]
            v = self.ex(a)
            to = e.cast
            if to is B.BOOL:
                return self.temp('b8', f'(b8)({v} != 0)')
            if to is B.FLOAT:
                return self.temp('f64', f'(f64){v}')
            n = INT_C[to]
            if a.ty is B.FLOAT:
                lo, hi = to.lo, to.hi + 1
                return self.temp(n, f'({n})bly_trunc_fits({v}, {float(lo)!r}, {float(hi)!r}, "{to.name}", {line})')
            return self.temp(n, f'bly_wrap_{n}((u64)(i64){v})')
        name = e.builtin
        if name == 'rev':
            raise CGenError('rev() is walked by for')
        args = [self.ex(a) for a in e.args]
        t = e.ty
        if name in B.SCREEN_FUNCS:
            return self.screen(name, e, args)
        if name == 'peek':
            self.peeks = True
            return self.temp('u8', f'bly_peek((i64){args[0]}, {line})')
        if name == 'poke':
            self.emit(f'bly_poke((i64){args[0]}, {self.conv(args[1], e.args[1].ty, B.BYTE)}, {line});')
            return None
        if name == 'lines':
            return self.temp('bly_lines *', f'bly_lines_new({line})')
        if name == 'input':
            return self.temp('bly_str', f'bly_input({line})')
        if name == 'grid':
            self.gname(B.Gen('grid', B.BYTE))
            return self.temp('grid_u8 *', f'bly_grid_input({line})')
        if name == 'intern':
            return self.temp('u16', f'bly_intern({args[0]}, {line})')
        if name == 'name':
            return self.temp('bly_str', f'bly_name({self.conv(args[0], e.args[0].ty, B.WORD)}, {line})')
        if name == 'chr':
            return self.temp('bly_str', f'bly_chr({args[0]})')
        if name in B.FLOAT_FUNCS:
            fn = {'ln': 'log', 'round': 'bly_round_', 'floor': 'bly_floor_'}.get(name, name)
            return self.temp('f64', f'bly_ffun("{name}", {fn}, (f64){args[0]}, {line})')
        ct = self.ctype(t)
        if name in ('min', 'max'):
            r = self.temp(ct, f'({ct}){args[0]}')
            for a in args[1:]:
                self.emit(f'if (({ct}){a} {"<" if name == "min" else ">"} {r}) {r} = ({ct}){a};')
            return r
        if t is B.FLOAT and name == 'abs':
            return self.temp('f64', f'fabs({args[0]})')
        if name == 'sign':
            return self.temp(ct, f'({ct})(({args[0]} > 0) - ({args[0]} < 0))')
        lo, hi = LIMITS[t]
        if name == 'abs':
            return self.temp(ct, f'({ct})bly_fit({args[0]} < 0 ? -(i128){args[0]} : (i128){args[0]}, {lo}, {hi}, "{t.name}", {line})')
        if name in ('gcd', 'lcm'):
            return self.temp(ct, f'({ct})bly_fit(bly_{name}128((i128){args[0]}, (i128){args[1]}), {lo}, {hi}, "{t.name}", {line})')
        if name == 'mod':
            return self.temp(ct, f'({ct})bly_mod128((i128){args[0]}, (i128){args[1]}, {line})')
        raise CGenError(f'no C for {name}()')

    def screen(self, name, e, args):
        """a screen or sound builtin: its arguments, already computed in order, as the reference's types; then one
        call into bly_zx.h, which checks them as zxgfx.py does"""
        params, ret = B.SCREEN_FUNCS[name]
        if name == 'attr' and len(args) == 2:                # attr(r, c) reads a square back
            name, params, ret = 'attr_read', [B.INT, B.INT], B.BYTE
        cargs = []
        for a, v, p in zip(e.args, args, params):
            if p == 'level':                                 # bright(true) is bright(1); a number is checked there
                cargs.append(f'(i16)({v})' if a.ty is B.BOOL else self.conv(v, a.ty, B.INT))
            elif p == 'flag':                                # inverse(1) and inverse(true) both
                cargs.append(f'(b8)({v} != 0)')
            elif isinstance(p, B.Gen):                       # udg's rows: a byte[] view, pointer and length
                view = self.temp(self.arr_view(B.BYTE), v)
                cargs += [f'{view}.p', f'{view}.n']
            else:
                cargs.append(self.conv(v, a.ty, p))
        if name not in ('cls', 'inverse', 'over', 'ticks', 'key'):
            cargs.append(str(e.line))
        call = f'bly_zx_{name}({", ".join(cargs)})'
        if ret is B.VOID:
            self.emit(call + ';')
            return None
        return self.temp(self.ctype(ret), call)

    def x_range(self, e):
        raise CGenError('a range is walked by for, or slices a str')


GRID_INPUT = '''static grid_u8 *bly_grid_input(int l) {
    i64 cols = bly_nln ? bly_lns[0].n : 0;
    grid_u8 *g = grid_u8_new(bly_nln, cols, 0, l);
    for (u32 r = 0; r < bly_nln; r++) {
        if (bly_lns[r].n != cols) {
            bly_pr_cstr("the input is not a grid: line "); bly_pr_int(r + 1); bly_pr_cstr(" is ");
            bly_pr_int(bly_lns[r].n); bly_pr_cstr(" long, not "); bly_pr_int(cols); bly_fail_end(l);
        }
        if (cols) memcpy(g->a + r * cols, bly_lns[r].p, (size_t)cols);
    }
    return g;
}'''


def compile_program(src, target='zx48'):
    decls = B.Parser(src).program()
    ck = B.Checker(decls, target)
    ck.check()
    return Gen(ck).program()


def main(argv):
    ap = argparse.ArgumentParser(prog='cgen.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog='then: cc -std=c11 -I rt program.c -lm -o program && ./program INPUT')
    ap.add_argument('program', metavar='PROGRAM.bly', help='the program; its C goes to standard output')
    ap.add_argument('--as', dest='target', choices=['zx48', 'cpm'], default='zx48',
                    help='the machine it is, as far as the program can tell (default zx48)')
    a = ap.parse_args(argv)
    try:
        src = open(a.program).read()
    except OSError as err:
        sys.exit(f'cgen.py: {a.program}: {err.strerror}')
    try:
        sys.stdout.write(compile_program(src, a.target))
    except B.BarleyError as err:
        print(err)                                   # the same words the interpreter says, on stdout
        sys.exit(1)

if __name__ == '__main__':
    main(sys.argv[1:])
