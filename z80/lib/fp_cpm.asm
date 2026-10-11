;; provides: bly_fadd bly_fsub bly_fmul bly_fdiv bly_fsqrt bly_fc bly_pr_f bly_str_float bly_fk bly_fexp bly_fln
;; provides: bly_fsin bly_fcos bly_ftan bly_fatan bly_fasin bly_facos bly_fpow
;; needs: bly_fx bly_fail bly_div0 bly_i_mul16 bly_pr_cstr bly_pr_str bly_out bly_fcmp bly_fround bly_f_to_int
;; needs: bly_f_from_i16 bly_fneg bly_fabs
;; targets: cpm test
;; Floats where there's no ROM (CP/M, and the bare Z80 the tests use): the ROM's 5-byte form all the same (ABI.md
;; section 11), with our own arithmetic, correctly rounded: the nearest 5 bytes, ties away from zero, as a literal is
;; (z80gen.rom5). Held bit for bit to a model of exact Fractions.
;; bly_fadd bly_fsub bly_fmul bly_fdiv   in: HL=&a DE=&b BC=&r   out: (BC) = a op b, in the full form
;;        fails: float overflow; division by zero (/)
;; bly_fsqrt      in: HL=&x BC=&r   out: (BC) = the root, correctly rounded   fails: sqrt({x}) has no answer (x < 0)
;; bly_str_float  in: HL=&str DE=&dest   out: (DE) = the number the str starts with, its first 40 significant
;;                digits rounded exactly (so "x".float() is the literal x)
;;                fails: "{s}" doesn't start with a number; {number} doesn't fit in a float
;; bly_fexp bly_fln   in: HL=&x BC=&r   within a few units of the last place (test_fpcpm.py prints the worst)
;;                fails: exp({x}) has no answer (too big), ln({x}) has no answer (x <= 0)
;; bly_fsin bly_fcos bly_ftan bly_fatan bly_fasin bly_facos   in: HL=&x BC=&r   likewise
;;                fails: asin({x}) / acos({x}) has no answer (|x| > 1)
;; bly_fpow       in: HL=&a DE=&b BC=&r   out: (BC) = a ** b, as exp(b ln a)
;;                fails: float ** has no answer (0 ** b < 0; a < 0 with b not whole); float overflow
;; bly_pr_f       in: HL=&x   prints x as the ROM's PRINT-FP lays a number out (8 digits, .0001, 1E+10), its digits
;;                exactly rounded, through bly_out (so print's column is kept)
;; Every routine clobbers AF BC DE HL IX.
;
; The one trick: rounding x to 32 bits with ties away from zero is floor(x + 1/2) = (floor(2x) + 1) >> 1, so each
; operation needs only the floor of its exact answer to 33 bits (32 and the one that decides): no sticky bits.
; * and / get exact floors by their nature (the whole 64-bit product; restoring division). + and - work in 40 bits,
; the larger number's mantissa a byte up: bits of the smaller shifted out of the bottom can't move a floor when adding,
; and when subtracting they take exactly one more unit off (the true difference lies strictly between two integers
; there, and rounding's boundaries are integers).
; bly_fc is the shared part: .pack rounds the window (.w, its top bit set) by its bit 31 and writes the answer.
; Scratch: bly_fc's .res .flip .sg .ex .ua .ub .w.

; -- + and - ---------------------------------------------------------------------------------------------------------
; In 40 bits, in registers: |a| >= |b| (swapped if not), X = A 2^8 (A's bytes a byte up: no shifting), Z = B 2^8 >> d
; in C:H:L:D:E (d = ea - eb: whole bytes, then bits), and W = X + Z, or X - Z less one more if Z lost any bits (a sticky):
; the floor of W's exact value either way, which is all the rounding needs (the one trick). W's top 32 bits are the
; mantissa and the bit below rounds it: W >> 8 (or W >> 9 after a carry out); a difference that has shrunk shifts left
; first, exactly when it shrinks far (d is 0 or 1 then, and nothing was lost), by a bit at most otherwise. From d = 34
; on, b moves a by under a quarter of its last place, and a, even at 2^31 less a little, rounds back to a: it's a.
; (A Python model held this to fp5 on 200,000 sums and differences before it was written.)
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
        ld hl,(bly_fc.ua)           ; else swap them, a word at a time: the larger is a from here
        ld de,(bly_fc.ub)
        ld (bly_fc.ua),de
        ld (bly_fc.ub),hl
        ld hl,(bly_fc.ua+2)
        ld de,(bly_fc.ub+2)
        ld (bly_fc.ua+2),de
        ld (bly_fc.ub+2),hl
        ld hl,(bly_fc.ua+4)
        ld de,(bly_fc.ub+4)
        ld (bly_fc.ua+4),de
        ld (bly_fc.ub+4),hl
.ord:   ld a,(bly_fc.ua)            ; the answer's sign is the larger's, its exponent the larger's to start
        ld (bly_fc.sg),a
        ld a,(bly_fc.ua+1)
        ld l,a
        ld h,0
        ld (bly_fc.ex),hl
        ld hl,bly_fc.ub+1           ; d = ea - eb
        sub (hl)
        cp 34
        ld hl,bly_fc.ua
        jp nc,bly_fc.put            ; 34 or more: a
        ld b,a                      ; B = d
        ld a,(bly_fc.ub+2)          ; Z = B 2^8: C:H:L:D:E, the top first
        ld c,a
        ld a,(bly_fc.ub+3)
        ld h,a
        ld a,(bly_fc.ub+4)
        ld l,a
        ld a,(bly_fc.ub+5)
        ld d,a
        ld e,0
        xor a
        ld (.stk),a                 ; what Z loses below: none yet
        ld a,b
        cp 8
        jr c,.bits
.byte:  ld a,e                      ; a whole byte down: E goes below
        or a
        jr z,.by0
        ld a,1
        ld (.stk),a
.by0:   ld e,d
        ld d,l
        ld l,h
        ld h,c
        ld c,0
        ld a,b
        sub 8
        ld b,a
        cp 8
        jr nc,.byte
.bits:  ld a,b                      ; then d % 8 bits
        or a
        jr z,.op
.bit:   srl c
        rr h
        rr l
        rr d
        rr e
        jr nc,.bt0
        ld a,1
        ld (.stk),a
.bt0:   djnz .bit
.op:    ld a,(bly_fc.ub)            ; the same signs: W = X + Z
        ld b,a
        ld a,(bly_fc.ua)
        xor b
        jr nz,.sub
        ld a,(bly_fc.ua+5)          ; (E + 0 is E)
        add a,d
        ld d,a
        ld a,(bly_fc.ua+4)
        adc a,l
        ld l,a
        ld a,(bly_fc.ua+3)
        adc a,h
        ld h,a
        ld a,(bly_fc.ua+2)
        adc a,c
        ld c,a
        jp nc,.out                  ; under 2^40: the mantissa is W >> 8, and E's top bit rounds it
        rr c                        ; 2^40 or more: W >> 9, the carry in at the top, and the bit shifted out rounds
        rr h
        rr l
        rr d
        ld a,0
        rra
        ld e,a
        ld a,c
        ld (bly_fc.w+7),a
        ld (bly_fc.w+5),hl
        ld (bly_fc.w+3),de
        ld hl,(bly_fc.ex)           ; one more in the exponent
        inc hl
        ld (bly_fc.ex),hl
        jp bly_fc.pack
.sub:   ld a,(.stk)                 ; signs differ: W = X - Z, less one more if Z lost any bits (a - b's floor)
        rra
        ld a,0
        sbc a,e
        ld e,a
        ld a,(bly_fc.ua+5)
        sbc a,d
        ld d,a
        ld a,(bly_fc.ua+4)
        sbc a,l
        ld l,a
        ld a,(bly_fc.ua+3)
        sbc a,h
        ld h,a
        ld a,(bly_fc.ua+2)
        sbc a,c
        ld c,a
        or h                        ; nothing left: 0
        or l
        or d
        or e
        jp z,bly_fc.zero
        ld b,0                      ; normalise, counting the shifts in B: whole bytes while C is 0 (only when d is
.nby:   ld a,c                      ; 0 or 1, and W exact), then bits
        or a
        jr nz,.nbt
        ld c,h
        ld h,l
        ld l,d
        ld d,e
        ld e,0
        ld a,b
        add a,8
        ld b,a
        jr .nby
.nbt:   bit 7,c
        jr nz,.nd
        sla e
        rl d
        rl l
        rl h
        rl c
        inc b
        jr .nbt
.nd:    ld a,c
        ld (bly_fc.w+7),a
        ld (bly_fc.w+5),hl
        ld (bly_fc.w+3),de
        ld a,b                      ; the exponent less the shifts
        or a
        jp z,bly_fc.pack
        ld hl,(bly_fc.ex)
        ld e,b
        ld d,0
        sbc hl,de                   ; (carry clear: or a)
        ld (bly_fc.ex),hl
        jp bly_fc.pack
.out:   ld a,c
        ld (bly_fc.w+7),a
        ld (bly_fc.w+5),hl
        ld (bly_fc.w+3),de
        jp bly_fc.pack
.stk:   db 0

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
; Restoring division, in registers: the remainder R in HL (high word) and DE (low), D's high word in BC throughout,
; and D's low word patched into the loop's `ld bc` (self-modifying, and .dl .dh are scratch inside the
; fragment: code runs from RAM, ABI.md section 0); no alternate registers. Most bits are settled by the high words alone: R's below D's means R < D (one sbc, undone);
; above means R > D, and only then are the low words subtracted. Equal high words, rarely, compare the low ones.
; Each quotient byte grows in A behind a marker bit that rla pushes out into carry after the eighth; its bits go in
; as their complements (the undoing's carry is set exactly when the bit is 0), and cpl puts them right.
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
        ld a,(bly_fc.ub+5)          ; D's low word, into the loop's code and .dl
        ld l,a
        ld a,(bly_fc.ub+4)
        ld h,a
        ld (.lo1+1),hl
        ld (.lo2+1),hl
        ld (.dl),hl
        ld a,(bly_fc.ub+3)          ; D's high word likewise
        ld l,a
        ld a,(bly_fc.ub+2)
        ld h,a
        ld (.hi1+1),hl
        ld (.hi2+1),hl
        ld (.dh),hl
        ld a,(bly_fc.ua+5)          ; a's mantissa, A, in HL DE
        ld e,a
        ld a,(bly_fc.ua+4)
        ld d,a
        ld a,(bly_fc.ua+3)
        ld l,a
        ld a,(bly_fc.ua+2)
        ld h,a
        push hl
        push de
        ex de,hl                    ; R = A - D
        ld bc,(.dl)
        or a
        sbc hl,bc
        ex de,hl
        ld bc,(.dh)
        sbc hl,bc
        pop bc
        jr c,.less
        pop bc                      ; A >= D: A/D is in [1, 2), the quotient's top bit is 2^32's, and the exponent
        ld bc,(bly_fc.ex)           ; one up (floor(A x 2^32 / D))
        inc bc
        ld (bly_fc.ex),bc
        jr .go
.less:  ex de,hl                    ; A < D: R = 2A - D = (A - D) + A, under D, and 2A/D is in [1, 2) (floor(A x 2^33 /
        add hl,bc                   ; D))
        ex de,hl
        pop bc
        adc hl,bc
.go:    ld bc,(.dh)                 ; 32 more bits below the top one, a byte at a time, high first
        call .byte
        cpl
        ld (bly_fc.w+7),a
        call .byte
        cpl
        ld (bly_fc.w+6),a
        call .byte
        cpl
        ld (bly_fc.w+5),a
        call .byte
        cpl
        ld (bly_fc.w+4),a
        scf                         ; 33 bits, the top one 1: the mantissa is them >> 1, and the last decides
        ld hl,bly_fc.w+7
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        dec hl
        rr (hl)
        ld a,0
        rra
        ld (bly_fc.w+3),a           ; (/'s rounding bit)
        jp bly_fc.pack
.byte:  ld a,1                      ; the marker
.bit:   sla e                       ; R = 2R
        rl d
        adc hl,hl
        jr c,.big                   ; 2^32 or more: certainly at least D
        sbc hl,bc                   ; the high words (carry clear)
        jr c,.no
        jr z,.eq
        ex de,hl                    ; R's above: R > D, so the low words too
.lo1:   ld bc,0                     ; (D's low word, patched)
        sbc hl,bc                   ; (carry clear)
        ex de,hl
.hi1:   ld bc,0                     ; (D's high word, patched)
        jr nc,.one
        dec hl                      ; the low words' borrow (the high difference is at least 1)
.one0:  or a                        ; a 1, as its complement
.one:   rla
        jr nc,.bit
        ret
.no:    add hl,bc                   ; R < D: undone, and the undoing's carry out is set, a 0's complement
        rla
        jr nc,.bit
        ret
.big:   ex de,hl                    ; R - D, the 2^32 taking the borrow
.lo2:   ld bc,0                     ; (patched)
        or a
        sbc hl,bc
        ex de,hl
.hi2:   ld bc,0                     ; (patched)
        sbc hl,bc
        jr .one0
.eq:    ex de,hl                    ; the high words equal: R >= D just when R's low word is at least D's
        ld bc,(.dl)
        sbc hl,bc                   ; (carry clear)
        jr nc,.eq1
        add hl,bc                   ; less: undone, and R's high word is D's again
        ex de,hl
        ld bc,(.dh)
        add hl,bc
        scf                         ; a 0, as its complement
        jr .one
.eq1:   ex de,hl                    ; at least: R - D is the low words' difference alone (HL is already 0)
        ld bc,(.dh)
        jr .one0
.dl:    dw 0
.dh:    dw 0

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
.d1:    ld bc,(.d)                  ; d0^2 = a^2 2^32 + 2aw 2^16 + w^2, for d0 = a 2^16 + w (a is 0 to 2)
        ld de,(.d)
        call bly_i_mul16            ; DE:HL = w^2
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

; -- reading: s.float() without a ROM, exactly ------------------------------------------------------------------------
; The number is \s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)? (barley.py's FLOAT_RE). Its first 40 significant digits make
; an integer D (the rest are dropped, as fp5.read drops them), and X is the power of ten of D's last digit. Since
; 10^a = 5^a x 2^a, only fives need big arithmetic: X >= 0 is D x 5^X, its bit length giving the exponent (plus X);
; X < 0 is q = floor(D x 2^s / 5^-X), s guessed so q has 33 bits and corrected by q's size, the exponent 33 - s + X.
; Either way the 33-bit floor's last bit rounds it, ties away, as a literal is rounded: so "x".float() is the literal x.
bly_str_float:
        ld (.s),hl
        ld (bly_fc.res),de
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld c,(hl)
        inc hl
        ld b,(hl)
        ex de,hl                    ; HL = p, BC = n
        ld a,b
        or c
        jp z,.bad
.ws:    ld a,(hl)                   ; spaces, tabs, LF, VT, FF, CR first
        cp ' '
        jr z,.wsk
        sub 9
        cp 5
        jr nc,.start
.wsk:   inc hl
        dec bc
        ld a,b
        or c
        jr nz,.ws
        jp .bad
.start: ld (.st),hl
        ld (.rem),bc                ; what's left of the str, from here on in .rem
        xor a
        ld (bly_fc.sg),a
        ld (.cnt),a
        ld (.seen),a
        ld (.x),a
        ld (.x+1),a
        push hl
        ld hl,.n                    ; D = 0
        ld b,32
.nz:    ld (hl),a
        inc hl
        djnz .nz
        pop hl
        ld a,(hl)
        cp '+'
        jr z,.sign
        cp '-'
        jr nz,.whole
        ld a,80h
        ld (bly_fc.sg),a
.sign:  inc hl
        call .used
.whole: call .dig                   ; whole digits: past 40 kept, each moves X up
        jr nc,.point
        call .take
        cp 2
        jr nz,.wn
        call .xup
.wn:    inc hl
        call .used
        jr .whole
.point: call .left
        jr z,.done
        ld a,(hl)
        cp '.'
        jr nz,.done
        inc hl
        call .used
.frac:  call .dig                   ; after the point: a kept digit, or a leading zero, moves X down
        jr nc,.done
        call .take
        cp 2
        call nz,.xdn
        inc hl
        call .used
        jr .frac
.done:  ld a,(.seen)
        or a
        jp z,.bad
        call .left                  ; an exponent only if it has digits: 3east is 3
        jp z,.end
        ld a,(hl)
        or 20h
        cp 'e'
        jp nz,.end
        push hl
        ld bc,(.rem)
        push bc
        inc hl
        call .used
        call .left
        jr z,.noexp
        xor a
        ld (.eneg),a
        ld a,(hl)
        cp '+'
        jr z,.es
        cp '-'
        jr nz,.ed
        ld a,1
        ld (.eneg),a
.es:    inc hl
        call .used
.ed:    call .dig
        jr nc,.noexp
        ld de,0                     ; DE = the exponent, held at 10000 at most
.el:    push hl
        ld h,d
        ld l,e
        add hl,hl
        add hl,hl
        add hl,de
        add hl,hl                   ; x10
        ld e,a
        ld d,0
        add hl,de
        ex de,hl
        pop hl
        ld a,d                      ; past 10000: stays 10000
        cp 27h
        jr c,.ek
        ld de,10000
.ek:    inc hl
        call .used
        call .dig
        jr c,.el
        pop af                      ; it was an exponent: forget where it started
        pop af
        ld a,(.eneg)
        or a
        jr z,.eadd
        ld a,e                      ; negative: DE = -DE
        cpl
        ld e,a
        ld a,d
        cpl
        ld d,a
        inc de
.eadd:  push hl
        ld hl,(.x)
        add hl,de
        ld (.x),hl
        pop hl
        jp .end
.noexp: pop bc
        ld (.rem),bc
        pop hl
.end:   ld (.end_),hl
        ld a,(.cnt)                 ; D = 0: the answer is 0
        or a
        jp z,bly_fc.zero
        ld hl,(.x)                  ; t = digits + X: over 39 is too big; -40 or less is under 2^-129, so 0
        ld e,a
        ld d,0
        add hl,de
        bit 7,h
        jr nz,.tneg
        ld de,-40
        add hl,de
        jp c,.big_                  ; 40 or more: too big
        jr .scale
.tneg:  ld de,40
        add hl,de
        jp nc,bly_fc.zero           ; -40 or less
.scale: ld a,(.x+1)
        bit 7,a
        jp nz,.small
        ld a,(.x)                   ; X >= 0: N = D x 5^X, then its top 33 bits
        or a
        jr z,.m5d
        ld b,a
.m5:    push bc
        call .mul5
        pop bc
        djnz .m5
.m5d:   call .bits                  ; HL = N's bit length L
        push hl
        ld de,-33                   ; q = N >> (L - 33), or N << (33 - L)
        add hl,de
        call .shift
        pop hl                      ; the exponent byte: L + X + 128
        ld de,(.x)
        add hl,de
        ld de,128
        add hl,de
        ld (bly_fc.ex),hl
        jp .round
.small: ld hl,(.x)                  ; X < 0: a = -X; s's guess: 33 - L(D) + ((a * 594) >> 8) + 1
        ld a,l
        neg
        ld (.a),a
        call .bits
        ld (.ld),hl
        ld a,(.a)
        ld l,a
        ld h,0
        ld d,h
        ld e,l
        add hl,hl                   ; a * 594 = a * (512 + 64 + 16 + 2)
        ld b,h
        ld c,l                      ; 2a
        add hl,hl
        add hl,hl
        add hl,hl                   ; 16a
        push hl
        add hl,hl
        add hl,hl                   ; 64a
        push hl
        add hl,hl
        add hl,hl
        add hl,hl                   ; 512a
        pop de
        add hl,de
        pop de
        add hl,de
        add hl,bc                   ; 594a
        ld l,h
        ld h,0                      ; >> 8
        inc hl
        ld de,33
        add hl,de
        ld de,(.ld)
        or a
        sbc hl,de
        ld (.sh),hl
.try:   ld hl,.n                    ; .w2 = D, then x 2^s (a floor if s < 0), then / 5, a times
        ld de,.w2
        ld bc,32
        ldir
        ld hl,(.sh)
        ld a,h                      ; .shift shifts .w2... by -(HL): make it right by -s
        cpl
        ld h,a
        ld a,l
        cpl
        ld l,a
        inc hl
        ld ix,.w2
        call .shiftx
        ld a,(.a)
        ld b,a
.d5:    push bc
        call .div5
        pop bc
        djnz .d5
        ld ix,.w2                   ; q has 33 bits? (2^32 <= q < 2^33)
        call .bitsx
        ld de,-34
        add hl,de
        bit 7,h
        jr z,.sup                   ; 34 or more: s one less
        inc hl
        ld a,h
        or l
        jr z,.sok                   ; 33 exactly
        ld hl,(.sh)                 ; fewer: s one more
        inc hl
        ld (.sh),hl
        jr .try
.sup:   ld hl,(.sh)
        dec hl
        ld (.sh),hl
        jr .try
.sok:   ld hl,.w2                   ; q into .n for .round
        ld de,.n
        ld bc,5
        ldir
        ld hl,(.sh)                 ; the exponent byte: 33 - s + X + 128
        ex de,hl
        ld hl,161
        or a
        sbc hl,de
        ld de,(.x)
        add hl,de
        ld (bly_fc.ex),hl
.round: ld hl,.n+4                  ; q (33 bits, in .n): the mantissa is q >> 1, its last bit decides
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
        ld hl,.n
        ld de,bly_fc.w+4
        ld bc,4
        ldir
        call bly_fc.packc
        ret nc
.big_:  ld hl,(.st)                 ; {number} doesn't fit in a float
        ld (.span),hl
        ex de,hl
        ld hl,(.end_)
        or a
        sbc hl,de
        ld (.span+2),hl
        ld hl,.span
        call bly_pr_str
        ld hl,.mbig
        jp bly_fail
.bad:   ld a,'"'
        call bly_out
        ld hl,(.s)
        call bly_pr_str
        ld hl,.mno
        jp bly_fail

.used:  ld bc,(.rem)                ; one byte of the str used
        dec bc
        ld (.rem),bc
        ret
.left:  ld bc,(.rem)                ; Z if the str is used up
        ld a,b
        or c
        ret
.dig:   call .left                  ; C (and A = its value) if a digit is at HL, before the end
        ret z                       ; (OR leaves NC)
        ld a,(hl)
        sub '0'
        cp 10
        ret
.take:  ld e,a                      ; a digit, E: A = 0 a leading zero, 1 kept, 2 dropped (past 40)
        ld a,1
        ld (.seen),a
        ld a,(.cnt)
        or a
        jr nz,.t1
        ld a,e
        or a
        ret z
.t1:    ld a,(.cnt)
        cp 40
        ld a,2
        ret nc
        ld a,(.cnt)
        inc a
        ld (.cnt),a
        push hl
        ld ix,.n                    ; D = D x 10 + the digit, over 17 bytes (D < 10^40 < 2^133)
        ld b,17
        ld c,e
.t2:    push bc
        ld l,(ix+0)
        ld h,0
        add hl,hl
        ld e,l
        ld d,h
        add hl,hl
        add hl,hl
        add hl,de
        pop bc
        ld e,c
        ld d,0
        add hl,de
        ld (ix+0),l
        ld c,h
        inc ix
        djnz .t2
        pop hl
        ld a,1
        ret
.xup:   push hl                     ; X + 1
        ld hl,(.x)
        inc hl
        ld (.x),hl
        pop hl
        ret
.xdn:   push hl                     ; X - 1
        ld hl,(.x)
        dec hl
        ld (.x),hl
        pop hl
        ret

.mul5:  ld hl,.n+31                 ; .n x 5, from the bottom to one byte past its top
        ld b,32
.fsk:   ld a,(hl)
        or a
        jr nz,.fgo
        dec hl
        djnz .fsk
        ret
.fgo:   ld a,b
        cp 32
        jr nc,.fok
        inc b
.fok:   ld ix,.n
        ld c,0
.f1:    ld l,(ix+0)
        ld h,0
        ld d,h
        ld e,l
        add hl,hl
        add hl,hl
        add hl,de
        ld e,c
        ld d,0
        add hl,de
        ld (ix+0),l
        ld c,h
        inc ix
        djnz .f1
        ret
.div5:  ld hl,.w2+31                ; .w2 / 5, from its top nonzero byte down: nested floors are exact
        ld b,32
.vsk:   ld a,(hl)
        or a
        jr nz,.vgo
        dec hl
        djnz .vsk
        ret
.vgo:   push hl
        pop ix
        xor a
.v1:    ld d,(ix+0)
        ld e,8
.v2:    sla d
        rla
        cp 5
        jr c,.v3
        sub 5
        inc d
.v3:    dec e
        jr nz,.v2
        ld (ix+0),d
        dec ix
        djnz .v1
        ret
.bits:  ld ix,.n                    ; HL = the bit length of the 32 bytes at IX (.n, or .w2 by .bitsx)
.bitsx: push ix
        pop hl
        ld de,31
        add hl,de
        ld b,32
.b1:    ld a,(hl)
        or a
        jr nz,.b2
        dec hl
        djnz .b1
        ld hl,0
        ret
.b2:    ld c,0                      ; B = the top byte's index + 1; bits = 8 * (B - 1) + that byte's length
.b3:    inc c
        srl a
        jr nz,.b3
        ld l,b
        ld h,0
        dec hl
        add hl,hl
        add hl,hl
        add hl,hl
        ld e,c
        ld d,0
        add hl,de
        ret
.shift: ld ix,.n                    ; the 32 bytes at IX shifted right by HL (left if HL is negative): whole
.shiftx:                            ; bytes, then bits; right is a floor
        bit 7,h
        jr nz,.sl
.sr:    ld a,h
        or a
        jr nz,.srb
        ld a,l
        cp 8
        jr c,.srbits
.srb:   push hl
        push ix
        pop hl
        ld d,h
        ld e,l
        inc hl
        ld bc,31
        ldir
        xor a
        ld (de),a
        pop hl
        ld de,-8
        add hl,de
        jr .sr
.srbits:
        or a
        ret z
        ld c,a
.sr1:   push ix
        pop hl
        ld de,31
        add hl,de
        or a
        ld b,32
.sr2:   rr (hl)
        dec hl
        djnz .sr2
        dec c
        jr nz,.sr1
        ret
.sl:    ld a,l                      ; left by -HL
        neg
        ld l,a
        ld h,0
.slb:   ld a,l
        cp 8
        jr c,.slbits
        push hl
        push ix
        pop hl
        ld de,30
        add hl,de
        ld d,h
        ld e,l
        inc de
        ld bc,31
        lddr
        xor a
        ld (de),a
        pop hl
        ld a,l
        sub 8
        ld l,a
        jr .slb
.slbits:
        or a
        ret z
        ld c,a
.sl1:   push ix
        pop hl
        or a
        ld b,32
.sl2:   rl (hl)
        inc hl
        djnz .sl2
        dec c
        jr nz,.sl1
        ret

.mno:   db 34," doesn't start with a number",0
.mbig:  db " doesn't fit in a float",0
.s:     dw 0
.st:    dw 0
.end_:  dw 0
.rem:   dw 0
.x:     dw 0
.sh:    dw 0
.ld:    dw 0
.a:     db 0
.cnt:   db 0
.seen:  db 0
.eneg:  db 0
.span:  dw 0,0
.n:     ds 32
.w2:    ds 32

; -- the functions: scripts for a small calculator over our own + - * /, as the ROM's are ---------------------------
; A script is bytes: 1 add, 2 sub, 3 mul, 4 div (the top two: a op b), 5 dup, 6 swap, 7 drop, 8 + an address (push
; the 5 bytes there), 9 i (push memory i), 10 i (store the top in memory i, keeping it), 11 n + an address (Horner:
; the top x becomes c0 x^n + ... + cn, the n + 1 constants there highest first), 12 neg, 0 end. Each function does
; its range reduction around a script or two. 13 is sqrt. The constants are exact rationals rounded once (coeffs.py).
bly_fk:
.reset: ld hl,.stk-5                ; an empty stack
        ld (.top),hl
        ret
.run:   ld (.pc),hl                 ; HL = a script
.nx:    ld hl,(.pc)
        ld a,(hl)
        inc hl
        ld (.pc),hl
        or a
        ret z
        cp 5
        jp c,.ar
        cp 8
        jp c,.st
        jp z,.push
        cp 10
        jp c,.ldm
        jp z,.stm
        cp 11
        jp z,.poly
        cp 12
        jp nz,.sqrt
        ld hl,(.top)                ; 12: neg
        ld b,h
        ld c,l
        call bly_fneg
        jp .nx
.sqrt:  ld hl,(.top)                ; 13: sqrt
        ld b,h
        ld c,l
        call bly_fsqrt
        jp .nx
.ar:    ld hl,(.top)                ; a op b: b on top, a below, the answer into a's slot
        ld d,h
        ld e,l
        ld bc,-5
        add hl,bc
        ld (.top),hl
        ld b,h
        ld c,l
        dec a
        jp z,.add
        dec a
        jp z,.sub
        dec a
        jp z,.mul
        call bly_fdiv
        jp .nx
.add:   call bly_fadd
        jp .nx
.sub:   call bly_fsub
        jp .nx
.mul:   call bly_fmul
        jp .nx
.st:    ld hl,(.top)                ; 5 dup, 6 swap, 7 drop
        cp 6
        jp z,.swap
        jp nc,.drop
        ld d,h                      ; dup
        ld e,l
        inc de
        inc de
        inc de
        inc de
        inc de
        push de
        ld bc,5
        ldir
        pop hl
        ld (.top),hl
        jp .nx
.swap:  ld d,h
        ld e,l
        ld bc,-5
        add hl,bc
        ld b,5
.sw:    ld a,(de)
        ld c,(hl)
        ld (hl),a
        ld a,c
        ld (de),a
        inc hl
        inc de
        djnz .sw
        jp .nx
.drop:  ld bc,-5
        add hl,bc
        ld (.top),hl
        jp .nx
.push:  call .addr                  ; 8: push the 5 bytes at an address
.push5: ld de,(.top)                ; HL = where they are
        inc de
        inc de
        inc de
        inc de
        inc de
        ld (.top),de
        ld bc,5
        ldir
        jp .nx
.ldm:   call .mem                   ; 9 i
        jp .push5
.stm:   call .mem                   ; 10 i
        ex de,hl
        ld hl,(.top)
        ld bc,5
        ldir
        jp .nx
.poly:  ld hl,(.pc)                 ; 11 n addr: the top is x
        ld a,(hl)
        ld (.n),a
        inc hl
        ld (.pc),hl
        call .addr
        ld (.c),hl
        ld hl,(.top)                ; x aside; the top becomes c0
        ld de,.px
        ld bc,5
        ldir
        ld hl,(.c)
        ld de,(.top)
        ld bc,5
        ldir
.pl:    ld hl,(.c)                  ; acc = acc x + the next constant
        ld de,5
        add hl,de
        ld (.c),hl
        ld hl,(.top)
        ld de,.px
        ld b,h
        ld c,l
        call bly_fmul
        ld hl,(.top)
        ld de,(.c)
        ld b,h
        ld c,l
        call bly_fadd
        ld hl,.n
        dec (hl)
        jp nz,.pl
        jp .nx
.addr:  ld hl,(.pc)                 ; the address that follows in the script, into HL
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld (.pc),hl
        ex de,hl
        ret
.mem:   ld hl,(.pc)                 ; the memory whose number follows, its address into HL
        ld a,(hl)
        inc hl
        ld (.pc),hl
        ld l,a
        ld h,0
        ld d,h
        ld e,l
        add hl,hl
        add hl,hl
        add hl,de
        ld de,.m
        add hl,de
        ret
.out:   ld hl,(.top)                ; the top to (.r)
        ld de,(.r)
        ld bc,5
        ldir
        ret
.no:    push de                     ; HL = the function's name, DE = &x: {name}({x}) has no answer
        call bly_pr_cstr
        ld a,'('
        call bly_out
        pop hl
        call bly_pr_f
        ld hl,.mno
        jp bly_fail
.mno:   db ") has no answer",0
.pc:    dw 0
.top:   dw 0
.r:     dw 0
.c:     dw 0
.n:     db 0
.px:    ds 5
.m:     ds 20                       ; four memories
.stk:   ds 40                       ; eight slots
.ln2hi:  db 80h,31h,72h,18h,00h         ; ln 2, 24 bits: k x it is exact
.ln2lo:  db 64h,82h,0E3h,08h,65h        ; the rest of ln 2
.rln2:   db 81h,38h,0AAh,3Bh,29h        ; 1 / ln 2
.pi2hi:  db 81h,49h,0Fh,0DBh,00h        ; pi/2, 24 bits
.pi2lo:  db 68h,0BBh,0BDh,2Eh,7Ch       ; the rest of pi/2
.rpi2:   db 80h,22h,0F9h,83h,6Eh        ; 2 / pi
.pi2:    db 81h,49h,0Fh,0DAh,0A2h       ; pi/2
.pi6:    db 80h,06h,0Ah,91h,0C1h        ; pi/6
.sqrt3:  db 81h,5Dh,0B3h,0D7h,43h       ; sqrt 3
.tan12:  db 7Fh,09h,30h,0A2h,0F5h       ; tan(pi/12)
.half:   db 80h,00h,00h,00h,00h         ; 0.5
.one:    db 81h,00h,00h,00h,00h         ; 1
.two:    db 82h,00h,00h,00h,00h         ; 2
.rt2:    db 80h,35h,04h,0F3h,34h        ; sqrt(1/2)
.expmax: db 87h,30h,0Fh,33h,0C8h        ; ln of the biggest float
.expmin: db 87h,0B2h,0D4h,0FCh,28h      ; ln 2^-129: below, exp is 0
; exp: 1/n!, n = 11 down to 0 (Horner)
.e11:    db 67h,57h,32h,2Bh,40h         ; 2.50521083854e-08
.e10:    db 6Bh,13h,0F2h,7Dh,0BCh       ; 2.7557319224e-07
.e9:     db 6Eh,38h,0EFh,1Dh,2Bh        ; 2.7557319224e-06
.e8:     db 71h,50h,0Dh,00h,0D0h        ; 2.48015873016e-05
.e7:     db 74h,50h,0Dh,00h,0D0h        ; 0.000198412698413
.e6:     db 77h,36h,0Bh,60h,0B6h        ; 0.00138888888889
.e5:     db 7Ah,08h,88h,88h,89h         ; 0.00833333333333
.e4:     db 7Ch,2Ah,0AAh,0AAh,0ABh      ; 0.0416666666667
.e3:     db 7Eh,2Ah,0AAh,0AAh,0ABh      ; 0.166666666667
.e2:     db 80h,00h,00h,00h,00h         ; 0.5
.e1:     db 81h,00h,00h,00h,00h         ; 1
.e0:     db 81h,00h,00h,00h,00h         ; 1
; ln: the atanh series in u = t^2: 1/(2k+1), k = 6 down to 0
.l6:     db 7Dh,1Dh,89h,0D8h,9Eh        ; 0.0769230769231
.l5:     db 7Dh,3Ah,2Eh,8Bh,0A3h        ; 0.0909090909091
.l4:     db 7Dh,63h,8Eh,38h,0E4h        ; 0.111111111111
.l3:     db 7Eh,12h,49h,24h,92h         ; 0.142857142857
.l2:     db 7Eh,4Ch,0CCh,0CCh,0CDh      ; 0.2
.l1:     db 7Fh,2Ah,0AAh,0AAh,0ABh      ; 0.333333333333
.l0:     db 81h,00h,00h,00h,00h         ; 1
; sin: (-1)^k / (2k+1)!, k = 6 down to 0, in u = r^2
.s6:     db 60h,30h,92h,30h,9Dh         ; 1.60590438368e-10
.s5:     db 67h,0D7h,32h,2Bh,40h        ; -2.50521083854e-08
.s4:     db 6Eh,38h,0EFh,1Dh,2Bh        ; 2.7557319224e-06
.s3:     db 74h,0D0h,0Dh,00h,0D0h       ; -0.000198412698413
.s2:     db 7Ah,08h,88h,88h,89h         ; 0.00833333333333
.s1:     db 7Eh,0AAh,0AAh,0AAh,0ABh     ; -0.166666666667
.s0:     db 81h,00h,00h,00h,00h         ; 1
; cos: (-1)^k / (2k)!, k = 7 down to 0, in u = r^2
.c7:     db 5Ch,0C9h,0CBh,0A5h,46h      ; -1.14707455977e-11
.c6:     db 64h,0Fh,76h,0C7h,80h        ; 2.08767569879e-09
.c5:     db 6Bh,93h,0F2h,7Dh,0BCh       ; -2.7557319224e-07
.c4:     db 71h,50h,0Dh,00h,0D0h        ; 2.48015873016e-05
.c3:     db 77h,0B6h,0Bh,60h,0B6h       ; -0.00138888888889
.c2:     db 7Ch,2Ah,0AAh,0AAh,0ABh      ; 0.0416666666667
.c1:     db 80h,80h,00h,00h,00h         ; -0.5
.c0:     db 81h,00h,00h,00h,00h         ; 1
; atan: (-1)^k / (2k+1), k = 9 down to 0, in u = y^2
.a9:     db 7Ch,0D7h,94h,35h,0E5h       ; -0.0526315789474
.a8:     db 7Ch,70h,0F0h,0F0h,0F1h      ; 0.0588235294118
.a7:     db 7Dh,88h,88h,88h,89h         ; -0.0666666666667
.a6:     db 7Dh,1Dh,89h,0D8h,9Eh        ; 0.0769230769231
.a5:     db 7Dh,0BAh,2Eh,8Bh,0A3h       ; -0.0909090909091
.a4:     db 7Dh,63h,8Eh,38h,0E4h        ; 0.111111111111
.a3:     db 7Eh,92h,49h,24h,92h         ; -0.142857142857
.a2:     db 7Eh,4Ch,0CCh,0CCh,0CDh      ; 0.2
.a1:     db 7Fh,0AAh,0AAh,0AAh,0ABh     ; -0.333333333333
.a0:     db 81h,00h,00h,00h,00h         ; 1

; exp: x past ln(the biggest float) has no answer; under ln 2^-129 it's 0. k = round(x / ln 2), r = x - k ln 2 (ln 2 in
; two parts, the first so short that k times it is exact), e^r by its Taylor terms (|r| <= ln2/2: to r^11), and 2^k
; straight into the exponent byte.
bly_fexp:
        ld (.x),hl
        ld (bly_fk.r),bc
        call .core
        ret nc
        ld hl,.name
        ld de,(.x)
        jp bly_fk.no
.core:  ld de,bly_fk.expmax         ; (.x) -> (bly_fk.r); C if too big, as ** wants it
        ld hl,(.x)
        call bly_fcmp
        dec a
        scf
        ret z                       ; past the biggest
        ld hl,(.x)
        ld de,bly_fk.expmin
        call bly_fcmp
        inc a
        jr nz,.go
        ld hl,(bly_fk.r)            ; under: 0
        ld b,5
.z:     ld (hl),a
        inc hl
        djnz .z
        or a
        ret
.go:    ld hl,(.x)
        ld de,bly_fk.m
        ld bc,5
        ldir
        call bly_fk.reset
        ld hl,.s1                   ; x / ln 2
        call bly_fk.run
        ld hl,(bly_fk.top)          ; rounded: n, a float, into memory 1, and k, its int
        ld b,h
        ld c,l
        call bly_fround
        ld hl,(bly_fk.top)
        ld de,bly_fk.m+5
        ld bc,5
        ldir
        ld hl,(bly_fk.top)
        ld a,2
        ld de,.k
        call bly_f_to_int
        call bly_fk.reset
        ld hl,.s2                   ; r, then e^r
        call bly_fk.run
        ld hl,(bly_fk.top)          ; times 2^k: k added to the exponent byte
        ld e,(hl)
        ld d,0
        push hl
        ld hl,(.k)
        add hl,de
        ex de,hl
        pop hl
        ld a,d
        or a
        jr nz,.range
        ld a,e
        or a
        jr z,.under
        ld (hl),a
        call bly_fk.out
        or a
        ret
.range: bit 7,d
        scf
        ret z                       ; too big
.under: ld hl,(bly_fk.r)
        ld b,5
        xor a
.u:     ld (hl),a
        inc hl
        djnz .u
        ret
.s1:    db 9,0,8
        dw bly_fk.rln2
        db 3,0
.s2:    db 9,0,9,1,8
        dw bly_fk.ln2hi
        db 3,2,9,1,8
        dw bly_fk.ln2lo
        db 3,2,11,11
        dw bly_fk.e11
        db 0
.x:     dw 0
.k:     dw 0
.name:  db "exp",0

; ln: x <= 0 has no answer. x = 2^k m with m in [sqrt(1/2), sqrt 2); t = (m - 1) / (m + 1); ln m = 2t(1 + t^2/3 +
; ... + t^12/13); ln x = (ln m + k ln2lo) + k ln2hi, the big part last.
bly_fln:
        ld (.x),hl
        ld (bly_fk.r),bc
        ld de,.u
        call bly_fx.unpack
        ld a,(.u+1)
        or a
        jr z,.no                    ; 0
        ld a,(.u)
        or a
        jr z,.pos                   ; negative
.no:    ld hl,.name
        ld de,(.x)
        jp bly_fk.no
.pos:   ld hl,.u+2                  ; m < sqrt(1/2)? (its mantissa against B504F334, sqrt(1/2)'s)
        ld de,.rt
        ld b,4
.c:     ld a,(de)
        cp (hl)
        jr nz,.cd
        inc hl
        inc de
        djnz .c
.cd:    ld a,128                    ; m's exponent byte: 128, or 129 (m doubled) when it's under
        jr c,.big                   ; (C: sqrt(1/2)'s byte < m's: m is the bigger)
        jr z,.big
        inc a
.big:   ld (bly_fk.m),a             ; memory 0 = m, memory 1 = k = e - that byte
        ld c,a
        ld a,(.u+2)
        and 7Fh
        ld (bly_fk.m+1),a
        ld hl,.u+3
        ld de,bly_fk.m+2
        ld a,c
        ld bc,3
        ldir
        ld c,a
        ld a,(.u+1)
        ld l,a
        ld h,0
        ld b,0
        or a
        sbc hl,bc
        ld bc,bly_fk.m+5
        call bly_f_from_i16
        call bly_fk.reset
        ld hl,.s
        call bly_fk.run
        jp bly_fk.out
.s:     db 9,0,8
        dw bly_fk.one
        db 2,9,0,8
        dw bly_fk.one
        db 1,4,10,2,5,3,11,6
        dw bly_fk.l6
        db 9,2,3,8
        dw bly_fk.two
        db 3,9,1,8
        dw bly_fk.ln2lo
        db 3,1,9,1,8
        dw bly_fk.ln2hi
        db 3,1,0
.rt:    db 0B5h,04h,0F3h,34h        ; sqrt(1/2)'s mantissa, its top bit set
.x:     dw 0
.u:     ds 6
.name:  db "ln",0

; sin, cos, tan: n = round(x / (pi/2)), r = x - n pi2hi - n pi2lo (pi/2 in two parts); n mod 4 (from bly_fx.toint:
; exact under 2^64, and past it n is a multiple of 4) picks sin r or cos r and the sign. cos is sin a quarter on.
bly_fsin:
        xor a
        jp bly_ftan.go
bly_fcos:
        ld a,1
        jp bly_ftan.go
bly_ftan:
        ld a,4                      ; 4: tan
.go:    ld (.q0),a
        ld (.x),hl
        ld (bly_fk.r),bc
        ld de,bly_fk.m
        ld bc,5
        ldir
        call bly_fk.reset
        ld hl,.s1                   ; n = round(x 2/pi) into memory 1
        call bly_fk.run
        ld hl,(bly_fk.top)
        ld b,h
        ld c,l
        call bly_fround
        ld hl,(bly_fk.top)
        ld de,bly_fk.m+5
        ld bc,5
        ldir
        ld hl,bly_fk.m+5            ; q = n mod 4
        call bly_fx.toint
        ld a,(bly_fx.mag)
        and 3
        ld b,a
        ld a,(bly_fx.neg)
        or a
        ld a,b
        jp z,.qp
        neg
        and 3
.qp:    ld (.q),a
        call bly_fk.reset
        ld hl,.s2                   ; r into memory 2
        call bly_fk.run
        ld a,(.q0)
        cp 4
        jp z,.tan
        ld hl,.q
        add a,(hl)
        and 3
        ld (.q),a
        rra                         ; odd: cos r, even: sin r
        ld hl,.ss
        jp nc,.f
        ld hl,.sc
.f:     call bly_fk.run
        ld a,(.q)                   ; 2 and 3: the other sign
        and 2
        jp z,bly_fk.out
        ld hl,.sn
        call bly_fk.run
        jp bly_fk.out
.tan:   ld hl,.ss                   ; sin r, then cos r, on the stack
        call bly_fk.run
        ld hl,.sc
        call bly_fk.run
        ld a,(.q)                   ; even: sin / cos; odd: -cos / sin
        rra
        ld hl,.sd
        jp nc,.t
        ld hl,.sdi
.t:     call bly_fk.run
        jp bly_fk.out
.s1:    db 9,0,8
        dw bly_fk.rpi2
        db 3,0
.s2:    db 9,0,9,1,8
        dw bly_fk.pi2hi
        db 3,2,9,1,8
        dw bly_fk.pi2lo
        db 3,2,10,2,7,0
.ss:    db 9,2,5,3,11,6             ; sin r = r (1 - r^2/3! + ... )
        dw bly_fk.s6
        db 9,2,3,0
.sc:    db 9,2,5,3,11,7             ; cos r = 1 - r^2/2! + ...
        dw bly_fk.c7
        db 0
.sn:    db 12,0
.sd:    db 4,0
.sdi:   db 6,4,12,0
.x:     dw 0
.q0:    db 0
.q:     db 0

; atan: |x| > 1 through 1/x (then pi/2 less), past tan(pi/12) through (y sqrt3 - 1)/(y + sqrt3) (then pi/6 more), and
; the series y(1 - y^2/3 + ...) to y^19; the sign last. asin x = atan(x / sqrt(1 - x^2)), +-1 exactly +-pi/2;
; acos = pi/2 - asin. Past 1, asin and acos have no answer.
bly_fatan:
        ld (bly_fk.r),bc
        ld (.x),hl
        ld bc,bly_fk.m              ; memory 0 = |x|
        call bly_fabs
        xor a
        ld (.inv),a
        ld (.far),a
        ld hl,bly_fk.m
        ld de,bly_fk.one
        call bly_fcmp
        dec a
        jp nz,.le1
        ld (.inv),a                 ; (A is 0 here: set it to 1)
        ld hl,.inv
        inc (hl)
        call bly_fk.reset
        ld hl,.sinv
        call bly_fk.run
.le1:   ld hl,bly_fk.m
        ld de,bly_fk.tan12
        call bly_fcmp
        dec a
        jp nz,.near
        ld a,1
        ld (.far),a
        call bly_fk.reset
        ld hl,.sfar
        call bly_fk.run
.near:  call bly_fk.reset
        ld hl,.sser
        call bly_fk.run
        ld a,(.far)
        or a
        ld hl,.spi6
        call nz,bly_fk.run
        ld a,(.inv)
        or a
        ld hl,.spi2
        call nz,bly_fk.run
        ld hl,(.x)                  ; negative x: negative answer
        inc hl
        bit 7,(hl)
        jp z,bly_fk.out
        ld hl,.sneg
        call bly_fk.run
        jp bly_fk.out
.sinv:  db 8
        dw bly_fk.one
        db 9,0,4,10,0,0
.sfar:  db 9,0,8
        dw bly_fk.sqrt3
        db 3,8
        dw bly_fk.one
        db 2,9,0,8
        dw bly_fk.sqrt3
        db 1,4,10,0,0
.sser:  db 9,0,5,3,11,9
        dw bly_fk.a9
        db 9,0,3,0
.spi6:  db 8
        dw bly_fk.pi6
        db 1,0
.spi2:  db 8
        dw bly_fk.pi2
        db 6,2,0
.sneg:  db 12,0
.x:     dw 0
.inv:   db 0
.far:   db 0

bly_fasin:
        ld (.x),hl
        ld (.r),bc
        ld de,.name
        call .check                 ; |x| > 1: no answer; |x| = 1: +-pi/2
        ret c
        call bly_fk.reset           ; y = x / sqrt(1 - x^2), then atan y
        ld hl,(.x)
        ld de,bly_fk.m
        ld bc,5
        ldir
        ld hl,.sy
        call bly_fk.run
        ld hl,(bly_fk.top)
        ld de,.y
        ld bc,5
        ldir
        ld hl,.y
        ld bc,(.r)
        jp bly_fatan
.check: push de                     ; C if done: |x| = 1 gives +-pi/2 at (.r); past 1 fails with the name at DE
        ld hl,(.x)
        ld bc,.y
        call bly_fabs
        ld hl,.y
        ld de,bly_fk.one
        call bly_fcmp
        pop de
        dec a
        jp z,.no
        inc a
        jp z,.one
        or a
        ret
.no:    ex de,hl
        ld de,(.x)
        jp bly_fk.no
.one:   ld hl,bly_fk.pi2            ; +-pi/2
        ld de,(.r)
        ld bc,5
        ldir
        ld hl,(.x)
        inc hl
        bit 7,(hl)
        scf
        ret z
        ld hl,(.r)
        ld b,h
        ld c,l
        call bly_fneg
        scf
        ret
.sy:    db 9,0,5,3,8
        dw bly_fk.one
        db 6,2,13,9,0,6,4,0
.x:     dw 0
.r:     dw 0
.y:     ds 5
.name:  db "asin",0

bly_facos:
        ld (bly_fasin.x),hl
        ld (.r),bc
        ld (bly_fasin.r),bc
        ld de,.name
        call bly_fasin.check
        jp c,.one
        ld hl,(bly_fasin.x)         ; asin, into .a; then pi/2 - it
        ld bc,.a
        call bly_fasin
        call bly_fk.reset
        ld hl,.s
        call bly_fk.run
        ld hl,(.r)
        ld (bly_fk.r),hl
        jp bly_fk.out
.one:   ld hl,(.r)                  ; asin was +-pi/2 there: acos is pi/2 less it
        ld de,.a
        ld bc,5
        ldir
        call bly_fk.reset
        ld hl,.s
        call bly_fk.run
        ld hl,(.r)
        ld (bly_fk.r),hl
        jp bly_fk.out
.s:     db 8
        dw bly_fk.pi2
        db 8
        dw .a
        db 2,0
.r:     dw 0
.a:     ds 5
.name:  db "acos",0

; **: 0 ** b is 1 for b = 0, 0 for b > 0, and has no answer for b < 0; a negative a needs a whole b (an odd one
; negates); else exp(b ln a), too big being float overflow, as the 48K's ** says. (fp.asm's ** has the same rules
; around the ROM's to-power; one day a shared wrapper in fp_exact.asm.)
bly_fpow:
        ld (.a),hl
        ld (.b),de
        ld (.r),bc
        call bly_fx.zero
        jp nz,.nz
        ld hl,(.b)                  ; 0 ** b
        call bly_fx.zero
        jp z,.one
        inc hl
        bit 7,(hl)
        jp nz,.no
        ld hl,(.r)
        ld b,5
        xor a
.z:     ld (hl),a
        inc hl
        djnz .z
        ret
.one:   ld hl,bly_fk.one
        ld de,(.r)
        ld bc,5
        ldir
        ret
.nz:    xor a
        ld (.odd),a
        ld hl,(.a)
        inc hl
        bit 7,(hl)
        jp z,.pos
        ld hl,(.b)                  ; a < 0: b whole, and odd or even
        call bly_fx.toint
        ld a,(bly_fx.fr)
        or a
        jp nz,.no
        ld a,(bly_fx.big)
        or a
        ld a,(bly_fx.mag)
        jp z,.par
        xor a
.par:   and 1
        ld (.odd),a
        ld hl,(.a)
        ld bc,.abs
        call bly_fabs
        ld hl,.abs
        ld (.a),hl
.pos:   ld hl,(.a)                  ; exp(b ln a)
        ld bc,.t
        call bly_fln
        ld hl,.t
        ld de,(.b)
        ld bc,.t
        call bly_fmul
        ld hl,(.r)
        ld (bly_fk.r),hl
        ld hl,.t
        ld (bly_fexp.x),hl
        call bly_fexp.core
        jp c,.ovf
        ld a,(.odd)
        or a
        ret z
        ld hl,(.r)
        ld b,h
        ld c,l
        jp bly_fneg
.ovf:   ld hl,bly_fc.movf
        jp bly_fail
.no:    ld hl,.mno
        jp bly_fail
.mno:   db "float ** has no answer",0
.a:     dw 0
.b:     dw 0
.r:     dw 0
.odd:   db 0
.abs:   ds 5
.t:     ds 5

; -- the shared part ------------------------------------------------------------------------------------------------
bly_fc:
.both:  ld (.res),bc                ; HL=&a DE=&b BC=&r: unpack both into .ua and .ub
        push de
        ld de,.ua
        call bly_fx.unpack
        pop hl
        ld de,.ub
        jp bly_fx.unpack

.pack:  call .packc                 ; as .packc, and too big is float overflow
        ret nc
        ld hl,.movf
        jp bly_fail
.packc: ld a,(.w+3)                 ; .w's top bit set, .ex its exponent byte (biased, 16 bits), .sg the sign:
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
        jr z,.zero                  ; under 2^-128: 0, as the ROM's (and NC, as a written answer)
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
        scf                         ; too big: C, and nothing written
        ret

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
.ex:    dw 0
.ua:    ds 6
.ub:    ds 6
.w:     ds 8
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
