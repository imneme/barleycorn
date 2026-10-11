;; provides: bly_fc
;; needs: bly_fx bly_fail
;; targets: cpm zx48 test
;; The ROM-free floats' shared part (internal): fp_cpm.asm's arithmetic and fp_sqrt.asm's root unpack with it, and
;; round and write their answers with it. The form is the ROM's 5 bytes (ABI.md section 11).
;; bly_fc.both    in: HL=&a DE=&b BC=&r   a and b unpacked (bly_fx.unpack) into .ua and .ub, &r kept in .res
;; bly_fc.pack    .w's top 32 bits (its top bit set) rounded by its bit 31, ties away from zero, with .ex the
;;                exponent byte (biased, 16 bits) and .sg the sign, written to (.res) in the full form; too small is 0
;;                fails: float overflow
;; bly_fc.packc   as .pack, but too big returns C instead of failing
;; bly_fc.zero    0 to (.res)       bly_fc.put   HL=&u (an unpacked float) to (.res)       bly_fc.shl   .w <<= 1
;; Scratch: .res .flip .sg .ex .ua .ub .w. Every entry clobbers AF BC DE HL.
;
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

