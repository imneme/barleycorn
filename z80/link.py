"""Linking before assembly: gather the library fragments a program needs, by their headers (see ABI.md, section 3).

    from link import gather
    frags, text = gather(['bly_add_i32'], 'cpm')     # text: every fragment needed, pasted, ready to assemble
"""
import os
import re

LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib')


class Frag:
    def __init__(self, path):
        self.path, self.name = path, os.path.basename(path)
        self.text = open(path).read()
        self.provides, self.needs, self.targets, self.uses = [], [], [], []   # uses: the program's symbols
        for line in self.text.splitlines():
            if not line.startswith(';;'):
                break
            keys = list(re.finditer(r'\b(provides|needs|targets|uses):', line))     # one a line, or several, as
            for k, m in enumerate(keys):                                            # DESIGN.md's example has
                if k == 0 and line[2:m.start()].strip():
                    break                                     # a line of prose that mentions a key: not a header
                end = keys[k + 1].start() if k + 1 < len(keys) else len(line)
                words = [w for w in line[m.end():end].split() if w != '(none)']
                getattr(self, m.group(1)).extend(words)
        if not self.provides or not self.targets:
            raise ValueError(f'{self.name}: a fragment needs provides: and targets: lines')
        undeclared = set(re.findall(r'^(bly_\w+):', self.text, re.M)) - set(self.provides)
        if undeclared:
            raise ValueError(f'{self.name}: global labels not in provides: {sorted(undeclared)}')


BROKEN = {}                                   # fragments whose header doesn't parse (someone mid-edit, say)


def load(lib=LIB):
    """every fragment whose header parses; the rest are noted in BROKEN rather than breaking everyone's build"""
    out = []
    for f in sorted(os.listdir(lib)):
        if f.endswith('.asm'):
            try:
                out.append(Frag(os.path.join(lib, f)))
            except (ValueError, OSError) as err:
                BROKEN[f] = str(err)
    return out


# Inside a fragment, each routine sits between two comment lines:
#     ;; routine bly_cmp_u8 (brings bly_cmp_u16)
#     ...
#     ;; end bly_cmp_u8
# and stays in a program only if something kept names it. "brings" lists routines that come with it whatever names
# them, because it runs on into them or uses one of their .local labels. "(fails)" marks a routine that only fails
# (prints its message and ends the program): a --terse build drops it and sends whatever names it to bly_terse, the
# platform's one wordless failure. To the assembler the markers are comments, so a fragment assembled on its own (as
# the tests and the size tables do) has every routine, as before; resolve() decides, once the whole program is
# there. libblocks.py holds the rules and checks them.
MARK = re.compile(r'^;; routine ([A-Za-z_]\w*)((?: \((?:brings [A-Za-z_][\w, ]*|fails)\))*)\s*$')
END = re.compile(r'^;; end ([A-Za-z_]\w*)\s*$')
INCLUDE = re.compile(r'^\s+include\s+"([^"]+)"', re.I)


def names(line):
    """the names a line of assembly mentions (not in its comment, nor in its strings)"""
    body = re.sub(r'"[^"]*"|\'[^\']*\'', ' ', line.split(';', 1)[0])
    return re.findall(r'[A-Za-z_]\w*', body)


def blocks(text):
    """{routine: (first line, last line, [what it brings], whether it only fails)} of a text's marked routines"""
    out, inside = {}, None
    for i, line in enumerate(text.splitlines()):
        m, e = MARK.match(line), END.match(line)
        if m:
            if inside:
                raise ValueError(f'routine {m.group(1)} starts inside {inside[0]}')
            groups = re.findall(r'\(([^)]*)\)', m.group(2))
            brings = [w for g in groups if g.startswith('brings ') for w in re.split(r'[ ,]+', g[7:]) if w]
            inside = (m.group(1), i, brings, 'fails' in groups)
        elif e:
            if not inside or e.group(1) != inside[0]:
                raise ValueError(f'end {e.group(1)} doesn\'t close ' + (inside[0] if inside else 'anything'))
            if inside[0] in out:
                raise ValueError(f'two blocks for {inside[0]}')
            out[inside[0]] = (inside[1], i, inside[2], inside[3])
            inside = None
    if inside:
        raise ValueError(f'routine {inside[0]} has no end')
    return out


def resolve(text, terse=False):
    """text with its marked routines decided: one stays if anything kept names it, or a kept routine brings it
    (everything outside the markers is kept, and so is a file it includes); the rest go. terse: a routine marked
    (fails) goes whatever names it, and each one named becomes another name for bly_terse"""
    lines = text.splitlines()
    bl = blocks(text)
    if not bl:
        return text
    owner = [None] * len(lines)
    for lab, (a, b, _, _) in bl.items():
        for k in range(a, b + 1):
            owner[k] = lab
    keep, todo, failing = set(), [], set()

    def want(n):
        if terse and n in bl and bl[n][3]:
            if n not in failing:
                failing.add(n)
                want('bly_terse')
        elif n in bl and n not in keep:
            keep.add(n)
            todo.append(n)

    def scan(rows):
        for row in rows:
            inc = INCLUDE.match(row)
            if inc and os.path.exists(inc.group(1)):
                scan(open(inc.group(1)).read().splitlines())
            for n in names(row):
                want(n)
    scan(line for k, line in enumerate(lines) if owner[k] is None)
    while todo:
        a, b, brings, _ = bl[todo.pop()]
        for n in brings:
            want(n)
        scan(lines[a + 1:b])
    out = [line for k, line in enumerate(lines) if owner[k] is None or owner[k] in keep]
    out += [f'{n} equ bly_terse                      ; --terse: every failure is the one wordless one' for n in sorted(failing)]
    return '\n'.join(out) + ('\n' if text.endswith('\n') or failing else '')


def gather(symbols, target, lib=LIB):
    """(the fragments, their text pasted together): every routine in them, for resolve() to decide once the whole
    program is there"""
    frags = [f for f in load(lib) if target in f.targets]
    by_sym = {}
    for f in frags:
        for s in f.provides:
            if s in by_sym:
                raise ValueError(f'{s} is provided by both {by_sym[s].name} and {f.name} for {target}')
            by_sym[s] = f
    chosen, todo = [], list(symbols)
    while todo:
        s = todo.pop()
        if s not in by_sym:
            extra = f' (unreadable fragments: {", ".join(sorted(BROKEN))})' if BROKEN else ''
            raise ValueError(f'nothing provides {s} for {target}{extra}')
        f = by_sym[s]
        if f not in chosen:
            chosen.append(f)
            todo += f.needs
    chosen.sort(key=lambda f: f.name)
    text = '\n'.join(f'; ---- {f.name}\n{f.text}' for f in chosen)
    return chosen, text
