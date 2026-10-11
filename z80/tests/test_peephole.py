"""peephole.py's register cache, on hand-written stretches of generated code: what it may delete, and what it must
keep. The pass has no other test of its own; the suite only sees it through whole programs, where a wrong deletion
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


def main():
    bad = 0
    for what, code, line, n in CASES:
        out = peephole.cache_pass(['        ' + c if not c.endswith(':') else c for c in code])
        got = sum(1 for o in out if o.strip() == line)
        if got != n:
            bad += 1
            print(f'WRONG {what}: {got} of "{line}" left, wanted {n}\n      ' + '\n      '.join(out))
    print('peephole:', 'all right' if not bad else f'{bad} wrong', f'({len(CASES)} cases)')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
