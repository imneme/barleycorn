;; provides: bly_ftrunc bly_ffloor bly_fround bly_fneg bly_fabs bly_fcmp bly_f_from_u16 bly_f_from_i16 bly_f_from_i64 bly_f_to_int bly_fx
;; needs: bly_pr_f bly_pr_cstr bly_fail
;; targets: cpm zx48
;; Floats, the part that's exact in Z80 and needs no ROM: the 48K's and CP/M's alike (ABI.md section 11). The form
;; is the ROM's 5 bytes on both: the short form 00 s lo hi 00, or e m3 m2 m1 m0, 0.1mmm... x 2^(e-128).
;; bly_ftrunc bly_ffloor bly_fround   in: HL=&x BC=&r   (exact: not the ROM's INT, which has a bug at -65536)
;;        round is floor(x + 0.5), as the interpreter's
;; bly_fneg bly_fabs   in: HL=&x BC=&r (r may be x)
;; bly_fcmp            in: HL=&a DE=&b   out: A = FFh/0/1, flags as after OR A   (never fails)
;; bly_f_from_u16      in: HL = a byte or word, BC=&r      bly_f_from_i16   in: HL = an int, BC=&r
;; bly_f_from_i64      in: HL=&q (a quad: the generator widens a long), BC=&r   (rounded to 32 bits, half away from 0)
;; bly_f_to_int        in: HL=&x A=the type code (0 byte .. 4 quad, 5 dword) DE=&dest   truncates toward zero
;;        fails: {x} doesn't fit in {a type} (x printed by the target's bly_pr_f)
;; Every routine clobbers AF BC DE HL IX. bly_fx is the shared part: unpacking, a float's whole part as 64 bits,
;; packing 64 bits back (rounded half away from zero), and their scratch; fp.asm's ** and CP/M's arithmetic use it.

; -- whole numbers: trunc, floor, round, exactly ---------------------------------------------------------------------
bly_ftrunc:
        xor a
        jr bly_fround.go
bly_ffloor:
        ld a,1
        jr bly_fround.go
bly_fround:
        ld a,2
.go:    ld (.mode),a
        ld (bly_fx.res),bc
        ld (bly_fx.pa),hl
        call bly_fx.toint
        ld a,(bly_fx.ee)
        or a
        jr z,.same                  ; the short form: whole already
        cp 160
        jr c,.cut
.same:  ld hl,(bly_fx.pa)           ; 2^31 or more: whole already
        ld de,(bly_fx.res)
        ld bc,5
        ldir
        ret
.cut:   ld a,(.mode)
        or a
        jr z,.done                  ; trunc: the whole part
        ld b,a
        ld a,(bly_fx.neg)
        or a
        ld a,(bly_fx.fr)
        jr z,.pos
        djnz .nrnd
        or a                        ; floor of a negative: any fraction takes the magnitude up
        jr nz,.up
        jr .done
.nrnd:  cp 3                        ; round of a negative: up only past a half (floor(-2.5 + 0.5) is -2)
        jr z,.up
        jr .done
.pos:   djnz .prnd
        jr .done                    ; floor of a positive: the whole part
.prnd:  and 1                       ; round of a positive: up from a half
        jr z,.done
.up:    ld hl,bly_fx.mag            ; the magnitude is under 2^31: 32 bits carry it
        inc (hl)
        jr nz,.done
        inc hl
        inc (hl)
        jr nz,.done
        inc hl
        inc (hl)
        jr nz,.done
        inc hl
        inc (hl)
.done:  jp bly_fx.frommag
.mode:  db 0

; -- sign and comparing ---------------------------------------------------------------------------------------------
bly_fneg:
        push bc
        ld d,b
        ld e,c
        ld bc,5
        ldir
        pop hl
.inplace:                           ; HL = &x: x = -x
        ld a,(hl)
        inc hl
        or a
        jr z,.short
        ld a,(hl)
        xor 80h
        ld (hl),a
        ret
.short: inc hl                      ; s lo hi: negate lo hi, flip s; zero stays zero
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld a,d
        or e
        jr nz,.nz
        dec hl
        dec hl
        ld a,(hl)
        or a
        ret z
        dec hl                      ; the slipped -65536 (never made here): +65536 in full, 91 00 00 00 00
        ld (hl),91h
        inc hl
        ld (hl),0
        ret
.nz:    xor a
        sub e
        ld e,a
        ld a,0
        sbc a,d
        ld (hl),a
        dec hl
        ld (hl),e
        dec hl
        ld a,(hl)
        cpl
        ld (hl),a
        ret

bly_fabs:
        push bc
        ld d,b
        ld e,c
        ld bc,5
        ldir
        pop hl
        inc hl
        bit 7,(hl)
        dec hl
        ret z
        jr bly_fneg.inplace

bly_fcmp:
        push de
        ld de,bly_fx.ua
        call bly_fx.unpack
        pop hl
        ld de,bly_fx.ub
        call bly_fx.unpack
        ld hl,bly_fx.ua
        ld de,bly_fx.ub
        ld a,(de)
        cp (hl)
        jr z,.same
        ld a,(hl)                   ; the signs differ: the negative one is less
        or a
        ld a,1
        jr z,.ret
        ld a,0FFh
.ret:   or a
        ret
.same:  ld c,a                      ; C = the common sign
        ld b,5
.lp:    inc hl
        inc de
        ld a,(de)
        cp (hl)                     ; carry if b's byte < a's
        jr nz,.diff
        djnz .lp
        xor a
        ret
.diff:  ld a,1
        jr c,.mag
        ld a,0FFh
.mag:   bit 7,c
        jr z,.ret
        neg                         ; both negative: the bigger magnitude is the smaller number
        jr .ret

; -- conversions ------------------------------------------------------------------------------------------------------
bly_f_from_u16:
        xor a
        jr bly_f_from_i16.put
bly_f_from_i16:
        ld a,h
        rla
        sbc a,a                     ; s: FFh if negative
.put:   ld d,b
        ld e,c
        ex de,hl
        ld (hl),0
        inc hl
        ld (hl),a
        inc hl
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld (hl),0
        ret

bly_f_from_i64:
        ld (bly_fx.res),bc
        ld de,bly_fx.mag
        ld bc,8
        ldir
        ld a,(bly_fx.mag+7)
        and 80h
        ld (bly_fx.neg),a
        call nz,bly_fx.negmag       ; |q| (the most negative quad's is 2^63, read unsigned)
        jp bly_fx.frommag

bly_f_to_int:
        ld (.type),a
        ld (.dest),de
        ld (bly_fx.pa),hl
        call bly_fx.toint
        ld a,(bly_fx.big)
        or a
        jr nz,.no
        ld a,(bly_fx.neg)
        or a
        jr z,.pos
        call bly_fx.negmag
        ld a,(bly_fx.mag+7)
        rla
        jr c,.q                     ; negative, as it should be
        ld hl,bly_fx.mag            ; or zero; anything else was past -2^63
        xor a
        ld b,8
.z:     or (hl)
        inc hl
        djnz .z
        jr nz,.no
        jr .q
.pos:   ld a,(bly_fx.mag+7)
        rla
        jr c,.no                    ; 2^63 or more
.q:     ld a,(.type)                ; the type's range: bytes w..7 all the extension of byte w-1 (0 if unsigned)
        ld e,a
        ld d,0
        ld hl,.width
        add hl,de
        ld b,(hl)
        ld hl,.signed
        add hl,de
        ld c,(hl)
        ld hl,bly_fx.mag-1
        ld e,b
        add hl,de                   ; HL = &mag[w-1]
        xor a
        bit 0,c
        jr z,.ext
        bit 7,(hl)
        jr z,.ext
        dec a
.ext:   ld c,a
        ld a,8
        sub b
        jr z,.fits
        ld e,b                      ; keep w
        ld b,a
.chk:   inc hl
        ld a,(hl)
        cp c
        jr nz,.no
        djnz .chk
        ld b,e
.fits:  ld c,b
        ld b,0
        ld hl,bly_fx.mag
        ld de,(.dest)
        ldir
        ret
.no:    ld hl,(bly_fx.pa)           ; {x} doesn't fit in a {type}
        call bly_pr_f
        ld hl,.m1
        call bly_pr_cstr
        ld a,(.type)
        add a,a
        ld e,a
        ld d,0
        ld hl,.names
        add hl,de
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        jp bly_fail
.type:  db 0
.dest:  dw 0
.width: db 1, 2, 2, 4, 8, 4
.signed: db 0, 0, 1, 1, 1, 0
.names: dw .n0, .n1, .n2, .n3, .n4, .n5
.n0:    db "a byte",0
.n1:    db "a word",0
.n2:    db "an int",0
.n3:    db "a long",0
.n4:    db "a quad",0
.n5:    db "a dword",0
.m1:    db " doesn't fit in ",0


; -- the shared part: unpacking, whole parts, packing, and their scratch ----------------------------------------
bly_fx:
.zero:  push hl                     ; Z if (HL) is zero: 00 00 00 00 (00 FF 00 00 would be -65536)
        ld a,(hl)                   ; clobbers AF
        inc hl
        or (hl)
        inc hl
        or (hl)
        inc hl
        or (hl)
        pop hl
        ret

; .toint: HL = &x -> .mag = |trunc x| as 64 bits (if it fits: else .big = 1), .neg = 0 or 80h, .ee = x's exponent
; byte (0 for the short form), .fr = the fraction cut off: bit 0 its first bit (a half), bit 1 any after it.
.toint: xor a
        ld (.big),a
        ld (.fr),a
        push hl
        ld hl,.mag
        ld b,8
.tz:    ld (hl),a
        inc hl
        djnz .tz
        pop hl
        ld a,(hl)
        ld (.ee),a
        inc hl
        or a
        jr nz,.tfull
        ld a,(hl)                   ; the short form: s lo hi
        and 80h
        ld (.neg),a
        inc hl
        ld e,(hl)
        inc hl
        ld d,(hl)
        or a
        jr z,.tpos
        ld hl,0                     ; (carry is clear: OR A above)
        sbc hl,de                   ; |x| = 65536 - (lo hi), where 0 means 65536
        ex de,hl
        ld a,d
        or e
        jr nz,.tpos
        inc a
        ld (.mag+2),a
.tpos:  ld (.mag),de
        ret
.tfull: ld a,(hl)
        and 80h
        ld (.neg),a
        ld a,(hl)                   ; the mantissa, its top bit back: DEHL, D the top byte
        or 80h
        ld d,a
        inc hl
        ld e,(hl)
        inc hl
        ld a,(hl)
        inc hl
        ld l,(hl)
        ld h,a
        ld a,(.ee)
        cp 160
        jr nc,.tleft
        ld b,a                      ; under 2^31: shift right 160 - e times (33 at most: by then all is fraction),
        ld a,160                    ; keeping the last bit out (the half) and whether any before it was set
        sub b
        cp 34
        jr c,.tn
        ld a,33
.tn:    ld b,a
        ld c,0                      ; C: bit 0 the half, bit 1 the rest
.tr:    ld a,c
        add a,a
        or c
        and 2
        srl d
        rr e
        rr h
        rr l
        adc a,0
        ld c,a
        djnz .tr
        ld a,c
        ld (.fr),a
        ld (.mag),hl
        ld (.mag+2),de
        ret
.tleft: sub 160                     ; e >= 160: whole, the mantissa times 2^(e-160): placed (e-160)/8 bytes up,
        ld b,a                      ; then shifted (e-160)%8 bits. Past e = 192 it's 2^64 or more.
        and 7
        ld c,a
        ld a,b
        rrca
        rrca
        rrca
        and 1Fh
        cp 4
        jr c,.tok
        jr nz,.tbig
        inc c
        dec c
        jr nz,.tbig
.tok:   ld ix,.mag
        push bc
        ld c,a
        ld b,0
        add ix,bc
        pop bc
        ld (ix+0),l
        ld (ix+1),h
        ld (ix+2),e
        ld (ix+3),d
        ld a,c
        or a
        ret z
        ld b,a
.tl:    ld hl,.mag
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
        djnz .tl
        ret
.tbig:  ld a,1
        ld (.big),a
        ret

.negmag:                            ; .mag = -.mag, 64 bits
        ld hl,.mag
        ld b,8
        or a
.ng:    ld a,0
        sbc a,(hl)
        ld (hl),a
        inc hl
        djnz .ng
        ret

; .frommag: .mag (64 bits, unsigned) with the sign .neg -> the float at (.res). Short form under 65536; otherwise the
; top 32 bits, rounded half away from zero on the next bit.
.frommag:
        ld hl,.mag+7
        ld b,7
.ftop:  ld a,(hl)
        or a
        jr nz,.ffound
        dec hl
        djnz .ftop
.ffound:                            ; B = the top nonzero byte's index (0 if none), HL = its address
        ld a,b
        cp 2
        jr nc,.ffull
        ld hl,(.mag)                ; under 65536: 00 s lo hi 00
        ld a,h
        or l
        jr z,.fshort                ; zero is never "negative": 00 FF 00 00 00 would be -65536
        ld a,(.neg)
        or a
        jr z,.fshort
        ex de,hl
        ld hl,0
        or a
        sbc hl,de
        ld a,0FFh
.fshort:
        ex de,hl
        ld hl,(.res)
        ld (hl),0
        inc hl
        ld (hl),a                   ; s: 0 (A is 0 from OR H/L or .neg) or FFh
        inc hl
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld (hl),0
        ret
.ffull: inc a                       ; e = 128 + 8 * (index + 1), less the normalising shifts
        add a,a
        add a,a
        add a,a
        add a,128
        ld b,a
        push hl
        pop ix                      ; DEHL and a guard byte C, from the top byte down (.pad makes the reads
        ld d,(ix+0)                 ; below .mag harmless: the top byte's index is 2 or more)
        ld e,(ix-1)
        ld h,(ix-2)
        ld l,(ix-3)
        ld c,(ix-4)
        jr .fnorm
.fsh:   sla c
        rl l
        rl h
        rl e
        rl d
        dec b
.fnorm: bit 7,d
        jr z,.fsh
        bit 7,c                     ; round on the next bit
        jr z,.fpack
        inc l
        jr nz,.fpack
        inc h
        jr nz,.fpack
        inc e
        jr nz,.fpack
        inc d
        jr nz,.fpack
        ld d,80h                    ; 1.000 -> 0.1000 x 2
        inc b
.fpack: push hl                     ; B = e, DEHL = the mantissa with its top bit
        ld hl,(.res)
        ld (hl),b
        inc hl
        ld a,d
        and 7Fh
        ld c,a
        ld a,(.neg)
        or c
        ld (hl),a
        inc hl
        ld (hl),e
        inc hl
        pop de
        ld (hl),d
        inc hl
        ld (hl),e
        ret

; .unpack: HL = &x, DE = &u -> u = sign (0 or 80h), e, m3 m2 m1 m0 (the mantissa with its top bit); zero is e = 0
.unpack:
        ld a,(hl)
        or a
        jr z,.ushort
        inc hl
        ld a,(hl)
        and 80h
        ld (de),a
        inc de
        dec hl
        ld a,(hl)
        ld (de),a
        inc de
        inc hl
        ld a,(hl)
        or 80h
        ld (de),a
        inc de
        inc hl
        ld bc,3
        ldir
        ret
.ushort:
        inc hl
        ld a,(hl)
        and 80h
        ld c,a                      ; C = the sign
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                      ; HL = lo hi
        ld a,c
        or a
        jr z,.upos
        push de
        ex de,hl
        ld hl,0
        or a
        sbc hl,de                   ; |x| = 65536 - (lo hi)
        pop de
        ld a,h
        or l
        jr nz,.upos
        ld a,c                      ; 0 here is the slipped -65536: 0.1b x 2^17
        ld (de),a
        inc de
        ld a,145
        ld (de),a
        inc de
        ld a,80h
        ld (de),a
        inc de
        xor a
        jr .u3
.upos:  ld a,c
        ld (de),a
        inc de
        ld a,h
        or l
        jr z,.uzero
        ld b,144                    ; HL = 0.HL x 2^16; normalise
.un:    bit 7,h
        jr nz,.und
        add hl,hl
        dec b
        jr .un
.und:   ld a,b
        ld (de),a
        inc de
        ld a,h
        ld (de),a
        inc de
        ld a,l
        ld (de),a
        inc de
        xor a
        ld (de),a
        inc de
        ld (de),a
        ret
.uzero: xor a
        ld (de),a
        inc de
        ld (de),a
        inc de
.u3:    ld (de),a
        inc de
        ld (de),a
        inc de
        ld (de),a
        ret

.pa:    dw 0                        ; the first operand (for a message)
.res:   dw 0                        ; where the answer goes
.neg:   db 0
.big:   db 0
.fr:    db 0
.ee:    db 0
.ua:    ds 6
.ub:    ds 6
.pad:   ds 5                        ; zeros, always: .frommag may read just below .mag
.mag:   ds 8
