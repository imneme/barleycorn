"""Watching test_fp.py fail: break fp.asm on purpose, one way at a time, and see the tests notice.

Each mutant is a copy of lib/ with one change to fp.asm (or, where it says, fp_exact.asm, the Z80-exact half,
or fp_read.asm, s.float()'s reading);
test_fp.py --quick runs against the copy (--lib), so lib/
itself is never touched. A mutant is caught when the run reports anything WRONG or blows up (the rig refuses a
call that leaves BASIC's state broken).

    $OMSE_AI_PYTHON z80/tests/test_fp_mutants.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, '..', 'lib')
FR = 'fp_read.asm'
FX = 'fp_exact.asm'

# (the text to change, what it becomes, what the change breaks[, the file: fp.asm unless it says])
MUTANTS = [
    ('        ld (hl),91h\n        inc hl\n        ld (hl),80h\n        ret', '        ret\n        nop\n        nop\n        nop',
     'keep the ROM\'s slipped -65536 (00 FF 00 00 00)'),
    ('        exx\n        ld hl,(.hlx)                ; BASIC\'s HL\' back\n        exx',
     '        nop\n        nop\n        nop\n        nop\n        nop', 'an error leaves HL\' as the calculator\'s pointer'),
    ('        pop hl                      ; .caught, unused\n        pop hl\n        ld (fp_ERR_SP),hl',
     '        pop hl                      ; .caught, unused\n        pop hl\n        nop\n        nop\n        nop',
     'ERR_SP left pointing at our handler'),
    ('        ld hl,(.xptr)\n        ld (fp_X_PTR),hl', '        nop\n        nop\n        nop\n        nop\n        nop\n        nop',
     'X_PTR left where the ROM\'s error put it'),
    ('        ld (hl),0FFh                ; no error', '        nop\n        nop                ; no error',
     'ERR_NR left holding the report'),
    ('        ld hl,(.stk)\n        ld (fp_STKEND),hl', '        nop\n        nop\n        nop\n        nop\n        nop\n        nop',
     'PRINT-FP\'s stray 0 left on the calculator stack'),
    ('        ld a,3\n        call fp_CHAN_OPEN', '        ld a,2\n        call fp_CHAN_OPEN', 'print on the screen\'s stream'),
    ('        neg                         ; both negative', '        nop\n        nop                         ; both negative',
     'compare: two negatives the wrong way round', FX),
    ('        bit 7,c                     ; round on the next bit', '        bit 7,b                     ; round on the next bit',
     'from_i64: round on the wrong bit', FX),
    ('.nrnd:  cp 3', '.nrnd:  cp 1', 'round: a negative half rounds away', FX),
    ('.prnd:  and 1', '.prnd:  and 2', 'round: a positive half rounds down', FX),
    ('.signed: db 0, 0, 1, 1, 1', '.signed: db 0, 0, 0, 1, 1', 'to_int: int checked as unsigned', FX),
    ('.width: db 1, 2, 2, 4, 8', '.width: db 1, 2, 2, 8, 8', 'to_int: long given a quad\'s range', FX),
    ('        jp z,bly_div0', '        nop\n        nop\n        nop', 'divide by zero through the ROM'),
    ('.par:   and 1', '.par:   and 0', '**: a negative base, an odd exponent, a positive answer'),
    ('        and 2\n        srl d', '        and 0\n        srl d', 'toint: forget the sticky bits', FX),
    ('        sbc hl,de                   ; |x| = 65536 - (lo hi)\n        pop de',
     '        add hl,de                   ; |x| = 65536 - (lo hi)\n        pop de', 'unpack: a negative short form\'s size', FX),
    ('        sbc hl,de                   ; |x| = 65536 - (lo hi), where', '        add hl,de                   ; |x| = 65536 - (lo hi), where',
     'toint: a negative short form\'s size', FX),
    ('        ld a,(hl)\n        cpl\n        ld (hl),a\n        ret', '        ld a,(hl)\n        nop\n        ld (hl),a\n        ret',
     'negate a short form: forget its sign byte', FX),
    ('        cp 4\n        jr c,.tok', '        cp 3\n        jr c,.tok', 'toint: 2^56..2^64 called too big', FX),
    ('        cp 34\n        jr c,.tn', '        cp 31\n        jr c,.tn', 'toint: tiny fractions cut short', FX),
    ('        cp 5\n        ld hl,.movf', '        cp 9\n        ld hl,.movf', 'overflow reported as no answer'),
    ('        ld (hl),0Dh                 ; an ENTER', '        nop\n        nop                 ; an ENTER',
     's.float: the ROM reads on past the number (2.5 3 is 2.53)', FR),
    ('        ld a,(.saved)\n        ld (hl),a\n        ret', '        ld a,(.saved)\n        nop\n        ret',
     's.float: the byte after the number left an ENTER', FR),
    ('.put:   ld hl,(.chadd)              ; CH_ADD, and the byte after the number, as they were\n        ld (5C5Dh),hl',
     '.put:   nop\n        nop\n        nop\n        nop\n        nop\n        nop', 's.float: CH_ADD left in the str', FR),
    ('        or a\n        jr z,.pos', '        or a\n        jr .pos', 's.float: a minus ignored', FR),
    ('        ld (5C3Dh),hl               ; and its ERR_SP', '        nop\n        nop\n        nop               ; and its ERR_SP',
     's.float: an error leaves ERR_SP at our handler', FR),
    ('        ld a,0FFh\n        ld (5C3Ah),a', '        nop\n        nop\n        nop\n        nop\n        nop',
     's.float: ERR_NR left holding the report', FR),
    ("        or 20h\n        cp 'e'", "        or 20h\n        cp 'x'", 's.float: an exponent never read (1E+05 is 1)', FR),
    ("        cp ' '\n        jr z,.skip", "        cp '!'\n        jr z,.skip", 's.float: spaces in front not skipped', FR),
    ('.whole: inc d\n        dec d\n        jp z,.bad', '.whole: nop\n        nop\n        nop\n        nop\n        nop',
     's.float: a point alone handed to the ROM', FR),
    ('.edig:  call .dig\n        jr nc,.noexp', '.edig:  call .dig\n        nop\n        nop',
     's.float: an e with no digits taken as an exponent (3east)', FR),
]


def main():
    py = sys.executable
    caught = 0
    for i, (old, new, what, *where) in enumerate(MUTANTS):
        with tempfile.TemporaryDirectory() as d:
            lib = os.path.join(d, 'lib')
            shutil.copytree(LIB, lib)
            p = os.path.join(lib, where[0] if where else 'fp.asm')
            s = open(p).read()
            if s.count(old) != 1:
                print(f'?? mutant {i} ({what}): its text is found {s.count(old)} times')
                continue
            open(p, 'w').write(s.replace(old, new))
            r = subprocess.run([py, os.path.join(HERE, 'test_fp.py'), '--quick', '--lib', lib],
                               capture_output=True, text=True, timeout=900)
            last = (r.stdout + r.stderr).strip().splitlines()[-1:] or ['']
            ok = r.returncode != 0
            caught += ok
            print(f'{"caught" if ok else "MISSED"}  {what}: {last[0][:110]}')
    print(f'{caught} of {len(MUTANTS)} mutants caught')
    sys.exit(0 if caught == len(MUTANTS) else 1)


if __name__ == '__main__':
    main()
