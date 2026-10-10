;; provides: bly_i_copyabs bly_i_negn bly_i_sig bly_i_neg32
;; needs: (none)
;; targets: cpm zx48 test
;; bly_i_copyabs  in: HL=&src DE=&dst B=N   out: (DE) = |src| as an unsigned N-byte magnitude (|MIN| is 80..00h),
;;                                          A = src's top byte (bit 7: its sign), S as A's bit 7 (internal)   clobbers: AF BC DE HL
;; bly_i_negn     in: HL=&x B=N             out: x = -x in place; V set when x was MIN (internal)   clobbers: AF B HL
;; bly_i_sig      in: HL=&x B=N (even)      out: A = the number of significant bytes of x, unsigned (0 when x is 0)
;;                                          (internal)                                                   clobbers: AF B HL
;; bly_i_neg32    in: HL:DE (HL high)       out: HL:DE = -HL:DE; V set when it was MIN (internal)       clobbers: AF DE HL
;
; Small N-byte helpers the multiply, the divide and the quad functions share. Internal: generated code doesn't call
; them, and their names may change.

bly_i_copyabs:
        push bc
        push de
        ld c,b
        ld b,0
        ldir
        dec hl
        ld a,(hl)                   ; src's top byte
        pop hl                      ; HL = dst
        pop bc                      ; B = N
        or a
        ret p
        push af
        call bly_i_negn
        pop af
        ret

bly_i_negn:
        or a
.l:     ld a,0                      ; LD keeps the borrow
        sbc a,(hl)
        ld (hl),a
        inc hl
        djnz .l
        ret

bly_i_sig:                          ; N is even: look at the bytes a pair at a time, from the top
        ld a,b
        add a,l
        ld l,a
        jr nc,.l
        inc h
.l:     dec hl
        ld a,(hl)
        dec hl
        or (hl)
        jr nz,.pair
        dec b
        djnz .l
        xor a
        ret
.pair:  inc hl                      ; the upper of the pair decides between B and B - 1
        ld a,(hl)
        or a
        ld a,b
        ret nz
        dec a
        ret

bly_i_neg32:
        xor a
        sub e
        ld e,a
        ld a,0
        sbc a,d
        ld d,a
        ld a,0
        sbc a,l
        ld l,a
        ld a,0
        sbc a,h
        ld h,a
        ret
