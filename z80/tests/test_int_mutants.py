"""Watching test_int.py fail: break the integer library on purpose, one way at a
time, and see the tests notice.

Each mutant is a copy of lib/ with one change; the linker is pointed at the
copy, so lib/ itself is never touched. A mutant counts as caught when its test
section reports anything WRONG (or the run blows up). Run it with omse-ai's
Python ($OMSE_AI_PYTHON).
"""
import argparse
import contextlib
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(prog='test_int_mutants.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('count', type=int, nargs='?', default=300,
                help='random cases per routine, for test_int (default 300)')
COUNT = str(ap.parse_args().count)
sys.argv = [sys.argv[0], COUNT]                    # test_int reads its count when it's imported
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
import harness                                     # noqa: E402
import link                                        # noqa: E402
import test_int                                    # noqa: E402

# (file, the text to change, what it becomes, the test section that should notice, what the change breaks)
MUTANTS = [
    # dword (intu32.asm)
    ('intu32.asm', 'call bly_i_mul16            ; HL = the low word of ahi * blo\n        ld de,(.hi)\n        add hl,de', 'call bly_i_mul16            ; HL = the low word of ahi * blo\n        ld de,(.hi)\n        ex de,hl', 'dword', 'mul_u32: drop ahi * blo'),
    ('intu32.asm', '.ne:    sbc a,a', '.ne:    ccf\n        sbc a,a', 'dword', 'cmp_u32 backwards'),
    ('intu32.asm', '.l:     srl h                       ; a bit at a time', '.l:     sra h                       ; a bit at a time', 'dword', 'shr_u32 keeps the sign'),
    ('intu32.asm', 'ld a,d\n        or a\n        jr nz,.zero', 'ld a,d\n        and 0\n        jr nz,.zero', 'dword', 'shr_u32 by 256 is by 0'),
    ('intu32.asm', 'ld hl,bly_i_ur              ; the remainder', 'ld hl,bly_i_ua              ; the remainder', 'dword', 'divmod_u32: the quotient for the remainder'),
    ('intu32.asm', 'jp z,bly_div0', 'nop\n        nop\n        nop', 'dword', 'divmod_u32 by zero goes on'),
    ('intu32.asm', 'ld a,0\n        sbc a,(hl)', 'ld a,1\n        sbc a,(hl)', 'dword', 'neg_u32 off by a carry'),
    # 16-bit
    ('int16.asm', 'adc a,0                     ; never reaches', 'nop                         ; never reaches', '16-bit', '16x8: drop the carry into the third byte'),
    ('int16.asm', 'cp 80h\n        jr c,.ok', 'cp 81h\n        jr c,.ok', '16-bit', 'mul_i16: let -32769 through'),
    ('int16.asm', 'jr c,.ok\n        jp nz,bly_ovf_int\n        ld a,l', 'jr .ok\n        jp nz,bly_ovf_int\n        ld a,l', '16-bit', 'mul_i16: no check on negative products'),
    ('int16.asm', 'cp e\n        jr c,.half', 'cp e\n        jr nc,.half', '16-bit', 'divu16: the byte-quotient shortcut backwards'),
    ('int16.asm', 'rra                         ; only', 'scf                         ; only', '16-bit', 'rem_i16 fails on -32768 % -1'),
    ('int16.asm', 'ld l,h\n        ld h,0\n        REPT 8', 'ld l,h\n        ld h,1\n        REPT 8', '16-bit', 'divu16, two-byte divisor: a wrong start'),
    ('int16.asm', 'add hl,de                   ; put it back', 'nop                         ; put it back', '16-bit', 'divu16, two-byte divisor: never restore'),
    ('int16.asm', 'sub e                       ; it goes; no borrow', 'sub d                       ; it goes; no borrow', '16-bit', 'div8: subtract the wrong register'),
    ('int16.asm', 'ld a,c\n        cpl\n        ld c,a\n        ld a,b', 'ld a,c\n        nop\n        ld c,a\n        ld a,b', '16-bit', 'div8: forget to complement the quotient'),
    ('int16.asm', 'jr c,.ws', 'nop', '16-bit', 'div8 by 128..255: lose the 9th bit'),
    ('int16.asm', 'bit 7,e\n        jr nz,.wide', 'bit 7,e\n        nop\n        nop', '16-bit', 'div8: 128..255 through the fast loop'),
    # add, sub, neg, cmp
    ('intarith.asm', 'ret po\n        jp bly_ovf_long\n\nbly_sub_i64', 'ret pe\n        jp bly_ovf_long\n\nbly_sub_i64', 'add', 'add_i32: overflow test inverted'),
    ('intarith.asm', 'ld a,(hl)                   ; the top bytes compare signed: flip their sign bits and compare unsigned\n        xor 80h',
     'ld a,(hl)\n        xor 0', 'add', 'cmp: the top byte unsigned'),
    ('intarith.asm', 'bly_neg_i64:\n        ld d,0', 'bly_neg_i64:\n        ld d,1', 'add', 'neg_i64: subtract from 1s'),
    # bits and shifts
    ('intbits.asm', 'and 1Fh', 'and 0Fh', 'bits', 'shifts: lose the 16 in the byte count'),
    ('intbits.asm', 'dec b\n        sra (hl)\n.rr:', 'dec b\n        srl (hl)\n.rr:', 'bits', 'shr, 8 bits and up: logical, not arithmetic'),
    ('intbits.asm', 'sra a                       ; the first pass', 'srl a                       ; the first pass', 'bits', 'shr, 1 to 7 bits: logical, not arithmetic'),
    ('intbits.asm', 'or a\n.p1:    ld a,(hl)\n        rla', 'scf\n.p1:    ld a,(hl)\n        rla', 'bits', 'shl, 1 to 7 bits: a 1 shifted in'),
    ('intbits.asm', 'pop hl\n        dec e\n        ret z\n.pn:    push hl\n        ld a,(.n)\n        ld b,a',
     'pop hl\n        dec e\n        dec e\n        ret z\n.pn:    push hl\n        ld a,(.n)\n        ld b,a', 'bits', 'shl, 1 to 7 bits: one pass short'),
    ('intbits.asm', 'lddr', 'ldir', 'bits', 'shl: move bytes the wrong way'),
    ('intbits.asm', 'bly_xor_i32:\n        REPT 4\n        ld a,(de)\n        xor (hl)', 'bly_xor_i32:\n        REPT 4\n        ld a,(de)\n        or (hl)', 'bits', 'xor is or'),
    # multiply
    ('intmul64.asm', 'dec a                       ; na + nb - 1', 'nop                         ; na + nb - 1', 'multiply', 'mul_i64: the byte-width rule one byte too strict'),
    ('intmul64.asm', 'cp 80h\n        jr nz,.ovf', 'cp 81h\n        jr nz,.ovf', 'multiply', 'mul_i64: refuse exactly MIN'),
    ('intmul64.asm', 'jr nc,.c1\n        inc b', 'jr .c1\n        inc b', 'multiply', 'mul_i64: drop a digit carry'),
    ('intmul64.asm', 'ld (.digit+2),a             ; self-modifying: ld e,(ix+d)\n        inc a',
     'ld (.digit+2),a\n        inc a\n        inc a', 'multiply', 'mul_i64: read the wrong high byte of a digit'),
    ('intmul32.asm', 'jp nz,bly_ovf_long          ; neither fits', 'nop\n        nop\n        nop                         ; neither fits', 'multiply', 'mul_i32: forget that two wide ones overflow'),
    ('intmul32.asm', 'sub 80h\n        or e', 'sub 81h\n        or e', 'multiply', 'mul_i32: refuse exactly MIN'),
    ('intmul32.asm', 'add hl,de\n        jp c,bly_ovf_long', 'add hl,de\n        nop\n        nop\n        nop', 'multiply', 'mul_i32: miss the carry out of the high word'),
    ('intmul32.asm', 'ld a,d\n        or e\n        jp nz,bly_ovf_long\n        pop de', 'ld a,d\n        and e\n        jp nz,bly_ovf_long\n        pop de', 'multiply', 'mul_i32: Xhi*Y past 16 bits let through'),
    ('intmul32.asm', 'ld e,a\n        ld d,0\n        ret\n.full:', 'ld e,0\n        ld d,0\n        ret\n.full:', 'multiply', 'mul16: lose the third byte when y < 256'),
    ('intmisc.asm', 'or a\n        ret p\n        push af', 'or a\n        ret m\n        push af', 'multiply', 'copyabs: negate the positives, keep the negatives'),
    ('intmisc.asm', 'ld a,0\n        sbc a,h\n        ld h,a\n        ret', 'ld a,1\n        sbc a,h\n        ld h,a\n        ret', 'multiply', 'neg32: the top byte off by one'),
    ('intmisc.asm', 'ret nz\n        dec a\n        ret', 'ret nz\n        nop\n        ret', 'multiply', 'sig: one byte too many when the pair\'s upper byte is 0'),
    # divide
    ('intdiv.asm', 'jr c,.big16', 'nop', 'divide', 'div by 32768 and up: lose the 17th bit'),
    ('intdiv.asm', 'bit 7,b\n        jr nz,.wide16', 'bit 7,b\n        nop\n        nop', 'divide', 'div by 32768 and up through the fast loop'),
    ('intdiv.asm', 'add hl,bc                   ; put back', 'nop                         ; put back', 'divide', 'div by two bytes: never restore'),
    ('intdiv.asm', 'jr c,.f32                   ; a 33rd bit', 'nop                         ; a 33rd bit', 'divide', 'div by 4 bytes: lose the 33rd bit'),
    ('intdiv.asm', 'ld (ix+0),0                 ; and the quotient', 'nop                         ; and the quotient', 'divide', 'div by 3-4 bytes: the quotient\'s top bytes not cleared'),
    ('intdiv.asm', 'adc a,(ix+3)\n        ld h,a\n.n32:', 'adc a,(ix+2)\n        ld h,a\n.n32:', 'divide', 'div by 3-4 bytes: a wrong add-back'),
    ('intdiv.asm', 'quads only\n        inc a', 'quads only\n        nop', 'divide', 'div by 5+ bytes: a remainder one byte short'),
    ('intdiv.asm', 'bit 7,(hl)\n        jp nz,bly_ovf_n', 'bit 6,(hl)\n        jp nz,bly_ovf_n', 'divide', 'div_i64: the MIN / -1 test on the wrong bit'),
    ('intdiv.asm', 'bit 7,h                     ; a positive quotient', 'bit 6,h                     ; a positive quotient', 'divide', 'div_i32: the MIN / -1 test on the wrong bit'),
    ('intdiv.asm', '.rem:   ld a,(.sa)', '.rem:   ld a,(.sb)', 'divide', 'div_i64: the remainder takes the divisor\'s sign'),
    ('intdiv.asm', 'ld (ix+1),0\n        dec ix', 'ld (ix+1),1\n        dec ix', 'divide', 'div by two bytes: a skipped digit not cleared'),
    ('intdiv.asm', 'ld (hl),0\n        dec hl\n        dec d', 'dec hl\n        dec d', 'divide', 'div by a byte: a skipped byte not cleared'),
    ('intdiv.asm', 'jp z,.gen                   ; -65536', 'nop\n        nop\n        nop                         ; -65536', 'divide', 'div_i32: -65536 taken as a 16-bit divisor'),
    ('intdiv.asm', 'jr c,.skip                  ; a\'s high word', 'jr nc,.skip                 ; a\'s high word', 'divide', 'div_i32: the high-word shortcut backwards'),
    # quad functions
    ('intquad.asm', 'srl d\n        rr e\n        inc b', 'srl d\n        rr e\n        nop', 'quad', 'gcd16: forget the common twos'),
    ('intquad.asm', 'add a,8', 'add a,7', 'quad', 'binary gcd: miscount a zero byte'),
    ('intquad.asm', 'ld a,8                      ; a positive product', 'ld a,88h                    ; a positive product', 'quad', 'lcm: let 2^63 through'),
    ('intquad.asm', '.same:  ld a,(.sm)', '.same:  ld a,(.sa)', 'quad', 'mod: the dividend\'s sign'),
    ('intquad.asm', '.long:  ld c,4', '.long:  ld c,3', 'quad', 'fit: long checked as three bytes'),
    ('intquad.asm', 'bit 7,(hl)\n        ret z\n        jp bly_ovf_quad             ; |MIN|', 'bit 6,(hl)\n        ret z\n        jp bly_ovf_quad             ; |MIN|', 'quad', 'abs: the wrong overflow bit'),
    ('intquad.asm', 'jp m,bly_ovf_quad', 'jp z,bly_ovf_quad', 'quad', 'gcd: 2^63 let through'),
    ('intquad.asm', 'jp z,bly_mod0', 'nop\n        nop\n        nop', 'quad', 'mod: no failure for mod by zero'),
]


def run_section(lib, title):
    real = link.gather
    harness.gather = lambda symbols, target: real(symbols, target, lib=lib)
    test_int.Tally.all.clear()
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            for t, needs, fn in test_int.SECTIONS:
                if title in t:
                    fn(test_int.runner(needs))
        return sum(t.bad for t in test_int.Tally.all), sum(t.n for t in test_int.Tally.all), ''
    except Exception as e:                         # a routine that never ends counts; an assembly error doesn't
        msg = str(e).splitlines()[0][:80]
        return (None if msg.startswith('sjasmplus') else -1), 0, f'{type(e).__name__}: {msg}'
    finally:
        harness.gather = real


def main():
    caught = missed = 0
    only = os.environ.get('ONLY')
    for fname, old, new, title, what in MUTANTS:
        if only and only not in what:
            continue
        with tempfile.TemporaryDirectory() as d:
            lib = os.path.join(d, 'lib')
            shutil.copytree(link.LIB, lib)
            path = os.path.join(lib, fname)
            text = open(path).read()
            if text.count(old) != 1:
                print(f'  ??  {fname}: the text to change is there {text.count(old)} times: {what}')
                missed += 1
                continue
            open(path, 'w').write(text.replace(old, new))
            bad, n, err = run_section(lib, title)
        if bad is None:
            missed += 1
            print(f'  INVALID {what:55} the mutant doesn\'t assemble: fix the mutant')
        elif bad:
            caught += 1
            print(f'  caught  {what:55} ' + (err or f'{bad} of {n} wrong'))
        else:
            missed += 1
            print(f'  MISSED  {what:55} all {n} cases still right')
    print(f'mutants: {caught} caught, {missed} missed')


if __name__ == '__main__':
    main()
