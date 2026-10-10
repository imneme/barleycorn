;; provides: bly_mul_i32 bly_i_mul16
;; needs: bly_i_neg32 bly_i_mul16x8 bly_ovf_long
;; targets: cpm zx48 test
;; bly_mul_i32   in: HL=&a DE=&b BC=&r   out: (BC) = a * b   fails: long overflow   clobbers: AF BC DE HL
;; bly_i_mul16   (internal) in: BC DE   out: DE:HL = BC * DE, all 32 bits (DE high)              clobbers: AF BC DE HL
;
; A long product, in registers. If neither magnitude fits 16 bits the product is at least 2^32: an overflow with no
; multiplying at all. Otherwise Y is one that fits and X the other, and the product is X*Y = Xlo*Y + (Xhi*Y << 16),
; each a 16x16 product: two of int16.asm's 16x8 steps, the second skipped when Y < 256. Xhi*Y must itself fit 16
; bits (it moves up 16), the sum mustn't carry out of the high word, and bit 31 settles the rest, allowing exactly
; 2^31 when the product is negative. r may be a or b.

bly_mul_i32:
        ld (.dst),bc
        push de
        call .ld4                   ; HL:DE = |a|
        ld (.s),a
        ld (.x),de
        ld (.x+2),hl
        pop hl
        call .ld4                   ; HL:DE = |b|
        ld c,a
        ld a,(.s)
        xor c
        ld (.s),a                   ; bit 7: the product's sign
        ld a,h
        or l
        jr z,.yb                    ; |b| fits 16 bits: Y = |b|, X = |a|
        ld bc,(.x+2)
        ld a,b
        or c
        jp nz,bly_ovf_long          ; neither fits 16 bits: the product is at least 2^32
        ld bc,(.x)                  ; Y = |a|; X = |b|, in HL:DE already
        jr .go
.yb:    ld b,d
        ld c,e
        ld de,(.x)
        ld hl,(.x+2)
.go:    ld a,h                      ; X = HL:DE, Y = BC
        or l
        jr nz,.xwide
        push bc                     ; X fits 16 bits too: one 16x16 product, of BC = X and DE = Y
        ld b,d
        ld c,e
        pop de
        ld a,d                      ; y is split into bytes: give it the one below 256, if either is
        or a
        jr z,.one
        ld a,b
        or a
        jr nz,.one
        push bc
        ld b,d
        ld c,e
        pop de
.one:   call bly_i_mul16
        jr .check
.xwide: push de                     ; Xlo
        ld d,b
        ld e,c                      ; DE = Y
        ld b,h
        ld c,l                      ; BC = Xhi
        push de
        call bly_i_mul16            ; DE:HL = Xhi * Y, which goes up 16 bits: it must fit 16
        ld a,d
        or e
        jp nz,bly_ovf_long
        pop de                      ; Y
        pop bc                      ; Xlo
        push hl
        call bly_i_mul16            ; DE:HL = Xlo * Y
        ex (sp),hl                  ; HL = Xhi * Y; the low word waits on the stack
        add hl,de
        jp c,bly_ovf_long
        ex de,hl
        pop hl                      ; DE:HL = the product
.check: bit 7,d                     ; it fits if bit 31 is clear, or it's exactly 2^31 and negative
        jr z,.ok
        ld a,(.s)
        or a
        jp p,bly_ovf_long
        ld a,d
        sub 80h
        or e
        or h
        or l
        jp nz,bly_ovf_long
.ok:    ld a,(.s)
        or a
        jp p,.store
        ex de,hl
        call bly_i_neg32
        ex de,hl
.store: ld b,d                      ; BC = the high word
        ld c,e
        ex de,hl                    ; DE = the low word
        ld hl,(.dst)
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld (hl),c
        inc hl
        ld (hl),b
        ret
.ld4:   ld e,(hl)                   ; HL = &v -> HL:DE = |v|, A = v's top byte
        inc hl
        ld d,(hl)
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        ld a,h
        or a
        ret p
        push af
        call bly_i_neg32
        pop af
        ret
.dst:   dw 0
.x:     ds 4
.s:     db 0

bly_i_mul16:
        ld a,d
        or a
        jr nz,.full
        ld a,e                      ; y < 256: one 16x8 product
        ld d,b
        ld e,c
        call bly_i_mul16x8
        ld e,a
        ld d,0
        ret
.full:  push de                     ; y
        ld a,e
        ld d,b
        ld e,c                      ; DE = x
        call bly_i_mul16x8          ; A:HL = x * y's low byte
        ex (sp),hl                  ; its low 16 bits wait; HL = y
        ld c,a                      ; and its third byte
        ld a,h
        call bly_i_mul16x8          ; A:HL = x * y's high byte (DE and C kept)
        ld b,a
        ex de,hl                    ; DE = its low 16 bits
        pop hl
        ld a,h                      ; the sum, the second shifted up a byte
        add a,e
        ld h,a
        ld a,c
        adc a,d
        ld e,a
        ld a,b
        adc a,0
        ld d,a
        ret
