;; provides: bly_divmod_i32 bly_divmod_i64 bly_rem_i32 bly_rem_i64 bly_i_udiv bly_i_ua bly_i_ub bly_i_ur
;; needs: bly_i_copyabs bly_i_sig bly_i_negn bly_i_neg32 bly_i_div8 bly_div0 bly_ovf_n bly_ovf_long
;; targets: cpm zx48 test
;; bly_divmod_i32  in: HL=&a DE=&b BC=&q IX=&r   out: (BC) = a / b truncated, (IX) = a % b with a's sign
;;                 fails: division by zero; long overflow for MIN / -1                   clobbers: AF BC DE HL IX
;; bly_divmod_i64  in: HL=&a DE=&b BC=&q IX=&r   out: (BC) = a / b truncated, (IX) = a % b with a's sign
;;                 fails: division by zero; quad overflow for MIN / -1                   clobbers: AF BC DE HL IX
;; bly_rem_i32     in: HL=&a DE=&b BC=&r   out: (BC) = a % b, for %: MIN % -1 is 0, not a failure
;;                 fails: division by zero                                               clobbers: AF BC DE HL IX
;; bly_rem_i64     in: HL=&a DE=&b BC=&r   out: (BC) = a % b, for %: MIN % -1 is 0, not a failure
;;                 fails: division by zero                                               clobbers: AF BC DE HL IX
;; bly_i_udiv      (internal) in: A=N, bly_i_ua = the dividend, bly_i_ub = the divisor (unsigned N-byte)
;;                 out: Z if the divisor is 0 (and nothing done); else NZ, bly_i_ua = the quotient,
;;                 bly_i_ur = the remainder (all 8 bytes, zero above N)                    clobbers: AF BC DE HL IX
;; bly_i_ua, bly_i_ub, bly_i_ur  (internal) 8 bytes each
;
; Signed division works on magnitudes: |a| / |b| unsigned, then the quotient is negated when the signs differ and
; the remainder takes a's sign (interp's tdiv and a - b * tdiv(a, b)). Only MIN / -1 overflows, and only for `/`.
;
; The unsigned divide goes by the divisor's significant bytes, nb (as z88dk does it):
; - nb = 1: long division in base 256, a byte at a time through bly_i_div8 (int16.asm)
; - nb = 2: long division in base 65536, the remainder in HL. Below 32768 the doubled remainder stays in 16 bits;
;   from 32768 up a 17th bit can appear, and when it does the divisor certainly goes, so it's subtracted regardless
;   (16-bit wraparound gives the right answer). This is the 64/16 path that printing, `quad % m` and lcm lean on.
; - nb = 3 or 4: the quotient has at most N - nb + 1 bytes, so the remainder starts as the dividend's top nb - 1
;   bytes and only 8(N - nb + 1) restoring steps run, with the remainder in H L D E and the divisor read through IX.
;   A 33rd bit is the 17th bit again.
; - nb = 5 to 8 (quads only): the same, on a remainder of nb + 1 bytes in memory (or 8: a remainder never exceeds
;   the part of the dividend read so far).
; All of them skip leading dividend digits below the divisor (their quotient digits are 0). A long divided by
; something that fits 16 bits skips the copying too: it loads a into registers and runs the same digit loops
; directly (two base-65536 digits, or four base-256 ones in place for a divisor below 256). The register loops
; don't set quotient bits: the carry after the trial subtraction (and after the add-back) is the quotient bit
; inverted, so it goes straight in with the next shift and the digit is complemented once at the end.

bly_rem_i32:
        ld (bly_divmod_i64.r),bc    ; the remainder goes to BC, and there's no quotient
        ld bc,0
        ld (bly_divmod_i64.q),bc
        jr bly_divmod_i32.go
bly_divmod_i32:
        ld (bly_divmod_i64.q),bc
        ld (bly_divmod_i64.r),ix
.go:    push hl                     ; a long divided by something that fits 16 bits stays in registers
        push de
        ex de,hl
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = b's low word
        inc hl
        ld a,(hl)
        inc hl
        cp (hl)
        jp nz,.gen                  ; the high word is neither 0000h nor FFFFh
        inc a
        jr z,.bneg
        dec a
        jp nz,.gen
        ld a,b
        or c
        jp z,bly_div0
        xor a
        jr .bok
.bneg:  ld a,b
        or c
        jp z,.gen                   ; -65536 is too wide
        xor a
        sub c
        ld c,a
        sbc a,a
        sub b
        ld b,a                      ; BC = |b|
        ld a,80h
.bok:   ld (bly_divmod_i64.sb),a
        pop de
        pop hl
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                      ; HL:DE = a
        ld a,h
        ld (bly_divmod_i64.sa),a
        or a
        call m,bly_i_neg32          ; |a|
        ld a,b
        or a
        jr nz,.w
        ld (bly_i_ua),de            ; a divisor below 256: four base-256 digits, in place in ua
        ld (bly_i_ua+2),hl
        ld e,c
        ld d,4
        ld hl,bly_i_ua+3
        call bly_i_udiv.skip
        ld de,(bly_i_ua)
        ld hl,(bly_i_ua+2)
        ld a,(bly_i_ur)
        ld c,a
        ld b,0
        jr .signs
.w:     push de                     ; two base-65536 digits, BC = |b|: a's low word waits
        ld a,h
        cp b
        jr c,.skip                  ; a's high word is below the divisor: quotient 0, and it's the remainder
        jr nz,.hi
        ld a,l
        cp c
        jr c,.skip
.hi:    ex de,hl
        ld hl,0
        call bly_i_udiv.digit16     ; DE = the high quotient word, HL = the remainder
        jr .lo
.skip:  ld de,0
.lo:    ex (sp),hl                  ; the remainder waits; HL = a's low word
        ex de,hl
        ex (sp),hl                  ; the high quotient word waits; HL = the remainder, DE = a's low word
        call bly_i_udiv.digit16
        ld b,h
        ld c,l                      ; BC = the remainder
        pop hl                      ; HL:DE = the quotient
.signs: push bc
        ld bc,(bly_divmod_i64.q)
        ld a,b
        or c
        jr z,.rem                   ; % alone
        ld a,(bly_divmod_i64.sa)
        push hl
        ld hl,bly_divmod_i64.sb
        xor (hl)
        pop hl
        jp m,.qneg
        bit 7,h                     ; a positive quotient with bit 31 set: MIN / -1
        jp nz,bly_ovf_long
        jr .qput
.qneg:  call bly_i_neg32
.qput:  ld a,e
        ld (bc),a
        inc bc
        ld a,d
        ld (bc),a
        inc bc
        ld a,l
        ld (bc),a
        inc bc
        ld a,h
        ld (bc),a
.rem:   pop de                      ; the remainder, below 65536
        ld hl,0
        ld a,(bly_divmod_i64.sa)
        or a
        call m,bly_i_neg32          ; with a's sign
        ld bc,(bly_divmod_i64.r)
        ld a,e
        ld (bc),a
        inc bc
        ld a,d
        ld (bc),a
        inc bc
        ld a,l
        ld (bc),a
        inc bc
        ld a,h
        ld (bc),a
        ret
.gen:   pop de
        pop hl
        ld a,4
        jr bly_divmod_i64.common
bly_rem_i64:
        ld (bly_divmod_i64.r),bc
        ld bc,0
        ld (bly_divmod_i64.q),bc
        ld a,8
        jr bly_divmod_i64.common
bly_divmod_i64:
        ld a,8
.go:    ld (.q),bc
        ld (.r),ix
.common:
        ld (.n),a
        push de
        ld de,bly_i_ua
        ld b,a
        call bly_i_copyabs          ; ua = |a|; A = a's top byte
        ld (.sa),a
        pop hl
        ld de,bly_i_ub
        ld a,(.n)
        ld b,a
        call bly_i_copyabs          ; ub = |b|
        ld (.sb),a
        ld a,(.n)
        call bly_i_udiv
        jp z,bly_div0
        ld hl,(.q)
        ld a,h
        or l
        jr z,.rem                   ; % alone
        ld a,(.sa)
        ld hl,.sb
        xor (hl)
        jp p,.qpos
        ld hl,bly_i_ua
        ld a,(.n)
        ld b,a
        call bly_i_negn
        jr .qput
.qpos:  ld a,(.n)                   ; a positive quotient with its top bit set: MIN / -1
        ld e,a
        ld d,0
        ld hl,bly_i_ua - 1
        add hl,de
        bit 7,(hl)
        jp nz,bly_ovf_n
.qput:  ld hl,bly_i_ua
        ld de,(.q)
        ld a,(.n)
        ld c,a
        ld b,0
        ldir
.rem:   ld a,(.sa)
        or a
        jp p,.rput
        ld hl,bly_i_ur
        ld a,(.n)
        ld b,a
        call bly_i_negn
.rput:  ld hl,bly_i_ur
        ld de,(.r)
        ld a,(.n)
        ld c,a
        ld b,0
        ldir
        ret

.q:     dw 0
.r:     dw 0
.n:     db 0
.sa:    db 0
.sb:    db 0

bly_i_udiv:
        ld (.n),a
        ld hl,bly_i_ub
        ld b,a
        call bly_i_sig              ; nb: the divisor's bytes
        or a
        ret z                       ; a divisor of 0: nothing done, and Z says so
        ld hl,0
        ld (bly_i_ur),hl
        ld (bly_i_ur+2),hl
        ld (bly_i_ur+4),hl
        ld (bly_i_ur+6),hl
        cp 2
        jr z,.d16
        jp nc,.big
        ld a,(bly_i_ub)             ; one byte: base 256
        ld e,a                      ; E = the divisor
        ld a,(.n)
        ld d,a                      ; D = the bytes to go
        ld hl,bly_i_ua - 1
        add a,l
        ld l,a
        jr nc,.skip
        inc h                       ; HL = the top byte
.skip:  ld a,(hl)                   ; a leading byte below the divisor: quotient byte 0, and it's the remainder
        cp e
        jr nc,.from0
        ld (hl),0
        dec hl
        dec d
        jr z,.d8done
        or a
        jr z,.skip
        jr .byte
.from0: xor a
.byte:  ld c,(hl)
        call bly_i_div8
        ld (hl),c
        dec hl
        dec d
        jr nz,.byte
.d8done:
        ld (bly_i_ur),a
        or 1                        ; NZ: done
        ret

.d16:   ld bc,(bly_i_ub)            ; two bytes: base 65536, BC = the divisor
        ld a,(.n)
        ld e,a
        srl a
        ld (.cnt),a                 ; digits
        ld d,0
        ld ix,bly_i_ua - 2
        add ix,de                   ; IX = the top digit
        ld hl,0
.skip16:
        ld e,(ix+0)                 ; leading digits below the divisor, as for bytes (HL = 0 here)
        ld d,(ix+1)
        ex de,hl
        or a
        sbc hl,bc
        add hl,bc                   ; carry: the digit is below the divisor
        jr nc,.from16
        ld (ix+0),0
        ld (ix+1),0
        dec ix
        dec ix
        ld a,(.cnt)
        dec a
        ld (.cnt),a
        jr z,.d16done
        ld a,h
        or l
        jr z,.skip16
        jr .dig
.from16:
        ld hl,0
.dig:   ld e,(ix+0)
        ld d,(ix+1)
        call .digit16
        ld (ix+0),e
        ld (ix+1),d
        dec ix
        dec ix
        ld a,(.cnt)
        dec a
        ld (.cnt),a
        jr nz,.dig
.d16done:
        ld (bly_i_ur),hl
        or 1
        ret

.digit16:                           ; HL = the remainder (below BC), DE = the next digit -> DE = its quotient digit
        bit 7,b
        jr nz,.wide16
        ld a,4                      ; a divisor below 32768: the doubled remainder never passes 16 bits
.l16:   REPT 4
        rl e                        ; the last quotient bit, inverted, in; the next dividend bit out
        rl d
        adc hl,hl
        sbc hl,bc                   ; carry: it borrowed, quotient bit 0
        jr nc,$+3
        add hl,bc                   ; put back, which carries: the carry is the quotient bit inverted either way
        ENDR
        dec a
        jr nz,.l16
        rl e
        rl d
        ld a,e
        cpl
        ld e,a
        ld a,d
        cpl
        ld d,a
        ret
.wide16:
        ld a,16                     ; 32768 and up: a bit can fall off the top of the remainder
.w16:   sla e
        rl d
        adc hl,hl
        jr c,.big16
        sbc hl,bc                   ; carry is clear here
        jr nc,.one16
        add hl,bc
        dec a
        jr nz,.w16
        ret
.big16: or a                        ; the 17th bit: the divisor goes, and the 16-bit wraparound is right
        sbc hl,bc
.one16: inc e
        dec a
        jr nz,.w16
        ret

.big:   ld (.nb),a                  ; three bytes or more
        ld a,(.n)
        ld c,a
        ld b,0
        ld hl,bly_i_ua - 1
        add hl,bc
        ex de,hl                    ; DE = &ua[N-1]
        ld hl,bly_i_ub - 1
        add hl,bc                   ; HL = &ub[N-1]
        ld b,c
.cmp:   ld a,(de)                   ; a dividend below the divisor: quotient 0, remainder the dividend
        cp (hl)
        jr c,.less
        jr nz,.divide
        dec hl
        dec de
        djnz .cmp
        jr .divide
.less:  ld hl,bly_i_ua
        ld de,bly_i_ur
        ld a,(.n)
        ld c,a
        ld b,0
        ldir
        ld hl,bly_i_ua
        ld b,a
        xor a
.zq:    ld (hl),a
        inc hl
        djnz .zq
        or 1
        ret
.divide:
        ld a,(.n)                   ; the quotient has N - nb + 1 bytes: cnt of them
        ld hl,.nb
        sub (hl)
        inc a
        ld (.cnt),a
        ld a,(hl)
        cp 5
        jp nc,.mem
        ld a,(.n)                   ; nb = 3 or 4: the remainder in H L D E
        ld e,a
        ld d,0
        ld ix,bly_i_ua - 1
        add ix,de                   ; IX = the dividend's top byte
        ld a,(.nb)
        dec a
        ld b,a
        ld hl,0
        ld de,0
.pre:   ld h,l                      ; the top nb - 1 bytes are the remainder to start with
        ld l,d
        ld d,e
        ld e,(ix+0)
        ld (ix+0),0                 ; and the quotient's top bytes are 0
        dec ix
        djnz .pre
        ld (.ptr),ix                ; the next byte to run
        ld c,(ix+0)
        ld ix,bly_i_ub
        ld b,8
.s32:   rl c                        ; the last quotient bit, inverted, in; the next dividend bit out
        rl e
        rl d
        adc hl,hl
        jr c,.f32                   ; a 33rd bit: the divisor goes
        ld a,e                      ; remainder - divisor
        sub (ix+0)
        ld e,a
        ld a,d
        sbc a,(ix+1)
        ld d,a
        ld a,l
        sbc a,(ix+2)
        ld l,a
        ld a,h
        sbc a,(ix+3)
        ld h,a
        jr nc,.n32                  ; no borrow: quotient bit 1, and carry 0
        ld a,e                      ; borrowed: put it back, which carries
        add a,(ix+0)
        ld e,a
        ld a,d
        adc a,(ix+1)
        ld d,a
        ld a,l
        adc a,(ix+2)
        ld l,a
        ld a,h
        adc a,(ix+3)
        ld h,a
.n32:   djnz .s32
        rl c
        ld a,c
        cpl
        push hl
        ld hl,(.ptr)
        ld (hl),a                   ; the quotient byte
        dec hl
        ld (.ptr),hl
        ld c,(hl)                   ; the next dividend byte (a harmless read after the last)
        pop hl
        ld a,(.cnt)
        dec a
        ld (.cnt),a
        ld b,8
        jr nz,.s32
        ld (bly_i_ur),de
        ld (bly_i_ur+2),hl
        or 1
        ret
.f32:   ld a,e                      ; the remainder passed 32 bits: subtract, and the wraparound is right
        sub (ix+0)
        ld e,a
        ld a,d
        sbc a,(ix+1)
        ld d,a
        ld a,l
        sbc a,(ix+2)
        ld l,a
        ld a,h
        sbc a,(ix+3)
        ld h,a
        or a                        ; quotient bit 1: carry 0
        jr .n32

.mem:   ld a,(.nb)                  ; five bytes or more, quads only
        inc a
        ld hl,.n
        cp (hl)
        jr c,.nrok
        ld a,(hl)
.nrok:  ld (.nr),a                  ; the remainder's working bytes: min(nb + 1, N)
        ld a,(.cnt)
        ld e,a
        ld d,0
        ld hl,bly_i_ua
        add hl,de                   ; HL = &ua[cnt], the start of the top nb - 1 bytes
        ld de,bly_i_ur
        ld a,(.nb)
        dec a
        ld c,a
        ld b,0
        push hl
        ldir                        ; they're the remainder to start with
        pop hl
        ld b,a
        xor a
.zt:    ld (hl),a                   ; and the quotient's top bytes are 0
        inc hl
        djnz .zt
        ld a,(.cnt)
        ld e,a
        ld d,0
        ld ix,bly_i_ua - 1
        add ix,de                   ; IX = the next dividend byte
.gbyte: ld c,(ix+0)
        ld a,8
        ld (.bits),a
.gbit:  sla c                       ; the next dividend bit, into the remainder
        ld hl,bly_i_ur
        ld a,(.nr)
        ld b,a
.sh:    rl (hl)
        inc hl
        djnz .sh
        ld de,bly_i_ur              ; remainder - divisor
        ld hl,bly_i_ub
        ld a,(.nr)
        ld b,a
        or a
.su:    ld a,(de)
        sbc a,(hl)
        ld (de),a
        inc de
        inc hl
        djnz .su
        jr nc,.q1
        ld de,bly_i_ur              ; it borrowed: add the divisor back
        ld hl,bly_i_ub
        ld a,(.nr)
        ld b,a
        or a
.ad:    ld a,(de)
        adc a,(hl)
        ld (de),a
        inc de
        inc hl
        djnz .ad
        jr .qn
.q1:    inc c
.qn:    ld hl,.bits
        dec (hl)
        jr nz,.gbit
        ld (ix+0),c
        dec ix
        ld hl,.cnt
        dec (hl)
        jr nz,.gbyte
        or 1
        ret

.n:     db 0
.nb:    db 0
.nr:    db 0
.cnt:   db 0
.bits:  db 0
.ptr:   dw 0
bly_i_ua: ds 8
bly_i_ub: ds 8
bly_i_ur: ds 8
