;; provides: bly_fsqrt
;; needs: bly_fc bly_fx bly_pr_cstr bly_pr_f bly_fail
;; targets: cpm zx48 test
;; The square root, the same on every machine: correctly rounded (the nearest 5 bytes, ties away from zero), and on the
;; 48K about 40 times quicker than the ROM's SQR, which is EXP(LN x / 2) (385,551 T on average to this 9,614).
;; bly_fsqrt      in: HL=&x BC=&r   out: (BC) = the root, in the full form   fails: sqrt({x}) has no answer (x < 0)
;;                clobbers: AF BC DE HL IX
;
; -- sqrt: exact, in two halves ---------------------------------------------------------------------------------------
; x = f x 2^p, f in [1/2, 1): the root is sqrt(f) x 2^(p/2) for an even p, sqrt(f/2) x 2^((p+1)/2) for an odd one, and
; its mantissa's 33-bit floor is y = isqrt(N), N = M << 34 or M << 33; the last bit rounds it (ties away), as
; everywhere. The answer's exponent byte is ((e - 127) >> 1) + 128. With N = M' x 2^2k (M' = M and k = 17, or M' = 2M
; and k = 16), y comes in two halves, each small enough for registers:
; - q1 and r1, isqrt(M') and M' - q1^2, by the bit-pair method: rem in C:HL and t = 4q + 1 in B:DE (so t becomes
;   2t + 3 or 2t - 1), the pairs shifted out of IX. An odd p's first pair is 0 and M's top bit, which is 1, leaving rem
;   0 and t 5; either way 16 pairs follow, M's or M << 1's.
; - y = q1 2^k + d, d the largest with q1 d 2^(k+1) + d^2 <= r1 2^2k. One division gives d0 = r1 2^(k-1) // q1, never
;   too small, and its remainder D0; the exact residue r1 2^2k - q1 d0 2^(k+1) - d0^2 is 2^(k+1) D0 - d0^2, and each
;   step d takes down adds q1 2^(k+1) + 2d - 1 to it, until it isn't negative: twice at most. (Held to Python's
;   math.isqrt on 600,000 roots before it was written.)
; Scratch inside the fragment: .x .n .s .ip .d .res .qk .t5.
bly_fsqrt:
        ld (bly_fc.res),bc
        ld (.x),hl
        ld de,bly_fc.ua
        call bly_fx.unpack
        ld a,(bly_fc.ua+1)
        or a
        jp z,bly_fc.zero            ; sqrt(0) is 0
        ld a,(bly_fc.ua)
        or a
        jp nz,.no                   ; a negative has no root
        ld (bly_fc.sg),a
        ld a,(bly_fc.ua+1)          ; the exponent: ((e - 127) >> 1) + 128, in 16 bits
        ld l,a
        ld h,0
        ld de,-127
        add hl,de
        sra h
        rr l
        ld de,128
        add hl,de
        ld (bly_fc.ex),hl
        ld a,(bly_fc.ua+5)          ; M, in HL:DE
        ld e,a
        ld a,(bly_fc.ua+4)
        ld d,a
        ld a,(bly_fc.ua+3)
        ld l,a
        ld a,(bly_fc.ua+2)
        ld h,a
        ld a,(bly_fc.ua+1)          ; e odd is p odd (p = e - 128): M' = 2M, its first pair taken (t 5), M << 1's next
        rra
        ld a,1
        jr nc,.even
        sla e
        rl d
        adc hl,hl
        ld a,5
.even:  ld (.s),hl
        ld (.s+2),de
        ld e,a                      ; t = B:DE, rem = C:HL = 0
        ld d,0
        ld b,d
        ld c,d
        ld h,d
        ld l,d
        ld ix,(.s)
        call .pairs
        ld ix,(.s+2)
        call .pairs
        srl b                       ; q1 = t >> 2 in B:DE (16 or 17 bits); r1 in C:HL (to 18)
        rr d
        rr e
        srl b
        rr d
        rr e
        xor a                       ; d0 = r1 2^(k-1) // q1: its integer part first, r1 // q1, 0 to 2
        ld (.ip),a
.ipl:   or a
        sbc hl,de
        ld a,c
        sbc a,b
        jr c,.ipd
        ld c,a
        ld a,(.ip)
        inc a
        ld (.ip),a
        jr .ipl
.ipd:   add hl,de                   ; R = r1 mod q1, below q1; then k - 1 bits more (16, or 15 for an odd p), into IX
        ld ix,0
        ld a,(bly_fc.ua+1)
        and 1
        ld a,16
        jr z,.fk
        dec a
.fk:    ld (.n),a
.frac:  add hl,hl                   ; R = 2R (below 2^18)
        rl c
        or a
        sbc hl,de
        ld a,c
        sbc a,b
        jr c,.f0
        ld c,a
        add ix,ix
        inc ix
        jr .fn
.f0:    add hl,de
        add ix,ix
.fn:    ld a,(.n)
        dec a
        ld (.n),a
        jr nz,.frac
        ld (.res+2),hl              ; .res = D0 2^(k+1), .qk = q1 2^(k+1): each << 16, then << 2 (or << 1, odd p)
        ld a,c
        ld (.res+4),a
        ld (.qk+2),de
        ld a,b
        ld (.qk+4),a
        ld hl,0
        ld (.res),hl
        ld (.qk),hl
        ld hl,.res
        call .shl5
        ld hl,.qk
        call .shl5
        ld a,(bly_fc.ua+1)
        rra
        jr c,.k1
        ld hl,.res
        call .shl5
        ld hl,.qk
        call .shl5
.k1:    ld (.d),ix                  ; d0 = ip 2^(k-1) + IX, three bytes
        ld a,(.ip)
        ld (.d+2),a
        ld a,(bly_fc.ua+1)
        rra
        jr nc,.d1
        ld hl,.d+2                  ; odd p: ip 2^15 (IX is below 2^15)
        srl (hl)
        dec hl
        jr nc,.d1
        set 7,(hl)
.d1:    ld de,(.d)                  ; d0^2 = a^2 2^32 + 2aw 2^16 + w^2, for d0 = a 2^16 + w (a is 0 to 2)
        call .square                ; DE:HL = w^2
        ld (.t5),hl
        ld (.t5+2),de
        xor a
        ld (.t5+4),a
        ld a,(.d+2)
        or a
        jr z,.sq
        ld b,0                      ; 2aw, in B:HL (below 2^18), at 2^16
        ld hl,(.d)
        add hl,hl
        rl b
        cp 1
        jr z,.aw
        add hl,hl
        rl b
.aw:    ld de,(.t5+2)
        add hl,de
        ld (.t5+2),hl
        ld a,b
        adc a,0
        ld b,a
        ld a,(.d+2)                 ; and a^2, 1 or 4, at 2^32
        cp 1
        ld a,1
        jr z,.a2
        ld a,4
.a2:    add a,b
        ld (.t5+4),a
.sq:    ld hl,.res                  ; the residue: D0 2^(k+1) - d0^2
        ld de,.t5
        call .sub5
.fix:   ld a,(.res+4)               ; negative: d one less, and the residue up by q1 2^(k+1) + 2d + 1 (d the new d)
        rla
        jr nc,.fixed
        ld hl,(.d)
        ld a,(.d+2)
        ld de,1
        or a
        sbc hl,de
        sbc a,0
        ld (.d),hl
        ld (.d+2),a
        ld (.t5),hl
        ld (.t5+2),a
        xor a
        ld (.t5+3),a
        ld (.t5+4),a
        ld hl,.t5
        call .shl5
        ld hl,.t5
        set 0,(hl)
        ld hl,.res
        ld de,.t5
        call .add5
        ld hl,.res
        ld de,.qk
        call .add5
        jr .fix
.fixed: ld hl,.qk+4                 ; y = q1 2^k + d = .qk / 2 + d, 33 bits
        srl (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        ld hl,(.d)
        ld a,(.d+2)
        ld (.t5),hl
        ld (.t5+2),a
        xor a
        ld (.t5+3),a
        ld (.t5+4),a
        ld hl,.qk
        ld de,.t5
        call .add5
        ld hl,.qk+4                 ; 33 bits: the mantissa is y >> 1, and y's last bit decides
        srl (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        ld a,0
        rra
        ld (bly_fc.w+3),a           ; (sqrt's rounding bit)
        ld hl,.qk
        ld de,bly_fc.w+4
        ld bc,4
        ldir
        jp bly_fc.pack
.pairs: ld a,8                      ; 8 pairs from IX, its top first
        ld (.n),a
.pair:  add ix,ix                   ; rem = 4 rem + the pair
        adc hl,hl
        rl c
        add ix,ix
        adc hl,hl
        rl c
        or a                        ; rem >= t? (both below 2^20)
        sbc hl,de
        ld a,c
        sbc a,b
        jr c,.p0
        ld c,a                      ; yes: rem -= t, and t = 2t + 3 (q becomes 2q + 1; E's low bits go 010 to 101,
        sla e                       ; with no carry)
        rl d
        rl b
        inc e
        inc e
        inc e
        jr .pn
.p0:    add hl,de                   ; no: rem as it was, and t = 2t - 1 (q becomes 2q; 010 to 001)
        sla e
        rl d
        rl b
        dec e
.pn:    ld a,(.n)
        dec a
        ld (.n),a
        jr nz,.pair
        ret
.square: ld b,d                     ; DE:HL = DE^2: BC the multiplicand, DE the multiplier shifting out above HL
        ld c,e                      ; as the product shifts in (its own, so as not to bring a 16-bit multiply's
        ld hl,0                     ; fragments along for one square)
        ld a,16
.sql:   add hl,hl
        rl e
        rl d
        jr nc,.sqn
        add hl,bc
        jr nc,.sqn
        inc de
.sqn:   dec a
        jr nz,.sql
        ret
.shl5:  sla (hl)                    ; (HL) <<= 1, five bytes, low first
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        ret
.add5:  or a                        ; (HL) += (DE), five bytes
        ld b,5
.a5:    ld a,(de)
        adc a,(hl)
        ld (hl),a
        inc hl
        inc de
        djnz .a5
        ret
.sub5:  ex de,hl                    ; (HL) -= (DE), five bytes: the subtrahend through HL, as sbc needs
        or a
        ld b,5
.s5:    ld a,(de)
        sbc a,(hl)
        ld (de),a
        inc hl
        inc de
        djnz .s5
        ret
.no:    ld hl,.msqrt                ; sqrt({x}) has no answer
        call bly_pr_cstr
        ld hl,(.x)
        call bly_pr_f
        ld hl,.mno
        jp bly_fail
.x:     dw 0
.n:     db 0
.s:     ds 4
.ip:    db 0
.d:     ds 3
.res:   ds 5
.qk:    ds 5
.t5:    ds 5
.msqrt: db "sqrt(",0
.mno:   db ") has no answer",0

