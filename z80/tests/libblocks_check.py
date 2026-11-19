"""libblocks.py's rules, each broken on purpose in a copy of a real fragment: the check must say so every time, and
each breakage must really have gone in (a mutant that didn't apply proves nothing). Then link.resolve on a small
program: what it keeps, what it drops, and that it follows chains and NEEDS. Speccy-Zone Fern, 19 Nov 2026."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import libblocks                                                        # noqa: E402
import link                                                             # noqa: E402

LIB = os.path.join(HERE, '..', 'lib')


def text(name):
    return open(os.path.join(LIB, name)).read()


# (what, fragment, the text replaced, what replaces it, a word the complaint must have)
MUTANTS = [
    ('a run-on into the next routine, not brought', 'core.asm',
     ';; routine bly_pr_i16 (brings bly_pr_u16)\n', ';; routine bly_pr_i16\n', 'run on into bly_pr_u16'),
    ('a call that runs on into the routine it called, not brought', 'intbits.asm',
     ';; routine bly_and_i64 (brings bly_and_i32)\n', ';; routine bly_and_i64\n', 'run on into bly_and_i32'),
    ('a jump to another routine\'s .local label, not brought', 'gen.asm',
     ';; routine bly_cmp_u8 (brings bly_cmp_u16)\n', ';; routine bly_cmp_u8\n', '.local label of bly_cmp_u16'),
    ('a jump to a label at the very end, which runs on, not brought', 'num.asm',
     ';; routine bly_pr_u32 (brings bly_n_dig)\n', ';; routine bly_pr_u32\n', 'run on into bly_n_dig'),
    ('a label the tools read, put in a block', 'plat_zx.asm',
     'bly_inputs_left: db 0', ';; routine bly_inputs_left\nbly_inputs_left: db 0\n;; end bly_inputs_left\n;',
     'read by the tools'),
    ('two routines in one block', 'gen.asm', [(';; end bly_cmp_u16\n;; routine bly_cmp_i16\n', ''),
                                              (';; end bly_cmp_i16\n', ';; end bly_cmp_u16\n')],
     None, 'holds other routines'),
    ('a marker naming another label than its block\'s first', 'gen.asm',
     ';; routine bly_cmp_i16\n', ';; routine bly_cmp_x\n', 'doesn\'t close'),
    ('a block left open', 'gen.asm', ';; end bly_cmp_u16\n', '', 'starts inside'),
    ('a marker misspelt', 'gen.asm', [(';; routine bly_cmp_i16\n', ';; routine: bly_cmp_i16\n'),
                                      (';; end bly_cmp_i16\n', ';;end bly_cmp_i16\n')], None, 'looks like a marker'),
    ('shared data put in a block', 'zxfzx.asm', 'zxf_font: dw 0\n',
     ';; routine zxf_font\nzxf_font: dw 0\n;; end zxf_font\n', 'holds only data'),
    ('a routine\'s .local label left outside its block', 'num.asm',
     '.go:                                ; fall into bly_n_dig\n;; end bly_pr_u32\n',
     ';; end bly_pr_u32\n.go:                                ; fall into bly_n_dig\n', 'outside its block'),
    ('bringing a routine that isn\'t marked', 'gen.asm', ';; routine bly_cmp_i16\n',
     ';; routine bly_cmp_i16 (brings bly_nothing)\n', 'isn\'t a marked routine'),
    ('a routine marked (fails) that can return', 'gen.asm', ';; routine bly_cmp_i16\n',
     ';; routine bly_cmp_i16 (fails)\n', 'can return'),
    ('a routine that doesn\'t fail bringing one that does', 'core.asm', ';; routine bly_fail (brings bly_fail_end) (fails)\n',
     ';; routine bly_fail (brings bly_fail_end)\n', 'only fails'),
    ('a routine that doesn\'t fail naming a .local of one that does', 'core.asm',
     ';; routine bly_fail_index_i16 (brings bly_fail_index_u16) (fails)\n',
     ';; routine bly_fail_index_i16 (brings bly_fail_index_u16)\n', 'only fails'),
]

PROGRAM = """        call r_a
        ld hl,(v_kept)
        ret
;; routine r_a (brings r_b)
r_a:    call r_c
;; end r_a
;; routine r_b
r_b:    ret
;; end r_b
;; routine r_c
r_c:    ret                     ; r_c, named only by r_a
;; end r_c
;; routine r_d
r_d:    call r_e                ; nobody names r_d, so r_e goes too
        ret
;; end r_d
;; routine r_e
r_e:    ret
;; end r_e
v_kept: dw 0
;; routine r_f
r_f:    ld hl,0                 ; ld hl,(v_kept) and call r_d here are a comment, and "r_d" a string
        db "r_d"
        ret
;; end r_f
;; routine bly_terse
bly_terse: ret
;; end bly_terse
;; routine r_fail (fails)
r_fail: jp r_e                  ; a terse build drops it: what it names isn't kept for it
;; end r_fail
"""


def main():
    bad = 0
    clean = {f: libblocks.check_text(f, text(f)) for f in {m[1] for m in MUTANTS}}
    for f, errs in clean.items():
        if errs:
            bad += 1
            print(f'WRONG: {f} isn\'t clean to start with: {errs[0]}')
    for what, f, old, new, word in MUTANTS:
        t = text(f)
        pairs = old if isinstance(old, list) else [(old, new)]
        if any(t.count(o) != 1 for o, _ in pairs):
            bad += 1
            print(f'WRONG: the mutant "{what}" didn\'t apply in {f}')
            continue
        for o, n in pairs:
            t = t.replace(o, n)
        errs = libblocks.check_text(f, t)
        if not any(word in e for e in errs):
            bad += 1
            print(f'WRONG: "{what}" wasn\'t caught' + (f'; it said: {errs[0]}' if errs else ''))
    out = link.resolve(PROGRAM)
    labels = set(re.findall(r'^([A-Za-z_]\w*):', out, re.M))
    want = {'r_a', 'r_b', 'r_c', 'v_kept'}
    if labels != want:
        bad += 1
        print(f'WRONG: resolve kept {sorted(labels)}, wanted {sorted(want)}')
    if any(f' r_{x}' in line for line in out.splitlines() if line.startswith(';;') for x in 'def'):
        bad += 1
        print('WRONG: resolve left the markers of a dropped routine')
    terse = link.resolve(PROGRAM.replace('        call r_a\n', '        call r_a\n        jp z,r_fail\n', 1),
                         terse=True)
    tl = set(re.findall(r'^([A-Za-z_]\w*):', terse, re.M))
    if tl != want | {'bly_terse'} or 'r_fail equ bly_terse' not in terse:
        bad += 1
        print(f'WRONG: terse resolve kept {sorted(tl)}, and r_fail as bly_terse: {"r_fail equ bly_terse" in terse}')
    if 'r_fail equ' in link.resolve(PROGRAM.replace('        call r_a\n', '        call r_a\n        jp z,r_fail\n', 1)):
        bad += 1
        print('WRONG: an ordinary resolve made r_fail bly_terse')
    print('libblocks_check:', 'all right' if not bad else f'{bad} wrong', f'({len(MUTANTS)} mutants, and resolve)')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
