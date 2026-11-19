"""peephole.py's register cache and spill rewrites, on hand-written stretches of generated code: what they may
delete or change, and what they must keep. The pass has no other test of its own; the suite only sees it through whole programs, where a wrong deletion
shows only if a program happens to need the value. Each case is code in, and the lines that must or mustn't survive.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import peephole                                                         # noqa: E402

CASES = [
    # (what, code, the line counted, how many of it must be left)
    ('a reload of the same slot goes',
     ['ld hl,(fr_f+0)', 'ld a,(fr_h+0)', 'ld hl,(fr_f+0)', 'ld (fr_g+2),hl'], 'ld hl,(fr_f+0)', 1),
    ('a register remembers one slot: stored to another, it holds that one (so a reload of the first stays)',
     ['ld hl,(fr_f+0)', 'ld (fr_g+0),hl', 'ld hl,(fr_f+0)', 'ld (fr_g+2),hl'], 'ld hl,(fr_f+0)', 2),
    ('pop af gives A back: the reload after it stays (the numbers me, reading the code map)',
     ['ld a,(fr_f+0)', 'push af', 'ld a,(fr_f+1)', 'pop af', 'ld a,(fr_f+1)', 'ld (fr_g+0),a'], 'ld a,(fr_f+1)', 2),
    ('pop hl gives HL back: the reload after it stays',
     ['ld hl,(fr_f+0)', 'push hl', 'ld hl,(fr_f+2)', 'pop hl', 'ld hl,(fr_f+2)', 'ld (fr_g+0),hl'],
     'ld hl,(fr_f+2)', 2),
    ('a call forgets everything', ['ld hl,(fr_f+0)', 'call bly_x', 'ld hl,(fr_f+0)', 'ld (fr_g+0),hl'],
     'ld hl,(fr_f+0)', 2),
    ('a label forgets everything', ['ld a,(fr_f+0)', 'L1:', 'ld a,(fr_f+0)', 'ld (fr_g+0),a'], 'ld a,(fr_f+0)', 2),
    ('a store to the slot it holds forgets it', ['ld hl,(fr_f+0)', 'ld (fr_f+1),a', 'ld hl,(fr_f+0)', 'ld (fr_g+0),hl'],
     'ld hl,(fr_f+0)', 2),
]


# spill_pass's three rewrites, run before and after on a tiny model of the instructions they touch (HL, DE and the
# slots; flags don't change in any of them): the machine must end the same, and each case says whether it rewrites
SPILLS = [
    ('a left side kept in a slot while a constant loads', ['ld (fr_f+0),hl', 'ld hl,1', 'ex de,hl', 'ld hl,(fr_f+0)'],
     ['ld (fr_f+0),hl', 'ld de,1']),
    ('... or a global', ['ld (fr_f+0+0),hl', 'ld hl,(gs+4)', 'ex de,hl', 'ld hl,(fr_f+0)'],
     ['ld (fr_f+0+0),hl', 'ld de,(gs+4)']),
    ('... or the slot itself', ['ld (fr_f+0),hl', 'ld hl,(fr_f+0)', 'ex de,hl', 'ld hl,(fr_f+0)'],
     ['ld (fr_f+0),hl', 'ld de,(fr_f+0)']),
    ('not across a label (the reload stays; the ld hl / ex de,hl / ld hl after it is the next rule\'s)',
     ['ld (fr_f+0),hl', 'L1:', 'ld hl,1', 'ex de,hl', 'ld hl,(fr_f+0)'],
     ['ld (fr_f+0),hl', 'L1:', 'ld de,1', 'ld hl,(fr_f+0)']),
    ('not when another slot is reloaded (the same)', ['ld (fr_f+0),hl', 'ld hl,1', 'ex de,hl', 'ld hl,(fr_f+2)'],
     ['ld (fr_f+0),hl', 'ld de,1', 'ld hl,(fr_f+2)']),
    ('HL loaded again at once after ex de,hl', ['ld hl,5', 'ex de,hl', 'ld hl,(gs+0)'], ['ld de,5', 'ld hl,(gs+0)']),
    ('... but not when HL is used', ['ld hl,5', 'ex de,hl', 'ld (gs+0),hl'], ['ld hl,5', 'ex de,hl', 'ld (gs+0),hl']),
    ('DE kept in a slot while DE loads, then HL takes the slot', ['ld (fr_f+4),de', 'ld de,(fr_f+2)', 'ld hl,(fr_f+4)'],
     ['ld (fr_f+4),de', 'ex de,hl', 'ld de,(fr_f+2)']),
    ('... DE loading that same slot', ['ld (fr_f+4),de', 'ld de,(fr_f+4)', 'ld hl,(fr_f+4)'],
     ['ld (fr_f+4),de', 'ex de,hl', 'ld de,(fr_f+4)']),
    ('not across a label in the DE rule', ['ld (fr_f+4),de', 'L2:', 'ld de,(fr_f+2)', 'ld hl,(fr_f+4)'],
     ['ld (fr_f+4),de', 'L2:', 'ld de,(fr_f+2)', 'ld hl,(fr_f+4)']),
]


def model(code):
    """run ld/ex on symbols: returns (HL, DE, slots)"""
    r, m = {'hl': 'HL0', 'de': 'DE0'}, {}
    for line in code:
        if peephole.is_label(line):
            continue
        op, args = peephole.split(line)
        if op == 'ex':
            r['hl'], r['de'] = r['de'], r['hl']
        elif op == 'ld' and args[0].startswith('('):
            m[peephole.mem(args[0])] = r[args[1]]
        elif op == 'ld':
            a = peephole.mem(args[1])
            r[args[0]] = m.get(a, ('was', a)) if a else ('k', args[1])
        else:
            raise ValueError(line)
    return r['hl'], r['de'], m


def spills():
    bad = 0
    for what, code, want in SPILLS:
        src = ['        ' + c if not c.endswith(':') else c for c in code]
        out = peephole.spill_pass(src)
        if model(out) != model(src) or [o.strip() for o in out] != want:
            bad += 1
            print(f'WRONG {what}: ' + ' / '.join(o.strip() for o in out))
    return bad


def main():
    bad = spills()
    for what, code, line, n in CASES:
        out = peephole.cache_pass(['        ' + c if not c.endswith(':') else c for c in code])
        got = sum(1 for o in out if o.strip() == line)
        if got != n:
            bad += 1
            print(f'WRONG {what}: {got} of "{line}" left, wanted {n}\n      ' + '\n      '.join(out))
    print('peephole:', 'all right' if not bad else f'{bad} wrong', f'({len(CASES) + len(SPILLS)} cases)')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
