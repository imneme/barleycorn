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
            m = re.match(r';;\s*(provides|needs|targets|uses):(.*)', line)
            if m:
                words = [w for w in m.group(2).split() if w != '(none)']
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


def gather(symbols, target, lib=LIB):
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
