"""Operand homes: the generator's last pass (z80gen.py's compile_program), Melissa O'Neill's suggestion of 27 November
2026. A variable can live in the immediate operand of the instruction that reads it hottest: `ld de,(x)` (20 T)
becomes `ld de,nn` (10 T), and that nn is x's home, which every other use of x reads and writes instead of its slot.
No use gets slower, and `ld de,nn` is a byte shorter than `ld de,(nn)`. The first Barley measured the idea at 2 to 8%
(HISTORY.md), and on this generator's own code it measured 3.7% across the benchmarks, never slower, before it was
built in.

The pass works on the finished assembly, from the generator's record of every slot it made (Gen.slot_log, the
globals, the return values). A slot of 1 or 2 bytes gets a home if every use of it is a plain load or store of
exactly it (ld r,(x) / ld (x),r; a byte of a word may be loaded or stored alone). One whose address is taken, or that
shares a 16-bit access with a neighbour (the save rule pushes two byte parameters at once: hanoi's), stays where it
is. The home is the read at the deepest loop nesting (by backward jumps), ties going to the bigger saving (ld de or
bc: 10 T; ld hl, ld ix, ld a: 6), then the earlier. The slots start at zero, and a global without a value relies on
that, so bly_init_globals zeroes those globals' homes first (one with a value is given it there anyway; locals,
parameters and temporaries are always written before they're read). Code runs from RAM on both targets (ABI.md section 1)."""
import re

EXPR = re.compile(r'\b(fr_\w+|rv_\w+|gs)((?:\s*[+-]\s*\d+)*)')
NUM = re.compile(r'([+-])\s*(\d+)')
JUMP = re.compile(r'^\s+(?:jp|jr|djnz)\s+(?:(?:n?z|n?c|p[oe]?|m)\s*,\s*)?([A-Za-z_.][\w.]*)\s*$')
LABEL = re.compile(r'^([A-Za-z_.][\w.]*):')
REG16 = ('hl', 'de', 'bc', 'sp', 'ix', 'iy')
SAVES = {'de': 10, 'bc': 10, 'hl': 6, 'ix': 6, 'iy': 6, 'a': 6}    # T-states the immediate form saves
IMM_AT = {'hl': 1, 'de': 1, 'bc': 1, 'a': 1, 'ix': 2, 'iy': 2}     # where the operand is, from the label


def parse(expr):
    m = EXPR.fullmatch(expr.strip())
    if not m:
        return None
    return m.group(1), sum(int(s + d) for s, d in NUM.findall(m.group(2)))


def place(asm, slots, zeroed=()):
    """slots: (name, size) for every slot, name as the generator writes it (fr_f+4, gs+0, rv_f+0). zeroed: the
    slots that rely on starting at zero (the globals without a value). Returns the assembly with the homes in, and
    [(slot, register, loop depth)] for each."""
    zeroed = {parse(n) for n in zeroed}
    byte_of = {}                                        # (base, offset) -> the slot (base, start, size) it's in
    for name, sz in slots:
        b, off = parse(name)
        for k in range(sz):
            byte_of.setdefault((b, off + k), (b, off, sz))
    lines = asm.split('\n')
    labels = {m.group(1): i for i, m in ((i, LABEL.match(ln)) for i, ln in enumerate(lines)) if m}
    pinned, sites, refs = set(), {}, []
    for i, ln in enumerate(lines):
        code = ln.split(';', 1)[0]
        if not code.startswith((' ', '\t')) or ' equ ' in code:
            continue
        ins = code.strip()
        for m in EXPR.finditer(code):
            p = parse(m.group(0))
            slot = byte_of.get(p) if p else None
            if slot is None:
                continue
            s, e = m.span()
            refs.append((i, (s, e), slot, p[1] - slot[1]))
            ok = False
            if code[:s].rstrip().endswith('(') and code[e:].lstrip().startswith(')'):
                x = re.escape(m.group(0))
                rd = re.fullmatch(r'ld\s+(\w+)\s*,\s*\(\s*' + x + r'\s*\)', ins)
                wr = re.fullmatch(r'ld\s+\(\s*' + x + r'\s*\)\s*,\s*(\w+)', ins)
                r = (rd or wr).group(1).lower() if (rd or wr) else None
                w = 1 if r == 'a' else 2 if r in REG16 else 8
                touched = {byte_of[(p[0], p[1] + k)] for k in range(w) if (p[0], p[1] + k) in byte_of}
                if touched == {slot} and (w == 1 and slot[2] <= 2 or w == 2 and slot[2] == 2 and p[1] == slot[1]):
                    ok = True
                    if rd and r in SAVES and w == slot[2]:
                        sites.setdefault(slot, []).append((i, r))
            else:                                       # its address taken: it, and up to 8 bytes on, stay put
                touched = {byte_of[(p[0], p[1] + k)] for k in range(8) if (p[0], p[1] + k) in byte_of}
            if not ok:
                pinned.update(touched)
    loops = []
    for j, ln in enumerate(lines):
        m = JUMP.match(ln.split(';', 1)[0])
        if m and labels.get(m.group(1), j) < j:
            loops.append((labels[m.group(1)], j))
    depth = lambda i: sum(1 for a, b in loops if a <= i <= b)
    homes = {}
    for slot in sorted(sites):
        if slot in pinned:
            continue
        i, r = max(sites[slot], key=lambda s: (depth(s[0]), SAVES[s[1]], -s[0]))
        homes[slot] = (i, r, f'oh_{len(homes)}')
    by_line = {}
    for i, span, slot, delta in refs:
        if slot in homes:
            by_line.setdefault(i, []).append((span, slot, delta))
    for i, items in by_line.items():
        ln = lines[i]
        for (s, e), slot, delta in sorted(items, reverse=True):
            _, r, lab = homes[slot]
            ln = ln[:s] + f'{lab}+{IMM_AT[r] + delta}' + ln[e:]
        lines[i] = ln
    for slot, (i, r, lab) in homes.items():
        lines[i] = f'{lab}:  ld {r},0                 ; the home of {slot[0]}+{slot[1]}'
    zero = [f'        ld ({lab}+{IMM_AT[r]}),{"a" if r == "a" else "hl"}'
            for slot, (i, r, lab) in sorted(homes.items(), key=lambda h: h[1][2]) if slot[:2] in zeroed]
    if zero:
        k = lines.index('bly_init_globals:')
        lines[k + 1:k + 1] = ['        xor a', '        ld h,a', '        ld l,a'] + zero
    return '\n'.join(lines), [(slot, r, depth(i)) for slot, (i, r, lab) in homes.items()]
