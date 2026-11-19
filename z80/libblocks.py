#!/usr/bin/env python3
"""The library's routines are linked one by one, not a fragment at a time: each is marked off in its fragment, and
link.resolve keeps it only if something kept names it, following chains (a routine named only by a routine nobody
names goes too). This holds the rules that keep that right, and can mark a fragment's routines.

    libblocks.py            check every fragment in lib/ (./check runs this)
    libblocks.py --wrap F   mark off each routine of fragment F, with what it brings

The form (ABI.md, section 3), comments to the assembler, so a fragment assembled on its own has every routine:

    ;; routine bly_cmp_u8 (brings bly_cmp_u16)
    bly_cmp_u8:
            cp e
            jr bly_cmp_u16.three
    ;; end bly_cmp_u8

"brings" lists the routines that must come along whatever names this one: those it can run on into, and those whose
.local labels it uses. The rules, each a way a routine could be dropped while something still runs into it:
1. A block is one routine: "routine X", then X's label, no other global label, then "end X". Blocks don't nest.
2. Code that can run off its end (its last instruction, data after it aside, isn't ret, reti, retn, or a jp or jr
   with no condition; a .local label after it counts as a way in) into a block brings that block's routine.
   Otherwise the next routine might not be there, and the code would run into whatever is. This is the one mistake
   the assembler can't see.
3. Code that names another routine's .local label brings that routine (the assembler would only say the label is
   undefined, in a program that happens to drop the routine).
4. A label the tools read from the symbol table (TOOL_READ) is never in a block.
5. A routine's .local labels are inside its block (left outside, one would stay when the block goes, and belong to
   whatever routine came before it).
6. A block holds code. Data under a global label (a shared variable, a table) stays outside every block, because
   code can reach it by an offset from its neighbour (P_FLAG's +1 and +2 are P_COL and P_LIN, say), and nothing in a
   name shows that. Data a routine owns sits in its block under a .local label.
Code outside every block is always kept, as all of it was before. A routine dropped by mistake shows up as an
undefined symbol in the assembly, which is loud; rules 2, 5 and 6 cover the quiet ways.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import link                                         # noqa: E402

LIB = os.path.join(HERE, 'lib')
TOOL_READ = {'bly_inputs_left'}                     # zxbuild.py pokes the count of inputs still to load into it
LABEL = re.compile(r'^([A-Za-z_]\w*):')             # a global label: at the start of the line, not .local
LOCAL = re.compile(r'^\.\w+:')
DATA = {'db', 'dw', 'ds', 'defb', 'defw', 'defs', 'defm', 'dm', 'byte', 'word', 'block'}
ENDS = {'ret', 'reti', 'retn'}


def stmt(line):
    """(label or None, mnemonic or None, operands) of a line, comments and the label taken off"""
    body = line.split(';', 1)[0].rstrip()
    lab = None
    m = LABEL.match(body)
    if m:
        lab, body = m.group(1), body[m.end():]
    elif LOCAL.match(body):
        body = body[body.index(':') + 1:]
    parts = body.split(None, 1)
    if not parts:
        return lab, None, ''
    op = parts[0].lower()
    if op in ('equ', '=') or (len(parts) > 1 and parts[1].split(None, 1)[0].lower() in ('equ', '=')):
        return None, None, ''                       # NAME equ VALUE: no address, no code
    return lab, op, parts[1].strip() if len(parts) > 1 else ''


def runs_on(ops):
    """can execution run off the end of these statements [(op, operands)]? Data at the end doesn't run, so it's the
    last instruction before it that decides: ret, reti, retn, or a jp or jr with no condition, doesn't run on;
    anything else does (a call or rst before data is taken to come back past it, as RST 8's inline byte does), and
    so does a .local label after the last instruction, since a jump to it runs on from there"""
    code = [o for k, o in enumerate(ops) if o[0] not in DATA and
            not (o[0] == '.label' and k + 1 < len(ops) and ops[k + 1][0] in DATA)]   # a label on data isn't a way in
    if not code:
        return False                                # data alone: nothing to run
    op, args = code[-1]
    if op in ENDS and not args:
        return False
    if op in ('jp', 'jr') and ',' not in args:
        return False
    return True


def is_code(ops):
    return any(o[0] not in DATA and o[0] != '.label' for o in ops)


def regions(lines):
    """the file cut at each global label: [(label or None, first, last)], last inclusive; a routine's region ends at
    its last statement or label, so the comments before the next label sit between regions"""
    starts = [i for i, l in enumerate(lines) if stmt(l)[0]]
    out = []
    if not starts or starts[0] > 0:
        out.append((None, 0, (starts[0] if starts else len(lines)) - 1))
    for k, i in enumerate(starts):
        end = (starts[k + 1] if k + 1 < len(starts) else len(lines)) - 1
        while end > i and stmt(lines[end])[1] is None and not LOCAL.match(lines[end]) and \
                not link.END.match(lines[end]):
            end -= 1                                # trailing blanks and comments belong to what follows
        out.append((stmt(lines[i])[0], i, end))
    return out


def facts(lines, first, last):
    """of a stretch: its statements (op, args), and the other routines' .locals it names"""
    ops, locals_ = [], set()
    for l in lines[first:last + 1]:
        if LOCAL.match(l):
            ops.append(('.label', ''))                # something can jump here: what follows can be reached
        _, op, args = stmt(l)
        if op is None:
            continue
        ops.append((op, args))
        for m in re.finditer(r'\b([A-Za-z_]\w*)\.[A-Za-z_]\w*', args):
            locals_.add(m.group(1))
    return ops, locals_


def check_text(name, text):
    lines = text.splitlines()
    errs = []
    try:
        bl = link.blocks(text)
    except ValueError as err:
        return [f'{name}: {err}']
    for line in lines:
        if re.match(r'^;;\s*(routine|end)\b', line) and not (link.MARK.match(line) or link.END.match(line)):
            errs.append(f'{name}: "{line}" looks like a marker but isn\'t one: ";; routine X (brings Y, Z)" '
                        f'or ";; end X"')
    inblock = {}
    for x, (a, b, _) in bl.items():
        for i in range(a, b + 1):
            inblock[i] = x
        labs = [(i, stmt(lines[i])[0]) for i in range(a + 1, b) if stmt(lines[i])[0]]
        if not labs or labs[0][1] != x:
            errs.append(f'{name}:{a + 1}: routine {x}, but the block\'s first label is '
                        f'{labs[0][1] if labs else "missing"}')
        if len(labs) > 1:
            errs.append(f'{name}:{a + 1}: the block for {x} holds other routines too: '
                        f'{", ".join(l for _, l in labs[1:])} (a block is one routine)')
        if any(stmt(lines[i])[1] is not None for i in range(a + 1, labs[0][0] if labs else b)):
            errs.append(f'{name}:{a + 1}: code before {x}\'s label in its block')
        for y in bl[x][2]:
            if y not in bl:
                errs.append(f'{name}:{a + 1}: {x} brings {y}, which isn\'t a marked routine here')
    owner = None                                    # rule 5
    for i, l in enumerate(lines):
        if stmt(l)[0]:
            owner = (stmt(l)[0], i in inblock)
        elif LOCAL.match(l) and owner and owner[1] and i not in inblock:
            errs.append(f'{name}:{i + 1}: {l.split(":")[0]} belongs to {owner[0]} but is outside its block')
    regs = regions(lines)
    for k, (lab, first, last) in enumerate(regs):
        ops, locs = facts(lines, first, last)
        brings = set(bl[lab][2]) if lab in bl and first in inblock else set()
        if lab in TOOL_READ and first in inblock:
            errs.append(f'{name}:{first + 1}: {lab} is read by the tools from the symbol table, so it can\'t be in '
                        f'a block')
        if first in inblock and ops and not is_code(ops):
            errs.append(f'{name}:{first + 1}: the block for {lab} holds only data: shared data stays outside the '
                        f'blocks, since code can reach it by an offset from its neighbour, which no name shows')
        nxt = regs[k + 1] if k + 1 < len(regs) else None
        if runs_on(ops) and nxt is not None and nxt[1] in inblock and inblock[nxt[1]] == nxt[0] \
                and nxt[0] not in brings:
            errs.append(f'{name}:{first + 1}: {lab or "the code before " + nxt[0]} can run on into {nxt[0]}, '
                        f'which is in a block: ' + (f'mark it "(brings {nxt[0]})"' if lab in bl else
                                                    f'{lab or "it"} isn\'t in a block, so {nxt[0]} can\'t be'))
        for y in sorted(locs - {lab} - brings):
            if y in bl:
                errs.append(f'{name}:{first + 1}: {lab or "code"} names a .local label of {y}, which is in a block: '
                            + (f'mark it "(brings {y})"' if lab in bl else f'{y} can\'t be in a block'))
    return errs


def wrap_text(text):
    """each routine marked off, with what it brings. Code before the first label, data, and TOOL_READ stay out, and
    so does a routine that unmarked code runs on into or names a .local of (it must always be there)"""
    lines = text.splitlines()
    regs = regions(lines)
    info = [facts(lines, first, last) for _, first, last in regs]
    marked = {lab for (lab, _, _), (ops, _) in zip(regs, info) if lab and lab not in TOOL_READ and is_code(ops)}
    changed = True
    while changed:
        changed = False
        for k, ((lab, _, _), (ops, locs)) in enumerate(zip(regs, info)):
            if lab in marked:
                continue
            nxt = regs[k + 1][0] if k + 1 < len(regs) else None
            for y in ([nxt] if runs_on(ops) and nxt else []) + sorted(locs):
                if y in marked:
                    marked.discard(y)
                    changed = True
    out, prev_end = [], -1
    for k, ((lab, first, last), (ops, locs)) in enumerate(zip(regs, info)):
        out += lines[prev_end + 1:first]
        prev_end = last
        body = lines[first:last + 1]
        if lab not in marked:
            out += body
            continue
        nxt = regs[k + 1][0] if k + 1 < len(regs) else None
        want = [nxt] if runs_on(ops) and nxt in marked else []
        want += sorted(y for y in locs - {lab} - set(want) if y in marked)
        out.append(f';; routine {lab}' + (f' (brings {", ".join(want)})' if want else ''))
        out += body
        out.append(f';; end {lab}')
    out += lines[prev_end + 1:]
    return '\n'.join(out) + ('\n' if text.endswith('\n') else '')


def main(argv=None):
    ap = argparse.ArgumentParser(prog='libblocks.py', description=__doc__.split('\n\n')[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--wrap', metavar='FRAGMENT', nargs='+', help='mark off these fragments\' routines, in place')
    a = ap.parse_args(argv)
    if a.wrap:
        for f in a.wrap:
            text = open(f).read()
            if link.blocks(text):
                sys.exit(f'{f} has its routines marked already')
            open(f, 'w').write(wrap_text(text))
        return 0
    errs, n, blocks = [], 0, 0
    for f in sorted(os.listdir(LIB)):
        if f.endswith('.asm'):
            text = open(os.path.join(LIB, f)).read()
            errs += check_text(f, text)
            n += 1
            blocks += len(link.blocks(text)) if not any(e.startswith(f + ': ') for e in errs) else 0
    for e in errs:
        print(e)
    print(f'libblocks: {n} fragments, {blocks} routines marked, ' + (f'{len(errs)} wrong' if errs else 'all right'))
    return 1 if errs else 0


if __name__ == '__main__':
    sys.exit(main())
