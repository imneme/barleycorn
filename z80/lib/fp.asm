;; provides: bly_fp bly_fadd bly_fsub bly_fmul bly_fdiv bly_fpow bly_fsin bly_fcos bly_ftan bly_fasin bly_facos bly_fatan bly_fln bly_fexp bly_pr_f
;; needs: bly_out bly_pr_cstr bly_fail bly_div0 bly_fx bly_fabs bly_fneg bly_zx_chan_k
;; targets: zx48
;; Floats on the 48K Spectrum: the ROM's own 5-byte form, worked by the ROM's calculator (RST 28h). ABI.md section 11.
;; This file is what the ROM does: arithmetic, the functions, printing. What's exact in Z80 (compare, negate, abs,
;; trunc, floor, round, the conversions) is fp_exact.asm, shared with CP/M.
;; A float is 5 bytes, either the short form 00 s lo hi 00 (a whole number -65535..65535: s is 00 or FFh, and lo hi
;; is the number's 16-bit two's complement) or e m3 m2 m1 m0, the value 0.1mmm... (binary: 32 bits, the top 1 hidden
;; under m3's bit 7, which holds the sign) times 2^(e-128). Zero is 00 00 00 00 00.
;; bly_fadd bly_fsub bly_fmul bly_fdiv bly_fpow   in: HL=&a DE=&b BC=&r   out: (BC) = a + b and so on
;;        fails: float overflow; division by zero (/); float ** has no answer (0 ** b with b < 0, or a < 0 with b
;;        not a whole number)
;; bly_fsin bly_fcos bly_ftan bly_fasin bly_facos bly_fatan bly_fln bly_fexp   in: HL=&x BC=&r
;;        fails: {name}({x}) has no answer   (the ROM's "A Invalid argument" and "6 Number too big")
;; bly_pr_f            in: HL=&x   prints x as the ROM's PRINT-FP does, through bly_out (so print's column is kept);
;;                     leaves stream 2 (the upper screen) open, as bly_start does
;; Every routine clobbers AF BC DE HL IX; those that use the ROM also clobber BC' and DE' (the ROM's own scratch, as
;; RST 10 does). HL' and IY are BASIC's and are kept: the calculator borrows HL', and if the ROM fails part-way
;; we put it back. bly_fp is the ROM-calling part (its .labels are used across this file); nothing outside calls it.
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
        call bly_fx.zero
        ex de,hl
        jp z,bly_div0               ; the ROM would say Number too big
        ld a,05h                    ; division
        jp bly_fp.bin

bly_fpow:
        call bly_fx.zero
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
        call bly_fx.toint           ; b's whole part and fraction
        ld a,(bly_fx.fr)
        or a
        jr nz,.no
        ld a,(bly_fx.big)           ; odd: under 2^64 (bigger is even) with the low bit set
        or a
        ld a,(bly_fx.mag)
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

.pa:    dw 0                        ; the first operand (for a message)
.res:   dw 0                        ; where the answer goes
.hlx:   dw 0                        ; BASIC's HL', while the calculator has it
.xptr:  dw 0
.code:  db 0
.movf:  db "float overflow",0
.mfloat: db "float ",0
.mno:   db " has no answer",0
.mclose: db ") has no answer",0
.names: db 0Fh,"+",0, 03h,"-",0, 04h,"*",0, 05h,"/",0, 06h,"**",0
        db 1Fh,"sin",0, 20h,"cos",0, 21h,"tan",0, 22h,"asin",0, 23h,"acos",0, 24h,"atan",0
        db 25h,"ln",0, 26h,"exp",0

; -- printing: the ROM's PRINT-FP, caught in a buffer and sent on through bly_out ------------------------------------
bly_pr_f:
        ld de,(fp_STKEND)
        ld (.stk),de                ; (PRINT-FP of a number between -1 and 1 leaves a 0 behind: the ROM's STR$ bug)
        call bly_fp.push
        ld hl,(5C8Fh)               ; the temporary colours (ATTR_T, MASK_T, P_FLAG), which opening a stream again
        ld (.temps),hl              ; resets (TEMPS): a print's colour items still colour what comes after
        ld a,(5C91h)
        ld (.temps+2),a
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
        dec a
        jr nz,.up
        call bly_zx_chan_k          ; the lower screen's again, a key not yet looked at kept for key() (zxchank.asm)
        jr .again
.up:    ld a,2
        call fp_CHAN_OPEN           ; the screen's again
.again: ld hl,(.stk)
        ld (fp_STKEND),hl
        ld hl,(.temps)              ; the temporary colours back
        ld (5C8Fh),hl
        ld a,(.temps+2)
        ld (5C91h),a
        ld hl,(.at)
        ld (hl),0
        ld hl,.buf
        jp bly_pr_cstr
.stk:   dw 0
.temps: ds 3
.back:  db 2
.take:  ld hl,(.at)                 ; A = a character (RST 10 runs this in the alternate set, and saved HL')
        ld (hl),a
        inc hl
        ld (.at),hl
        ret
.chan:  dw .take, .take             ; a channel: output, input
.at:    dw 0
.buf:   ds 16
