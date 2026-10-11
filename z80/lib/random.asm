;; provides: bly_rand16 bly_random_u16 bly_random_i16 bly_random_q bly_randomize_q bly_random_none
;; needs: bly_pr_cstr bly_pr_i16 bly_pr_i64 bly_fail
;; targets: cpm zx48 test
;; bly_rand16       out: HL = the next 16 bits                                             clobbers: AF BC DE HL
;; bly_random_u16   in: HL = n (a word)   out: HL = 0..n-1   fails: random(0) has nothing to choose from
;;                                                                                         clobbers: AF BC DE HL
;; bly_random_i16   in: HL = n (an int)   as bly_random_u16, failing for n of 0 or less     clobbers: AF BC DE HL
;; bly_random_q     in: HL = &n (a quad) BC = &dest (a quad)   (BC) = 0..n-1   fails as above   clobbers: AF BC DE HL IX
;; bly_randomize_q  in: HL = &n (a quad)   the state randomize(n) gives                    clobbers: AF DE HL
;; bly_random_none  (internal: the failure's words, after "random(" and n)
;
; Melissa's chaotic generator (her prng-test.cpp, -s), which came from Z80 assembler in the first place: barley.py's
; rng_ functions are its meaning, and z80/tests/test_random.py holds this to them. The state is BCDE, which each
; step permutes with four byte swizzles (each one invertible, so the whole is a permutation of the 2^32 states),
; and HL, which the new BC and DE feed: HL += BC, L ^= H, HL += DE, and HL is the output. randomize(n) puts n's low
; 36 bits in: 16 in HL, 20 in BCDE as 48300000h | (20 bits), every one of which is inside a run of states lying on
; the permutation's two long cycles (3,244,470,814 and 1,050,471,109; Melissa's cycle map). Until a program
; seeds it, it's as randomize(0).
;
; random(n) draws 1, 2 or 4 words a try, as n - 1 needs 16, 32 or 64 bits (by its value, not its type, so every
; backend draws the same), the first the most significant, masks them to n - 1's bits, and keeps them if they're
; below n: fewer than two tries on average, and no bias.

bly_rand16:
        ld bc,(.s+2)                ; B C: BCDE's high half
        ld de,(.s)                  ; D E: its low half
        ld a,b                      ; D = rlca(B) xor D
        rlca
        xor d
        ld d,a
        rlca                        ; C = rlca(D) + C
        add a,c
        ld c,a
        rrca                        ; E = rrca3(C) xor E
        rrca
        rrca
        xor e
        ld e,a
        rrca                        ; B = rrca(E) - B
        sub b
        ld b,a
        ld (.s+2),bc
        ld (.s),de
        ld hl,(.h)                  ; HL += BC, L ^= H, HL += DE
        add hl,bc
        ld a,l
        xor h
        ld l,a
        add hl,de
        ld (.h),hl
        ret
.s:     dd 48300000h
.h:     dw 0

bly_random_i16:                     ; HL = n, an int: none of 0 or less
        bit 7,h
        jr z,bly_random_u16
        push hl
        ld hl,bly_random_none.pre
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        jp bly_random_none
bly_random_u16:                     ; HL = n, a word
        ld a,h
        or l
        jr nz,.some
        ld hl,bly_random_none.zero
        jp bly_fail
.some:  dec hl
        ld (.m),hl                  ; m = n - 1
        ld de,0
.grow:  ld a,d                      ; the mask: 0, 1, 3, 7... until it covers m
        cp h
        jr c,.more
        jr nz,.draw0
        ld a,e
        cp l
        jr nc,.draw0
.more:  scf
        rl e
        rl d
        jr .grow
.draw0: ld (.mask),de
.draw:  call bly_rand16
        ld de,(.mask)
        ld a,h
        and d
        ld h,a
        ld a,l
        and e
        ld l,a                      ; HL = the word, masked
        ld de,(.m)
        ex de,hl
        or a
        sbc hl,de                   ; m - it: a borrow means it's past m
        ex de,hl
        jr c,.draw
        ret
.m:     dw 0
.mask:  dw 0

bly_random_q:                       ; HL = &n, BC = &dest: quads
        ld (.dst),bc
        ld (.n),hl
        ld de,7
        add hl,de
        bit 7,(hl)
        jp nz,.none                 ; below 0
        ld hl,(.n)
        ld de,.m
        ld b,8
        scf
.dec:   ld a,(hl)                   ; m = n - 1
        sbc a,0
        ld (de),a
        inc hl
        inc de
        djnz .dec
        jp c,.none                  ; n was 0
        ld hl,.m+7                  ; m's top byte that isn't 0: B = its index + 1 (0 if m is 0)
        ld b,8
.top:   ld a,(hl)
        or a
        jr nz,.found
        dec hl
        djnz .top
.found: ld a,b
        ld c,1                      ; how many words a try: 1 up to 2 bytes, 2 up to 4, else 4
        cp 3
        jr c,.kset
        ld c,2
        cp 5
        jr c,.kset
        ld c,4
.kset:  ld a,c
        ld (.k),a
        ld a,b                      ; the top byte, smeared: every bit below its highest set
        or a
        jr z,.smear
        ld hl,.m-1
        ld e,b
        ld d,0
        add hl,de
        ld a,(hl)
.smear: ld c,a
        srl a
        or c
        ld c,a
        srl a
        srl a
        or c
        ld c,a
        srl a
        srl a
        srl a
        srl a
        or c
        ld c,a                      ; C = the mask's top byte
        ld hl,.mask                 ; FFh below the top byte, C at it, 0 above
        ld e,8
.mf:    ld a,b
        or a
        jr z,.mz
        dec b
        jr z,.mt
        ld (hl),0FFh
        jr .mn
.mt:    ld (hl),c
        jr .mn
.mz:    ld (hl),0
.mn:    inc hl
        dec e
        jr nz,.mf
.try:   ld hl,.v                    ; v = 0, then the words, the first at the top
        ld b,8
        xor a
.zero:  ld (hl),a
        inc hl
        djnz .zero
        ld a,(.k)
.word:  push af
        call bly_rand16
        pop af
        push af
        dec a
        add a,a
        ld e,a
        ld d,0
        ld ix,.v
        add ix,de
        ld (ix+0),l
        ld (ix+1),h
        pop af
        dec a
        jr nz,.word
        ld hl,.v                    ; masked
        ld de,.mask
        ld b,8
.and:   ld a,(de)
        and (hl)
        ld (hl),a
        inc hl
        inc de
        djnz .and
        ld hl,.m                    ; m - v: a borrow means v is past m, so again
        ld de,.v
        ld b,8
        or a
.cmp:   ld a,(de)
        ld c,a
        ld a,(hl)
        sbc a,c
        inc hl
        inc de
        djnz .cmp
        jr c,.try
        ld hl,.v
        ld de,(.dst)
        ld bc,8
        ldir
        ret
.none:  ld hl,bly_random_none.pre
        call bly_pr_cstr
        ld hl,(.n)
        call bly_pr_i64
        jp bly_random_none
.n:     dw 0
.dst:   dw 0
.k:     db 0
.m:     ds 8
.mask:  ds 8
.v:     ds 8

bly_randomize_q:                    ; HL = &n: its low 16 bits to HL, the next 20 to BCDE's low bits
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld (bly_rand16.h),de
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld (bly_rand16.s),de        ; E D
        ld a,(hl)
        and 0Fh
        or 30h
        ld (bly_rand16.s+2),a       ; C: 30h and the top 4 of the 20
        ld a,48h
        ld (bly_rand16.s+3),a       ; B
        ret

bly_random_none:
        ld hl,.post
        jp bly_fail
.pre:   db "random(",0
.post:  db ") has nothing to choose from",0
.zero:  db "random(0) has nothing to choose from",0
