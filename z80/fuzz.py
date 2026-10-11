"""Random Barley programs over the integer core, with the interpreter as the
oracle (phase one's fuzzer, grown up). Each program runs in the interpreter,
as C (clang, sanitizers on) and as a CP/M .COM under tnylpo; any disagreement
is kept in fuzz/ as fail-SEED.bly with what each said. What it aims at is what
the generator's next steps change:
- every integer width, with compares, and/or/not, casts, shifts, min/max
- locals and globals, and functions that change globals inside expressions
  (reads in place)
- self-calls that permute their own arguments (the parallel-move hazard)
- loops whose bounds the body changes, break and continue
- constant tables of every width, read at random indices
"""
import argparse
import os, random, re, subprocess, sys, multiprocessing as mp
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'interp', 'tests'))
OUT = os.path.join(HERE, '..', 'build', 'fuzz-failures')

INTS = ['byte', 'word', 'int', 'long', 'quad', 'dword']
UP = {'byte': ['byte', 'word', 'int', 'long', 'quad', 'dword'], 'word': ['word', 'long', 'quad', 'dword'],
      'int': ['int', 'long', 'quad'], 'long': ['long', 'quad'], 'quad': ['quad'], 'dword': ['dword', 'quad']}
SIGNED = {'int', 'long', 'quad'}
EDGE = {'byte': [0, 1, 127, 128, 255], 'word': [0, 1, 255, 256, 32767, 32768, 65535],
        'int': [0, 1, -1, 127, -128, 255, 32767, -32768], 'long': [0, 1, -1, 65535, 65536, 2147483647, -2147483648],
        'quad': [0, 1, -1, 4294967296, -4294967296],
        'dword': [0, 1, 65535, 65536, 2147483647, 2147483648, 4294967295]}


class Gen:
    def __init__(self, seed):
        self.r = random.Random(seed)
        self.lines = []
        self.funcs = []             # (name, [(param, type)], return type)

    def pick(self, xs):
        return self.r.choice(xs)

    def lit(self, t):
        if self.r.random() < 0.15:
            v = self.pick(EDGE[t])
        else:
            v = self.r.randint(0, 9) if t not in SIGNED or self.r.random() < 0.7 else -self.r.randint(1, 9)
        return f'({v})' if v < 0 else str(v)

    def var(self, t, scope):
        """a variable of type t, or a byte where a byte meets anything t's siblings could be (word and int never
        meet: Barley types bottom-up, so word + int is an error whatever the context wants)"""
        ok = {'byte': {'byte'}, 'word': {'byte', 'word'}, 'int': {'byte', 'int'}, 'long': {'byte', 'long'},
              'quad': {'byte', 'quad'}, 'dword': {'byte', 'word', 'dword'}}[t]
        c = [n for n, vt in scope if vt in ok]
        return self.pick(c) if c else None

    def expr(self, t, scope, d, fname=None):
        e = self.expr1(t, scope, d, fname)
        if t in ('byte', 'word', 'dword') and not re.search(r'\b(g_|p\d|v_|i_|w_|arr|d\b|f\d)', e) and not e.isdigit():
            e = f'{t}({e})'                    # a constant that folds negative is an error where a byte is wanted
        return e

    def expr1(self, t, scope, d, fname=None):
        r = self.r.random()
        if d <= 0 or r < 0.25:
            v = self.var(t, scope) if self.r.random() < 0.7 else None
            return v or self.lit(t)
        r = self.r.random()
        if r < 0.40:
            op = self.pick(['+', '-', '&', '|', '^', '+', '-', '*'])
            return f'({self.expr(t, scope, d - 1, fname)} {op} {self.expr(t, scope, d - 1, fname)})'
        if r < 0.46:
            op = self.pick(['/', '%'])
            return f'({self.expr(t, scope, d - 1, fname)} {op} ({self.expr(t, scope, d - 1, fname)} | 1))'
        if r < 0.50:                                     # by a constant: powers of two, small, and the edges
            op = self.pick(['*', '/', '%'])
            hi = {'byte': 255, 'word': 65535, 'int': 32767, 'long': 65535, 'quad': 65535, 'dword': 65535}[t]
            k = self.pick([x for x in (1, 2, 4, 8, 16, 32, 64, 128, 256, 1024, 32768, 3, 5, 7, 10, 25, 255, 65535)
                           if x <= hi])
            return f'({self.expr(t, scope, d - 1, fname)} {op} {k})'
        if r < 0.53:
            op = self.pick(['<<', '>>'])
            return f'({self.expr(t, scope, d - 1, fname)} {op} {self.r.randint(0, 9) if self.r.random() < 0.8 else self.r.randint(10, 70)})'
        if r < 0.60:
            s = self.pick(INTS)
            return f'{t}({self.expr(s, scope, d - 1, fname)})'
        if r < 0.66 and t in SIGNED:
            return f'(-{self.expr(t, scope, d - 1, fname)})'
        if r < 0.70:
            return f'(~{self.expr(t, scope, d - 1, fname)})'
        if r < 0.76:
            return f'{self.pick(["min", "max"])}({self.expr(t, scope, d - 1, fname)}, {self.expr(t, scope, d - 1, fname)})'
        if r < 0.79:                                     # a constant table, laid out in the program
            return f'T_{t}[{self.expr("int", scope, d - 1, fname)} & 7]'
        if r < 0.82 and t in UP['int']:
            return f'arr[{self.expr("int", scope, d - 1, fname)} & 7]'
        if r < 0.92:
            c = self.call(t, scope, d, fname)
            if c:
                return c
        return self.var(t, scope) or self.lit(t)

    def call(self, t, scope, d, fname):
        """a call of an earlier function (or this one, one level down) whose result widens to t"""
        if fname == 'leaf':                                        # a base case calls nothing
            return None
        cands = list(self.funcs)
        if fname is not None:
            cands = [f for f in cands if f[0] <= fname]
        if not cands:
            return None
        name, params, rt = self.pick(cands)
        depth = 'd - 1' if fname is not None else str(self.r.randint(0, 3))
        args = [self.expr(pt, scope, d - 1, fname) for _, pt in params[1:]]
        if fname == name and self.r.random() < 0.5:                 # our own parameters, shuffled
            ps = params[1:]
            args = [self.pick([q for q, qt in ps if qt == pt]) for _, pt in ps]
        c = f'{name}({", ".join([depth] + args)})'
        return c if rt == t else f'{t}({c})'

    def cond(self, scope, d, fname):
        r = self.r.random()
        if d <= 0 or r < 0.55:
            t = self.pick(INTS)
            op = self.pick(['<', '<=', '>', '>=', '==', '!='])
            return f'{self.expr(t, scope, d - 1, fname)} {op} {self.expr(t, scope, d - 1, fname)}'
        if r < 0.75:
            return f'({self.cond(scope, d - 1, fname)}) {self.pick(["and", "or"])} ({self.cond(scope, d - 1, fname)})'
        if r < 0.85:
            return f'not ({self.cond(scope, d - 1, fname)})'
        b = [n for n, vt in scope if vt == 'bool']
        return self.pick(b) if b else 'true'

    def stmts(self, scope, depth, n, fname, ind, in_for=False):
        out = []
        for _ in range(n):
            out += self.stmt(scope, depth, fname, ind, in_for)
        return out

    def stmt(self, scope, depth, fname, ind, in_for):
        r = self.r.random()
        sp = '  ' * ind
        writable = [(n, t) for n, t in scope if t != 'bool' and not n.startswith('i_') and n != 'd']
        if r < 0.30 and writable:
            n, t = self.pick(writable)
            op = self.pick(['=', '=', '+=', '-=', '&=', '|=', '^='])
            return [f'{sp}{n} {op} {self.expr(t, scope, 3, fname)}']
        if r < 0.38:
            return [f'{sp}arr[{self.expr("int", scope, 2, fname)} & 7] = {self.expr("int", scope, 2, fname)}']
        if r < 0.50:
            items = []
            for _ in range(self.r.randint(1, 3)):
                items.append(self.expr(self.pick(INTS), scope, 3, fname) if self.r.random() < 0.8 else
                             f'({self.cond(scope, 1, fname)})')
            sep = '; " "; '
            return [f'{sp}print {sep.join(items)}']
        if r < 0.62 and depth > 0:
            out = [f'{sp}if {self.cond(scope, 2, fname)} then']
            out += self.stmts(list(scope), depth - 1, self.r.randint(1, 3), fname, ind + 1, in_for)
            if self.r.random() < 0.3:
                out += [f'{sp}elif {self.cond(scope, 2, fname)} then']
                out += self.stmts(list(scope), depth - 1, self.r.randint(1, 2), fname, ind + 1, in_for)
            if self.r.random() < 0.5:
                out += [f'{sp}else']
                out += self.stmts(list(scope), depth - 1, self.r.randint(1, 2), fname, ind + 1, in_for)
            return out + [f'{sp}end']
        if r < 0.72 and depth > 0:
            k = len([1 for n, _ in scope if n.startswith('i_')])
            iv = f'i_{k}'
            hi = self.pick([str(self.r.randint(0, 6)), f'(int({self.var("int", scope) or "3"}) & 7)'])
            bound_var = [n for n, t in writable if t == 'int']
            pre = []
            if self.r.random() < 0.35:                 # a plain variable as the bound, which the body may change
                nv = f'n_{self.r.randint(0, 10 ** 6)}'
                pre = [f'{sp}var {nv}: int = {self.r.randint(0, 5)}']
                scope.append((nv, 'int'))
                hi = nv
            out = pre + [f'{sp}for {iv} in {"rev(0.." + hi + ")" if self.r.random() < 0.2 else "0.." + hi} do']
            sub = list(scope) + [(iv, 'int')]
            body = self.stmts(sub, depth - 1, self.r.randint(1, 3), fname, ind + 1, True)
            if self.r.random() < 0.3:
                body.insert(self.r.randint(0, len(body)),
                            f'{sp}  if {self.cond(sub, 1, fname)} then {self.pick(["break", "continue"])} end')
            return out + body + [f'{sp}end']
        if r < 0.78 and depth > 0:
            k = self.r.randint(0, 10 ** 6)
            w = f'w_{k}'
            out = [f'{sp}var {w} = 0', f'{sp}while {w} < {self.r.randint(1, 5)} and ({self.cond(scope, 1, fname)}) do']
            out += self.stmts(list(scope), depth - 1, self.r.randint(1, 3), fname, ind + 1, False)
            return out + [f'{sp}  {w} += 1', f'{sp}end']
        if r < 0.86:
            t = self.pick(INTS + ['bool'])
            k = self.r.randint(0, 10 ** 6)
            n = f'v_{k}'
            e = self.cond(scope, 2, fname) if t == 'bool' else self.expr(t, scope, 3, fname)
            scope.append((n, t))
            return [f'{sp}var {n}: {t} = {e}']
        if writable:
            n, t = self.pick(writable)
            return [f'{sp}{n} = {self.expr(t, scope, 3, fname)}']
        return [f'{sp}print 0']

    def program(self):
        gl = [(f'g_{t}', t) for t in INTS] + [('g_bool', 'bool')]
        src = ['var arr: int[8]'] + [f'var {n}: {t} = {self.lit(t) if t != "bool" else "true"}' for n, t in gl]
        for t in INTS:                                   # a table of each width: edges, and anywhere in range
            lo, hi = {'byte': (0, 255), 'word': (0, 65535), 'int': (-32768, 32767), 'long': (-2 ** 31, 2 ** 31 - 1),
                      'quad': (-2 ** 63, 2 ** 63 - 1), 'dword': (0, 2 ** 32 - 1)}[t]
            vals = [self.pick(EDGE[t]) if self.r.random() < 0.4 else self.r.randint(lo, hi) for _ in range(8)]
            src.append(f'const T_{t} = {t}[{", ".join(map(str, vals))}]')
        for k in range(self.r.randint(1, 3)):
            name = f'f{k}'
            params = [('d', 'int')] + [(f'p{j}', self.pick(INTS)) for j in range(self.r.randint(1, 4))]
            rt = self.pick(INTS)
            self.funcs.append((name, params, rt))
            scope = list(gl) + params
            body = [f'func {name}({", ".join(f"{p}: {t}" for p, t in params)}): {rt}',
                    f'  if d <= 0 then return {self.expr(rt, scope, 2, "leaf")} end']
            body += self.stmts(scope, 2, self.r.randint(1, 4), name, 1)
            body += [f'  return {self.expr(rt, scope, 3, name)}', 'end', '']
            src += [''] + body
        scope = list(gl)
        main = ['func main()'] + self.stmts(scope, 3, self.r.randint(4, 10), None, 1)
        main += ['  print ' + '; " "; '.join(n for n, _ in gl), '  print arr[0]; " "; arr[7]', 'end']
        return '\n'.join(src + [''] + main) + '\n'


class ContGen:
    """random programs over the containers: one to three of them (list, queue, heap, map, set, grid) of ints, words,
    bytes, longs, positions or a record, and forty-odd operations, each read printed. Keys are small, so they collide;
    most operations are guarded so a program runs long, and about one in ten isn't, so the failures (full, empty, no
    key, off the grid, changed while walking) are compared too. The meaning is the interpreter's, as for Gen."""
    ELEMS = ['int', 'word', 'byte', 'long', 'pos', 'R']

    def __init__(self, seed):
        self.r = random.Random(seed)

    def val(self, t):
        r = self.r
        if t == 'pos':
            return f'pos({r.randint(-3, 9)}, {r.randint(-3, 9)})'
        if t == 'R':
            return f'R({r.randint(-5, 5)}, {r.randint(0, 9)})'
        small = r.randint(0, 15)
        return str(r.choice([small, small, small] + EDGE[t]))

    def key(self, t):
        return self.val(t) if t == 'pos' else str(self.r.randint(0, 15) if t != 'byte' else self.r.randint(0, 15))

    def walk(self, c, kind, two=False):
        r = self.r
        body = ['  print k; ":"; v; " ";' if two else '  print x; " ";']
        if r.random() < 0.08:                                   # changing it while walking: a failure (on a line of
            body.append('  ' + {'list': f'{c}.clear()', 'queue': f'var y = {c}.get()',  # its own: a print takes
                                'map': f'{c}.clear()', 'set': f'{c}.clear()'}[kind])  # the rest of its line)
        return [f'for {"k, v" if two else "x"} in {c} do'] + body + ['end', 'print']

    def op(self, c, kind, t, k2=None):
        r = self.r
        safe = r.random() > 0.1
        v = lambda: self.val(t)
        if kind == 'list':
            return r.choice([
                [f'if {c}.len < {c}_cap then {c}.push({v()}) end' if safe else f'{c}.push({v()})'],
                [f'if {c}.len > 0 then print {c}.pop() end' if safe else f'print {c}.pop()'],
                [f'if {c}.len > 0 then print {c}[{r.randint(0, 7)} % int({c}.len)] end' if safe
                 else f'print {c}[{r.randint(0, 9)}]'],
                [f'if {c}.len > 2 then {c}[1] = {v()} end'],
                [f'print {c}.len'], [f'{c}.sort()'], [f'{c}.clear()'] if r.random() < 0.3 else [f'print {c}.len'],
                self.walk(c, 'list')])
        if kind == 'queue':
            return r.choice([
                [f'if {c}.len < {c}_cap then {c}.put({v()}) end' if safe else f'{c}.put({v()})'],
                [f'if {c}.len > 0 then print {c}.get() end' if safe else f'print {c}.get()'],
                [f'print {c}.len'], self.walk(c, 'queue')])
        if kind == 'heap':
            return r.choice([
                [f'if {c}.len < {c}_cap then {c}.push({v()}) end' if safe else f'{c}.push({v()})'],
                [f'if {c}.len > 0 then print {c}.pop() end' if safe else f'print {c}.pop()'],
                [f'print {c}.len']])
        if kind == 'map':
            k = self.key(t)
            return r.choice([
                [f'if {c}.len < {c}_cap or {k} in {c} then {c}[{k}] = {self.val(k2)} end' if safe
                 else f'{c}[{k}] = {self.val(k2)}'],
                [f'if {k} in {c} then print {c}[{k}] end' if safe else f'print {c}[{k}]'],
                [f'print {c}.get({k}, {self.val(k2)})'], [f'print {k} in {c}'], [f'{c}.del({k})'],
                [f'print {c}.len'], [f'{c}.clear()'] if r.random() < 0.2 else [f'print {c}.len'],
                self.walk(c, 'map', two=True)])
        if kind == 'set':
            k = self.key(t)
            return r.choice([
                [f'if {c}.len < {c}_cap or {k} in {c} then {c}.add({k}) end' if safe else f'{c}.add({k})'],
                [f'print {k} in {c}'], [f'{c}.del({k})'], [f'print {c}.len'],
                [f'{c}.clear()'] if r.random() < 0.2 else [f'print {c}.len'], self.walk(c, 'set')])
        if kind == 'grid':
            rr, cc = r.randint(-1, 5), r.randint(-1, 6)
            inside = f'{c}.has(pos({rr}, {cc}))'
            return r.choice([
                [f'if {inside} then {c}[{rr}, {cc}] = {v()} end' if safe else f'{c}[{rr}, {cc}] = {v()}'],
                [f'if {inside} then print {c}[pos({rr}, {cc})] end' if safe else f'print {c}[{rr}, {cc}]'],
                [f'print {inside}'], [f'print {c}.rows; " "; {c}.cols'],
                [f'print {c}.find({v()})'] if not safe else [f'print {inside}']])

    def program(self):
        r = self.r
        decls, ops = [], []
        conts = []
        for i in range(r.randint(1, 3)):
            kind = r.choice(['list', 'queue', 'heap', 'map', 'set', 'grid'])
            t = r.choice(self.ELEMS if kind not in ('map', 'set') else ['int', 'word', 'byte', 'long', 'pos'])
            c, cap = f'c{i}', r.randint(1, 12)
            if kind == 'map':
                k2 = r.choice(self.ELEMS)
                decls += [f'  var {c}_cap: word = {cap}', f'  var {c} = map[{t}, {k2}]({cap})']
                conts.append((c, kind, t, k2))
            elif kind == 'grid':
                decls += [f'  var {c} = grid[{t}]({r.randint(1, 4)}, {r.randint(1, 5)})']
                conts.append((c, kind, t, None))
            else:
                decls += [f'  var {c}_cap: word = {cap}', f'  var {c} = {kind}[{t}]({cap})']
                conts.append((c, kind, t, None))
        for _ in range(r.randint(20, 60)):
            c, kind, t, k2 = r.choice(conts)
            ops += ['  ' + line for line in self.op(c, kind, t, k2)]
        return 'record R  a: int; b: word  end\n\nfunc main()\n' + '\n'.join(decls + ops) + '\nend\n'


def run_one(seed, zx=False, containers=False):
    import run as R
    src = (ContGen if containers else Gen)(seed).program()
    sys.path.insert(0, os.path.join(HERE, '..'))
    import paths
    d = os.path.join(paths.BUILD, 'fuzz', str(os.getpid()))
    os.makedirs(d, exist_ok=True)
    R.ZBUILD = os.path.join(d, 'z')
    R.BUILD = os.path.join(d, 'c')
    path = os.path.join(d, f'f{seed}.bly')
    open(path, 'w').write(src)
    sys.path.insert(0, os.path.join(HERE, '..', 'interp'))
    import barley as B
    try:
        B.Checker(B.Parser(src).program(), 'cpm').check()
    except B.BarleyError as err:
        return seed, 'rejected', src, {'why': str(err)}         # the checker said no: the generator's fault
    try:
        want = subprocess.run([sys.executable, '-I', R.BARLEY, '--as', 'cpm', path], capture_output=True, text=True,
                              encoding='latin-1', timeout=60, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return seed, 'slow', src, {}
    if want.returncode not in (0, 1) or 'Traceback' in want.stderr:
        return seed, 'interp crashed', src, {'interp': want.stdout + want.stderr}
    got = {}
    got['z80'] = R.run_z80(path, [])
    os.makedirs(R.BUILD, exist_ok=True)
    base = os.path.join(R.BUILD, f'f{seed}')
    g = subprocess.run([sys.executable, '-I', R.CGEN, path], capture_output=True, text=True, encoding='latin-1')
    if g.returncode:
        got['c'] = g.stdout + g.stderr
    else:
        open(base + '.c', 'w').write(g.stdout)
        cc = subprocess.run(R.CC + [base + '.c', '-lm', '-o', base], capture_output=True, text=True, encoding='latin-1')
        got['c'] = ('C COMPILER: ' + cc.stderr) if cc.returncode else \
            (lambda r: r.stdout + (('\nSTDERR: ' + r.stderr) if r.stderr.strip() else ''))(
                subprocess.run([base], capture_output=True, text=True, encoding='latin-1', timeout=60,
                               stdin=subprocess.DEVNULL))
    if zx:
        got['zx'] = R.run_zx(path, [])
    bad = {k: v for k, v in got.items() if v != want.stdout}
    return seed, ('ok' if not bad else 'FAIL'), src, dict(bad, interp=want.stdout) if bad else {}


def main(argv):
    ap = argparse.ArgumentParser(prog='fuzz.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('n', metavar='N', type=int, nargs='?', default=100, help='how many programs (default 100)')
    ap.add_argument('--seed', type=int, help='the first seed (default: a random one, printed at the end)')
    ap.add_argument('--jobs', type=int, default=6, help='how many at once (default 6)')
    ap.add_argument('--zx', action='store_true', help="the 48K too (slower)")
    ap.add_argument('--containers', action='store_true', help='programs over the containers, not the integer core')
    a = ap.parse_args(argv)
    n, zx, jobs = a.n, a.zx, a.jobs
    seed = a.seed if a.seed is not None else random.randrange(10 ** 6)
    os.makedirs(OUT, exist_ok=True)
    counts = {}
    with mp.Pool(jobs) as pool:
        for s, verdict, src, outs in pool.imap_unordered(lambda_run, [(seed + k, zx, a.containers) for k in range(n)]):
            counts[verdict] = counts.get(verdict, 0) + 1
            if verdict == 'rejected' and counts[verdict] <= 3:
                print('rejected:', outs.get('why'), flush=True)
            if verdict not in ('ok', 'rejected', 'slow'):
                open(os.path.join(OUT, f'fail-{s}.bly'), 'w').write(src)
                with open(os.path.join(OUT, f'fail-{s}.txt'), 'w') as f:
                    for k, v in outs.items():
                        f.write(f'--- {k}\n{v}\n')
                print(f'{verdict}: seed {s} ({", ".join(k for k in outs if k != "interp")})', flush=True)
    print(f'{n} programs from seed {seed}: ' + ', '.join(f'{v} {k}' for k, v in sorted(counts.items())))
    return sum(v for k, v in counts.items() if k not in ('ok', 'rejected', 'slow'))     # rejected: the generator's

def lambda_run(a):
    return run_one(*a)


if __name__ == '__main__':
    sys.exit(1 if main(sys.argv[1:]) else 0)            # a FAIL or a crash fails ./check, whatever it printed
