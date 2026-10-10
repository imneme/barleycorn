#!/usr/bin/env python3
"""Barley, grown up: the reference interpreter, which is the language's
specification (see ../DESIGN.md).

It parses the whole program, types every expression (integer widths decide
where arithmetic wraps or traps), then walks the tree. Every check the
design promises for a checked build happens here, always: indices,
capacities, signed overflow, division by zero, missing keys. A failure
prints "what happened at line N", as a Spectrum would, and exits with
status 1.

The screen and sound draw with ../z80/zxgfx.py into a 64K memory that peek
and poke share (the ROM at 0000h, the screen at 4000h, the UDGs at FF58h).
What's typed at the keyboard comes on stdin: ask() reads its lines, and
key() and inkey() its keys, unless stdin is a terminal, where they find none.
Not here yet: mark/release.
"""

import os, sys, re, math
from collections import deque
import heapq


def article(t):
    """a type, with its article: a word, an int, an Item"""
    name = t if isinstance(t, str) else repr(t)
    return ('an ' if name[:1].lower() in 'aeiou' else 'a ') + name


class BarleyError(Exception):
    def __init__(self, msg, line=None):
        super().__init__(msg)
        self.msg, self.line = msg, line

    def __str__(self):
        return f'{self.msg} at line {self.line}' if self.line else self.msg


# -- types -----------------------------------------------------------------------------------------------------

class Type:
    def __repr__(self):
        return self.name


class IntT(Type):
    def __init__(self, name, bits, signed):
        self.name, self.bits, self.signed = name, bits, signed
        self.lo = -(1 << (bits - 1)) if signed else 0
        self.hi = (1 << (bits - 1)) - 1 if signed else (1 << bits) - 1


BYTE, WORD, INT = IntT('byte', 8, False), IntT('word', 16, False), IntT('int', 16, True)
LONG, QUAD = IntT('long', 32, True), IntT('quad', 64, True)
DWORD = IntT('dword', 32, False)          # unsigned, as byte and word are: it wraps, for hashes and the like
INTS = {t.name: t for t in (BYTE, WORD, INT, LONG, QUAD, DWORD)}
WIDENS = {BYTE: (WORD, INT, LONG, DWORD, QUAD), WORD: (LONG, DWORD, QUAD), INT: (LONG, QUAD), LONG: (QUAD,),
          DWORD: (QUAD,)}


class Simple(Type):
    def __init__(self, name):
        self.name = name


BOOL, STR, VOID, LINES = Simple('bool'), Simple('str'), Simple('void'), Simple('lines')
FLOAT = Simple('float')                    # the machine's own: the ROM's 5-byte floats on a Spectrum
BIT = Simple('bit')                        # an element type only: reads as bool, packed 8 to a byte on the Z80
FLEX = Simple('integer constant')          # a literal (or s.int()) whose type comes from where it's used


class RecordT(Type):
    def __init__(self, name):
        self.name, self.fields, self.index = name, [], {}

    def set_fields(self, fields):
        self.fields = fields
        self.index = {f: i for i, (f, _) in enumerate(fields)}


POS = RecordT('pos')
POS.set_fields([('r', INT), ('c', INT)])


class Gen(Type):
    """array, list, queue, map, grid, range, iter: a kind and its type arguments"""

    def __init__(self, kind, *args, n=None):
        self.kind, self.args, self.n = kind, tuple(args), n
        self.name = f'{kind}[{", ".join(map(repr, args))}]' if kind != 'array' else f'{args[0]!r}[{"" if n is None else n}]'

    def __eq__(self, o):
        return isinstance(o, Gen) and o.kind == self.kind and o.args == self.args

    def __hash__(self):
        return hash((self.kind, self.args))


CONTAINERS = ('list', 'queue', 'map', 'grid')        # the generic kinds a program can make; heap and set come next


def widens(a, b):
    return a == b or b in WIDENS.get(a, ())


def is_int(t):
    return isinstance(t, IntT)


def wrap(v, t):
    m = 1 << t.bits
    v &= m - 1
    return v - m if t.signed and v > t.hi else v


def fit(v, t, line):
    """the result of arithmetic in type t: unsigned types wrap, signed types trap"""
    if t.lo <= v <= t.hi:
        return v
    if t.signed:
        raise BarleyError(f'{t.name} overflow', line)
    return wrap(v, t)


def zero(t):
    if is_int(t):
        return 0
    if t is BOOL or t is BIT:
        return False
    if t is FLOAT:
        return 0.0
    if t is STR:
        return b''
    if isinstance(t, RecordT):
        return tuple(zero(ft) for _, ft in t.fields)
    if isinstance(t, Gen) and t.kind == 'array':
        return [zero(t.args[0]) for _ in range(t.n)]
    return None


# -- lexer -----------------------------------------------------------------------------------------------------

KEYWORDS = {'const', 'var', 'func', 'record', 'end', 'if', 'then', 'elif', 'else', 'while', 'do', 'for', 'in',
            'break', 'continue', 'return', 'case', 'when', 'and', 'or', 'not', 'print', 'assert',
            'true', 'false', 'asm'}
OPS = ['<<=', '>>=', '..', '**', '<<', '>>', '==', '!=', '<=', '>=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=',
       '+', '-', '*', '/', '%', '&', '|', '^', '~', '<', '>', '=', '(', ')', '[', ']', '{', '}', ',', ':', ';', '.']
CONTINUES = {'<<', '>>', '==', '!=', '<=', '>=', '+', '-', '*', '/', '%', '&', '|', '^', '~', '<', '>', '=',
             '..', 'and', 'or', 'not', '(', '[', '{', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '<<=', '>>='}
OPERAND_END = ('num', 'float', 'name', 'str', 'char')
ESCAPES = {'n': 10, 't': 9, 'r': 13, '0': 0, '\\': 92, "'": 39, '"': 34}


class Tok:
    def __init__(self, kind, val, line):
        self.kind, self.val, self.line = kind, val, line

    def __repr__(self):
        return f'{self.kind}:{self.val!r}'


def unescape(body, line):
    out, i = bytearray(), 0
    while i < len(body):
        ch = body[i]
        if ord(ch) > 126 or (ord(ch) < 32 and ch != '\t'):
            raise BarleyError(f'string literals are ASCII: U+{ord(ch):04X} needs an escape such as \\x{ord(ch):02X}', line)
        if ch != '\\':
            out.append(ord(ch))
            i += 1
            continue
        e = body[i + 1]
        if e == 'x':
            out.append(int(body[i + 2:i + 4], 16))
            i += 4
        elif e in ESCAPES:
            out.append(ESCAPES[e])
            i += 2
        else:
            raise BarleyError(f'unknown escape \\{e}', line)
    return bytes(out)


def lex(src):
    toks, line, depth, i = [], 1, 0, 0
    opre = '|'.join(re.escape(o) for o in OPS)
    pat = re.compile(rf"""(?P<ws>[ \t\r]+) | (?P<comment>--[^\n]*) | (?P<nl>\n)
      | (?P<hex>(?:0x|\$)[0-9A-Fa-f]+) | (?P<bin>(?:0b|%)[01]+)
      | (?P<float>[0-9]+\.[0-9]+(?:[eE][-+]?[0-9]+)?|[0-9]+[eE][-+]?[0-9]+) | (?P<num>[0-9]+)
      | (?P<char>'(?:[^'\\]|\\x[0-9A-Fa-f]{{2}}|\\.)') | (?P<str>"(?:[^"\\\n]|\\.)*")
      | (?P<name>[A-Za-z_][A-Za-z_0-9]*) | (?P<op>{opre})""", re.X)
    while i < len(src):
        m = pat.match(src, i)
        if not m:
            raise BarleyError(f'unexpected character {src[i]!r}', line)
        kind, text = m.lastgroup, m.group()
        prev = toks[-1] if toks else None
        if kind == 'bin' and text.startswith('%') and prev and (prev.kind in OPERAND_END or prev.val in (')', ']')):
            kind, text = 'op', '%'                     # a % after an operand is the operator, not binary 0b...
            m = re.compile(r'%').match(src, i)
        i = m.end()
        if kind in ('ws', 'comment'):
            continue
        if kind == 'nl':
            if depth == 0 and toks and toks[-1].kind != 'nl' and toks[-1].val not in CONTINUES:
                toks.append(Tok('nl', '\n', line))
            line += 1
            continue
        if kind == 'hex':
            toks.append(Tok('num', int(text[2:] if text.startswith('0x') else text[1:], 16), line))
        elif kind == 'bin':
            toks.append(Tok('num', int(text[2:] if text.startswith('0b') else text[1:], 2), line))
        elif kind == 'num':
            toks.append(Tok('num', int(text), line))
        elif kind == 'float':
            toks.append(Tok('float', float(text), line))
        elif kind == 'char':
            b = unescape(text[1:-1], line)
            toks.append(Tok('char', b[0], line))
        elif kind == 'str':
            toks.append(Tok('str', unescape(text[1:-1], line), line))
        elif kind == 'name':
            toks.append(Tok('kw' if text in KEYWORDS else 'name', text, line))
        else:
            if text in '([{':
                depth += 1
            elif text in ')]}':
                depth -= 1
            toks.append(Tok('op', text, line))
    toks.append(Tok('nl', '\n', line))
    toks.append(Tok('eof', None, line))
    return toks


# -- syntax tree -------------------------------------------------------------------------------------------------

class N:
    """a node: k is its kind; the rest are fields. The checker adds ty (and cval for constants)."""

    def __init__(self, k, line, **kw):
        self.k, self.line, self.ty, self.cval = k, line, None, None
        self.__dict__.update(kw)

    def __repr__(self):
        return f'N({self.k}, {", ".join(f"{a}={b!r}" for a, b in self.__dict__.items() if a not in ("k", "line"))})'


GENERIC_KINDS = ('list', 'queue', 'map', 'grid', 'heap', 'set')
BLOCK_END = ('end', 'elif', 'else', 'when')


class Parser:
    def __init__(self, src):
        self.toks, self.i = lex(src), 0

    @property
    def t(self):
        return self.toks[self.i]

    def peek(self, n=1):
        return self.toks[self.i + n]

    def at(self, val, kind=None):
        t = self.t
        return t.val == val and (kind is None or t.kind == kind) and t.kind != 'str'

    def next(self):
        t = self.t
        self.i += 1
        return t

    def expect(self, val):
        if not self.at(val):
            raise BarleyError(f'expected {val!r} but found {self.describe()}', self.t.line)
        return self.next()

    def describe(self):
        t = self.t
        return {'nl': 'the end of the line', 'eof': 'the end of the file'}.get(t.kind, repr(t.val))

    def name(self):
        if self.t.kind != 'name':
            raise BarleyError(f'expected a name but found {self.describe()}', self.t.line)
        return self.next().val

    def skip_nl(self):
        while self.t.kind == 'nl' or self.at(';', 'op'):
            self.next()

    def end_stmt(self):
        if self.t.kind == 'nl' or self.at(';', 'op'):
            self.next()
        elif not (self.t.kind == 'kw' and self.t.val in BLOCK_END) and self.t.kind != 'eof':
            raise BarleyError(f'expected the end of the statement but found {self.describe()}', self.t.line)

    # -- program
    def program(self):
        decls = []
        self.skip_nl()
        while self.t.kind != 'eof':
            line = self.t.line
            if self.at('const', 'kw'):
                self.next()
                name = self.name()
                ty = self.type_() if self.at(':') and self.next() else None
                self.expect('=')
                decls.append(N('const', line, name=name, tyx=ty, e=self.expr()))
            elif self.at('var', 'kw'):
                decls.append(self.var())
            elif self.at('func', 'kw'):
                decls.append(self.func())
            elif self.at('record', 'kw'):
                decls.append(self.record())
            else:
                raise BarleyError(f'expected const, var, func or record but found {self.describe()}', line)
            self.end_stmt()
            self.skip_nl()
        return decls

    def var(self):
        line = self.expect('var').line
        name = self.name()
        ty = None
        if self.at(':'):
            self.next()
            ty = self.type_()
        e = None
        if self.at('='):
            self.next()
            e = self.expr()
        return N('var', line, name=name, tyx=ty, e=e)

    def record(self):
        line = self.expect('record').line
        name = self.name()
        fields = []
        self.skip_nl()
        while not self.at('end', 'kw'):
            names = [self.name()]
            while self.at(','):
                self.next()
                names.append(self.name())
            self.expect(':')
            ty = self.type_()
            fields += [(n, ty) for n in names]
            self.skip_nl()
        self.expect('end')
        return N('record', line, name=name, fields=fields)

    def func(self):
        line = self.expect('func').line
        name = self.name()
        self.expect('(')
        params = []
        while not self.at(')'):
            pname = self.name()
            self.expect(':')
            params.append((pname, self.type_()))
            if not self.at(')'):
                self.expect(',')
        self.expect(')')
        ret = None
        if self.at(':'):
            self.next()
            ret = self.type_()
        body = self.block()
        asm = None
        if self.at('asm', 'kw'):
            self.next()
            if self.t.kind != 'str':
                raise BarleyError('asm takes a file name in quotes', self.t.line)
            asm = self.next().val.decode()
            self.skip_nl()
        self.expect('end')
        return N('func', line, name=name, params=params, retx=ret, body=body, asm=asm)

    def type_(self):
        line = self.t.line
        name = self.name()
        if name in GENERIC_KINDS:
            self.expect('[')
            args = [self.type_()]
            while self.at(','):
                self.next()
                args.append(self.type_())
            self.expect(']')
            return ('gen', name, args, line)
        if self.at('['):
            self.next()
            if self.at(']'):
                self.next()
                return ('array', ('name', name, line), None, line)
            size = self.expr()
            self.expect(']')
            return ('array', ('name', name, line), size, line)
        return ('name', name, line)

    # -- statements
    def block(self):
        stmts = []
        self.skip_nl()
        while not (self.t.kind == 'kw' and self.t.val in BLOCK_END):
            if self.t.kind == 'eof':
                raise BarleyError('the file ended inside a block: is an end missing?', self.t.line)
            stmts.append(self.stmt())
            self.skip_nl()
        return stmts

    def stmt(self):
        t, line = self.t, self.t.line
        if t.kind == 'kw':
            if t.val == 'var':
                s = self.var()
                self.end_stmt()
                return s
            if t.val == 'if':
                self.next()
                arms = [(self.expr(), self.then_block())]
                else_ = []
                while True:
                    if self.at('elif', 'kw'):
                        self.next()
                        arms.append((self.expr(), self.then_block()))
                    elif self.at('else', 'kw'):
                        self.next()
                        else_ = self.block()
                    else:
                        break
                self.expect('end')
                self.end_stmt()
                return N('if', line, arms=arms, else_=else_)
            if t.val == 'while':
                self.next()
                cond = self.expr()
                self.expect('do')
                body = self.block()
                self.expect('end')
                self.end_stmt()
                return N('while', line, cond=cond, body=body)
            if t.val == 'for':
                self.next()
                names = [self.name()]
                if self.at(','):
                    self.next()
                    names.append(self.name())
                tyx = None
                if self.at(':'):
                    self.next()
                    tyx = self.type_()
                self.expect('in')
                it = self.expr()
                self.expect('do')
                body = self.block()
                self.expect('end')
                self.end_stmt()
                return N('for', line, names=names, tyx=tyx, it=it, body=body)
            if t.val == 'case':
                self.next()
                subject = self.expr()
                self.skip_nl()
                whens, else_ = [], []
                while self.at('when', 'kw'):
                    self.next()
                    vals = [self.expr()]
                    while self.at(','):
                        self.next()
                        vals.append(self.expr())
                    whens.append((vals, self.then_block()))
                if self.at('else', 'kw'):
                    self.next()
                    else_ = self.block()
                self.expect('end')
                self.end_stmt()
                return N('case', line, e=subject, whens=whens, else_=else_)
            if t.val in ('break', 'continue'):
                self.next()
                self.end_stmt()
                return N(t.val, line)
            if t.val == 'return':
                self.next()
                e = None
                if not (self.t.kind in ('nl', 'eof') or self.at(';', 'op') or (self.t.kind == 'kw' and self.t.val in BLOCK_END)):
                    e = self.expr()
                self.end_stmt()
                return N('return', line, e=e)
            if t.val == 'assert':
                self.next()
                e = self.expr()
                self.end_stmt()
                return N('assert', line, e=e)
            if t.val == 'print':
                return self.print_()
        e = self.expr()
        if self.t.kind == 'op' and self.t.val in ('=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '<<=', '>>='):
            op = self.next().val
            s = N('assign', line, target=e, op=op[:-1] or None, e=self.expr())
        else:
            s = N('expr', line, e=e)
        self.end_stmt()
        return s

    def then_block(self):
        self.expect('then')
        return self.block()

    def print_(self):
        """BASIC's PRINT: ; joins, , moves to the next 16-column zone, a trailing ; or , keeps the line open.
        A print takes the rest of its line."""
        line = self.expect('print').line
        items, newline = [], True

        def ends():
            return self.t.kind in ('nl', 'eof') or (self.t.kind == 'kw' and self.t.val in BLOCK_END)

        while not ends():
            if self.t.kind == 'name' and self.t.val == 'at' and self.peek().kind not in ('nl', 'eof') \
                    and self.peek().val not in (';', ','):        # at is a keyword only here, as in BASIC
                self.next()
                r = self.expr()
                self.expect(',')
                items.append(('at', (r, self.expr())))
                if self.at(';', 'op') or self.at(',', 'op'):
                    self.next()
                    if ends():
                        newline = False
                continue
            items.append(('item', self.expr()))
            if self.at(';', 'op') or self.at(',', 'op'):
                sep = self.next().val
                if sep == ',':
                    items.append(('zone', None))
                if ends():
                    newline = False
            else:
                break
        if self.t.kind == 'nl':
            self.next()
        return N('print', line, items=items, newline=newline)

    # -- expressions, loosest first
    def expr(self):
        return self.or_()

    def binlevel(self, ops, sub, kw=False):
        e = sub()
        while (self.t.kind == ('kw' if kw else 'op')) and self.t.val in ops:
            t = self.next()
            e = N('bin', t.line, op=t.val, a=e, b=sub())
        return e

    def or_(self):
        return self.binlevel(('or',), self.and_, kw=True)

    def and_(self):
        return self.binlevel(('and',), self.not_, kw=True)

    def not_(self):
        if self.at('not', 'kw'):
            line = self.next().line
            return N('un', line, op='not', a=self.not_())
        return self.cmp()

    def cmp(self):
        e = self.range_()
        if (self.t.kind == 'op' and self.t.val in ('==', '!=', '<', '>', '<=', '>=')) or self.at('in', 'kw'):
            t = self.next()
            e = N('bin', t.line, op=t.val, a=e, b=self.range_())
        return e

    def range_(self):
        e = self.bitor()
        if self.at('..', 'op'):
            line = self.next().line
            e = N('range', line, a=e, b=self.bitor(), rev=False)
        return e

    def bitor(self):
        return self.binlevel(('|', '^'), self.bitand)

    def bitand(self):
        return self.binlevel(('&',), self.shift)

    def shift(self):
        return self.binlevel(('<<', '>>'), self.add)

    def add(self):
        return self.binlevel(('+', '-'), self.mul)

    def mul(self):
        return self.binlevel(('*', '/', '%'), self.unary)

    def unary(self):
        if self.at('-', 'op') or self.at('~', 'op'):
            t = self.next()
            return N('un', t.line, op=t.val, a=self.unary())
        return self.power()

    def power(self):
        e = self.postfix()
        if self.at('**', 'op'):
            t = self.next()
            return N('bin', t.line, op='**', a=e, b=self.unary())
        return e

    def args(self):
        self.expect('(')
        args = []
        while not self.at(')'):
            args.append(self.expr())
            if not self.at(')'):
                self.expect(',')
        self.expect(')')
        return args

    def postfix(self):
        e = self.primary()
        while True:
            if self.at('(', 'op') and e.k == 'name':
                e = N('call', e.line, name=e.name, args=self.args())
            elif self.at('[', 'op'):
                line = self.next().line
                idx = [self.expr()]
                while self.at(','):
                    self.next()
                    idx.append(self.expr())
                self.expect(']')
                e = N('index', line, obj=e, idx=idx)
            elif self.at('.', 'op'):
                line = self.next().line
                name = self.name()
                args = self.args() if self.at('(', 'op') else None
                e = N('dot', line, obj=e, name=name, args=args)
            else:
                return e

    def primary(self):
        t = self.t
        if t.kind == 'num':
            self.next()
            return N('num', t.line, v=t.val)
        if t.kind == 'float':
            self.next()
            return N('float', t.line, v=t.val)
        if t.kind == 'char':
            self.next()
            return N('char', t.line, v=t.val)
        if t.kind == 'str':
            self.next()
            return N('str', t.line, v=t.val)
        if self.at('true', 'kw') or self.at('false', 'kw'):
            self.next()
            return N('bool', t.line, v=t.val == 'true')
        if self.at('(', 'op'):
            self.next()
            e = self.expr()
            self.expect(')')
            return e
        if t.kind == 'name':
            self.next()
            if t.val in GENERIC_KINDS and self.at('[', 'op'):
                self.next()
                targs = [self.type_()]
                while self.at(','):
                    self.next()
                    targs.append(self.type_())
                self.expect(']')
                return N('new', t.line, kind=t.val, targs=targs, args=self.args())
            return N('name', t.line, name=t.val)
        raise BarleyError(f'expected a value but found {self.describe()}', t.line)


# -- checker -----------------------------------------------------------------------------------------------------

class Var:
    def __init__(self, name, ty, where, const=False, loop=False, cval=None):
        self.name, self.ty, self.where, self.const, self.loop, self.cval = name, ty, where, const, loop, cval


SCREEN_FUNCS = {                                   # the Spectrum's screen and sound (z80/zxgfx.py is their meaning)
    'cls': ([], VOID), 'ink': ([INT], VOID), 'paper': ([INT], VOID), 'border': ([INT], VOID),
    'bright': (['level'], VOID), 'flash': (['level'], VOID), 'inverse': (['flag'], VOID), 'over': (['flag'], VOID),
    'plot': ([INT, INT], VOID), 'line': ([INT] * 4, VOID), 'circle': ([INT] * 3, VOID),
    'point': ([INT, INT], BOOL), 'attr': ([INT, INT, BYTE], VOID), 'udg': ([INT, Gen('array', BYTE, n=None)], VOID),
    'key': ([], BYTE), 'inkey': ([], BYTE), 'ticks': ([], LONG), 'pause': ([INT], VOID), 'beep': ([INT, INT], VOID)}
MACHINE_FUNCS = {                                  # the machine's 64K: an address is any whole number, as an index is
    'peek': (['addr'], BYTE), 'poke': (['addr', BYTE], VOID),
    'inp': (['port'], BYTE), 'outp': (['port', BYTE], VOID)}   # and its ports (IN and OUT), numbered the same way
FLOAT_FUNCS = {'sqrt': math.sqrt, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan, 'asin': math.asin,
               'acos': math.acos, 'atan': math.atan, 'ln': math.log, 'exp': math.exp,
               'trunc': lambda x: float(math.trunc(x)), 'floor': lambda x: float(math.floor(x)),
               'round': lambda x: float(math.floor(x + 0.5))}
BUILTIN_FUNCS = {'lines', 'grid', 'input', 'intern', 'name', 'chr', 'min', 'max', 'abs', 'sign', 'gcd', 'lcm', 'mod',
                 'rev', 'pos', 'ask'}
TARGET_CONSTS = ('ZX', 'CPM', 'C')


class Checker:
    def __init__(self, decls, target):
        self.decls, self.target = decls, target
        self.records, self.funcs, self.globals = {}, {}, {}
        self.scopes, self.func = [], None
        for t in TARGET_CONSTS:
            self.globals[t] = Var(t, BOOL, 'const', const=True, cval=(t == {'zx48': 'ZX', 'cpm': 'CPM'}[target]))
        self.globals['dirs4'] = Var('dirs4', Gen('array', POS, n=4), 'const', const=True,
                                    cval=[(-1, 0), (0, 1), (1, 0), (0, -1)])
        self.globals['dirs8'] = Var('dirs8', Gen('array', POS, n=8), 'const', const=True,
                                    cval=[(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)])

    # -- types from syntax
    def ty(self, tx):
        kind = tx[0]
        if kind == 'name':
            _, name, line = tx
            if name in INTS:
                return INTS[name]
            if name == 'bool':
                return BOOL
            if name == 'bit':
                return BIT
            if name == 'float':
                return FLOAT
            if name == 'str':
                return STR
            if name == 'pos':
                return POS
            if name in self.records:
                return self.records[name]
            raise BarleyError(f'unknown type {name}', line)
        if kind == 'array':
            _, elem, size, line = tx
            et = self.ty(elem)
            if size is None:
                return Gen('array', et, n=None)
            n = self.const_int(size)
            if n <= 0:
                raise BarleyError('an array needs at least one element', line)
            if n > 65535:                             # its .len is a word, as a container's is
                raise BarleyError('an array holds at most 65535', line)
            return Gen('array', et, n=n)
        _, gkind, args, line = tx
        targs = [self.ty(a) for a in args]
        want = 2 if gkind == 'map' else 1
        if BIT in targs and gkind not in ('grid', 'list'):
            raise BarleyError('bit is for arrays, lists and grids', line)
        if len(targs) != want:
            raise BarleyError(f'{gkind} takes {want} type argument{"s" * (want > 1)}', line)
        if gkind in ('map', 'set') and not (is_int(targs[0]) or targs[0] is POS):
            raise BarleyError(f'a {gkind} key is a number or a pos (intern makes names into numbers)', line)
        return Gen(gkind, *targs)

    def const_int(self, e):
        t = self.expr(e)
        if e.cval is None or not (is_int(t) or t is FLEX):
            raise BarleyError('this has to be a constant', e.line)
        return e.cval

    # -- scopes
    def lookup(self, name, line):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        if name in self.globals:
            return self.globals[name]
        raise BarleyError(f'{name} is not defined', line)

    def declare(self, var, line):
        for scope in self.scopes:
            if var.name in scope:
                raise BarleyError(f'{var.name} is already defined in this function', line)
        if var.name in self.globals and self.globals[var.name].where != 'const':
            pass                                        # a local may shadow a global variable? no:
        if var.name in self.globals and var.name not in TARGET_CONSTS and self.globals[var.name].where == 'global':
            raise BarleyError(f'{var.name} is already a global', line)
        self.scopes[-1][var.name] = var

    # -- the program
    def check(self):
        for d in self.decls:
            if d.k == 'record':
                if d.name in self.records:
                    raise BarleyError(f'record {d.name} is defined twice', d.line)
                self.records[d.name] = RecordT(d.name)
        for d in self.decls:
            if d.k == 'record':
                self.records[d.name].set_fields([(f, self.ty(tx)) for f, tx in d.fields])
            elif d.k == 'func':
                if d.name in self.funcs:
                    raise BarleyError(f'func {d.name} is defined twice', d.line)
                d.ptys = [self.ty(tx) for _, tx in d.params]
                d.rty = self.ty(d.retx) if d.retx else VOID
                self.funcs[d.name] = d
        for d in self.decls:
            if d.k == 'const' and self.is_table(d.e):
                if d.name in self.globals:
                    raise BarleyError(f'{d.name} is defined twice', d.line)
                self.globals[d.name] = self.table(d)
                continue
            if d.k == 'const':
                t = self.expr(d.e)
                if d.e.k == 'str':                    # a string constant: each use becomes the literal itself
                    self.globals[d.name] = Var(d.name, STR, 'const', const=True)
                    self.globals[d.name].sval = d.e.v
                    continue
                if d.tyx:
                    t = self.ty(d.tyx)
                    self.coerce(d.e, t)
                    self.fold_shift(d.e)
                if d.e.cval is None:
                    if t is FLEX:                     # a literal shifted, with no type to settle in
                        raise BarleyError(f'const {d.name} needs a type to shift in: const {d.name}: long = ...',
                                          d.line)
                    raise BarleyError(f'const {d.name} has to be a constant', d.line)
                self.globals[d.name] = Var(d.name, t, 'const', const=True, cval=d.e.cval)
            elif d.k == 'var':
                self.scopes = [{}]
                d.ty = self.var_type(d)
                self.scopes = []
                if d.name in self.globals:
                    raise BarleyError(f'{d.name} is defined twice', d.line)
                self.globals[d.name] = Var(d.name, d.ty, 'global')
        if 'main' not in self.funcs:
            raise BarleyError('there is no func main()')
        for d in self.decls:
            if d.k == 'func':
                self.func = d
                self.scopes = [{}]
                for (pname, _), pty in zip(d.params, d.ptys):
                    if is_int(pty) or pty in (BOOL, STR, FLOAT) or isinstance(pty, RecordT) or isinstance(pty, Gen):
                        self.declare(Var(pname, pty, 'local'), d.line)
                self.block(d.body)
                self.scopes = []
        self.tables_unchanged()
        self.reachable = self.reach()
        if self.target == 'cpm':
            self.spectrum_only()

    # -- constant tables
    def is_table(self, e):
        """int[0, 2, 4], pos[pos(0, 1), ...], Step[Step(1, p), ...]: a type's name, indexed"""
        return (e.k == 'index' and e.obj.k == 'name' and not any(e.obj.name in sc for sc in self.scopes)
                and (e.obj.name in INTS or e.obj.name in ('bool', 'float', 'str', 'pos', 'bit')
                     or e.obj.name in self.records))

    def table(self, d):
        """const NAME = T[e1, e2, ...]: a constant array, its elements constants of type T"""
        et = self.ty(('name', d.e.obj.name, d.line))
        if et is BIT:
            raise BarleyError(f'{d.name}: a table of bits is a table of bools: bool[...]', d.line)
        if len(d.e.idx) > 65535:
            raise BarleyError(f'{d.name}: a table holds at most 65535', d.line)
        vals = [self.table_elem(el, et, d.name) for el in d.e.idx]
        d.table, d.ty = True, Gen('array', et, n=len(vals))
        return Var(d.name, d.ty, 'const', const=True, cval=vals)

    def table_elem(self, el, t, name):
        """a table element's value, as the interpreter holds it (a record is a tuple); it has to be a constant"""
        if isinstance(t, RecordT):
            rname = 'pos' if t is POS else t.name
            if el.k != 'call' or el.name != rname:
                raise BarleyError(f'{name}: each element of a {rname} table is {rname}(...)', el.line)
            if len(el.args) != len(t.fields):
                raise BarleyError(f'{rname}(...) takes {len(t.fields)} values', el.line)
            return tuple(self.table_elem(a, ft, name) for a, (_, ft) in zip(el.args, t.fields))
        self.expr(el)
        if t is STR:
            if el.k != 'str':
                raise BarleyError(f"{name}: a table's elements have to be constants", el.line)
            return el.v
        if not (is_int(t) or t in (BOOL, FLOAT)):
            raise BarleyError(f"a table's elements are numbers, bools, floats, text or records, not {article(t)}",
                              el.line)
        self.coerce(el, t)
        self.fold_shift(el)
        if el.cval is None:
            raise BarleyError(f"{name}: a table's elements have to be constants", el.line)
        return float(el.cval) if t is FLOAT else el.cval

    def fold_shift(self, e):
        """a literal shifted, its type now settled, is a constant where one is needed (a const, a table's element):
        1 << 40 in a quad. (Elsewhere it's worked out where it runs, so a shift a run never reaches can't fail.)"""
        if e.cval is None and e.k == 'bin' and e.op in ('<<', '>>') and is_int(e.ty) \
                and e.a.cval is not None and e.b.cval is not None:
            self.fold_shift(e.a)
            e.cval = arith(e.op, e.a.cval, e.b.cval, e.ty, e.line)

    def tables_unchanged(self):
        """a constant array (a table, dirs4, dirs8) passed to a function that may change that parameter is an error.
        A function may change an array parameter if it assigns into it, sorts it, or passes it on to a function
        that may change it (worked out to a fixed point)"""
        def nodes(x):
            if isinstance(x, (list, tuple)):
                for v in x:
                    yield from nodes(v)
            elif isinstance(x, N):
                yield x
                for k, v in x.__dict__.items():
                    if k not in ('func', 'var', 'ty', 'record', 'cast', 'opnode', 'cval'):
                        yield from nodes(v)

        def root(e):
            while e.k in ('index', 'dot'):
                e = e.obj
            return e

        writes, passes, calls = {n: set() for n in self.funcs}, [], []
        for name, f in self.funcs.items():
            arrays = {p: i for i, ((p, _), t) in enumerate(zip(f.params, f.ptys))
                      if isinstance(t, Gen) and t.kind == 'array'}
            for x in nodes(f.body):
                if x.k == 'assign' and x.target.k != 'name':
                    r = root(x.target)
                    if r.k == 'name' and r.name in arrays:
                        writes[name].add(arrays[r.name])
                elif x.k == 'dot' and x.name == 'sort' and x.obj.k == 'name' and x.obj.name in arrays:
                    writes[name].add(arrays[x.obj.name])
                elif x.k == 'call' and getattr(x, 'func', None) is not None:
                    calls.append(x)
                    for j, a in enumerate(x.args):
                        if a.k == 'name' and a.name in arrays:
                            passes.append((name, arrays[a.name], x.func.name, j))
        changed = True
        while changed:
            changed = False
            for f, i, g, j in passes:
                if j in writes[g] and i not in writes[f]:
                    writes[f].add(i)
                    changed = True
        for d in self.decls:
            if d.k == 'var' and d.e is not None:
                calls += [x for x in nodes(d.e) if x.k == 'call' and getattr(x, 'func', None) is not None]
        for c in calls:
            for j, a in enumerate(c.args):
                if a.k == 'name' and getattr(a, 'var', None) is not None and a.var.const and j in writes[c.func.name]:
                    pname = c.func.params[j][0]
                    raise BarleyError(f"{a.name} is a constant table, and {c.func.name}() may change its {pname}",
                                      c.line)

    # -- what this target can reach
    def walk_live(self, x, visit):
        """call visit(node) on every node a run can reach on this target: a branch that folds away here (if ZX on
        CP/M, say), and a constant expression's parts (false and f()), are skipped"""
        if isinstance(x, (list, tuple)):
            for v in x:
                self.walk_live(v, visit)
            return
        if not isinstance(x, N):
            return
        if getattr(x, 'cval', None) is not None and x.k != 'name':
            return
        visit(x)
        if x.k == 'if':
            for cond, body in x.arms:
                if cond.cval is not None and not cond.cval:
                    continue
                self.walk_live(cond, visit)
                self.walk_live(body, visit)
                if cond.cval:
                    return                            # a true arm: nothing after it can run
            self.walk_live(x.else_, visit)
            return
        if x.k == 'while' and x.cond.cval is not None and not x.cond.cval:
            return
        for k, v in x.__dict__.items():
            if k not in ('func', 'var', 'ty', 'record', 'cast', 'opnode', 'cval'):
                self.walk_live(v, visit)

    def reach(self):
        """the functions a run can reach on this target, from main and the globals' first values"""
        seen, todo = set(), ['main']
        def calls(node):
            if node.k == 'call' and getattr(node, 'func', None) is not None and node.func.name not in seen:
                todo.append(node.func.name)
        for d in self.decls:
            if d.k == 'var' and d.e is not None:
                self.walk_live(d.e, calls)
        while todo:
            name = todo.pop()
            if name in seen:
                continue
            seen.add(name)
            self.walk_live(self.funcs[name].body, calls)
        return seen

    def spectrum_only(self):
        """on CP/M, the screen and sound are an error wherever a run can reach them: the same rule in the interpreter
        (--as cpm) and every compiler, said at the line"""
        found = []
        def visit(node):
            if node.k == 'call' and (getattr(node, 'name', None) in SCREEN_FUNCS or getattr(node, 'name', None)
                                     in MACHINE_FUNCS) and not hasattr(node, 'func'):
                found.append((node.line, f'{node.name}()'))
            elif node.k == 'print' and any(kind == 'at' for kind, _ in node.items):
                found.append((node.line, 'print at'))
        for d in self.decls:
            if d.k == 'var' and d.e is not None:
                self.walk_live(d.e, visit)
        for name in sorted(self.reachable, key=lambda n: self.funcs[n].line):
            self.walk_live(self.funcs[name].body, visit)
        if found:
            line, what = min(found)
            raise BarleyError(f'{what} is Spectrum-only: put it inside if ZX then ... end', line)

    def var_type(self, d):
        if d.tyx:
            t = self.ty(d.tyx)
            if t is BIT:
                raise BarleyError('bit is an element type: a bit variable is a bool', d.line)
            if isinstance(t, Gen) and t.kind == 'array' and t.n is None:
                raise BarleyError('an array variable needs a size: T[N]', d.line)
            if d.e is not None:
                self.coerce(d.e, t)
            elif isinstance(t, Gen) and t.kind != 'array':
                raise BarleyError(f'a {t.kind} needs making, with its capacity: {t.kind}[...](n)', d.line)
            return t
        if d.e is None:
            raise BarleyError(f'var {d.name} needs a type or a value', d.line)
        t = self.expr(d.e)
        if t is FLEX:
            t = self.settle_default(d.e)
        if t is VOID:
            raise BarleyError('that has no value', d.line)
        if isinstance(t, Gen) and t.kind in ('iter', 'range'):
            raise BarleyError('split(), ints() and ranges are walked by for, directly', d.line)
        return t

    # -- statements
    def block(self, stmts):
        self.scopes.append({})
        for s in stmts:
            self.stmt(s)
        self.scopes.pop()

    def stmt(self, s):
        k = s.k
        if k == 'var':
            s.ty = self.var_type(s)
            if isinstance(s.ty, Gen) and s.ty.kind == 'array' and self.func is not None:
                pass                                    # local arrays: fine where a function isn't recursive
            self.declare(Var(s.name, s.ty, 'local'), s.line)
        elif k == 'assign':
            self.assign(s)
        elif k == 'expr':
            t = self.expr(s.e)
            if s.e.k not in ('call', 'dot'):
                raise BarleyError('this value is computed and then thrown away', s.line)
            if t is FLEX:
                self.settle_default(s.e)
        elif k == 'if':
            for cond, body in s.arms:
                self.want_bool(cond)
                self.block(body)
            self.block(s.else_)
        elif k == 'while':
            self.want_bool(s.cond)
            self.block(s.body)
        elif k == 'for':
            self.for_(s)
        elif k == 'case':
            t = self.expr(s.e)
            if t is FLEX:
                t = self.settle_default(s.e)
            if not (is_int(t) or t is BOOL):
                raise BarleyError('case works on numbers and bytes', s.line)
            for vals, body in s.whens:
                for v in vals:
                    self.expr(v)
                    if v.cval is None:
                        raise BarleyError('a when needs constants', v.line)
                    self.coerce(v, t)
                self.block(body)
            self.block(s.else_)
        elif k in ('break', 'continue'):
            pass
        elif k == 'return':
            rty = self.func.rty
            if s.e is None:
                if rty is not VOID:
                    raise BarleyError(f'{self.func.name} must return {article(rty)}', s.line)
            else:
                if rty is VOID:
                    raise BarleyError(f'{self.func.name} returns nothing', s.line)
                self.expr(s.e)
                self.coerce(s.e, rty)
        elif k == 'assert':
            self.want_bool(s.e)
        elif k == 'print':
            for kind, e in s.items:
                if kind == 'at':
                    for x in e:
                        self.expr(x)
                        self.coerce(x, INT)
                    continue
                if kind == 'item':
                    t = self.expr(e)
                    if t is FLEX:
                        self.settle_default(e)
                    elif t is VOID or isinstance(t, Gen):
                        raise BarleyError(f"print can't show {article(t)}", e.line)
        else:
            raise BarleyError(f'unknown statement {k}', s.line)

    def want_bool(self, e):
        if self.expr(e) is not BOOL:
            raise BarleyError(f'this needs to be true or false, not a {e.ty!r}', e.line)

    def assign(self, s):
        tt = self.lvalue(s.target)
        if s.op is None:
            self.expr(s.e)
            self.coerce(s.e, tt)
        else:
            op = N('bin', s.line, op=s.op, a=s.target, b=s.e)
            rt = self.binary(op, keep_a=True)
            if not widens(rt, tt):
                raise BarleyError(f'{s.op}= would make {article(rt)} but this is {article(tt)}', s.line)
            s.opnode = op

    def lvalue(self, e):
        if e.k == 'name':
            v = self.lookup(e.name, e.line)
            if v.const:
                raise BarleyError(f"{e.name} is a constant and can't be assigned", e.line)
            if v.loop:
                raise BarleyError(f'{e.name} is the loop variable; the loop owns it', e.line)
            if isinstance(v.ty, Gen) and v.ty.kind == 'array':
                raise BarleyError('a whole array can\'t be assigned; assign its elements', e.line)
            e.var, e.ty = v, v.ty
            return v.ty
        if e.k == 'index':
            t = self.expr(e)
            ot = e.obj.ty
            if ot is STR:
                raise BarleyError("a str can't be changed; it's a view of the text", e.line)
            r = e.obj                                     # (a field inside a table comes here through .lvalue)
            if r.k == 'name' and getattr(r, 'var', None) is not None and r.var.const:
                raise BarleyError(f"{r.name} is a constant table and can't be changed", e.line)
            if e.slice:
                raise BarleyError("a slice can't be assigned", e.line)
            return t
        if e.k == 'dot' and e.args is None:
            t = self.expr(e)
            if not isinstance(e.obj.ty, RecordT):
                raise BarleyError(f".{e.name} can't be assigned", e.line)
            self.lvalue(e.obj)
            return t
        raise BarleyError("that can't be assigned to", e.line)

    def for_(self, s):
        t = self.expr(s.it)
        decl = self.ty(s.tyx) if s.tyx else None
        names = s.names
        if isinstance(t, Gen) and t.kind == 'map':
            vts = [t.args[0], t.args[1]][:len(names)]
        elif len(names) == 2:
            raise BarleyError('two loop variables walk a map: for k, v in m', s.line)
        elif isinstance(t, Gen) and t.kind == 'range':
            vts = [t.args[0]]
        elif isinstance(t, Gen) and t.kind in ('array', 'list', 'queue', 'set'):
            vts = [BOOL if t.args[0] is BIT else t.args[0]]
        elif isinstance(t, Gen) and t.kind == 'heap':
            raise BarleyError("a heap can't be walked in order; pop it", s.line)
        elif isinstance(t, Gen) and t.kind == 'grid':
            vts = [POS]
        elif isinstance(t, Gen) and t.kind == 'iter':
            vts = [t.args[0]]
        elif t is STR:
            vts = [BYTE]
        elif t is LINES:
            vts = [STR]
        else:
            raise BarleyError(f"for can't walk {article(t)}", s.line)
        if decl is not None:
            if vts[0] is FLEX:
                if not is_int(decl):
                    raise BarleyError('these are numbers', s.line)
                vts[0] = decl
            elif vts[0] != decl:
                raise BarleyError(f'the loop variable is a {vts[0]!r}', s.line)
        if vts[0] is FLEX:
            vts[0] = LONG
        s.vtys = vts
        if isinstance(t, Gen) and t.kind == 'iter':
            s.it.elem = vts[0]
        self.scopes.append({})
        for name, vt in zip(names, vts):
            self.declare(Var(name, vt, 'local', loop=True), s.line)
        self.block(s.body)
        self.scopes.pop()

    # -- expressions
    def settle(self, e, t):
        """give a flexible constant (or s.int(), or a literal shifted) the type t"""
        if e.k == 'bin' and e.op in ('<<', '>>') and e.ty is FLEX:
            if not is_int(t):
                raise BarleyError(f'a number where {article(t)} is needed', e.line)
            self.settle(e.a, t)
            e.ty = t
            return t
        if t is FLOAT and e.cval is not None:
            e.ty, e.cval = FLOAT, float(e.cval)
            return FLOAT
        if not is_int(t):
            raise BarleyError(f'a number where {article(t)} is needed', e.line)
        if e.cval is not None and not (t.lo <= e.cval <= t.hi):
            raise BarleyError(f"{e.cval} doesn't fit in {article(t.name)}", e.line)
        e.ty = t
        return t

    def settle_default(self, e):
        if e.k == 'bin' and e.op in ('<<', '>>') and e.ty is FLEX:
            return self.settle(e, self.settle_default(e.a))     # with nothing to say, as its literal would be
        if e.cval is None:
            return self.settle(e, LONG)
        for t in (INT, LONG, QUAD):
            if t.lo <= e.cval <= t.hi:
                return self.settle(e, t)
        raise BarleyError(f"{e.cval} doesn't fit in a quad", e.line)

    def coerce(self, e, t):
        et = e.ty if e.ty is not None else self.expr(e)
        if et is FLEX:
            return self.settle(e, t)
        if et == t or (is_int(et) and is_int(t) and widens(et, t)):
            return t
        if isinstance(et, Gen) and isinstance(t, Gen) and et.kind == t.kind == 'array' and et.args == t.args \
                and (t.n is None or t.n == et.n):
            return t
        raise BarleyError(f'{article(et)} where {article(t)} is needed', e.line)

    def unify(self, a, b, line):
        if widens(a, b):
            return b
        if widens(b, a):
            return a
        raise BarleyError(f'mixing {a!r} and {b!r} needs a cast: {a!r}(x) or {b!r}(x)', line)

    def flex_with(self, f, other, line):
        """a flexible operand meets a typed one"""
        v = f.cval
        if v is None and f.k == 'bin' and f.op in ('<<', '>>'):
            v = f.a.cval                              # a literal shifted fits where its literal does
        if v is None or other.lo <= v <= other.hi:
            return self.settle(f, other)
        for t in (INT, LONG, QUAD):
            if widens(other, t) and t.lo <= v <= t.hi:
                self.settle(f, t)
                return t
        raise BarleyError(f"{v} doesn't fit with {article(other)}", line)

    def expr(self, e):
        t = getattr(self, 'x_' + e.k)(e)
        e.ty = t
        return t

    def x_num(self, e):
        e.cval = e.v
        return FLEX

    def x_float(self, e):
        e.cval = e.v
        return FLOAT

    def x_char(self, e):
        e.cval = e.v
        return BYTE

    def x_str(self, e):
        return STR

    def x_bool(self, e):
        e.cval = e.v
        return BOOL

    def x_name(self, e):
        v = self.lookup(e.name, e.line)
        if v.const and hasattr(v, 'sval'):           # a string constant is its literal, everywhere it's used
            e.k, e.v = 'str', v.sval
            return STR
        e.var = v
        if v.const:
            e.cval = v.cval
        return v.ty

    def x_range(self, e):
        ta, tb = self.expr(e.a), self.expr(e.b)
        t = self.arith_type(e.a, e.b, ta, tb, e.line)
        if t is FLEX:
            t = self.unify(self.settle_default(e.a), self.settle_default(e.b), e.line)
        if not is_int(t):
            raise BarleyError('a range is made of numbers', e.line)
        return Gen('range', t)

    def arith_type(self, a, b, ta, tb, line):
        if FLOAT in (ta, tb):
            for x, tx in ((a, ta), (b, tb)):
                if tx is FLEX and x.cval is not None:
                    self.settle(x, FLOAT)
                elif tx is not FLOAT:
                    raise BarleyError(f'mixing float and {tx!r} needs a conversion: float(x), or a cast such as int(x)', line)
            return FLOAT
        if ta is FLEX and tb is FLEX:
            if a.cval is None or b.cval is None:
                self.settle_default(a)
                self.settle_default(b)
                return self.unify(a.ty, b.ty, line)
            return FLEX
        if ta is FLEX:
            if not is_int(tb):
                raise BarleyError(f'a number with {article(tb)}', line)
            return self.flex_with(a, tb, line)
        if tb is FLEX:
            if not is_int(ta):
                raise BarleyError(f'{article(ta)} with a number', line)
            return self.flex_with(b, ta, line)
        if is_int(ta) and is_int(tb):
            return self.unify(ta, tb, line)
        raise BarleyError(f"can't do arithmetic with {article(ta)} and {article(tb)}", line)

    def x_bin(self, e):
        return self.binary(e)

    def binary(self, e, keep_a=False):
        op = e.op
        if op in ('and', 'or'):
            self.want_bool(e.a)
            self.want_bool(e.b)
            if e.a.cval is not None:                  # a constant on the left decides, or hands over to the right:
                if (op == 'and') != bool(e.a.cval):   # so `if ZX and x > 2` folds away where ZX is false, and the
                    e.cval = bool(e.a.cval)           # right side is never evaluated, as at run time
                elif e.b.cval is not None:
                    e.cval = bool(e.b.cval)
            e.ty = BOOL
            return BOOL
        if op == 'in':
            tb = self.expr(e.b)
            self.expr(e.a)
            if not (isinstance(tb, Gen) and tb.kind in ('map', 'set')):
                raise BarleyError('in asks a map or a set whether it holds a key', e.line)
            self.coerce(e.a, tb.args[0])
            e.ty = BOOL
            return BOOL
        ta = e.a.ty if keep_a else self.expr(e.a)
        tb = self.expr(e.b)
        if op in ('==', '!=', '<', '>', '<=', '>='):
            if (is_int(ta) or ta in (FLEX, FLOAT)) and (is_int(tb) or tb in (FLEX, FLOAT)):
                self.arith_type(e.a, e.b, ta, tb, e.line)
                if e.a.cval is not None and e.b.cval is not None:
                    e.cval = compare(op, e.a.cval, e.b.cval)
            elif ta != tb or not (ta in (BOOL, STR) or isinstance(ta, RecordT)):
                raise BarleyError(f"can't compare {article(ta)} with {article(tb)}", e.line)
            elif ta is BOOL and op not in ('==', '!='):
                raise BarleyError('true and false are equal or not; they have no order', e.line)
            e.ty = BOOL
            return BOOL
        if op in ('<<', '>>'):
            if tb is FLEX:
                self.settle_default(e.b)
            if ta is FLEX and e.a.cval is not None:   # a literal shifted takes its type from where it's used, as a
                if not is_int(e.b.ty):                # literal does: w |= 1 << d makes a word
                    raise BarleyError('shifts are for numbers', e.line)
                e.ty = FLEX
                return FLEX
            if ta is FLEX:
                ta = self.settle_default(e.a)
            if not (is_int(ta) and is_int(e.b.ty)):
                raise BarleyError('shifts are for numbers', e.line)
            e.ty = ta
            return ta
        if ta is POS and tb is POS and op in ('+', '-'):
            e.ty = POS
            return POS
        if op == '**' and FLOAT not in (ta, tb):
            if ta is FLEX and tb is FLEX and e.a.cval is not None and e.b.cval is not None:
                self.settle(e.a, FLOAT)
            else:
                raise BarleyError('** is for floats: float(x) ** y', e.line)
        t = self.arith_type(e.a, e.b, ta, tb, e.line)
        if t is FLOAT and op in ('%', '&', '|', '^'):
            raise BarleyError(f'{op} is for whole numbers', e.line)
        if t is FLEX:
            e.cval = arith(op, e.a.cval, e.b.cval, None, e.line)
        e.ty = t
        return t

    def x_un(self, e):
        t = self.expr(e.a)
        if e.op == 'not':
            if t is not BOOL:
                raise BarleyError('not needs true or false', e.line)
            if e.a.cval is not None:
                e.cval = not e.a.cval
            return BOOL
        if t is FLEX and e.a.cval is None:            # s.int(), or a literal shifted: not a constant, so it
            t = self.settle_default(e.a)              # settles as it would with nothing to say
        elif t is FLEX:
            e.cval = -e.a.cval if e.op == '-' else ~e.a.cval
            return FLEX
        if t is FLOAT and e.op == '-':
            if e.a.cval is not None:                  # a negative float literal is a constant too
                e.cval = -e.a.cval
            return t
        if not is_int(t):
            raise BarleyError(f'{e.op} is for numbers', e.line)
        return t

    def x_index(self, e):
        if self.is_table(e):
            raise BarleyError(f'{e.obj.name}[...] is a table, and a table is a const: const NAME = {e.obj.name}[...]',
                              e.line)
        ot = self.expr(e.obj)
        e.slice = False
        if ot is STR and len(e.idx) == 1 and e.idx[0].k == 'range':
            self.expr(e.idx[0])
            e.slice = True
            return STR
        if isinstance(ot, Gen) and ot.kind == 'grid':
            if len(e.idx) == 2:
                for i in e.idx:
                    self.index_int(i)
            elif len(e.idx) == 1:
                self.expr(e.idx[0])
                self.coerce(e.idx[0], POS)
            else:
                raise BarleyError('a grid takes g[p] or g[r, c]', e.line)
            return BOOL if ot.args[0] is BIT else ot.args[0]
        if len(e.idx) != 1:
            raise BarleyError('one index here', e.line)
        if isinstance(ot, Gen) and ot.kind == 'map':
            self.expr(e.idx[0])
            self.coerce(e.idx[0], ot.args[0])
            return ot.args[1]
        self.index_int(e.idx[0])
        if ot is STR:
            return BYTE
        if isinstance(ot, Gen) and ot.kind in ('array', 'list'):
            return BOOL if ot.args[0] is BIT else ot.args[0]
        raise BarleyError(f"{article(ot)} can't be indexed", e.line)

    def index_int(self, i):
        t = self.expr(i)
        if t is FLEX:
            t = self.settle_default(i)
        if not is_int(t):
            raise BarleyError(f'an index is a number, not {article(t)}', i.line)

    def x_dot(self, e):
        ot = self.expr(e.obj)
        name, args = e.name, e.args
        if args is None:                                         # a field or a property
            if isinstance(ot, RecordT):
                if name not in ot.index:
                    raise BarleyError(f'{article(ot)} has no field {name}', e.line)
                return ot.fields[ot.index[name]][1]
            if name == 'len' and (ot is STR or (isinstance(ot, Gen) and ot.kind in ('array', 'list', 'queue', 'map', 'heap', 'set'))):
                return WORD
            if name in ('rows', 'cols') and isinstance(ot, Gen) and ot.kind == 'grid':
                return INT
            raise BarleyError(f'{article(ot)} has no .{name}', e.line)
        sig = self.method_sig(ot, name, e)
        if sig is None:
            raise BarleyError(f'{article(ot)} has no .{name}()', e.line)
        if name == 'sort' and e.obj.k == 'name' and getattr(e.obj, 'var', None) is not None and e.obj.var.const:
            raise BarleyError(f"{e.obj.name} is a constant table and can't be changed", e.line)
        params, ret = sig
        if len(args) != len(params) and not (name in ('int', 'split', 'find', 'starts', 'get') and len(args) <= len(params)):
            raise BarleyError(f'.{name}() takes {len(params)} argument{"s" * (len(params) != 1)}', e.line)
        for a, p in zip(args, params):
            self.expr(a)
            if p == 'text':                                       # a byte or a str
                if a.ty is not STR and a.ty is not BYTE:
                    raise BarleyError('this wants a character or a str', a.line)
            elif p == 'int':
                if a.ty is FLEX:
                    self.settle_default(a)
                elif not is_int(a.ty):
                    raise BarleyError('this wants a number', a.line)
            else:
                self.coerce(a, p)
        if ret is FLEX:
            e.cval = None                                         # s.int(): a number whose type comes from use
        return ret

    def method_sig(self, ot, name, e):
        if ot is STR:
            return {'int': (['int'], FLEX), 'ints': ([], Gen('iter', FLEX)), 'split': (['text'], Gen('iter', STR)),
                    'find': (['text'], INT), 'starts': (['text'], BOOL), 'trim': ([], STR)}.get(name)
        if ot is LINES:
            return {'next': ([], STR)}.get(name)
        if isinstance(ot, Gen):
            el = ot.args[0]
            if ot.kind == 'array':
                return {'sort': ([], VOID)}.get(name)
            if ot.kind == 'list':
                el = BOOL if el is BIT else el
                return {'push': ([el], VOID), 'pop': ([], el), 'sort': ([], VOID), 'clear': ([], VOID)}.get(name)
            if ot.kind == 'queue':
                return {'put': ([el], VOID), 'get': ([], el)}.get(name)
            if ot.kind == 'heap':
                return {'push': ([el], VOID), 'pop': ([], el)}.get(name)
            if ot.kind == 'set':
                return {'add': ([el], VOID), 'del': ([el], VOID)}.get(name)
            if ot.kind == 'map':
                return {'get': ([el, ot.args[1]], ot.args[1]), 'del': ([el], VOID)}.get(name)
            if ot.kind == 'grid':
                return {'has': ([POS], BOOL), 'find': ([el], POS)}.get(name)
        return None

    def x_new(self, e):
        t = self.ty(('gen', e.kind, [tx for tx in e.targs], e.line))
        if e.kind == 'grid':
            if len(e.args) not in (2, 3):
                raise BarleyError('grid[T](rows, cols[, value])', e.line)
            for a in e.args[:2]:
                self.index_int(a)
            if len(e.args) == 3:
                self.expr(e.args[2])
                self.coerce(e.args[2], t.args[0])
        else:
            if len(e.args) != 1:
                raise BarleyError(f'{e.kind}[...](capacity)', e.line)
            self.index_int(e.args[0])
        return t

    def x_call(self, e):
        name, args = e.name, e.args
        f = self.funcs.get(name)
        if f is not None and not any(name in s for s in self.scopes):
            if len(args) != len(f.params):
                raise BarleyError(f'{name} takes {len(f.params)} argument{"s" * (len(f.params) != 1)}', e.line)
            for a, pt in zip(args, f.ptys):
                self.expr(a)
                self.coerce(a, pt)
            e.func = f
            return f.rty
        if name in self.records or name == 'pos':
            rt = POS if name == 'pos' else self.records[name]
            if len(args) != len(rt.fields):
                raise BarleyError(f'{name}(...) takes {len(rt.fields)} values', e.line)
            for a, (_, ft) in zip(args, rt.fields):
                self.expr(a)
                self.coerce(a, ft)
            e.record = rt
            return rt
        if name in INTS or name in ('bool', 'float'):
            if len(args) != 1:
                raise BarleyError(f'{name}(x) takes one value', e.line)
            t = self.expr(args[0])
            if t is FLEX:
                self.settle_default(args[0])
            elif not (is_int(t) or t is BOOL or (t is FLOAT and name != 'bool')):
                raise BarleyError(f"can't make {article(name)} from {article(t)}", e.line)
            e.cast = {'bool': BOOL, 'float': FLOAT}.get(name) or INTS[name]
            return e.cast
        if name in SCREEN_FUNCS or name in MACHINE_FUNCS:
            params, ret = SCREEN_FUNCS.get(name) or MACHINE_FUNCS[name]
            if name == 'attr' and len(args) == 2:                 # attr(r, c) reads a square back, as BASIC's ATTR
                params, ret = [INT, INT], BYTE
            elif name == 'attr' and len(args) != 3:
                raise BarleyError('attr takes 2 values (to read a square) or 3 (to set it)', e.line)
            if len(args) != len(params):
                raise BarleyError(f'{name} takes {len(params)} value{"s" * (len(params) != 1)}', e.line)
            for a, p in zip(args, params):
                t = self.expr(a)
                if p == 'level':                                  # bright: true or false, or 0, 1 or 8, as BASIC
                    if t is BOOL:
                        continue
                    if not (is_int(t) or t is FLEX):
                        raise BarleyError(f'{name} takes true or false, or 0, 1 or 8', a.line)
                    self.coerce(a, INT)
                elif p == 'flag':                                 # inverse(1) and inverse(true) both, as BASIC
                    if not (t is BOOL or is_int(t) or t is FLEX):
                        raise BarleyError(f'{name} takes true or false (or 0 or 1)', a.line)
                    if t is FLEX:
                        self.settle_default(a)
                elif p in ('addr', 'port'):                       # checked when it's used: 0..65536
                    if not (is_int(t) or t is FLEX):
                        raise BarleyError(f'{name} takes {"an address" if p == "addr" else "a port"}, a whole number',
                                          a.line)
                    if t is FLEX:
                        self.settle_default(a)
                else:
                    self.coerce(a, p)
            e.builtin = name
            return ret
        e.builtin = name
        tys = [self.expr(a) for a in args]
        if name in ('lines', 'grid', 'input'):
            if args:
                raise BarleyError(f'{name}() takes nothing', e.line)
            return {'lines': LINES, 'grid': Gen('grid', BYTE), 'input': STR}[name]
        if name == 'intern':
            self.one(e, STR)
            return WORD
        if name == 'ask':                                 # ask() or ask(prompt): a line typed at the keyboard
            if len(args) > 1:
                raise BarleyError('ask takes a prompt, or nothing', e.line)
            if args:
                self.coerce(args[0], STR)
            return STR
        if name == 'name':
            self.one(e, WORD)
            return STR
        if name == 'chr':
            self.one(e, BYTE)
            return STR
        if name == 'rev':
            if len(args) != 1 or not (isinstance(tys[0], Gen) and tys[0].kind == 'range'):
                raise BarleyError('rev(a..b) walks a range downwards', e.line)
            args[0].rev = True
            e.passthrough = True
            return tys[0]
        if name in FLOAT_FUNCS:
            if len(args) != 1:
                raise BarleyError(f'{name} takes one float', e.line)
            if tys[0] is FLEX and args[0].cval is not None:
                self.settle(args[0], FLOAT)
            elif tys[0] is not FLOAT:
                raise BarleyError(f'{name} is for floats: {name}(float(x))', e.line)
            return FLOAT
        if name in ('min', 'max') and FLOAT in tys:
            for a in args:
                if a.ty is FLEX and a.cval is not None:
                    self.settle(a, FLOAT)
                elif a.ty is not FLOAT:
                    raise BarleyError(f'{name} of a float and a {a.ty!r}', e.line)
            return FLOAT
        if name in ('min', 'max', 'gcd', 'lcm', 'mod'):
            if len(args) < 2 or (name != 'min' and name != 'max' and len(args) != 2):
                raise BarleyError(f'{name} takes {"two or more" if name in ("min", "max") else "two"} numbers', e.line)
            t = None
            for a in args:
                if a.ty is FLEX:
                    continue
                if not is_int(a.ty):
                    raise BarleyError(f'{name} is for numbers', a.line)
                t = a.ty if t is None else self.unify(t, a.ty, e.line)
            if t is None:
                t = INT
                for a in args:
                    t = self.unify(t, self.settle_default(a), e.line)
            for a in args:
                if a.ty is FLEX:
                    self.flex_with(a, t, e.line)
                    t = self.unify(t, a.ty, e.line)
            return t
        if name in ('abs', 'sign'):
            if len(args) != 1:
                raise BarleyError(f'{name} takes one number', e.line)
            t = tys[0] if tys[0] is not FLEX else self.settle_default(args[0])
            if t is FLOAT:
                return FLOAT if name == 'abs' else INT
            if not is_int(t):
                raise BarleyError(f'{name} is for numbers', e.line)
            return t
        raise BarleyError(f'{name} is not defined', e.line)

    def one(self, e, t):
        if len(e.args) != 1:
            raise BarleyError(f'{e.name} takes one value', e.line)
        self.coerce(e.args[0], t)


def compare(op, a, b):
    return {'==': a == b, '!=': a != b, '<': a < b, '>': a > b, '<=': a <= b, '>=': a >= b}[op]


def tdiv(a, b, line):
    if b == 0:
        raise BarleyError('division by zero', line)
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


def farith(op, a, b, line):
    """floats: whatever the machine gives (here, Python's doubles)"""
    try:
        return {'+': lambda: a + b, '-': lambda: a - b, '*': lambda: a * b, '/': lambda: a / b,
                '**': lambda: math.pow(a, b)}[op]()
    except ZeroDivisionError:
        raise BarleyError('division by zero', line)
    except OverflowError:
        raise BarleyError('float overflow', line)
    except ValueError:
        raise BarleyError(f'float {op} has no answer', line)


def arith(op, a, b, t, line):
    """exact arithmetic; t is the result type (None for a constant, settled later)"""
    if t is FLOAT or isinstance(a, float) or isinstance(b, float):
        return farith(op, a, b, line)
    if op == '+':
        r = a + b
    elif op == '-':
        r = a - b
    elif op == '*':
        r = a * b
    elif op == '/':
        r = tdiv(a, b, line)
    elif op == '%':
        r = a - b * tdiv(a, b, line)
    elif op == '&':
        r = a & b
    elif op == '|':
        r = a | b
    elif op == '^':
        r = a ^ b
    elif op in ('<<', '>>'):
        if b < 0:
            raise BarleyError('negative shift count', line)
        if op == '>>':
            return a >> b
        return wrap(a << min(b, 64), t) if t else a << b        # shifts are bit operations: they wrap
    else:
        raise BarleyError(f'unknown operator {op}', line)
    if t is None:
        return r
    if op in ('&', '|', '^'):
        return wrap(r, t)
    return fit(r, t, line)


# -- the runtime's containers and text ---------------------------------------------------------------------------

NUM_RE = re.compile(rb'\d+')


def ints_in(s):
    """every integer in s; a minus is a sign unless it follows a digit, so 2-4 is two numbers"""
    out = []
    for m in NUM_RE.finditer(s):
        v, st = int(m.group()), m.start()
        if st > 0 and s[st - 1:st] == b'-' and not (st > 1 and s[st - 2:st - 1].isdigit()):
            v = -v
        out.append(v)
    return out


class BList:
    """every container counts the changes to which items it holds (ver), so a for walking it can stop if that
    happens under it; changing an element's value isn't such a change"""

    def __init__(self, cap, kind='list'):
        self.cap, self.items, self.kind, self.ver = cap, [], kind, 0

    def push(self, v, line):
        if len(self.items) >= self.cap:
            raise BarleyError(f'{self.kind} full ({self.cap})', line)
        self.items.append(v)
        self.ver += 1


class BQueue:
    def __init__(self, cap):
        self.cap, self.items, self.ver = cap, deque(), 0


class BMap:
    """maps iterate in insertion order, so every implementation walks them the same way"""

    def __init__(self, cap):
        self.cap, self.d, self.ver = cap, {}, 0


class BHeap:
    def __init__(self, cap):
        self.cap, self.items, self.ver = cap, [], 0


class BSet:
    """sets iterate in insertion order too"""

    def __init__(self, cap):
        self.cap, self.d, self.ver = cap, {}, 0


class BGrid:
    def __init__(self, rows, cols, fill):
        self.rows, self.cols = rows, cols
        self.cells = [[fill] * cols for _ in range(rows)]

    def check(self, r, c, line):
        if not (0 <= r < self.rows and 0 <= c < self.cols):
            raise BarleyError(f'({r}, {c}) is off the grid ({self.rows} x {self.cols})', line)


class BLines:
    def __init__(self, lines):
        self.lines, self.i = lines, 0


class Range:
    def __init__(self, a, b, rev):
        self.a, self.b, self.rev = a, b, rev

    def __iter__(self):
        return iter(range(self.b - 1, self.a - 1, -1) if self.rev else range(self.a, self.b))


# -- the interpreter ---------------------------------------------------------------------------------------------

class Break(Exception):
    pass


class Continue(Exception):
    pass


class Return(Exception):
    def __init__(self, v):
        self.v = v


class Interp:
    def __init__(self, checker, text, out, need_rom=False):
        self.ck, self.out = checker, out
        self.text = text
        self.input_lines = re.split(rb'\r\n|\n|\r', text)
        if self.input_lines and self.input_lines[-1] == b'':
            self.input_lines.pop()
        for n, ln in enumerate(self.input_lines):
            if len(ln) > 65535:
                raise BarleyError(f'input line {n + 1} is longer than 65535')
        self.globals = {}
        self.interned, self.names = {}, []
        self.col = 0
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'z80'))
        import zxgfx                                       # the screen and sound's meaning
        self.zx = zxgfx
        self.machine = need_rom or checker is None or uses_machine(checker.decls)          # only then does anything need the 48K ROM
        self.screen = zxgfx.Screen() if self.machine else zxgfx.Screen(bytes(96 * 8))
        # the machine's 64K, which peek and poke see: the 48K's ROM at 0000h (poke there does nothing, as on the real
        # one), and the screen's own bytes, which the screen draws into, at 4000h (6,912) and FF58h (the 21 UDGs)
        self.memory = bytearray(65536)
        if self.machine:
            self.memory[0:0x4000] = zxgfx.rom()
        self.memory[0x4000:0x5B00] = self.screen.mem
        self.memory[0xFF58:0x10000] = self.screen.udgs
        mem = memoryview(self.memory)
        self.screen.mem, self.screen.udgs = mem[0x4000:0x5B00], mem[0xFF58:0x10000]

    def run(self):
        for d in self.ck.decls:
            if d.k == 'var':
                self.globals[d.name] = self.ev(d.e, {}) if d.e is not None else zero(d.ty)
        self.call(self.ck.funcs['main'], [])

    # -- output, as BASIC prints
    def write(self, s, screen_only=False):
        """print's text: on the virtual screen, and in the output unless it was printed at a place (screen_only)"""
        data = s.encode('latin-1')
        for ch in data:                                     # every printed byte also lands on the virtual screen
            self.screen.out(ch)
        if screen_only:
            pass
        elif hasattr(self.out, 'buffer'):                   # bytes as they are, 80h-FFh included, as C and the Z80 print
            self.out.flush()
            self.out.buffer.write(data)
        else:
            self.out.write(s)
        nl = s.rfind('\n')
        self.col = len(s) - nl - 1 if nl >= 0 else self.col + len(s)

    def ask(self, prompt, line):
        """a line typed at the keyboard (the keys: zxgfx.Keys). On the 48K, and so here and in C, the prompt and
        the typing are display, not output: the prompt goes to stderr. On CP/M there's one console, so they're
        output, taken a key at a time as cpmask.asm takes them: a printable key echoed, DELETE or backspace
        rubbing one out (echoed as backspace, space, backspace), ENTER ending the line and a newline printed;
        ^C, or the keys running out before anything's typed, is a STOP, as it is everywhere"""
        keys = self.screen.keys
        if self.ck.target != 'cpm':
            self.out.flush()                                 # what was printed first shows first
            if hasattr(self.out, 'buffer'):
                self.out.buffer.flush()
            sys.stderr.buffer.write(prompt)
            sys.stderr.flush()
            got = keys.line() if keys else None
            self.screen.asked()
            if got is None:
                raise BarleyError('STOP in ask', line)
            if len(got) > 65535:
                raise BarleyError('the line typed is longer than 65535, too long for one str', line)
            return got
        self.write(prompt.decode('latin-1'))
        got, echo = bytearray(), []
        while True:
            b = keys.stream.read(1) if keys and keys.stream else b''
            c = b[0] if b else 0x1A                          # tnylpo reads the end of stdin as 1Ah, and so do we
            if c in (13, 10) or c == 0x1A and got:
                self.write(''.join(echo) + '\n')
                if len(got) > 65535:
                    raise BarleyError('the line typed is longer than 65535, too long for one str', line)
                return bytes(got)
            if c in (3, 0x1A):
                self.write(''.join(echo))
                raise BarleyError('STOP in ask', line)
            if c in (8, 0x7F):
                if got:
                    got.pop()
                    echo.append('\b \b')
            elif c >= 32:
                got.append(c)
                echo.append(chr(c))

    def show(self, v, t):
        if t is BOOL:
            return 'true' if v else 'false'
        if t is STR:
            return v.decode('latin-1')
        if t is FLOAT:
            return f'{v if v != 0 else 0.0:.10g}'    # the ROM has no negative zero, so -0.0 prints as 0
        if isinstance(t, RecordT):
            inner = ', '.join(self.show(x, ft) for x, (_, ft) in zip(v, t.fields))
            return f'({inner})' if t is POS else f'{t.name}({inner})'
        return str(v)

    # -- calls and statements
    def call(self, f, args):
        env = {pname: a for (pname, _), a in zip(f.params, args)}
        try:
            self.block(f.body, env)
        except Return as r:
            return r.v
        return None

    def block(self, stmts, env):
        for s in stmts:
            self.stmt(s, env)

    def stmt(self, s, env):
        k = s.k
        if k == 'var':
            env[s.name] = self.ev(s.e, env) if s.e is not None else zero(s.ty)
        elif k == 'assign':                                   # the target's parts first, once, then the value:
            read, write = self.locate(s.target, env)          # left to right, as DESIGN.md says
            if s.op is None:
                write(self.ev(s.e, env))
            else:
                old = read()
                write(self.apply_bin(s.opnode, old, self.ev(s.e, env)))
        elif k == 'expr':
            self.ev(s.e, env)
        elif k == 'if':
            for cond, body in s.arms:
                if self.ev(cond, env):
                    self.block(body, env)
                    return
            self.block(s.else_, env)
        elif k == 'while':
            while self.ev(s.cond, env):
                try:
                    self.block(s.body, env)
                except Break:
                    break
                except Continue:
                    continue
        elif k == 'for':
            self.for_(s, env)
        elif k == 'case':
            v = self.ev(s.e, env)
            for vals, body in s.whens:
                if any(v == w.cval for w in vals):
                    self.block(body, env)
                    return
            self.block(s.else_, env)
        elif k == 'break':
            raise Break()
        elif k == 'continue':
            raise Continue()
        elif k == 'return':
            raise Return(self.ev(s.e, env) if s.e is not None else None)
        elif k == 'assert':
            if not self.ev(s.e, env):
                raise BarleyError('assertion failed', s.line)
        elif k == 'print':
            placed = False                                  # from the first at on, the text is the screen's alone
            for kind, e in s.items:
                if kind == 'item':
                    self.write(self.show(self.ev(e, env), e.ty), placed)
                elif kind == 'at':
                    r, c = self.ev(e[0], env), self.ev(e[1], env)
                    self.screen_call(lambda: self.screen.at(r, c), s.line)
                    self.col = c
                    placed = True
                else:
                    self.write(' ' * (16 - self.col % 16), placed)
            if s.newline:
                self.write('\n', placed)

    def walk(self, it, t, s):
        """what for walks, one item at a time, live: a for sees element changes, and stops if the container's
        items change under it"""
        if isinstance(t, Gen) and t.kind in ('list', 'queue', 'map', 'set'):
            ver, i = it.ver, 0
            keys = list(it.d) if t.kind in ('map', 'set') else None
            while True:
                if it.ver != ver:
                    raise BarleyError(f'the {t.kind} changed while for was walking it', s.line)
                if keys is not None:
                    if i >= len(keys):
                        return
                    k = keys[i]
                    yield (k, it.d[k]) if len(s.names) == 2 else k
                else:
                    if i >= len(it.items):
                        return
                    yield it.items[i]
                i += 1
        elif isinstance(t, Gen) and t.kind == 'array':
            for i in range(len(it)):
                yield it[i]
        elif isinstance(t, Gen) and t.kind == 'grid':
            for r in range(it.rows):
                for c in range(it.cols):
                    yield (r, c)
        elif t is LINES:
            while it.i < len(it.lines):
                it.i += 1
                yield it.lines[it.i - 1]
        elif isinstance(t, Gen) and t.kind == 'iter' and t.args[0] is FLEX:
            for v in it:
                if not (s.vtys[0].lo <= v <= s.vtys[0].hi):
                    raise BarleyError(f"{v} doesn't fit in {article(s.vtys[0].name)}", s.line)
                yield v
        else:
            yield from it

    def for_(self, s, env):
        it = self.ev(s.it, env)
        for v in self.walk(it, s.it.ty, s):
            if len(s.names) == 2:
                env[s.names[0]], env[s.names[1]] = v
            else:
                env[s.names[0]] = v
            try:
                self.block(s.body, env)
            except Break:
                break
            except Continue:
                continue

    def locate(self, target, env):
        """(read, write) for an assignment's target, its parts (the container, the index or key) evaluated now,
        once, left to right; the index is checked when it's used, after the value, as every backend does"""
        k = target.k
        if k == 'name':
            if target.var.where == 'global':
                return (lambda: self.globals[target.name]), (lambda v: self.globals.__setitem__(target.name, v))
            return (lambda: env[target.name]), (lambda v: env.__setitem__(target.name, v))
        if k == 'dot':
            rd, wr = self.locate(target.obj, env)
            i = target.obj.ty.index[target.name]
            return (lambda: rd()[i]), (lambda v: (lambda rec: wr(rec[:i] + (v,) + rec[i + 1:]))(rd()))
        obj = self.ev(target.obj, env)
        ot = target.obj.ty
        if ot.kind == 'map':
            key = self.ev(target.idx[0], env)

            def rd():
                if key not in obj.d:
                    raise BarleyError(f'no key {self.show(key, ot.args[0])} in the map', target.line)
                return obj.d[key]

            def wr(v):
                if key not in obj.d:
                    if len(obj.d) >= obj.cap:
                        raise BarleyError(f'map full ({obj.cap})', target.line)
                    obj.ver += 1
                obj.d[key] = v
            return rd, wr
        if ot.kind == 'grid':
            r, c = self.grid_rc(target, env)

            def gset(v):
                obj.check(r, c, target.line)
                obj.cells[r][c] = v
            return (lambda: (obj.check(r, c, target.line), obj.cells[r][c])[1]), gset
        items = obj if ot.kind == 'array' else obj.items
        i = self.ev(target.idx[0], env)

        def check():
            if not 0 <= i < len(items):
                raise BarleyError(f'index {i} is outside 0..{len(items)}', target.line)

        def iset(v):
            check()
            items[i] = v
        return (lambda: (check(), items[i])[1]), iset

    def store(self, target, v, env):
        k = target.k
        if k == 'name':
            if target.var.where == 'global':
                self.globals[target.name] = v
            else:
                env[target.name] = v
        elif k == 'index':
            obj = self.ev(target.obj, env)
            ot = target.obj.ty
            if ot.kind == 'map':
                key = self.ev(target.idx[0], env)
                if key not in obj.d:
                    if len(obj.d) >= obj.cap:
                        raise BarleyError(f'map full ({obj.cap})', target.line)
                    obj.ver += 1
                obj.d[key] = v
            elif ot.kind == 'grid':
                r, c = self.grid_rc(target, env)
                obj.check(r, c, target.line)
                obj.cells[r][c] = v
            else:
                items = obj if ot.kind == 'array' else obj.items
                i = self.ev(target.idx[0], env)
                if not 0 <= i < len(items):
                    raise BarleyError(f'index {i} is outside 0..{len(items)}', target.line)
                items[i] = v
        elif k == 'dot':
            rec = self.ev(target.obj, env)
            i = target.obj.ty.index[target.name]
            self.store(target.obj, rec[:i] + (v,) + rec[i + 1:], env)

    def screen_call(self, f, line):
        try:
            return f()
        except self.zx.ScreenError as err:
            raise BarleyError(str(err), line)

    def grid_rc(self, e, env):
        if len(e.idx) == 2:
            return self.ev(e.idx[0], env), self.ev(e.idx[1], env)
        return self.ev(e.idx[0], env)

    # -- expressions
    def ev(self, e, env):
        if e.cval is not None and e.k != 'name' or (e.k == 'name' and e.var.const):
            return e.cval
        return getattr(self, 'e_' + e.k)(e, env)

    def e_str(self, e, env):
        return e.v

    def e_name(self, e, env):
        v = e.var
        if v.where == 'global':
            return self.globals[e.name]
        return env[e.name]

    def e_range(self, e, env):
        return Range(self.ev(e.a, env), self.ev(e.b, env), e.rev)

    def e_bin(self, e, env):
        op = e.op
        if op == 'and':
            return bool(self.ev(e.a, env)) and bool(self.ev(e.b, env))
        if op == 'or':
            return bool(self.ev(e.a, env)) or bool(self.ev(e.b, env))
        a = self.ev(e.a, env)
        if op == 'in':
            return a in self.ev(e.b, env).d
        return self.apply_bin(e, a, self.ev(e.b, env))

    def apply_bin(self, e, a, b):
        op = e.op
        if op in ('==', '!=', '<', '>', '<=', '>='):
            return compare(op, a, b)
        if e.ty is POS:
            return fit(a[0] + b[0] if op == '+' else a[0] - b[0], INT, e.line), \
                fit(a[1] + b[1] if op == '+' else a[1] - b[1], INT, e.line)
        return arith(op, a, b, e.ty, e.line)

    def e_un(self, e, env):
        a = self.ev(e.a, env)
        if e.op == 'not':
            return not a
        if e.op == '-':
            return -a if e.ty is FLOAT else fit(-a, e.ty, e.line)
        return wrap(~a, e.ty)

    def e_index(self, e, env):
        obj = self.ev(e.obj, env)
        ot = e.obj.ty
        if e.slice:
            rg = self.ev(e.idx[0], env)
            if not (0 <= rg.a <= rg.b <= len(obj)):
                raise BarleyError(f'slice {rg.a}..{rg.b} is outside 0..{len(obj)}', e.line)
            return obj[rg.a:rg.b]
        if isinstance(ot, Gen) and ot.kind == 'map':
            key = self.ev(e.idx[0], env)
            if key not in obj.d:
                raise BarleyError(f'no key {self.show(key, ot.args[0])} in the map', e.line)
            return obj.d[key]
        if isinstance(ot, Gen) and ot.kind == 'grid':
            r, c = self.grid_rc(e, env)
            obj.check(r, c, e.line)
            return obj.cells[r][c]
        i = self.ev(e.idx[0], env)
        items = obj if ot is STR or ot.kind == 'array' else obj.items
        if not 0 <= i < len(items):
            raise BarleyError(f'index {i} is outside 0..{len(items)}', e.line)
        return items[i]

    def e_dot(self, e, env):
        obj = self.ev(e.obj, env)
        ot, name = e.obj.ty, e.name
        if e.args is None:
            if isinstance(ot, RecordT):
                return obj[ot.index[name]]
            if name == 'len':
                if ot is STR or ot.kind == 'array':
                    return len(obj)
                return len(obj.d) if ot.kind in ('map', 'set') else len(obj.items)
            return obj.rows if name == 'rows' else obj.cols
        args = [self.ev(a, env) for a in e.args]
        line = e.line
        if ot is STR:
            if name == 'int':
                if args:
                    found = ints_in(obj)
                    if not 0 <= args[0] < len(found):
                        raise BarleyError(f'there is no integer {args[0]} in "{obj.decode("latin-1")}"', line)
                    v = found[args[0]]
                else:
                    m = re.match(rb'\s*([-+]?\d+)', obj)
                    if not m:
                        raise BarleyError(f'"{obj.decode("latin-1")}" doesn\'t start with an integer', line)
                    v = int(m.group(1))
                if not (e.ty.lo <= v <= e.ty.hi):
                    raise BarleyError(f"{v} doesn't fit in {article(e.ty.name)}", line)
                return v
            if name == 'ints':
                return ints_in(obj)
            if name == 'split':
                sep = args[0] if isinstance(args[0], bytes) else bytes([args[0]])
                if not sep:
                    raise BarleyError('split needs a separator', line)
                return obj.split(sep)
            if name == 'find':
                sep = args[0] if isinstance(args[0], bytes) else bytes([args[0]])
                return fit(obj.find(sep), INT, line)
            if name == 'starts':
                sep = args[0] if isinstance(args[0], bytes) else bytes([args[0]])
                return obj.startswith(sep)
            if name == 'trim':
                return obj.strip(b' \t')
        if ot is LINES:
            if obj.i >= len(obj.lines):
                raise BarleyError('no more input lines', line)
            obj.i += 1
            return obj.lines[obj.i - 1]
        kind = ot.kind
        if kind == 'array':
            obj.sort()
            return None
        if kind == 'list':
            if name == 'push':
                obj.push(args[0], line)
            elif name == 'pop':
                if not obj.items:
                    raise BarleyError('list empty', line)
                obj.ver += 1
                return obj.items.pop()
            elif name == 'sort':
                obj.items.sort()
                obj.ver += 1
            elif name == 'clear':
                obj.items.clear()
                obj.ver += 1
            return None
        if kind == 'queue':
            if name == 'put':
                if len(obj.items) >= obj.cap:
                    raise BarleyError(f'queue full ({obj.cap})', line)
                obj.items.append(args[0])
                obj.ver += 1
                return None
            if not obj.items:
                raise BarleyError('queue empty', line)
            obj.ver += 1
            return obj.items.popleft()
        if kind == 'heap':
            if name == 'push':
                if len(obj.items) >= obj.cap:
                    raise BarleyError(f'heap full ({obj.cap})', line)
                heapq.heappush(obj.items, args[0])
                return None
            if not obj.items:
                raise BarleyError('heap empty', line)
            return heapq.heappop(obj.items)
        if kind == 'set':
            if name == 'add':
                if args[0] not in obj.d:
                    if len(obj.d) >= obj.cap:
                        raise BarleyError(f'set full ({obj.cap})', line)
                    obj.d[args[0]] = True
                    obj.ver += 1
            elif args[0] in obj.d:
                del obj.d[args[0]]
                obj.ver += 1
            return None
        if kind == 'map':
            if name == 'get':
                return obj.d.get(args[0], args[1])
            if args[0] in obj.d:
                del obj.d[args[0]]
                obj.ver += 1
            return None
        if kind == 'grid':
            if name == 'has':
                r, c = args[0]
                return 0 <= r < obj.rows and 0 <= c < obj.cols
            for r in range(obj.rows):
                for c in range(obj.cols):
                    if obj.cells[r][c] == args[0]:
                        return (r, c)
            raise BarleyError(f'{self.show(args[0], ot.args[0])} is not on the grid', line)
        raise BarleyError(f'.{name}() is not implemented', line)

    def e_new(self, e, env):
        args = [self.ev(a, env) for a in e.args]
        t = e.ty
        if e.kind == 'grid':
            if args[0] < 0 or args[1] < 0:
                raise BarleyError('a grid has no negative sides', e.line)
            if args[0] > 32767 or args[1] > 32767:
                raise BarleyError('a grid side is at most 32767', e.line)
            return BGrid(args[0], args[1], args[2] if len(args) == 3 else zero(t.args[0]))
        if args[0] <= 0:
            raise BarleyError(f'a {e.kind} needs a capacity of at least 1', e.line)
        if args[0] > 65535:
            raise BarleyError(f'a {e.kind} holds at most 65535', e.line)
        return {'list': BList, 'queue': BQueue, 'map': BMap, 'heap': BHeap, 'set': BSet}[e.kind](args[0])

    def e_call(self, e, env):
        if hasattr(e, 'func'):
            return self.call(e.func, [self.ev(a, env) for a in e.args])
        args = [self.ev(a, env) for a in e.args]
        if hasattr(e, 'record'):
            return tuple(args)
        if hasattr(e, 'cast'):
            v = args[0]
            if e.cast is BOOL:
                return v != 0
            if e.cast is FLOAT:
                return float(v)
            if isinstance(v, float):                     # a float to a whole number: truncate, and it must fit
                if v != v or v in (math.inf, -math.inf) or not (e.cast.lo <= math.trunc(v) <= e.cast.hi):
                    raise BarleyError(f"{v:.10g} doesn't fit in {article(e.cast.name)}", e.line)
                return math.trunc(v)
            return wrap(int(v), e.cast)
        name = e.builtin
        if name in MACHINE_FUNCS:
            a = args[0]
            if not 0 <= a <= 65535:
                raise BarleyError(f'{"port" if name in ("inp", "outp") else "address"} {a} is outside 0..65536', e.line)
            if name == 'peek':
                return self.memory[a]
            if name == 'inp':                                # the ULA, the Kempston joystick, nothing (zxgfx.py)
                return self.screen.inp(a)
            if name == 'outp':
                self.screen.outp(a, args[1])
            elif a >= 0x4000:                                # poke: the ROM can't be written
                self.memory[a] = args[1]
            return None
        if name in SCREEN_FUNCS:
            sc = self.screen
            f = {'inverse': sc.set_inverse, 'over': sc.set_over}.get(name) or getattr(sc, name)
            return self.screen_call(lambda: f(*args), e.line)
        if name == 'lines':
            return BLines(self.input_lines)
        if name == 'ask':
            return self.ask(args[0] if args else b'', e.line)
        if name == 'input':
            if len(self.text) > 65535:
                raise BarleyError('the input is longer than 65535, too long for one str', e.line)
            return self.text
        if name == 'grid':
            rows = self.input_lines
            g = BGrid(len(rows), len(rows[0]) if rows else 0, 0)
            for r, row in enumerate(rows):
                if len(row) != g.cols:
                    raise BarleyError(f'the input is not a grid: line {r + 1} is {len(row)} long, not {g.cols}',
                                      e.line)
                g.cells[r] = list(row)
            return g
        if name == 'intern':
            s = args[0]
            if s not in self.interned:
                if len(self.names) >= 65536:
                    raise BarleyError('too many names: intern holds 65536', e.line)
                self.interned[s] = len(self.names)
                self.names.append(s)
            return self.interned[s]
        if name == 'name':
            if not 0 <= args[0] < len(self.names):
                raise BarleyError(f'no name has the number {args[0]}', e.line)
            return self.names[args[0]]
        if name == 'chr':
            return bytes([args[0]])
        if name in FLOAT_FUNCS:
            try:
                return FLOAT_FUNCS[name](args[0])
            except (ValueError, OverflowError):
                raise BarleyError(f'{name}({args[0]:.10g}) has no answer', e.line)
        if name == 'rev':
            return args[0]
        t = e.ty
        if name == 'min':
            return min(args)
        if name == 'max':
            return max(args)
        if name == 'abs':
            return abs(args[0]) if t is FLOAT else fit(abs(args[0]), t, e.line)
        if name == 'sign':
            return (args[0] > 0) - (args[0] < 0)
        if name == 'mod':
            if args[1] == 0:
                raise BarleyError('mod by zero', e.line)
            return args[0] % args[1]
        if name == 'gcd':
            a, b = abs(args[0]), abs(args[1])
            while b:
                a, b = b, a % b
            return fit(a, t, e.line)
        if name == 'lcm':
            a, b = abs(args[0]), abs(args[1])
            if a == 0 or b == 0:
                return 0
            g, x = a, b
            while x:
                g, x = x, g % x
            return fit(a // g * b, t, e.line)
        raise BarleyError(f'{name} is not implemented', e.line)


def uses_machine(decls):
    """does the program draw, sound, print at, peek or poke? Only those can see the screen's pixels or the ROM, so only
    they need the 48K ROM (its font, and its bytes for peek)"""
    def walk(x):
        if isinstance(x, N):
            if x.k == 'call' and (getattr(x, 'name', None) in SCREEN_FUNCS or getattr(x, 'name', None) in MACHINE_FUNCS):
                return True
            if x.k == 'print' and any(kind == 'at' for kind, _ in x.items):
                return True
            return any(walk(v) for k, v in x.__dict__.items() if k not in ('func', 'var', 'ty', 'record', 'cast'))
        if isinstance(x, (list, tuple)):
            return any(walk(v) for v in x)
        return False
    return walk(decls)


def uses_keys(decls):
    """does the program read the keyboard (ask, inkey, key)? Only then does anything need stdin"""
    def walk(x):
        if isinstance(x, N):
            if x.k == 'call' and getattr(x, 'name', None) in ('ask', 'inkey', 'key') and not hasattr(x, 'func'):
                return True
            return any(walk(v) for k, v in x.__dict__.items() if k not in ('func', 'var', 'ty', 'record', 'cast'))
        if isinstance(x, (list, tuple)):
            return any(walk(v) for v in x)
        return False
    return walk(decls)


def run(src, text=b'', target='zx48', out=sys.stdout, screen=None, sound=None, keys=None):
    """screen: a .png path to save the virtual screen to at the end (and a .scr beside it); sound: a path for the
    beep log, one "ms semitone" a line; keys: what was typed (a zxgfx.Keys), or none"""
    decls = Parser(src).program()
    ck = Checker(decls, target)
    ck.check()
    it = Interp(ck, text, out, need_rom=bool(screen))
    it.screen.keys = keys
    try:
        it.run()
    finally:
        if screen:
            it.screen.png(screen)
            open(os.path.splitext(screen)[0] + '.scr', 'wb').write(it.screen.scr())
        if sound:
            open(sound, 'w').write(''.join(f'{ms} {st}\n' for ms, st in it.screen.sound))


def it_keys(stdin):
    """the keyboard: stdin's keys, unless it's a terminal, where only ask() reads (a line at a time)"""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'z80'))
    import zxgfx
    return zxgfx.Keys(stdin.buffer, stdin.isatty())


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog='barley.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('program', metavar='PROGRAM.bly', help='the program')
    ap.add_argument('input', metavar='INPUT', nargs='?', help='its input: what lines(), grid() and input() read')
    ap.add_argument('--as', dest='target', choices=['zx48', 'cpm'], default='zx48',
                    help='the machine it is, as far as the program can tell (default zx48)')
    ap.add_argument('--screen', metavar='OUT.png',
                    help="save the Spectrum's screen at the end as a picture (and OUT.scr beside it)")
    ap.add_argument('--sound', metavar='OUT.txt', help='save a log of the notes it played')
    a = ap.parse_args(argv)
    try:
        src = open(a.program).read()
        text = open(a.input, 'rb').read() if a.input else b''
    except OSError as err:
        sys.exit(f'barley.py: {err.filename}: {err.strerror}')
    sys.setrecursionlimit(20000)
    try:
        keys = None if sys.stdin is None else it_keys(sys.stdin)
        run(src, text, a.target, screen=a.screen, sound=a.sound, keys=keys)
    except BarleyError as err:
        sys.stdout.flush()
        sys.stdout.buffer.flush()
        print(err)
        sys.exit(1)


if __name__ == '__main__':
    main(sys.argv[1:])
