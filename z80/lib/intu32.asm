;; provides: bly_add_u32 bly_sub_u32 bly_neg_u32 bly_cmp_u32 bly_mul_u32 bly_divmod_u32 bly_shr_u32 bly_pr_u32p
;; needs: bly_i_mul16 bly_i_udiv bly_i_ua bly_i_ub bly_i_ur bly_div0 bly_neg_shift bly_pr_u32
;; targets: cpm zx48 test
;; bly_add_u32     in: HL=&a DE=&b BC=&r   out: (BC) = a + b, wrapping                        clobbers: AF BC DE HL
;; bly_sub_u32     in: HL=&a DE=&b BC=&r   out: (BC) = a - b, wrapping                        clobbers: AF BC DE HL
;; bly_neg_u32     in: HL=&a BC=&r         out: (BC) = -a, wrapping                           clobbers: AF BC D HL
;; bly_cmp_u32     in: HL=&a DE=&b         out: A = FFh, 0 or 1 (a <, =, > b), flags as after OR A
;;                                                                                            clobbers: AF BC DE HL
;; bly_mul_u32     in: HL=&a DE=&b BC=&r   out: (BC) = a * b, its low 32 bits                 clobbers: AF BC DE HL
;; bly_divmod_u32  in: HL=&a DE=&b BC=&q IX=&r   out: (BC) = a / b, (IX) = a % b; either may be 0 for "not wanted"
;;                 fails: division by zero                                                    clobbers: AF BC DE HL IX
;; bly_shr_u32     in: HL=&a DE=count (signed) BC=&r   out: (BC) = a >> count, zeros in at the top
;;                 fails: negative shift count                                                clobbers: AF BC DE HL
;; bly_pr_u32p     in: HL=&v   prints it, as num.asm's bly_pr_u32 does from DE:HL                 clobbers: AF BC DE HL IX
;; The dword's arithmetic: unsigned 32 bits, which wraps and never traps, as byte and word do. Its own fragment, so
;; a program without a dword doesn't carry it; & | ^ ~ and << are the long's (the same bits). r may be a or b.

bly_add_u32:
        or a
        REPT 4
        ld a,(de)
        adc a,(hl)
        ld (bc),a
        inc hl
        inc de
        inc bc
        ENDR
        ret

bly_sub_u32:
        ex de,hl                    ; DE = &a, HL = &b
        or a
        REPT 4
        ld a,(de)
        sbc a,(hl)
        ld (bc),a
        inc hl
        inc de
        inc bc
        ENDR
        ret

bly_neg_u32:
        ld d,4
        or a
.l:     ld a,0
        sbc a,(hl)
        ld (bc),a
        inc hl
        inc bc
        dec d
        jr nz,.l
        ret

bly_cmp_u32:                        ; from the top byte down
        ld bc,3
        add hl,bc
        ex de,hl
        add hl,bc                   ; HL = &b + 3, DE = &a + 3
        ld b,4
.l:     ld a,(de)
        cp (hl)                     ; a's byte - b's
        jr nz,.ne
        dec hl
        dec de
        djnz .l
        xor a                       ; equal
        ret
.ne:    sbc a,a                     ; FFh if a < b (carry), else 0
        or 1                        ; FFh or 1, flags as after OR A
        ret

bly_mul_u32:                        ; a * b mod 2^32 = alo*blo + ((alo*bhi + ahi*blo) << 16)
        ld (.dst),bc
        ld (.pa),hl
        ld (.pb),de
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = alo
        ex de,hl
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; DE = blo
        call bly_i_mul16            ; DE:HL = alo * blo
        ld (.lo),hl
        ld (.hi),de
        ld hl,(.pa)
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = alo
        ld hl,(.pb)
        inc hl
        inc hl
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; DE = bhi
        call bly_i_mul16            ; HL = the low word of alo * bhi
        ld de,(.hi)
        add hl,de
        ld (.hi),hl
        ld hl,(.pa)
        inc hl
        inc hl
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = ahi
        ld hl,(.pb)
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; DE = blo
        call bly_i_mul16            ; HL = the low word of ahi * blo
        ld de,(.hi)
        add hl,de
        ex de,hl                    ; DE = the product's high word
        ld hl,(.dst)
        ld bc,(.lo)
        ld (hl),c
        inc hl
        ld (hl),b
        inc hl
        ld (hl),e
        inc hl
        ld (hl),d
        ret
.dst:   dw 0
.pa:    dw 0
.pb:    dw 0
.lo:    dw 0
.hi:    dw 0

bly_divmod_u32:
        ld (.q),bc
        ld (.r),ix
        push de
        ld de,bly_i_ua              ; the dividend, zero above its 4 bytes
        call .ld8
        pop hl
        ld de,bly_i_ub              ; the divisor
        call .ld8
        ld a,4
        call bly_i_udiv
        jp z,bly_div0
        ld hl,bly_i_ua              ; the quotient
        ld de,(.q)
        call .st4
        ld hl,bly_i_ur              ; the remainder
        ld de,(.r)
.st4:   ld a,d                      ; HL = 4 bytes to (DE), unless DE is 0
        or e
        ret z
        ld bc,4
        ldir
        ret
.ld8:   ld bc,4                     ; (HL), 4 bytes, to (DE) and 4 zeros after
        ldir
        xor a
        ld b,4
.z:     ld (de),a
        inc de
        djnz .z
        ret
.q:     dw 0
.r:     dw 0

bly_shr_u32:
        bit 7,d
        jp nz,bly_neg_shift
        push bc                     ; &r
        ld c,(hl)                   ; a: BC = its low word, HL its high
        inc hl
        ld b,(hl)
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        ld a,d
        or a
        jr nz,.zero                 ; 256 bits or more
        ld a,e
        cp 32
        jr nc,.zero                 ; 32 or more: nothing is left
        or a
        jr z,.store
.l:     srl h                       ; a bit at a time, zeros in at the top
        rr l
        rr b
        rr c
        dec a
        jr nz,.l
.store: ex de,hl                    ; DE = the high word
        pop hl                      ; HL = &r
        ld (hl),c
        inc hl
        ld (hl),b
        inc hl
        ld (hl),e
        inc hl
        ld (hl),d
        ret
.zero:  ld hl,0
        ld b,h
        ld c,l
        jr .store

bly_pr_u32p:                        ; HL = &v -> DE:HL = v, then num.asm's unsigned printer
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        ex de,hl
        jp bly_pr_u32
