;; provides: bly_add_i32 bly_add_i64 bly_sub_i32 bly_sub_i64 bly_neg_i32 bly_neg_i64 bly_cmp_i32 bly_cmp_i64
;; needs: bly_ovf_long bly_ovf_quad
;; targets: cpm zx48 test
;; bly_add_i32  in: HL=&a DE=&b BC=&r   out: (BC) = a + b   fails: long overflow   clobbers: AF BC DE HL
;; bly_add_i64  in: HL=&a DE=&b BC=&r   out: (BC) = a + b   fails: quad overflow   clobbers: AF BC DE HL
;; bly_sub_i32  in: HL=&a DE=&b BC=&r   out: (BC) = a - b   fails: long overflow   clobbers: AF BC DE HL
;; bly_sub_i64  in: HL=&a DE=&b BC=&r   out: (BC) = a - b   fails: quad overflow   clobbers: AF BC DE HL
;; bly_neg_i32  in: HL=&a BC=&r         out: (BC) = -a      fails: long overflow   clobbers: AF BC D HL
;; bly_neg_i64  in: HL=&a BC=&r         out: (BC) = -a      fails: quad overflow   clobbers: AF BC D HL
;; bly_cmp_i32  in: HL=&a DE=&b         out: A = FFh, 0 or 1 (a <, =, > b), flags as after OR A   clobbers: AF BC DE HL
;; bly_cmp_i64  in: HL=&a DE=&b         out: A = FFh, 0 or 1 (a <, =, > b), flags as after OR A   clobbers: AF BC DE HL
;
; r may be a or b: each byte is read before it's written. The overflow test is V after the top byte's ADC or SBC.
; The 64-bit forms run a four-byte block twice (CALL and RET keep the carry); the 32-bit forms have it inline.

bly_add_i64:
        or a
        call .four
        call .four
        ret po
        jp bly_ovf_quad
.four:
        REPT 4
        ld a,(de)
        adc a,(hl)
        ld (bc),a
        inc hl
        inc de
        inc bc
        ENDR
        ret

bly_add_i32:
        or a
        REPT 4
        ld a,(de)
        adc a,(hl)
        ld (bc),a
        inc hl
        inc de
        inc bc
        ENDR
        ret po
        jp bly_ovf_long

bly_sub_i64:
        ex de,hl                    ; DE = &a, HL = &b
        or a
        call .four
        call .four
        ret po
        jp bly_ovf_quad
.four:
        REPT 4
        ld a,(de)
        sbc a,(hl)
        ld (bc),a
        inc hl
        inc de
        inc bc
        ENDR
        ret

bly_sub_i32:
        ex de,hl
        or a
        REPT 4
        ld a,(de)
        sbc a,(hl)
        ld (bc),a
        inc hl
        inc de
        inc bc
        ENDR
        ret po
        jp bly_ovf_long

bly_neg_i64:
        ld d,0
        or a
        call .four
        call .four
        ret po
        jp bly_ovf_quad
.four:
        REPT 4
        ld a,d
        sbc a,(hl)
        ld (bc),a
        inc hl
        inc bc
        ENDR
        ret

bly_neg_i32:
        ld d,0
        or a
        call bly_neg_i64.four
        ret po
        jp bly_ovf_long

bly_cmp_i64:
        ld bc,7
        jr bly_cmp_i32.go
bly_cmp_i32:
        ld bc,3
.go:    add hl,bc                   ; to the top bytes
        ex de,hl
        add hl,bc
        ex de,hl
        ld b,c                      ; the bytes below the top
        ld a,(hl)                   ; the top bytes compare signed: flip their sign bits and compare unsigned
        xor 80h
        ld c,a
        ld a,(de)
        xor 80h
        cp c                        ; b - a: carry when a > b
        jr nz,.diff
.l:     dec hl
        dec de
        ld a,(de)
        cp (hl)
        jr nz,.diff
        djnz .l
        xor a
        ret
.diff:  sbc a,a                     ; FFh when a > b
        cpl
        or 1                        ; a > b: 1; a < b: FFh
        ret
