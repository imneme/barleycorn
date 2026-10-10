;; provides: bly_fp bly_fadd bly_fsub bly_fmul bly_fdiv bly_fpow bly_fneg bly_fabs bly_fcmp bly_fsqrt bly_fsin bly_fcos bly_ftan bly_fasin bly_facos bly_fatan bly_fln bly_fexp bly_ftrunc bly_ffloor bly_fround bly_f_from_u16 bly_f_from_i16 bly_f_from_i64 bly_f_to_int bly_pr_f
;; needs: bly_out bly_pr_cstr bly_fail bly_div0
;; targets: zx48
;; Floats on the 48K Spectrum: the ROM's own 5-byte form, worked by the ROM's calculator (RST 28h). ABI.md section 11.
;; A float is 5 bytes, either the short form 00 s lo hi 00 (a whole number -65535..65535: s is 00 or FFh, and lo hi
;; is the number's 16-bit two's complement) or e m3 m2 m1 m0, the value 0.1mmm... (binary: 32 bits, the top 1 hidden
;; under m3's bit 7, which holds the sign) times 2^(e-128). Zero is 00 00 00 00 00.
;; bly_fadd bly_fsub bly_fmul bly_fdiv bly_fpow   in: HL=&a DE=&b BC=&r   out: (BC) = a + b and so on
;;        fails: float overflow; division by zero (/); float ** has no answer (0 ** b with b < 0, or a < 0 with b
;;        not a whole number)
;; bly_fsqrt bly_fsin bly_fcos bly_ftan bly_fasin bly_facos bly_fatan bly_fln bly_fexp   in: HL=&x BC=&r
;;        fails: {name}({x}) has no answer   (the ROM's "A Invalid argument" and "6 Number too big")
;; bly_ftrunc bly_ffloor bly_fround   in: HL=&x BC=&r   (exact, in Z80: not the ROM's INT, which has a bug at -65536)
;;        round is floor(x + 0.5), as the interpreter's
;; bly_fneg bly_fabs   in: HL=&x BC=&r (r may be x)
;; bly_fcmp            in: HL=&a DE=&b   out: A = FFh/0/1, flags as after OR A   (exact, in Z80; never fails)
;; bly_f_from_u16      in: HL = a byte or word, BC=&r      bly_f_from_i16   in: HL = an int, BC=&r
;; bly_f_from_i64      in: HL=&q (a quad: the generator widens a long), BC=&r   (rounded to 32 bits, half away from 0)
;; bly_f_to_int        in: HL=&x A=the type code (0 byte .. 4 quad, 5 dword) DE=&dest   truncates toward zero
;;        fails: {x} doesn't fit in {a type}
;; bly_pr_f            in: HL=&x   prints x as the ROM's PRINT-FP does, through bly_out (so print's column is kept);
;;                     leaves stream 2 (the upper screen) open, as bly_start does
;; Every routine clobbers AF BC DE HL IX; those that use the ROM also clobber BC' and DE' (the ROM's own scratch, as
;; RST 10 does). HL' and IY are BASIC's and are kept: the calculator borrows HL', and if the ROM fails part-way
;; we put it back. bly_fp is the shared part (its .labels are used across this file); nothing outside calls it.
;
; Catching the ROM's errors is Melissa O'Neill's call_with_errhandler (https://github.com/imneme/spectrum-minilib),
; borrowed with her blessing: push a handler, point ERR_SP at it, and the ROM's error unwinding (ERROR-3 sets
; SP from ERR_SP, then SET-STK's RET) returns into the handler, with the report code - 1 in ERR_NR. Hers passes the
; routine in the alternate registers; Barley's contract keeps out of those, so the routine here is always RST 28h
; with a one-operation script. ERR_SP, X_PTR (which ERROR-1 overwrites) and HL' are saved in memory first and put
; back by hand: HL' is read only to be restored, and not off the stack, where an interrupt during the ROM's error
; unwinding could overwrite it.
; Self-modifying code: bly_fp.lit is the script's one operation, written before each RST 28h.

fp_STKEND   equ 5C65h               ; the calculator stack's end: the top number is the 5 bytes below it
fp_ERR_SP   equ 5C3Dh
fp_ERR_NR   equ 5C3Ah
fp_X_PTR    equ 5C5Fh
fp_CURCHL   equ 5C51h
fp_PRINT_FP equ 2DE3h
fp_CHAN_OPEN equ 1601h

; -- arithmetic: the ROM's calculator ------------------------------------------------------------------------------
bly_fadd:
        ld a,0Fh                    ; addition
        jp bly_fp.bin
bly_fsub:
        ld a,03h                    ; subtract
        jp bly_fp.bin
bly_fmul:
        ld a,04h                    ; multiply
        jp bly_fp.bin
bly_fdiv:
        ex de,hl
        call bly_fp.zero
        ex de,hl
        jp z,bly_div0               ; the ROM would say Number too big
        ld a,05h                    ; division
        jp bly_fp.bin

bly_fpow:
        call bly_fp.zero
        jr nz,.nz
        ex de,hl                    ; 0 ** b: no answer when b < 0 (the ROM would say Number too big)
        inc hl
        bit 7,(hl)
        dec hl
        ex de,hl
        jr z,.rom
.no:    ld a,06h
        jp bly_fp.noans
.nz:    inc hl
        bit 7,(hl)                  ; a < 0? (the sign bit, or a short form's FFh)
        dec hl
        jr nz,.neg
.rom:   ld a,06h                    ; to-power
        jp bly_fp.bin
.neg:   ; The ROM's to-power is exp(b * ln a), and LN refuses every negative a, even for (-2) ** 2. So: |a| ** b,
        ; negated when b is odd. A b that isn't a whole number has no answer, as in the interpreter.
        push bc
        push hl
        ex de,hl
        ld (.b),hl
        call bly_fp.toint           ; b's whole part and fraction
        ld a,(bly_fp.fr)
        or a
        jr nz,.no
        ld a,(bly_fp.big)           ; odd: under 2^64 (bigger is even) with the low bit set
        or a
        ld a,(bly_fp.mag)
        jr z,.par
        xor a
.par:   and 1
        ld (.odd),a
        pop hl
        ld bc,.abs
        call bly_fabs
        ld hl,.abs
        ld de,(.b)
        pop bc
        push bc
        ld a,06h
        call bly_fp.bin
        pop hl
        ld a,(.odd)
        or a
        ret z
        jp bly_fneg.inplace
.b:     dw 0
.abs:   ds 5
.odd:   db 0

; -- the functions: the ROM's -----------------------------------------------------------------------------------------
bly_fsqrt:
        ld a,28h
        jr bly_fp.fun
bly_fsin:
        ld a,1Fh
        jr bly_fp.fun
bly_fcos:
        ld a,20h
        jr bly_fp.fun
bly_ftan:
        ld a,21h
        jr bly_fp.fun
bly_fasin:
        ld a,22h
        jr bly_fp.fun
bly_facos:
        ld a,23h
        jr bly_fp.fun
bly_fatan:
        ld a,24h
        jr bly_fp.fun
bly_fln:
        ld a,25h
        jr bly_fp.fun
bly_fexp:
        ld a,26h
        ; on into bly_fp.fun

; -- the shared part: one calculator operation, with the ROM's errors caught --------------------------------------------
bly_fp:
.fun:   ld (.pa),hl                 ; A = the literal, HL = &x, BC = &r
        ld (.lit),a
        ld (.res),bc
        call .push
        jr .run
.bin:   ld (.pa),hl                 ; A = the literal, HL = &a, DE = &b, BC = &r
        ld (.lit),a                 ; (self-modifying: the script's operation)
        ld (.res),bc
        push de
        call .push
        pop hl
        call .push
.run:   exx
        ld (.hlx),hl                ; BASIC's HL': the calculator borrows it, and an error leaves it borrowed
        exx
        ld hl,(fp_X_PTR)
        ld (.xptr),hl               ; and X_PTR, which an error overwrites
        ld hl,(fp_ERR_SP)
        push hl                     ; BASIC's ERR_SP, to put back
        ld hl,.caught
        push hl
        ld (fp_ERR_SP),sp           ; a ROM error now unwinds to .caught
        rst 28h
.lit:   db 0                        ; the operation (written above)
        db 38h                      ; end-calc
        pop hl                      ; .caught, unused
        pop hl
        ld (fp_ERR_SP),hl
        ld hl,(fp_STKEND)           ; the answer, off the calculator's stack into (.res)
        ld de,-5
        add hl,de
        ld (fp_STKEND),hl
        ld de,(.res)
        ld bc,5
        ldir
        ld hl,(.res)                ; The ROM's slip: -65535 - 1 comes out short, 00 FF 00 00 00, which its own
        ld a,(hl)                   ; routines then misread (PRINT shows -1E-38). Write it in full: 91 80 00 00 00.
        or a
        ret nz
        inc hl
        ld a,(hl)
        inc a
        ret nz
        inc hl
        ld a,(hl)
        inc hl
        or (hl)
        ret nz
        inc hl
        ld (hl),a
        ld hl,(.res)
        ld (hl),91h
        inc hl
        ld (hl),80h
        ret

.caught:                            ; the ROM failed: SP is just above the handler's push, ERR_NR = the report - 1
        exx
        ld hl,(.hlx)                ; BASIC's HL' back
        exx
        pop hl
        ld (fp_ERR_SP),hl           ; and its ERR_SP
        ld hl,fp_ERR_NR
        ld a,(hl)
        ld (.code),a                ; 5: "6 Number too big"; 9: "A Invalid argument"
        ld (hl),0FFh                ; no error, as far as BASIC will know
        ld hl,(.xptr)
        ld (fp_X_PTR),hl            ; ERROR-1 pointed X_PTR into the BASIC
        ld a,(.lit)
        cp 18h
        jr nc,.funno
        ld a,(.code)
        cp 5
        ld hl,.movf
        jp z,bly_fail
        ld a,(.lit)
.noans: call .name                  ; A = the literal: float {op} has no answer
        push hl
        ld hl,.mfloat
        call bly_pr_cstr
        pop hl
        call bly_pr_cstr
        ld hl,.mno
        jp bly_fail
.funno: call .name                  ; {name}({x}) has no answer
        call bly_pr_cstr
        ld a,'('
        call bly_out
        ld hl,(.pa)
        call bly_pr_f
        ld hl,.mclose
        jp bly_fail

.name:  ld hl,.names                ; A = a literal -> HL = its name (entries: the literal, the name, 0)
.nm:    cp (hl)
        inc hl
        ret z
.sk:    ld c,(hl)                   ; past this name and its 0
        inc hl
        inc c
        dec c
        jr nz,.sk
        jr .nm

.push:  ld de,(fp_STKEND)           ; HL = &x onto the calculator's stack (STACK-NUM without its room check:
        ld bc,5                     ; this program's stack is nowhere near BASIC's workspace)
        ldir
        ld (fp_STKEND),de
        ret

.zero:  push hl                     ; Z if (HL) is zero: 00 00 00 00 (00 FF 00 00 would be -65536)
        ld a,(hl)                   ; clobbers AF
        inc hl
        or (hl)
        inc hl
        or (hl)
        inc hl
        or (hl)
        pop hl
        ret

; .toint: HL = &x -> .mag = |trunc x| as 64 bits (if it fits: else .big = 1), .neg = 0 or 80h, .ee = x's exponent
; byte (0 for the short form), .fr = the fraction cut off: bit 0 its first bit (a half), bit 1 any after it.
.toint: xor a
        ld (.big),a
        ld (.fr),a
        push hl
        ld hl,.mag
        ld b,8
.tz:    ld (hl),a
        inc hl
        djnz .tz
        pop hl
        ld a,(hl)
        ld (.ee),a
        inc hl
        or a
        jr nz,.tfull
        ld a,(hl)                   ; the short form: s lo hi
        and 80h
        ld (.neg),a
        inc hl
        ld e,(hl)
        inc hl
        ld d,(hl)
        or a
        jr z,.tpos
        ld hl,0                     ; (carry is clear: OR A above)
        sbc hl,de                   ; |x| = 65536 - (lo hi), where 0 means 65536
        ex de,hl
        ld a,d
        or e
        jr nz,.tpos
        inc a
        ld (.mag+2),a
.tpos:  ld (.mag),de
        ret
.tfull: ld a,(hl)
        and 80h
        ld (.neg),a
        ld a,(hl)                   ; the mantissa, its top bit back: DEHL, D the top byte
        or 80h
        ld d,a
        inc hl
        ld e,(hl)
        inc hl
        ld a,(hl)
        inc hl
        ld l,(hl)
        ld h,a
        ld a,(.ee)
        cp 160
        jr nc,.tleft
        ld b,a                      ; under 2^31: shift right 160 - e times (33 at most: by then all is fraction),
        ld a,160                    ; keeping the last bit out (the half) and whether any before it was set
        sub b
        cp 34
        jr c,.tn
        ld a,33
.tn:    ld b,a
        ld c,0                      ; C: bit 0 the half, bit 1 the rest
.tr:    ld a,c
        add a,a
        or c
        and 2
        srl d
        rr e
        rr h
        rr l
        adc a,0
        ld c,a
        djnz .tr
        ld a,c
        ld (.fr),a
        ld (.mag),hl
        ld (.mag+2),de
        ret
.tleft: sub 160                     ; e >= 160: whole, the mantissa times 2^(e-160): placed (e-160)/8 bytes up,
        ld b,a                      ; then shifted (e-160)%8 bits. Past e = 192 it's 2^64 or more.
        and 7
        ld c,a
        ld a,b
        rrca
        rrca
        rrca
        and 1Fh
        cp 4
        jr c,.tok
        jr nz,.tbig
        inc c
        dec c
        jr nz,.tbig
.tok:   ld ix,.mag
        push bc
        ld c,a
        ld b,0
        add ix,bc
        pop bc
        ld (ix+0),l
        ld (ix+1),h
        ld (ix+2),e
        ld (ix+3),d
        ld a,c
        or a
        ret z
        ld b,a
.tl:    ld hl,.mag
        sla (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        djnz .tl
        ret
.tbig:  ld a,1
        ld (.big),a
        ret

.negmag:                            ; .mag = -.mag, 64 bits
        ld hl,.mag
        ld b,8
        or a
.ng:    ld a,0
        sbc a,(hl)
        ld (hl),a
        inc hl
        djnz .ng
        ret

; .frommag: .mag (64 bits, unsigned) with the sign .neg -> the float at (.res). Short form under 65536; otherwise the
; top 32 bits, rounded half away from zero on the next bit.
.frommag:
        ld hl,.mag+7
        ld b,7
.ftop:  ld a,(hl)
        or a
        jr nz,.ffound
        dec hl
        djnz .ftop
.ffound:                            ; B = the top nonzero byte's index (0 if none), HL = its address
        ld a,b
        cp 2
        jr nc,.ffull
        ld hl,(.mag)                ; under 65536: 00 s lo hi 00
        ld a,h
        or l
        jr z,.fshort                ; zero is never "negative": 00 FF 00 00 00 would be -65536
        ld a,(.neg)
        or a
        jr z,.fshort
        ex de,hl
        ld hl,0
        or a
        sbc hl,de
        ld a,0FFh
.fshort:
        ex de,hl
        ld hl,(.res)
        ld (hl),0
        inc hl
        ld (hl),a                   ; s: 0 (A is 0 from OR H/L or .neg) or FFh
        inc hl
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld (hl),0
        ret
.ffull: inc a                       ; e = 128 + 8 * (index + 1), less the normalising shifts
        add a,a
        add a,a
        add a,a
        add a,128
        ld b,a
        push hl
        pop ix                      ; DEHL and a guard byte C, from the top byte down (.pad makes the reads
        ld d,(ix+0)                 ; below .mag harmless: the top byte's index is 2 or more)
        ld e,(ix-1)
        ld h,(ix-2)
        ld l,(ix-3)
        ld c,(ix-4)
        jr .fnorm
.fsh:   sla c
        rl l
        rl h
        rl e
        rl d
        dec b
.fnorm: bit 7,d
        jr z,.fsh
        bit 7,c                     ; round on the next bit
        jr z,.fpack
        inc l
        jr nz,.fpack
        inc h
        jr nz,.fpack
        inc e
        jr nz,.fpack
        inc d
        jr nz,.fpack
        ld d,80h                    ; 1.000 -> 0.1000 x 2
        inc b
.fpack: push hl                     ; B = e, DEHL = the mantissa with its top bit
        ld hl,(.res)
        ld (hl),b
        inc hl
        ld a,d
        and 7Fh
        ld c,a
        ld a,(.neg)
        or c
        ld (hl),a
        inc hl
        ld (hl),e
        inc hl
        pop de
        ld (hl),d
        inc hl
        ld (hl),e
        ret

; .unpack: HL = &x, DE = &u -> u = sign (0 or 80h), e, m3 m2 m1 m0 (the mantissa with its top bit); zero is e = 0
.unpack:
        ld a,(hl)
        or a
        jr z,.ushort
        inc hl
        ld a,(hl)
        and 80h
        ld (de),a
        inc de
        dec hl
        ld a,(hl)
        ld (de),a
        inc de
        inc hl
        ld a,(hl)
        or 80h
        ld (de),a
        inc de
        inc hl
        ld bc,3
        ldir
        ret
.ushort:
        inc hl
        ld a,(hl)
        and 80h
        ld c,a                      ; C = the sign
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                      ; HL = lo hi
        ld a,c
        or a
        jr z,.upos
        push de
        ex de,hl
        ld hl,0
        or a
        sbc hl,de                   ; |x| = 65536 - (lo hi)
        pop de
        ld a,h
        or l
        jr nz,.upos
        ld a,c                      ; 0 here is the slipped -65536: 0.1b x 2^17
        ld (de),a
        inc de
        ld a,145
        ld (de),a
        inc de
        ld a,80h
        ld (de),a
        inc de
        xor a
        jr .u3
.upos:  ld a,c
        ld (de),a
        inc de
        ld a,h
        or l
        jr z,.uzero
        ld b,144                    ; HL = 0.HL x 2^16; normalise
.un:    bit 7,h
        jr nz,.und
        add hl,hl
        dec b
        jr .un
.und:   ld a,b
        ld (de),a
        inc de
        ld a,h
        ld (de),a
        inc de
        ld a,l
        ld (de),a
        inc de
        xor a
        ld (de),a
        inc de
        ld (de),a
        ret
.uzero: xor a
        ld (de),a
        inc de
        ld (de),a
        inc de
.u3:    ld (de),a
        inc de
        ld (de),a
        inc de
        ld (de),a
        ret

.pa:    dw 0                        ; the first operand (for a message)
.res:   dw 0                        ; where the answer goes
.hlx:   dw 0                        ; BASIC's HL', while the calculator has it
.xptr:  dw 0
.code:  db 0
.neg:   db 0
.big:   db 0
.fr:    db 0
.ee:    db 0
.ua:    ds 6
.ub:    ds 6
.pad:   ds 5                        ; zeros, always: .frommag may read just below .mag
.mag:   ds 8
.movf:  db "float overflow",0
.mfloat: db "float ",0
.mno:   db " has no answer",0
.mclose: db ") has no answer",0
.names: db 0Fh,"+",0, 03h,"-",0, 04h,"*",0, 05h,"/",0, 06h,"**",0
        db 28h,"sqrt",0, 1Fh,"sin",0, 20h,"cos",0, 21h,"tan",0, 22h,"asin",0, 23h,"acos",0, 24h,"atan",0
        db 25h,"ln",0, 26h,"exp",0

; -- whole numbers: trunc, floor, round, exactly ---------------------------------------------------------------------
bly_ftrunc:
        xor a
        jr bly_fround.go
bly_ffloor:
        ld a,1
        jr bly_fround.go
bly_fround:
        ld a,2
.go:    ld (.mode),a
        ld (bly_fp.res),bc
        ld (bly_fp.pa),hl
        call bly_fp.toint
        ld a,(bly_fp.ee)
        or a
        jr z,.same                  ; the short form: whole already
        cp 160
        jr c,.cut
.same:  ld hl,(bly_fp.pa)           ; 2^31 or more: whole already
        ld de,(bly_fp.res)
        ld bc,5
        ldir
        ret
.cut:   ld a,(.mode)
        or a
        jr z,.done                  ; trunc: the whole part
        ld b,a
        ld a,(bly_fp.neg)
        or a
        ld a,(bly_fp.fr)
        jr z,.pos
        djnz .nrnd
        or a                        ; floor of a negative: any fraction takes the magnitude up
        jr nz,.up
        jr .done
.nrnd:  cp 3                        ; round of a negative: up only past a half (floor(-2.5 + 0.5) is -2)
        jr z,.up
        jr .done
.pos:   djnz .prnd
        jr .done                    ; floor of a positive: the whole part
.prnd:  and 1                       ; round of a positive: up from a half
        jr z,.done
.up:    ld hl,bly_fp.mag            ; the magnitude is under 2^31: 32 bits carry it
        inc (hl)
        jr nz,.done
        inc hl
        inc (hl)
        jr nz,.done
        inc hl
        inc (hl)
        jr nz,.done
        inc hl
        inc (hl)
.done:  jp bly_fp.frommag
.mode:  db 0

; -- sign and comparing ---------------------------------------------------------------------------------------------
bly_fneg:
        push bc
        ld d,b
        ld e,c
        ld bc,5
        ldir
        pop hl
.inplace:                           ; HL = &x: x = -x
        ld a,(hl)
        inc hl
        or a
        jr z,.short
        ld a,(hl)
        xor 80h
        ld (hl),a
        ret
.short: inc hl                      ; s lo hi: negate lo hi, flip s; zero stays zero
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld a,d
        or e
        jr nz,.nz
        dec hl
        dec hl
        ld a,(hl)
        or a
        ret z
        dec hl                      ; the slipped -65536 (never made here): +65536 in full, 91 00 00 00 00
        ld (hl),91h
        inc hl
        ld (hl),0
        ret
.nz:    xor a
        sub e
        ld e,a
        ld a,0
        sbc a,d
        ld (hl),a
        dec hl
        ld (hl),e
        dec hl
        ld a,(hl)
        cpl
        ld (hl),a
        ret

bly_fabs:
        push bc
        ld d,b
        ld e,c
        ld bc,5
        ldir
        pop hl
        inc hl
        bit 7,(hl)
        dec hl
        ret z
        jr bly_fneg.inplace

bly_fcmp:
        push de
        ld de,bly_fp.ua
        call bly_fp.unpack
        pop hl
        ld de,bly_fp.ub
        call bly_fp.unpack
        ld hl,bly_fp.ua
        ld de,bly_fp.ub
        ld a,(de)
        cp (hl)
        jr z,.same
        ld a,(hl)                   ; the signs differ: the negative one is less
        or a
        ld a,1
        jr z,.ret
        ld a,0FFh
.ret:   or a
        ret
.same:  ld c,a                      ; C = the common sign
        ld b,5
.lp:    inc hl
        inc de
        ld a,(de)
        cp (hl)                     ; carry if b's byte < a's
        jr nz,.diff
        djnz .lp
        xor a
        ret
.diff:  ld a,1
        jr c,.mag
        ld a,0FFh
.mag:   bit 7,c
        jr z,.ret
        neg                         ; both negative: the bigger magnitude is the smaller number
        jr .ret

; -- conversions ------------------------------------------------------------------------------------------------------
bly_f_from_u16:
        xor a
        jr bly_f_from_i16.put
bly_f_from_i16:
        ld a,h
        rla
        sbc a,a                     ; s: FFh if negative
.put:   ld d,b
        ld e,c
        ex de,hl
        ld (hl),0
        inc hl
        ld (hl),a
        inc hl
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld (hl),0
        ret

bly_f_from_i64:
        ld (bly_fp.res),bc
        ld de,bly_fp.mag
        ld bc,8
        ldir
        ld a,(bly_fp.mag+7)
        and 80h
        ld (bly_fp.neg),a
        call nz,bly_fp.negmag       ; |q| (the most negative quad's is 2^63, read unsigned)
        jp bly_fp.frommag

bly_f_to_int:
        ld (.type),a
        ld (.dest),de
        ld (bly_fp.pa),hl
        call bly_fp.toint
        ld a,(bly_fp.big)
        or a
        jr nz,.no
        ld a,(bly_fp.neg)
        or a
        jr z,.pos
        call bly_fp.negmag
        ld a,(bly_fp.mag+7)
        rla
        jr c,.q                     ; negative, as it should be
        ld hl,bly_fp.mag            ; or zero; anything else was past -2^63
        xor a
        ld b,8
.z:     or (hl)
        inc hl
        djnz .z
        jr nz,.no
        jr .q
.pos:   ld a,(bly_fp.mag+7)
        rla
        jr c,.no                    ; 2^63 or more
.q:     ld a,(.type)                ; the type's range: bytes w..7 all the extension of byte w-1 (0 if unsigned)
        ld e,a
        ld d,0
        ld hl,.width
        add hl,de
        ld b,(hl)
        ld hl,.signed
        add hl,de
        ld c,(hl)
        ld hl,bly_fp.mag-1
        ld e,b
        add hl,de                   ; HL = &mag[w-1]
        xor a
        bit 0,c
        jr z,.ext
        bit 7,(hl)
        jr z,.ext
        dec a
.ext:   ld c,a
        ld a,8
        sub b
        jr z,.fits
        ld e,b                      ; keep w
        ld b,a
.chk:   inc hl
        ld a,(hl)
        cp c
        jr nz,.no
        djnz .chk
        ld b,e
.fits:  ld c,b
        ld b,0
        ld hl,bly_fp.mag
        ld de,(.dest)
        ldir
        ret
.no:    ld hl,(bly_fp.pa)           ; {x} doesn't fit in a {type}
        call bly_pr_f
        ld hl,.m1
        call bly_pr_cstr
        ld a,(.type)
        add a,a
        ld e,a
        ld d,0
        ld hl,.names
        add hl,de
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        jp bly_fail
.type:  db 0
.dest:  dw 0
.width: db 1, 2, 2, 4, 8, 4
.signed: db 0, 0, 1, 1, 1, 0
.names: dw .n0, .n1, .n2, .n3, .n4, .n5
.n0:    db "a byte",0
.n1:    db "a word",0
.n2:    db "an int",0
.n3:    db "a long",0
.n4:    db "a quad",0
.n5:    db "a dword",0
.m1:    db " doesn't fit in ",0

; -- printing: the ROM's PRINT-FP, caught in a buffer and sent on through bly_out ------------------------------------
bly_pr_f:
        ld de,(fp_STKEND)
        ld (.stk),de                ; (PRINT-FP of a number between -1 and 1 leaves a 0 behind: the ROM's STR$ bug)
        call bly_fp.push
        ld hl,.buf
        ld (.at),hl
        ld a,2                      ; the stream to come back to: the screen's, or the lower screen's (print #1,
        bit 0,(iy+2)                ; whose channel K sets TV_FLAG bit 0)
        jr z,.s2
        dec a
.s2:    ld (.back),a
        ld a,3
        call fp_CHAN_OPEN           ; off the screen's stream while PRINT-FP runs (omse-ai's text log follows
        ld hl,.chan                 ; CHAN-OPEN, not CURCHL; on a real 48K this is just tidy)
        ld (fp_CURCHL),hl           ; and its characters come to .take, not the printer
        call fp_PRINT_FP
        ld a,(.back)
        call fp_CHAN_OPEN           ; that stream again
        ld hl,(.stk)
        ld (fp_STKEND),hl
        ld hl,(.at)
        ld (hl),0
        ld hl,.buf
        jp bly_pr_cstr
.stk:   dw 0
.back:  db 2
.take:  ld hl,(.at)                 ; A = a character (RST 10 runs this in the alternate set, and saved HL')
        ld (hl),a
        inc hl
        ld (.at),hl
        ret
.chan:  dw .take, .take             ; a channel: output, input
.at:    dw 0
.buf:   ds 16
