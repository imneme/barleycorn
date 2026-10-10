;; provides: bly_mul_u16 bly_mul_i16 bly_divmod_u16 bly_divmod_i16 bly_rem_i16 bly_i_mul16x8 bly_i_divu16 bly_i_div8
;; needs: bly_ovf_int bly_div0
;; targets: cpm zx48 test
;; bly_mul_u16     in: HL DE   out: HL = HL*DE, wrapping (word)                                     clobbers: AF BC DE HL
;; bly_mul_i16     in: HL DE   out: HL = HL*DE (int)   fails: int overflow                          clobbers: AF BC DE HL
;; bly_divmod_u16  in: HL DE   out: HL = HL/DE, DE = HL%DE (word)   fails: division by zero         clobbers: AF BC DE HL
;; bly_divmod_i16  in: HL DE   out: HL = HL/DE truncated, DE = the remainder, with the dividend's sign (int)
;;                             fails: division by zero; int overflow for -32768/-1                 clobbers: AF BC DE HL
;; bly_rem_i16     in: HL DE   as bly_divmod_i16, for %: -32768/-1 doesn't fail (HL = -32768, DE = 0)
;;                             fails: division by zero                                             clobbers: AF BC DE HL
;; bly_i_mul16x8   in: DE A    out: A:HL = DE*A, all 24 bits (internal)                             clobbers: F B HL
;; bly_i_divu16    in: HL DE (DE not 0)   out: HL = HL/DE, DE = HL%DE, unsigned (internal)          clobbers: AF BC DE HL
;; bly_i_div8      in: A = the remainder so far (below E), C = the next dividend byte, E = the divisor (not 0)
;;                 out: C = the quotient byte, A = the remainder: one base-256 digit (internal)   clobbers: F B
;
; Multiplying: a 16x8 product is the step everything is built from. The multiplier rides in the top of A while the
; product's third byte grows in underneath it (z88dk's sharing trick, one byte wider), and the leading
; zeros of the multiplier are skipped. A 16x16 product truncated to 16 bits is HL*E + (L*D)<<8; a checked one is
; settled by width first (both at least 256 overflows) and then by the 24-bit product.
;
; Dividing, by width (as z88dk does it): a divisor of one byte is two base-256 digits of long division
; (bly_i_div8, shared with the wide divides), or one when the dividend's high byte is already below it; a divisor of
; two bytes means a quotient of one byte, so 8 steps on a 16-bit remainder (Barley's old runtime's loop, unrolled,
; less a 17th-bit branch a 16/16 divide can never take). The unrolled steps don't set quotient bits: the carry after
; the trial subtraction (and the add-back) is already the quotient bit inverted, so it goes straight in with the next
; shift and the byte is complemented once at the end.

bly_i_mul16x8:                      ; A:HL = DE * A
        ld hl,0
        or a
        ret z
        ld b,8
.lz:    dec b                       ; skip the multiplier's leading zeros: at its top 1 the product is DE
        add a,a
        jr nc,.lz
        ld h,d
        ld l,e
        inc b
        dec b
        ret z
.step:  add hl,hl                   ; A:HL doubles: H's top bit goes into A, the next multiplier bit comes out
        rla
        jr nc,.next
        add hl,de
        adc a,0                     ; never reaches the multiplier bits still waiting in A's top
.next:  djnz .step
        ret

bly_mul_u16:
        ld a,d
        or a
        jr z,.de8                   ; DE < 256: it's the multiplier
        ld a,h
        or a
        jr z,.hl8                   ; HL < 256
        ld c,l                      ; both wide: (L*D) mod 256 goes into the high byte
        ld b,8
        xor a
.m8:    add a,a
        sla d
        jr nc,.n8
        add a,c
.n8:    djnz .m8
        push af
        ld a,e
        ex de,hl
        call bly_i_mul16x8          ; HL = low 16 bits of HL*E
        pop af
        add a,h
        ld h,a
        ret
.de8:   ld a,e
        ex de,hl
        jp bly_i_mul16x8
.hl8:   ld a,l
        jp bly_i_mul16x8

bly_mul_i16:
        ld a,h
        xor d
        push af                     ; S: the product's sign
        bit 7,h
        jr z,.ha
        xor a                       ; HL = |HL| (-32768 becomes 8000h, unsigned)
        sub l
        ld l,a
        sbc a,a
        sub h
        ld h,a
.ha:    bit 7,d
        jr z,.da
        xor a
        sub e
        ld e,a
        sbc a,a
        sub d
        ld d,a
.da:    ld a,d
        or a
        jr z,.d8
        ld a,h
        or a
        jp nz,bly_ovf_int      ; both at least 256: the product is at least 65536
        ld a,l
        jr .go
.d8:    ld a,e
        ex de,hl
.go:    call bly_i_mul16x8          ; A:HL = the product's magnitude
        or a
        jp nz,bly_ovf_int
        pop af
        jp m,.neg
        bit 7,h
        ret z
        jp bly_ovf_int
.neg:   ld a,h                      ; a negative product may reach 8000h exactly
        cp 80h
        jr c,.ok
        jp nz,bly_ovf_int
        ld a,l
        or a
        jp nz,bly_ovf_int
.ok:    xor a
        sub l
        ld l,a
        sbc a,a
        sub h
        ld h,a
        ret

bly_divmod_u16:
        ld a,d
        or e
        jp z,bly_div0
bly_i_divu16:
        ld a,d
        or a
        jr nz,.wide
        ld a,h                      ; a divisor of one byte, E: two base-256 digits
        cp e
        jr c,.half                  ; H < E: the high quotient byte is 0, and H is the remainder so far
        ld c,h
        xor a
        call bly_i_div8
        ld h,c
        jr .low
.half:  ld h,0
.low:   ld c,l
        call bly_i_div8
        ld l,c
        ld e,a
        ld d,0
        ret
.wide:  ld a,h                      ; the divisor is at least 256: the quotient fits a byte
        cp d
        jr c,.zero                  ; H < D, so HL < DE
        ld c,l
        ld l,h
        ld h,0
        REPT 8                      ; C: dividend bits out of the top, complemented quotient bits in at the bottom
        rl c
        adc hl,hl                   ; never carries: the remainder is at most the 15 bits read before the last shift
        sbc hl,de                   ; carry: it borrowed, quotient bit 0
        jr nc,$+3
        add hl,de                   ; put it back, which carries: the carry is always the quotient bit, inverted
        ENDR
        rl c
        ld a,c
        cpl
        ex de,hl
        ld l,a
        ld h,0
        ret
.zero:  ex de,hl
        ld hl,0
        ret

bly_i_div8:
        bit 7,e
        jr nz,.wide
        REPT 8                      ; a divisor below 128: the doubled remainder never passes 255
        rl c                        ; the last step's quotient bit, inverted, in; the next dividend bit out
        rla
        cp e                        ; carry: the divisor doesn't go, quotient bit 0
        jr c,$+3
        sub e                       ; it goes; no borrow, so the carry is 0
        ENDR
        rl c
        ld b,a
        ld a,c
        cpl
        ld c,a
        ld a,b
        ret
.wide:  ld b,8                      ; 128 and up: a remainder past 255 means the divisor goes
.w:     sla c
        rla
        jr c,.ws
        cp e
        jr c,.wn
.ws:    sub e
        inc c
.wn:    djnz .w
        ret

bly_rem_i16:
        xor a
        jr bly_divmod_i16.go
bly_divmod_i16:
        ld a,1
.go:    ld c,a                      ; C = 1: -32768/-1 fails
        ld a,d
        or e
        jp z,bly_div0
        ld b,h                      ; B bit 7: the dividend's sign
        ld a,h
        xor d
        and 80h
        or c                        ; A bit 7: the quotient's sign; bit 0: fail on overflow
        push af
        push bc
        bit 7,h
        jr z,.ha
        xor a
        sub l
        ld l,a
        sbc a,a
        sub h
        ld h,a
.ha:    bit 7,d
        jr z,.da
        xor a
        sub e
        ld e,a
        sbc a,a
        sub d
        ld d,a
.da:    call bly_i_divu16
        pop bc
        bit 7,b
        jr z,.rpos
        xor a                       ; the remainder takes the dividend's sign
        sub e
        ld e,a
        sbc a,a
        sub d
        ld d,a
.rpos:  pop af
        jp m,.qneg
        bit 7,h
        ret z
        rra                         ; only -32768/-1 gets here
        ret nc
        jp bly_ovf_int
.qneg:  xor a
        sub l
        ld l,a
        sbc a,a
        sub h
        ld h,a
        ret
