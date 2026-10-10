;; provides: bly_gcd_i64 bly_lcm_i64 bly_mod_i64 bly_abs_i64 bly_fit_i64 bly_i_ugcd bly_i_gcd16 bly_i_gx bly_i_gy
;; needs: bly_i_copyabs bly_i_sig bly_i_negn bly_i_udiv bly_i_ua bly_i_ub bly_i_ur bly_i_mulmag bly_i_mx bly_i_my bly_shl_i64 bly_mod0 bly_ovf_quad bly_ovf_n
;; targets: cpm zx48 test
;; bly_gcd_i64   in: HL=&a DE=&b BC=&r   out: (BC) = gcd(|a|, |b|) (gcd(0, 0) is 0)   fails: quad overflow (2^63)   clobbers: AF BC DE HL IX
;; bly_lcm_i64   in: HL=&a DE=&b BC=&r   out: (BC) = lcm(|a|, |b|), 0 when either is 0   fails: quad overflow   clobbers: AF BC DE HL IX
;; bly_mod_i64   in: HL=&a DE=&m BC=&r   out: (BC) = a mod m, with m's sign (Python's %)   fails: mod by zero   clobbers: AF BC DE HL IX
;; bly_abs_i64   in: HL=&a BC=&r         out: (BC) = |a|                                 fails: quad overflow (MIN)    clobbers: AF BC DE HL
;; bly_fit_i64   in: HL=&v A=the type (0 byte, 1 word, 2 int, 3 long, 4 quad) DE=&dest
;;               out: (DE) = v in that type's 1, 2, 2, 4 or 8 bytes: byte and word wrap   fails: int or long overflow   clobbers: AF BC DE HL
;; bly_i_ugcd    (internal) in: bly_i_gx, bly_i_gy = unsigned 8-byte   out: bly_i_gx = their gcd   clobbers: AF BC DE HL IX, gy
;; bly_i_gcd16   (internal) in: HL DE   out: HL = gcd(HL, DE), unsigned (0 and 0 give 0)       clobbers: AF B DE HL
;; bly_i_gx, bly_i_gy  (internal) 8 bytes each
;
; The quad functions the code generator widens everything into (ABI.md section 8), then narrows with bly_fit_i64.
; - gcd needs no division when both are wide: binary gcd (as z88dk does it) on 8 bytes in memory. But as soon as
;   either value fits 16 bits, one 64/16 remainder brings the other down too, and a 16-bit binary gcd in registers
;   finishes. AoC's usual gcd(big, small) is one fast divide and a few hundred T.
; - lcm is a / gcd(a, b) * b: the divide by a small gcd is the fast path, and the multiply is the checked one.
; - mod is the truncating remainder, moved to the divisor's sign.
; r may be a or b throughout: the inputs are copied before anything is written.

bly_gcd_i64:
        push bc
        push de
        ld de,bly_i_gx
        ld b,8
        call bly_i_copyabs
        pop hl
        ld de,bly_i_gy
        ld b,8
        call bly_i_copyabs
        call bly_i_ugcd
        ld a,(bly_i_gx+7)
        or a
        jp m,bly_ovf_quad           ; 2^63: from MIN with 0 or MIN
        pop de
        ld hl,bly_i_gx
        ld bc,8
        ldir
        ret

bly_lcm_i64:
        ld (.dst),bc
        push de
        ld de,.x
        ld b,8
        call bly_i_copyabs          ; x = |a|
        pop hl
        ld de,.y
        ld b,8
        call bly_i_copyabs          ; y = |b|
        ld hl,.x
        ld b,8
        call bly_i_sig
        or a
        jr z,.zero
        ld hl,.y
        ld b,8
        call bly_i_sig
        or a
        jr z,.zero
        ld hl,.x
        ld de,bly_i_gx
        ld bc,8
        ldir
        ld hl,.y
        ld de,bly_i_gy
        ld bc,8
        ldir
        call bly_i_ugcd             ; gx = g
        ld hl,.x
        ld de,bly_i_ua
        ld bc,8
        ldir
        ld hl,bly_i_gx
        ld de,bly_i_ub
        ld bc,8
        ldir
        ld a,8
        call bly_i_udiv             ; ua = x / g, exactly
        ld hl,bly_i_ua
        ld de,bly_i_mx
        ld bc,8
        ldir
        ld hl,.y
        ld de,bly_i_my
        ld bc,8
        ldir
        ld bc,(.dst)
        ld a,8                      ; a positive product of 8 bytes
        jp bly_i_mulmag
.zero:  ld hl,(.dst)
        ld b,8
        xor a
.z:     ld (hl),a
        inc hl
        djnz .z
        ret
.dst:   dw 0
.x:     ds 8
.y:     ds 8

bly_mod_i64:
        ld (.dst),bc
        push de
        ld de,bly_i_ua
        ld b,8
        call bly_i_copyabs          ; ua = |a|
        ld (.sa),a
        pop hl
        ld de,bly_i_ub
        ld b,8
        call bly_i_copyabs          ; ub = |m|
        ld (.sm),a
        ld a,8
        call bly_i_udiv             ; ur = |a| mod |m|
        jp z,bly_mod0
        ld hl,bly_i_ur
        ld b,8
        call bly_i_sig
        or a
        jr z,.put                   ; 0 has no sign
        ld a,(.sa)
        ld hl,.sm
        xor (hl)
        jp p,.same
        ld de,bly_i_ub              ; the signs differ: |m| - r
        ld hl,bly_i_ur
        ld b,8
        or a
.d:     ld a,(de)
        sbc a,(hl)
        ld (hl),a
        inc de
        inc hl
        djnz .d
.same:  ld a,(.sm)                  ; and the result takes m's sign
        or a
        jp p,.put
        ld hl,bly_i_ur
        ld b,8
        call bly_i_negn
.put:   ld hl,bly_i_ur
        ld de,(.dst)
        ld bc,8
        ldir
        ret
.dst:   dw 0
.sa:    db 0
.sm:    db 0

bly_abs_i64:
        push bc
        ld d,b
        ld e,c
        ld b,8
        call bly_i_copyabs
        pop hl
        ld de,7
        add hl,de
        bit 7,(hl)
        ret z
        jp bly_ovf_quad             ; |MIN| is 2^63

bly_fit_i64:
        or a
        jr z,.byte
        dec a
        jr z,.word
        dec a
        jr z,.int
        dec a
        jr z,.long
        ld bc,8
        ldir
        ret
.byte:  ld a,(hl)
        ld (de),a
        ret
.word:  ld bc,2
        ldir
        ret
.int:   ld c,2
        jr .chk
.long:  ld c,4
.chk:   push hl                     ; C = the bytes kept: the rest must be the sign of the top one kept
        push de
        ld b,0
        add hl,bc
        dec hl
        ld a,(hl)
        inc hl
        rla
        sbc a,a
        ld d,a                      ; D = 00h or FFh
        ld a,8
        sub c
        ld b,a
.l:     ld a,(hl)
        cp d
        jr nz,.ovf
        inc hl
        djnz .l
        pop de
        pop hl
        ld b,0
        ldir
        ret
.ovf:   ld a,c
        jp bly_ovf_n

bly_i_ugcd:
        xor a
        ld (.k),a
        ld hl,bly_i_gx
        ld b,8
        call bly_i_sig
        ld c,a                      ; C = gx's bytes
        or a
        jr nz,.x
        ld hl,bly_i_gy              ; gcd(0, y) = y
        ld de,bly_i_gx
        ld bc,8
        ldir
        ret
.x:     ld hl,bly_i_gy
        ld b,8
        call bly_i_sig              ; A = gy's bytes (keeps C)
        or a
        ret z                       ; gcd(x, 0) = x
        cp 3
        jr nc,.ybig
        ld b,a
        ld a,c
        cp 3
        jr nc,.finy                 ; y small, x wide
        ld hl,(bly_i_gx)            ; both small
        ld de,(bly_i_gy)
        call bly_i_gcd16
        ld (bly_i_gx),hl
        ret
.ybig:  ld a,c
        cp 3
        jr c,.finx                  ; x small, y wide
        ld hl,bly_i_gx              ; both wide: binary gcd, the common twos counted in k
        call .strip
        ld (.k),a
        ld hl,bly_i_gy
        call .strip
        ld hl,.k
        cp (hl)
        jr nc,.loop
        ld (hl),a
.loop:  ld hl,bly_i_gx              ; both odd here
        ld b,8
        call bly_i_sig
        cp 3
        jr c,.finx
        ld hl,bly_i_gy
        ld b,8
        call bly_i_sig
        cp 3
        jr c,.finy
        ld hl,bly_i_gx+7
        ld de,bly_i_gy+7
        ld b,8
.c:     ld a,(de)
        cp (hl)                     ; carry when gx > gy
        jr nz,.ne
        dec hl
        dec de
        djnz .c
        jr .done                    ; equal: that's the odd part of the gcd
.ne:    jr c,.xbig
        ld de,bly_i_gy              ; gy -= gx, then shed its twos
        ld hl,bly_i_gx
        call .sub8
        ld hl,bly_i_gy
        call .strip
        jr .loop
.xbig:  ld de,bly_i_gx
        ld hl,bly_i_gy
        call .sub8
        ld hl,bly_i_gx
        call .strip
        jr .loop
.finx:  ld hl,bly_i_gx              ; gx fits 16 bits
        ld de,bly_i_gy
        jr .fin
.finy:  ld hl,bly_i_gy
        ld de,bly_i_gx
.fin:   push hl                     ; gcd(small, big) = gcd16(small, big mod small)
        ex de,hl
        ld de,bly_i_ua
        ld bc,8
        ldir
        pop hl
        push hl
        ld de,bly_i_ub
        ld bc,8
        ldir
        ld a,8
        call bly_i_udiv
        pop hl
        ld e,(hl)
        inc hl
        ld d,(hl)
        ex de,hl
        ld de,(bly_i_ur)
        call bly_i_gcd16
        ld (bly_i_gx),hl
        ld hl,0
        ld (bly_i_gx+2),hl
        ld (bly_i_gx+4),hl
        ld (bly_i_gx+6),hl
.done:  ld a,(.k)                   ; the common twos go back on
        or a
        ret z
        ld e,a
        ld d,0
        ld hl,bly_i_gx
        ld b,h
        ld c,l
        jp bly_shl_i64

.sub8:  ld b,8                      ; (DE) -= (HL), 8 bytes
        or a
.s8:    ld a,(de)
        sbc a,(hl)
        ld (de),a
        inc de
        inc hl
        djnz .s8
        ret

.strip: ld c,0                      ; HL = &x, not 0: shift x right until it's odd; A = how far
.sb:    ld a,(hl)
        or a
        jr nz,.sbit
        push hl                     ; a whole zero byte: move everything down one
        ld d,h
        ld e,l
        inc hl
        push bc
        ld bc,7
        ldir
        pop bc
        xor a
        ld (de),a
        pop hl
        ld a,c
        add a,8
        ld c,a
        jr .sb
.sbit:  bit 0,(hl)
        jr nz,.sdone
        push hl
        ld de,7
        add hl,de
        srl (hl)
        ld b,7
.sr:    dec hl
        rr (hl)
        djnz .sr
        pop hl
        inc c
        jr .sbit
.sdone: ld a,c
        ret

.k:     db 0

bly_i_gcd16:
        ld a,h
        or l
        jr nz,.h
        ex de,hl                    ; gcd(0, y) = y
        ret
.h:     ld a,d
        or e
        ret z                       ; gcd(x, 0) = x
        ld b,0                      ; the common twos
.two:   ld a,l
        or e
        rra
        jr c,.oh
        srl h
        rr l
        srl d
        rr e
        inc b
        jr .two
.oh:    bit 0,l                     ; HL odd
        jr nz,.od
        srl h
        rr l
        jr .oh
.od:    bit 0,e                     ; DE odd
        jr nz,.sub
        srl d
        rr e
        jr .od
.sub:   or a                        ; both odd: the larger becomes their difference, which is even
        sbc hl,de
        jr z,.eq
        jr nc,.sh
        add hl,de                   ; HL was the smaller: swap, and take the difference the other way
        ex de,hl
        or a
        sbc hl,de
.sh:    srl h                       ; shed the difference's twos (it isn't 0)
        rr l
        bit 0,l
        jr z,.sh
        jr .sub
.eq:    ex de,hl
        inc b
        jr .st
.shl:   add hl,hl
.st:    djnz .shl
        ret

bly_i_gx: ds 8
bly_i_gy: ds 8
