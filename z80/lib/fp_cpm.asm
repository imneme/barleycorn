;; provides: bly_fadd bly_fsub bly_fmul bly_fdiv bly_fsqrt bly_fc bly_pr_f
;; needs: bly_fx bly_fail bly_div0 bly_i_mul16 bly_pr_cstr
;; targets: cpm test
;; Floats where there's no ROM (CP/M, and the bare Z80 the tests use): the ROM's 5-byte form all the same (ABI.md
;; section 11), with our own arithmetic, correctly rounded: the nearest 5 bytes, ties away from zero, as a literal is
;; (z80gen.rom5). Held bit for bit to a model of exact Fractions.
;; bly_fadd bly_fsub bly_fmul bly_fdiv   in: HL=&a DE=&b BC=&r   out: (BC) = a op b, in the full form
;;        fails: float overflow; division by zero (/)
;; bly_fsqrt      in: HL=&x BC=&r   out: (BC) = the root, correctly rounded   fails: sqrt({x}) has no answer (x < 0)
;; bly_pr_f       in: HL=&x   prints x as the ROM's PRINT-FP lays a number out (8 digits, .0001, 1E+10), its digits
;;                exactly rounded, through bly_out (so print's column is kept)
;; Every routine clobbers AF BC DE HL IX.
;
; The one trick: rounding x to 32 bits with ties away from zero is floor(x + 1/2) = (floor(2x) + 1) >> 1, so each
; operation needs only the floor of its exact answer to 33 bits (32 and the one that decides): no sticky bits.
; * and / get exact floors by their nature (the whole 64-bit product; restoring division). + and - work in a 64-bit
; window, the larger number at its top: bits of the smaller shifted out of the bottom can't move a floor at the
; rounding's scale when adding, and when subtracting they take exactly one more unit off (the true difference lies
; strictly between two integers of the window, and rounding's boundaries are integers there).
; bly_fc is the shared part: .pack rounds the window (.w, its top bit set) by its bit 31 and writes the answer.
; Scratch: bly_fc's .res .flip .sg .lost .ex .ua .ub .w .v .r .d .q.

; -- + and - ---------------------------------------------------------------------------------------------------------
bly_fsub:
        ld a,80h                    ; b's sign flipped
        jr bly_fadd.go
bly_fadd:
        xor a
.go:    ld (bly_fc.flip),a
        call bly_fc.both
        ld hl,bly_fc.ub
        ld a,(bly_fc.flip)
        xor (hl)
        ld (hl),a
        ld a,(bly_fc.ub+1)
        or a
        ld hl,bly_fc.ua
        jp z,bly_fc.put             ; b is 0: a
        ld a,(bly_fc.ua+1)
        or a
        ld hl,bly_fc.ub
        jp z,bly_fc.put             ; a is 0: b, its sign as flipped
        ld hl,bly_fc.ua+1           ; |a| >= |b|? the exponents, then the mantissas, high byte first
        ld de,bly_fc.ub+1
        ld b,5
.cmp:   ld a,(de)
        cp (hl)
        jr nz,.cmpd
        inc hl
        inc de
        djnz .cmp
        jr .ord
.cmpd:  jr c,.ord                   ; b's is smaller
        ld hl,bly_fc.ua             ; else swap them: the larger is a from here
        ld de,bly_fc.ub
        ld b,6
.sw:    ld a,(de)
        ld c,(hl)
        ld (hl),a
        ld a,c
        ld (de),a
        inc hl
        inc de
        djnz .sw
.ord:   ld hl,bly_fc.w              ; .w = a's mantissa << 32; .v = 0
        xor a
        ld b,16
.z:     ld (hl),a
        inc hl
        djnz .z
        ld (bly_fc.lost),a
        ld hl,bly_fc.ua+2
        ld de,bly_fc.w+7
        ld b,4
.wa:    ld a,(hl)
        ld (de),a
        inc hl
        dec de
        djnz .wa
        ld a,(bly_fc.ua+1)          ; d = ea - eb
        ld hl,bly_fc.ub+1
        sub (hl)
        cp 64
        jr nc,.op                   ; all of b is below the window: a alone rounds as a - b does
        ld c,a                      ; C = d
        rrca
        rrca
        rrca
        and 1Fh                     ; whole bytes: k = d / 8
        ld b,a
        ld a,7
        sub b                       ; where b's top byte lands: 7 - k, then down
        ld hl,bly_fc.ub+2
        ld b,4
.pl:    bit 7,a
        jr nz,.pn                   ; below the window (see .bits)
        push hl
        ld e,a
        ld d,0
        ld hl,bly_fc.v
        add hl,de
        ex de,hl
        pop hl
        push af
        ld a,(hl)
        ld (de),a
        pop af
        jr .pn
.pn:    inc hl
        dec a
        djnz .pl
        ld a,c                      ; and d % 8 bits. Only here can what b loses matter, and only at d = 33: from
        and 7                       ; 34 on, what's left of b is 1 to 2^30, so a - b can't sit on a rounding
                                    ; boundary (multiples of 2^30, after the one shift a - b can need); whole bytes
                                    ; go below only from 40, and from 64 nothing is left and a rounds as a - b
        jr z,.op
        ld b,a
.bits:  ld hl,bly_fc.v+7
        srl (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        jr nc,.bnl
        ld a,1
        ld (bly_fc.lost),a
.bnl:   djnz .bits
.op:    ld a,(bly_fc.ua)            ; the answer's sign is the larger's
        ld (bly_fc.sg),a
        ld a,(bly_fc.ua+1)
        ld l,a
        ld h,0
        ld (bly_fc.ex),hl
        ld a,(bly_fc.ub)
        ld hl,bly_fc.ua
        xor (hl)
        jr nz,.sub
        ld hl,bly_fc.w              ; the same signs: .w += .v
        ld de,bly_fc.v
        ld b,8
        or a
.ad:    ld a,(de)
        adc a,(hl)
        ld (hl),a
        inc hl
        inc de
        djnz .ad
        jp nc,bly_fc.pack
        ld hl,bly_fc.w+7            ; a carry out: shift it back in at the top, one more in the exponent
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        ld hl,(bly_fc.ex)
        inc hl
        ld (bly_fc.ex),hl
        jp bly_fc.pack
.sub:   ld a,(bly_fc.lost)          ; signs differ: .w -= .v, and one more unit if b lost any bits
        rra
        ld hl,bly_fc.v
        ld de,bly_fc.w
        ld b,8
.sb:    ld a,(de)
        sbc a,(hl)
        ld (de),a
        inc hl
        inc de
        djnz .sb
        ld hl,bly_fc.w              ; nothing left: 0
        xor a
        ld b,8
.nz:    or (hl)
        inc hl
        djnz .nz
        jp z,bly_fc.zero
.norm:  ld a,(bly_fc.w+7)           ; normalise: whole bytes first, then bits
        or a
        jr nz,.nb
        ld hl,bly_fc.w+6
        ld de,bly_fc.w+7
        ld bc,7
        lddr
        xor a
        ld (bly_fc.w),a
        ld hl,(bly_fc.ex)
        ld de,-8
        add hl,de
        ld (bly_fc.ex),hl
        jr .norm
.nb:    bit 7,a
        jp nz,bly_fc.pack
        call bly_fc.shl
        ld hl,(bly_fc.ex)
        dec hl
        ld (bly_fc.ex),hl
        jr .nb2
.nb2:   ld a,(bly_fc.w+7)
        jr .nb

; -- * ----------------------------------------------------------------------------------------------------------------
bly_fmul:
        call bly_fc.both
        ld a,(bly_fc.ua+1)
        or a
        jp z,bly_fc.zero
        ld a,(bly_fc.ub+1)
        or a
        jp z,bly_fc.zero
        ld a,(bly_fc.ua)
        ld hl,bly_fc.ub
        xor (hl)
        ld (bly_fc.sg),a
        ld a,(bly_fc.ua+1)          ; e = ea + eb - 128 (both biased)
        ld l,a
        ld h,0
        ld a,(bly_fc.ub+1)
        ld e,a
        ld d,0
        add hl,de
        ld de,-128
        add hl,de
        ld (bly_fc.ex),hl
        ld hl,bly_fc.w              ; the 64-bit product of the mantissas, from four 16 x 16 products
        xor a
        ld b,8
.z:     ld (hl),a
        inc hl
        djnz .z
        ld ix,bly_fc.w+4            ; ah * bh at 32
        ld hl,bly_fc.ua+2
        ld de,bly_fc.ub+2
        call .part
        ld ix,bly_fc.w              ; al * bl at 0
        ld hl,bly_fc.ua+4
        ld de,bly_fc.ub+4
        call .part
        ld ix,bly_fc.w+2            ; ah * bl and al * bh at 16
        ld hl,bly_fc.ua+2
        ld de,bly_fc.ub+4
        call .part
        ld ix,bly_fc.w+2
        ld hl,bly_fc.ua+4
        ld de,bly_fc.ub+2
        call .part
        ld a,(bly_fc.w+7)           ; [2^62, 2^64): at most one shift to normalise
        rla
        jp c,bly_fc.pack
        call bly_fc.shl
        ld hl,(bly_fc.ex)
        dec hl
        ld (bly_fc.ex),hl
        jp bly_fc.pack
.part:  ld b,(hl)                   ; HL, DE = two big-endian 16-bit halves; their product added at IX, with its
        inc hl                      ; carry into IX+4 and IX+5
        ld c,(hl)
        ex de,hl
        ld d,(hl)
        inc hl
        ld e,(hl)
        call bly_i_mul16            ; DE:HL = BC * DE
        ld a,(ix+0)
        add a,l
        ld (ix+0),a
        ld a,(ix+1)
        adc a,h
        ld (ix+1),a
        ld a,(ix+2)
        adc a,e
        ld (ix+2),a
        ld a,(ix+3)
        adc a,d
        ld (ix+3),a
        ret nc
        inc (ix+4)
        ret nz
        inc (ix+5)
        ret

; -- / ----------------------------------------------------------------------------------------------------------------
bly_fdiv:
        call bly_fc.both
        ld a,(bly_fc.ub+1)
        or a
        jp z,bly_div0
        ld a,(bly_fc.ua+1)
        or a
        jp z,bly_fc.zero
        ld a,(bly_fc.ua)
        ld hl,bly_fc.ub
        xor (hl)
        ld (bly_fc.sg),a
        ld a,(bly_fc.ua+1)          ; e = ea - eb + 128
        ld l,a
        ld h,0
        ld a,(bly_fc.ub+1)
        ld e,a
        ld d,0
        or a
        sbc hl,de
        ld de,128
        add hl,de
        ld (bly_fc.ex),hl
        ld hl,bly_fc.ua+2           ; .r = a's mantissa, .d = b's, .q = 0 (five bytes each, little-endian)
        ld de,bly_fc.r+3
        call .ld4
        ld hl,bly_fc.ub+2
        ld de,bly_fc.d+3
        call .ld4
        xor a
        ld (bly_fc.r+4),a
        ld (bly_fc.d+4),a
        ld hl,bly_fc.q
        ld b,5
.qz:    ld (hl),a
        inc hl
        djnz .qz
        ld b,33                     ; 33 quotient bits: the top one at 2^32
        call .cmp
        jr c,.loop                  ; a's mantissa < b's: the first step finds it
        call .sub                   ; >= : the quotient's 1 now, 32 more, and the exponent one up
        ld a,1
        ld (bly_fc.q),a
        ld b,32
        ld hl,(bly_fc.ex)
        inc hl
        ld (bly_fc.ex),hl
.loop:  ld hl,bly_fc.r              ; R = 2R
        sla (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        call .cmp                   ; NC if R >= D
        ccf
        jr nc,.q0
        call .sub
        scf
.q0:    ld hl,bly_fc.q              ; Q = 2Q + the bit
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        djnz .loop
        ld hl,bly_fc.q+4            ; 33 bits: the mantissa is Q >> 1, and Q's last bit decides
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
        ld (bly_fc.w+3),a
        ld hl,bly_fc.q
        ld de,bly_fc.w+4
        ld bc,4
        ldir
        jp bly_fc.pack
.ld4:   ld b,4                      ; HL = big-endian m3..m0 -> DE down to DE-3 (little-endian)
.l4:    ld a,(hl)
        ld (de),a
        inc hl
        dec de
        djnz .l4
        ret
.cmp:   push bc                     ; C if R < D (five bytes, high first)
        ld hl,bly_fc.d+4
        ld de,bly_fc.r+4
        ld b,5
.c1:    ld a,(de)
        cp (hl)
        jr nz,.c2
        dec hl
        dec de
        djnz .c1
.c2:    pop bc
        ret
.sub:   push bc                     ; R -= D
        ld hl,bly_fc.d
        ld de,bly_fc.r
        ld b,5
        or a
.s1:    ld a,(de)
        sbc a,(hl)
        ld (de),a
        inc hl
        inc de
        djnz .s1
        pop bc
        ret

; -- sqrt: exact, by the bit-pair method ---------------------------------------------------------------------------
; x = f x 2^p, f in [1/2, 1): the root is sqrt(f) x 2^(p/2) for an even p, sqrt(f/2) x 2^((p+1)/2) for an odd one, and
; its mantissa's 33-bit floor is isqrt(M << 34) or isqrt(M << 33), which the bit-pair method gives exactly; the last
; bit rounds it (ties away), as everywhere. The answer's exponent byte is ((e - 127) >> 1) + 128.
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
        ld hl,.rad                  ; .rad = M << 40 (or << 39 for an odd p): its top pair is the radicand's
        xor a
        ld b,9+5+5
.z:     ld (hl),a                   ; (.rad, .rem and .q cleared together)
        inc hl
        djnz .z
        ld hl,bly_fc.ua+2           ; M, big-endian, into .rad+8 down to .rad+5
        ld de,.rad+8
        ld b,4
.ld:    ld a,(hl)
        ld (de),a
        inc hl
        dec de
        djnz .ld
        ld a,(bly_fc.ua+1)          ; e odd is p odd (p = e - 128): one place lower
        rra
        jr nc,.even
        ld hl,.rad+8
        srl (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
.even:  ld a,33                     ; 33 pairs, the root's 33 bits
        ld (.n),a
.step:  call .pair                  ; .rem = .rem << 2 | the next pair
        call .pair
        ld hl,.q                    ; .t = .q << 2 | 1
        ld de,.t
        ld bc,5
        ldir
        ld hl,.t
        sla (hl)
        call .rl4
        ld hl,.t
        sla (hl)
        call .rl4
        ld hl,.t
        set 0,(hl)
        ld hl,.t+4                  ; .rem >= .t? (high byte first)
        ld de,.rem+4
        ld b,5
.cp:    ld a,(de)
        cp (hl)
        jr nz,.cpd
        dec hl
        dec de
        djnz .cp
.cpd:   jr c,.q0
        ld hl,.t                    ; .rem -= .t, and a 1 into the root
        ld de,.rem
        ld b,5
        or a
.sb:    ld a,(de)
        sbc a,(hl)
        ld (de),a
        inc hl
        inc de
        djnz .sb
        scf
        jr .qs
.q0:    or a
.qs:    ld hl,.q                    ; .q = .q << 1 | the bit
        rl (hl)
        call .rl4
        ld hl,.n
        dec (hl)
        jr nz,.step
        ld hl,.q+4                  ; 33 bits: the mantissa is .q >> 1, its last bit decides
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
        ld (bly_fc.w+3),a
        ld hl,.q
        ld de,bly_fc.w+4
        ld bc,4
        ldir
        jp bly_fc.pack
.pair:  ld hl,.rad                  ; the radicand's top bit into .rem
        sla (hl)
        ld b,8
.p1:    inc hl
        rl (hl)
        djnz .p1
        ld hl,.rem
        rl (hl)
.rl4:   inc hl                      ; carry on through the next four bytes
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        inc hl
        rl (hl)
        ret
.no:    ld hl,.msqrt                ; sqrt({x}) has no answer
        call bly_pr_cstr
        ld hl,(.x)
        call bly_pr_f
        ld hl,.mno
        jp bly_fail
.x:     dw 0
.n:     db 0
.rad:   ds 9                        ; .rad, .rem and .q are cleared together: keep them in this order
.rem:   ds 5
.q:     ds 5
.t:     ds 5
.msqrt: db "sqrt(",0
.mno:   db ") has no answer",0

; -- the shared part ------------------------------------------------------------------------------------------------
bly_fc:
.both:  ld (.res),bc                ; HL=&a DE=&b BC=&r: unpack both into .ua and .ub
        push de
        ld de,.ua
        call bly_fx.unpack
        pop hl
        ld de,.ub
        jp bly_fx.unpack

.pack:  ld a,(.w+3)                 ; .w's top bit set, .ex its exponent byte (biased, 16 bits), .sg the sign:
        rla                         ; round by bit 31, ties away, and write the 5 bytes; out of range is an
        ld hl,(.w+4)                ; overflow, or 0
        ld de,(.w+6)
        jr nc,.rd
        inc l
        jr nz,.rd
        inc h
        jr nz,.rd
        inc e
        jr nz,.rd
        inc d
        jr nz,.rd
        ld d,80h                    ; 1.000... -> 0.1000... x 2
        ld bc,(.ex)
        inc bc
        ld (.ex),bc
.rd:    ld bc,(.ex)
        ld a,b
        or a
        jr nz,.range
        ld a,c
        or a
        jr z,.zero                  ; under 2^-128: 0, as the ROM's
        ld ix,(.res)
        ld (ix+0),c
        ld a,d
        and 7Fh
        ld b,a
        ld a,(.sg)
        or b
        ld (ix+1),a
        ld (ix+2),e
        ld (ix+3),h
        ld (ix+4),l
        ret
.range: bit 7,b
        jr nz,.zero                 ; below: 0
        ld hl,.movf
        jp bly_fail

.zero:  ld hl,(.res)
        ld b,5
        xor a
.zl:    ld (hl),a
        inc hl
        djnz .zl
        ret

.put:   ld de,(.res)                ; HL = &u (sign, e, m3 m2 m1 m0) -> (.res) in the full form (0 stays 0)
        ld c,(hl)
        inc hl
        ld a,(hl)
        ld (de),a
        inc hl
        inc de
        ld a,(hl)
        and 7Fh
        or c
        ld (de),a
        inc hl
        inc de
        ld bc,3
        ldir
        ret

.shl:   ld hl,.w                    ; .w <<= 1
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
        ret

.res:   dw 0
.flip:  db 0
.sg:    db 0
.lost:  db 0
.ex:    dw 0
.ua:    ds 6
.ub:    ds 6
.w:     ds 8                        ; .v follows .w: + and - clear both at once
.v:     ds 8
.r:     ds 5
.d:     ds 5
.q:     ds 5
.movf:  db "float overflow",0

; -- printing: PRINT-FP's layout, the 8 digits exactly rounded -------------------------------------------------------
; x = M x 2^E (M the 32-bit mantissa, E = e - 160). Guess k with 10^k <= x < 10^(k+1) as ((e - 129) * 77) >> 8,
; then q = floor(x x 10^(8 - k)) exactly, in 24 bytes: x10 and then the shift (a floor), or the shift and then /10
; (nested floors of positive divisions are exact). q in [10^8, 10^9) says the guess was right (else k moves by one,
; and again); its last digit rounds it to 8, ties away (what's below that digit is under one of its units). 10^8
; after rounding is 10^7 with k one up. Then the digits, their trailing zeros off, laid out as fp5.show lays them.
bly_pr_f:
        ld de,.u
        call bly_fx.unpack
        ld de,.txt
        ld a,(.u+1)
        or a
        jr nz,.nz
        ld a,'0'                    ; 0
        ld (de),a
        inc de
        jp .out
.nz:    ld a,(.u)
        or a
        jr z,.pos
        ld a,'-'
        ld (de),a
        inc de
.pos:   ld (.at),de
        ld a,(.u+1)                 ; k's guess: ((e - 129) * 77) >> 8, which is low by one at most
        sub 129
        ld l,a
        rla
        sbc a,a
        ld h,a                      ; HL = e - 129
        push hl
        add hl,hl
        add hl,hl
        push hl                     ; 4x
        add hl,hl
        push hl                     ; 8x
        add hl,hl
        add hl,hl
        add hl,hl                   ; 64x
        pop de
        add hl,de
        pop de
        add hl,de
        pop de
        add hl,de                   ; 77x
        ld a,h
        ld (.k),a
.calc:  ld hl,.big                  ; .big = M (little-endian), the rest 0
        xor a
        ld b,24
.cz:    ld (hl),a
        inc hl
        djnz .cz
        ld hl,.u+5
        ld de,.big
        ld b,4
.cm:    ld a,(hl)
        ld (de),a
        dec hl
        inc de
        djnz .cm
        ld a,(.k)
        neg
        add a,8                     ; 8 - k: q's scale
        ld (.s1),a
        bit 7,a
        jr nz,.down
        or a
        jr z,.e1
        ld b,a
.up:    push bc
        call .mul10
        pop bc
        djnz .up
.e1:    call .scale
        jr .got
.down:  call .scale
        ld a,(.s1)
        neg
        ld b,a
.dn:    push bc
        call .div10
        pop bc
        djnz .dn
.got:   ld hl,.big+4                ; q: is it in [10^8, 10^9)?
        xor a
        ld b,20
.gz:    or (hl)
        inc hl
        djnz .gz
        jr nz,.kup
        ld hl,.t9+3
        call .cmp4
        jr nc,.kup
        ld hl,.t8+3
        call .cmp4
        jr nc,.kok
        ld hl,.k                    ; under: k one down
        dec (hl)
        jr .calc
.kup:   ld hl,.k
        inc (hl)
        jr .calc
.kok:   call .div10                 ; d = q / 10, up one if its last digit is 5 or more
        cp 5
        jr c,.nr
        ld hl,.big
        inc (hl)
        jr nz,.nr
        inc hl
        inc (hl)
        jr nz,.nr
        inc hl
        inc (hl)
        jr nz,.nr
        inc hl
        inc (hl)
.nr:    ld hl,.t8+3                 ; rounded up to 10^8: 10^7, one more in k
        call .cmp4
        jr nz,.dg0
        ld hl,.t7
        ld de,.big
        ld bc,4
        ldir
        ld hl,.k
        inc (hl)
.dg0:   ld hl,.dig+7                ; the 8 digits, the last first
        ld b,8
.dg:    push bc
        push hl
        call .div10
        pop hl
        add a,'0'
        ld (hl),a
        dec hl
        pop bc
        djnz .dg
        ld hl,.dig+7                ; C = how many, trailing zeros off (one stays)
        ld c,8
.tz:    ld a,c
        dec a
        jr z,.lay
        ld a,(hl)
        cp '0'
        jr nz,.lay
        dec hl
        dec c
        jr .tz
.lay:   ld de,(.at)                 ; DE writes the text; HL reads the digits
        ld hl,.dig
        ld a,(.k)
        add a,5
        cp 13
        jr nc,.sci                  ; k outside -5..7: E notation
        ld a,(.k)
        bit 7,a
        jr nz,.frac
        inc a                       ; k >= 0: k + 1 whole digits (zeros past the last), then any more after a point
        ld b,a
.wh:    ld a,c
        or a
        ld a,'0'
        jr z,.w0
        ld a,(hl)
        inc hl
        dec c
.w0:    ld (de),a
        inc de
        djnz .wh
        ld a,c
        or a
        jr z,.out
        ld a,'.'
        ld (de),a
        inc de
.rest:  ld a,(hl)
        ld (de),a
        inc hl
        inc de
        dec c
        jr nz,.rest
        jr .out
.frac:  cp 0FFh                     ; k = -1: 0. then the digits; else . then -k-1 zeros, then the digits
        jr nz,.fz
        ld a,'0'
        ld (de),a
        inc de
.fz:    ld a,'.'
        ld (de),a
        inc de
        ld a,(.k)
        neg
        dec a
        jr z,.rest
        ld b,a
        ld a,'0'
.fzl:   ld (de),a
        inc de
        djnz .fzl
        jr .rest
.sci:   ld a,(hl)                   ; d.ddd then E, its sign, and k
        ld (de),a
        inc hl
        inc de
        dec c
        jr z,.ex
        ld a,'.'
        ld (de),a
        inc de
.sd:    ld a,(hl)
        ld (de),a
        inc hl
        inc de
        dec c
        jr nz,.sd
.ex:    ld a,'E'
        ld (de),a
        inc de
        ld a,(.k)
        ld b,'+'
        bit 7,a
        jr z,.ep
        neg
        ld b,'-'
.ep:    ld c,a
        ld a,b
        ld (de),a
        inc de
        ld a,c
        ld b,'0'-1                  ; tens (k is under 40)
.et:    inc b
        sub 10
        jr nc,.et
        add a,10+'0'
        ld c,a
        ld a,b
        cp '0'
        jr z,.eu
        ld (de),a
        inc de
.eu:    ld a,c
        ld (de),a
        inc de
.out:   xor a
        ld (de),a
        ld hl,.txt
        jp bly_pr_cstr

.scale: ld a,(.u+1)                 ; .big x 2^E, E = e - 160: left, or right (a floor); whole bytes first
        sub 160
        jr c,.right
        ret z
        ld c,a
.lb:    ld a,c
        cp 8
        jr c,.lbits
        ld hl,.big+22
        ld de,.big+23
        ld b,0
        push bc
        ld bc,23
        lddr
        pop bc
        xor a
        ld (.big),a
        ld a,c
        sub 8
        ld c,a
        jr .lb
.lbits: or a
        ret z
.lft:   ld hl,.big
        or a
        ld b,24
.l1:    rl (hl)
        inc hl
        djnz .l1
        dec c
        jr nz,.lft
        ret
.right: neg
        ld c,a
.rb:    ld a,c
        cp 8
        jr c,.rbits
        ld hl,.big+1
        ld de,.big
        push bc
        ld bc,23
        ldir
        pop bc
        xor a
        ld (.big+23),a
        ld a,c
        sub 8
        ld c,a
        jr .rb
.rbits: or a
        ret z
.rgt:   ld hl,.big+23
        or a
        ld b,24
.r1:    rr (hl)
        dec hl
        djnz .r1
        dec c
        jr nz,.rgt
        ret

.mul10: ld hl,.big+23               ; .big x 10, from the bottom to one byte past its top
        ld b,24
.msk:   ld a,(hl)
        or a
        jr nz,.mgo
        dec hl
        djnz .msk
        ret                         ; 0 stays 0
.mgo:   ld a,b                      ; B = its significant bytes: one more for the carry, 24 at most
        cp 24
        jr nc,.mok
        inc b
.mok:   ld ix,.big
        ld c,0
.m1:    ld l,(ix+0)
        ld h,0
        add hl,hl
        ld e,l
        ld d,h
        add hl,hl
        add hl,hl
        add hl,de
        ld e,c
        ld d,0
        add hl,de
        ld (ix+0),l
        ld c,h
        inc ix
        djnz .m1
        ret

.div10: ld hl,.big+23               ; .big / 10, from its top nonzero byte down; A = the remainder
        ld b,24
.dsk:   ld a,(hl)
        or a
        jr nz,.dgo
        dec hl
        djnz .dsk
        ret                         ; 0: 0, remainder 0 (A is 0)
.dgo:   push hl
        pop ix
        xor a
.d1:    ld d,(ix+0)
        ld e,8
.d2:    sla d
        rla
        cp 10
        jr c,.d3
        sub 10
        inc d
.d3:    dec e
        jr nz,.d2
        ld (ix+0),d
        dec ix
        djnz .d1
        ret

.cmp4:  ld de,.big+3                ; .big's low 32 bits against the constant whose top byte is at HL: C if less
        ld b,4
.c4:    ld a,(de)
        cp (hl)
        ret nz
        dec hl
        dec de
        djnz .c4
        ret

.t9:    db 00h,0CAh,9Ah,3Bh         ; 10^9, little-endian
.t8:    db 00h,0E1h,0F5h,05h        ; 10^8
.t7:    db 80h,96h,98h,00h          ; 10^7
.u:     ds 6
.k:     db 0
.s1:    db 0
.at:    dw 0
.big:   ds 24
.dig:   ds 8
.txt:   ds 20
