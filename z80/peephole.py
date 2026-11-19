"""Phase one's register cache, as a pass over a function's generated code, and dead stores to temps.

The cache knows, within a stretch of straight-line code, which memory word HL and DE hold, which memory byte A holds,
or which constant. A load of what a register already holds is deleted. A load into HL or DE of what the other pair
holds becomes two register moves. Anything it doesn't understand forgets everything; so do labels, calls, and any
write through a pointer (which could hit any slot). It never deletes an instruction that sets flags: only loads,
which don't.

Then dead stores: a temp (a slot the generator made for one value) whose address appears nowhere except as the
target of plain stores is never read, so the stores go. Its references in the function's cold code count as reads.
"""
import re

ADDR = re.compile(r'^\(([A-Za-z_][\w.]*)((?:[+-]\d+)*)\)$')
R16 = {'hl', 'de', 'bc', 'ix', 'iy', 'sp'}
REGS = R16 | {'a', 'b', 'c', 'd', 'e', 'h', 'l', 'af'}
R8 = {'a': 'a', 'h': 'hl', 'l': 'hl', 'd': 'de', 'e': 'de', 'b': 'bc', 'c': 'bc'}


def mem(op):
    """'(fr_f+12+2)' -> ('fr_f', 14); None for anything that isn't a direct address"""
    m = ADDR.match(op.strip())
    if not m or m.group(1).lower() in REGS:                  # (hl), (de), (ix+3): through a pointer, not an address
        return None
    off = sum(int(x) for x in re.findall(r'[+-]\d+', m.group(2))) if m.group(2) else 0
    return (m.group(1), off)


def overlaps(a, an, b, bn):
    return a[0] == b[0] and a[1] < b[1] + bn and b[1] < a[1] + an


class Cache:
    def __init__(self):
        self.k = {}                                  # 'hl', 'de' -> ('m', addr) or ('i', text); 'a' -> ('m8', addr) or ('i', text)

    def forget(self, *regs):
        for r in regs or list(self.k):
            self.k.pop(r, None)

    def store(self, addr, n):
        """memory at addr (n bytes) changed: forget any register known to hold an overlapping word or byte"""
        for r, v in list(self.k.items()):
            if v[0] in ('m', 'm8') and overlaps(v[1], 2 if v[0] == 'm' else 1, addr, n):
                del self.k[r]

    def forget_memory(self):
        for r, v in list(self.k.items()):
            if v[0] in ('m', 'm8'):
                del self.k[r]


def split(line):
    s = line.strip()
    if not s or s.startswith(';'):
        return None, []
    s = s.split(';')[0].strip()
    parts = s.split(None, 1)
    op = parts[0].lower()
    args = [a.strip() for a in parts[1].split(',')] if len(parts) > 1 else []
    return op, args


def is_label(line):
    return not line.startswith(' ') and line.rstrip().endswith(':') or (not line.startswith(' ') and ':' in line)


def cache_pass(code):
    out = []
    c = Cache()
    for line in code:
        if is_label(line):
            c.forget()
            out.append(line)
            continue
        op, args = split(line)
        if op is None:
            out.append(line)
            continue
        if op == 'ld' and len(args) == 2:
            dst, src = args[0].lower(), args[1]
            sm, dm = mem(src), mem(args[0])
            if dst in ('hl', 'de') and sm:                       # ld rr,(X)
                other = 'de' if dst == 'hl' else 'hl'
                if c.k.get(dst) == ('m', sm):
                    continue                                     # already there
                if c.k.get(other) == ('m', sm):
                    hi, lo = ('h', 'l') if dst == 'hl' else ('d', 'e')
                    oh, ol = ('d', 'e') if dst == 'hl' else ('h', 'l')
                    out.append(f'        ld {hi},{oh}')
                    out.append(f'        ld {lo},{ol}')
                    c.k[dst] = ('m', sm)
                    continue
                out.append(line)
                c.k[dst] = ('m', sm)
                continue
            if dst == 'a' and sm:                                # ld a,(X)
                if c.k.get('a') == ('m8', sm):
                    continue
                out.append(line)
                c.k['a'] = ('m8', sm)
                continue
            if dm and src.lower() in ('hl', 'de'):               # ld (X),rr
                out.append(line)
                c.store(dm, 2)
                c.k[src.lower()] = ('m', dm)
                continue
            if dm and src.lower() == 'a':                        # ld (X),a
                out.append(line)
                c.store(dm, 1)
                c.k['a'] = ('m8', dm)
                continue
            if dm:                                               # ld (X),bc / ix / sp ...: memory changed
                out.append(line)
                c.store(dm, 2)
                continue
            if dst in ('hl', 'de') and not src.startswith('('):  # ld rr,constant (a number or an address)
                if c.k.get(dst) == ('i', src):
                    continue
                out.append(line)
                c.k[dst] = ('i', src)
                continue
            if dst == 'a' and not src.startswith('(') and src.lower() not in R8 and src.lower() not in ('i', 'r'):
                if c.k.get('a') == ('i', src):
                    continue
                out.append(line)
                c.k['a'] = ('i', src)
                continue
            out.append(line)                                     # any other ld: what it writes is unknown now
            if args[0].startswith('('):
                c.forget_memory()                                # through a pointer: could be any slot
            elif dst in R8:
                c.forget(R8[dst])
            elif dst in R16:
                c.forget(dst)
            else:
                c.forget()
            continue
        out.append(line)
        if op == 'ex' and args and args[0].lower() == 'de':
            hl, de = c.k.pop('hl', None), c.k.pop('de', None)
            if hl:
                c.k['de'] = hl
            if de:
                c.k['hl'] = de
        elif op in ('jp', 'jr') and len(args) == 1 or op == 'ret' and not args:
            c.forget()                                           # what follows is reached only through a label
        elif op in ('jp', 'jr') and len(args) == 2 or op == 'ret':
            pass                                                 # conditional: the fall-through keeps what it knew
        elif op in ('push', 'bit', 'cp', 'nop', 'scf', 'ccf', 'di', 'ei'):
            if op == 'cp':
                pass
        elif op in ('or', 'and', 'xor', 'sub', 'add', 'adc', 'sbc', 'neg', 'cpl', 'rla', 'rra', 'rlca', 'rrca',
                    'daa') and (not args or args[0].lower() == 'a' or len(args) == 1):
            c.forget('a')                                        # 8-bit arithmetic writes A (and only A)
            if args and args[-1].startswith('(') and mem(args[-1]) is None and op != 'cp':
                pass
        elif op in ('add', 'adc', 'sbc') and args and args[0].lower() in R16:
            c.forget(args[0].lower())
        elif op in ('inc', 'dec') and args:
            r = args[0].lower()
            if r in R8:
                c.forget(R8[r])
            elif r in R16:
                c.forget(r)
            elif mem(args[0]) is None:
                c.forget_memory()                                # inc (hl): through a pointer
            else:
                c.forget()
        elif op == 'pop' and args:
            r = args[0].lower()
            c.forget('a' if r == 'af' else r)                    # the cache's key for AF is A (the numbers me found)
        elif op in ('djnz',):
            c.forget('bc')
        else:
            c.forget()                                           # call, ldir, ex (sp), rst, anything else
            c.forget_memory()
    return out


def refs(code):
    """every (base, offset) a line mentions, with whether the mention is the target of a plain store"""
    for line in code:
        if is_label(line):
            continue
        op, args = split(line)
        if op is None:
            continue
        for i, a in enumerate(args):
            for m in re.finditer(r'\(?([A-Za-z_][\w.]*)((?:[+-]\d+)*)\)?', a):
                base = m.group(1)
                off = sum(int(x) for x in re.findall(r'[+-]\d+', m.group(2))) if m.group(2) else 0
                store = op == 'ld' and i == 0 and a.startswith('(') and len(args) == 2 and \
                    args[1].lower() in ('a', 'hl', 'de', 'bc') and mem(a) is not None
                yield line, (base, off), store


def dead_stores(code, cold, temps):
    """delete plain stores to temps that nothing reads"""
    table = {(tb, to + k): t for t, (tb, to, tn) in temps.items() for k in range(tn)}

    def owner(base, off):
        return table.get((base, off))
    read = set()
    for line, (base, off), store in list(refs(code)) + list(refs(cold)):
        t = owner(base, off)
        if t is not None and not store:
            read.add(t)
    out = []
    for line in code:
        op, args = split(line) if not is_label(line) else (None, [])
        if op == 'ld' and len(args) == 2 and mem(args[0]) and args[1].lower() in ('a', 'hl', 'de', 'bc'):
            t = owner(*mem(args[0]))
            if t is not None and t not in read:
                continue
        out.append(line)
    return out


def spill_pass(code):
    """A binary operation whose right side is loaded after its left is in HL comes out as
        ld (T),hl / ld hl,X / ex de,hl / ld hl,(T)
    (the left kept in T while HL loads the right, then swapped into DE). That's ld (T),hl / ld de,X: the same HL, DE
    and memory, and no flags change either way. The store to T stays, for dead_stores to drop if nothing else reads
    it. X is a constant or a direct address (ld de,nn and ld de,(nn) both exist). (Speccy-Zone, 18 Nov 2026, after
    Fronds' profile of the elves against SDCC.)"""
    sig = [i for i, line in enumerate(code) if split(line)[0] is not None or is_label(line)]
    drop = set()
    for k in range(len(sig) - 3):
        i0, i1, i2, i3 = sig[k:k + 4]
        if any(is_label(code[i]) for i in (i0, i1, i2, i3)) or drop & {i0, i1, i2, i3}:
            continue
        (o0, a0), (o1, a1), (o2, a2), (o3, a3) = (split(code[i]) for i in (i0, i1, i2, i3))
        if not (o0 == 'ld' and len(a0) == 2 and a0[1].lower() == 'hl' and mem(a0[0]) is not None):
            continue
        if not (o1 == 'ld' and len(a1) == 2 and a1[0].lower() == 'hl'):
            continue
        x = a1[1]
        if not simple(x):
            continue
        if not (o2 == 'ex' and [a.lower() for a in a2] == ['de', 'hl']):
            continue
        if not (o3 == 'ld' and len(a3) == 2 and a3[0].lower() == 'hl' and mem(a3[1]) == mem(a0[0])):
            continue
        code = code[:i1] + ['        ld de,' + x] + code[i1 + 1:]
        drop |= {i2, i3}
    code = [line for i, line in enumerate(code) if i not in drop]
    # and ld hl,X / ex de,hl / ld hl,Y, where HL is loaded again at once: ld de,X / ld hl,Y (the HL that ex de,hl
    # brought over from DE is never read)
    sig = [i for i, line in enumerate(code) if split(line)[0] is not None or is_label(line)]
    drop = set()
    for k in range(len(sig) - 2):
        i0, i1, i2 = sig[k:k + 3]
        if any(is_label(code[i]) for i in (i0, i1, i2)) or drop & {i0, i1, i2}:
            continue
        (o0, a0), (o1, a1), (o2, a2) = (split(code[i]) for i in (i0, i1, i2))
        if not (o0 == 'ld' and len(a0) == 2 and a0[0].lower() == 'hl' and simple(a0[1])):
            continue
        if not (o1 == 'ex' and [a.lower() for a in a1] == ['de', 'hl']):
            continue
        if not (o2 == 'ld' and len(a2) == 2 and a2[0].lower() == 'hl' and simple(a2[1])):
            continue
        code = code[:i0] + ['        ld de,' + a0[1]] + code[i0 + 1:]
        drop.add(i1)
    code = [line for i, line in enumerate(code) if i not in drop]
    # and ld (T),de / ld de,X / ld hl,(T): HL gets what DE had, so ld (T),de / ex de,hl / ld de,X (the store stays
    # for dead_stores; if X is (T) itself, it still reads what was stored)
    sig = [i for i, line in enumerate(code) if split(line)[0] is not None or is_label(line)]
    for k in range(len(sig) - 2):
        i0, i1, i2 = sig[k:k + 3]
        if any(is_label(code[i]) for i in (i0, i1, i2)):
            continue
        (o0, a0), (o1, a1), (o2, a2) = (split(code[i]) for i in (i0, i1, i2))
        if not (o0 == 'ld' and len(a0) == 2 and a0[1].lower() == 'de' and mem(a0[0]) is not None):
            continue
        if not (o1 == 'ld' and len(a1) == 2 and a1[0].lower() == 'de' and simple(a1[1])):
            continue
        if not (o2 == 'ld' and len(a2) == 2 and a2[0].lower() == 'hl' and mem(a2[1]) == mem(a0[0])):
            continue
        code[i1], code[i2] = '        ex de,hl', '        ld de,' + a1[1]
    return code


def simple(x):
    """a constant, or a direct address: what ld hl,x and ld de,x both take"""
    if x.startswith('('):
        return mem(x) is not None
    return re.fullmatch(r'[\w.+\-$#]+', x) is not None and x.lower() not in REGS


def optimise(code, cold, temps):
    """temps: name -> (base, offset, size)"""
    for _ in range(3):
        new = dead_stores(spill_pass(cache_pass(code)), cold, temps)    # the cache first: a reload it can drop
                                                                         # is cheaper gone than rewritten
        if new == code:
            break
        code = new
    return code
