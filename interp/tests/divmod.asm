;; provides: divmod   needs: bly_divmod_i16   targets: zx48 cpm
;; in: HL = divisor, DE = dividend (ints), BC = &result, a QR (q at +0, r at +2)
;; out: (BC) = QR(dividend / divisor, dividend % divisor)
;; fails: division by zero; int overflow for -32768 / -1        clobbers: AF BC DE HL
;
; Jörg Pleumann's __divmod (PASTA/80's examples/divmod.asm), rewritten for Barleycorn's registers (z80/ABI.md,
; section 2: arguments in HL, DE, BC; a result wider than 16 bits written to the address in the last one). His
; takes HL = Divisor, DE = Dividend, BC = @Quotient, calls his runtime's __sdiv16c and returns the remainder in
; HL; this one calls Barleycorn's own bly_divmod_i16, which gives both from one division just as __sdiv16c does,
; and writes the pair into the QR the caller passes. Written by the numbers me in the Pasta/80 bake-off, before
; Barleycorn ran a clause's fragment, and checked then on a bare Z80 against its twin's meaning (2,019 cases); now
; the suite runs it in place of its twin (semantics.txt, "the numbers me's divmod").

divmod:
        ex de,hl                    ; HL = dividend, DE = divisor
        push bc                     ; keep &result: bly_divmod_i16 clobbers BC
        call bly_divmod_i16         ; HL = the quotient, DE = the remainder; fails on 0, and on -32768 / -1
        pop bc
        ld a,l                      ; result.q
        ld (bc),a
        inc bc
        ld a,h
        ld (bc),a
        inc bc
        ld a,e                      ; result.r
        ld (bc),a
        inc bc
        ld a,d
        ld (bc),a
        ret
