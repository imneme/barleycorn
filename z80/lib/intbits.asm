;; provides: bly_and_i32 bly_and_i64 bly_or_i32 bly_or_i64 bly_xor_i32 bly_xor_i64 bly_not_i32 bly_not_i64 bly_shl_i32 bly_shl_i64 bly_shr_i32 bly_shr_i64 bly_i_shprep
;; needs: bly_neg_shift
;; targets: cpm zx48 test
;; bly_and_i32  in: HL=&a DE=&b BC=&r   out: (BC) = a & b                                   clobbers: AF BC DE HL
;; bly_and_i64  in: HL=&a DE=&b BC=&r   out: (BC) = a & b                                   clobbers: AF BC DE HL
;; bly_or_i32   in: HL=&a DE=&b BC=&r   out: (BC) = a | b                                   clobbers: AF BC DE HL
;; bly_or_i64   in: HL=&a DE=&b BC=&r   out: (BC) = a | b                                   clobbers: AF BC DE HL
;; bly_xor_i32  in: HL=&a DE=&b BC=&r   out: (BC) = a ^ b                                   clobbers: AF BC DE HL
;; bly_xor_i64  in: HL=&a DE=&b BC=&r   out: (BC) = a ^ b                                   clobbers: AF BC DE HL
;; bly_not_i32  in: HL=&a BC=&r         out: (BC) = ~a                                      clobbers: AF BC E HL
;; bly_not_i64  in: HL=&a BC=&r         out: (BC) = ~a                                      clobbers: AF BC E HL
;; bly_shl_i32  in: HL=&a DE=count (signed) BC=&r   out: (BC) = a << count, wrapping   fails: negative shift count   clobbers: AF BC DE HL
;; bly_shl_i64  in: HL=&a DE=count (signed) BC=&r   out: (BC) = a << count, wrapping   fails: negative shift count   clobbers: AF BC DE HL
;; bly_shr_i32  in: HL=&a DE=count (signed) BC=&r   out: (BC) = a >> count, keeping the sign   fails: negative shift count   clobbers: AF BC DE HL
;; bly_shr_i64  in: HL=&a DE=count (signed) BC=&r   out: (BC) = a >> count, keeping the sign   fails: negative shift count   clobbers: AF BC DE HL
;; bly_i_shprep (internal) in: A=N HL=&a DE=count BC=&r   copies a to r; out: HL=&r C=N B=whole bytes (N when count >= 8N)
;;                         E=the bits left over, A=a's top byte   fails: negative shift count   clobbers: AF BC DE HL
;
; r may be a or b. A shift moves whole bytes first (LDDR or LDIR within r) and then shifts the rest one bit at a time.
; Any count of 8N or more empties a left shift and leaves only the sign after a right one, as interp's
; wrap(a << min(b, 64)) and a >> b do. The count is a signed word: generated code saturates wider counts to 64.

bly_and_i64:
        call bly_and_i32
bly_and_i32:
        REPT 4
        ld a,(de)
        and (hl)
        ld (bc),a
        inc hl
        inc de
        inc bc
        ENDR
        ret

bly_or_i64:
        call bly_or_i32
bly_or_i32:
        REPT 4
        ld a,(de)
        or (hl)
        ld (bc),a
        inc hl
        inc de
        inc bc
        ENDR
        ret

bly_xor_i64:
        call bly_xor_i32
bly_xor_i32:
        REPT 4
        ld a,(de)
        xor (hl)
        ld (bc),a
        inc hl
        inc de
        inc bc
        ENDR
        ret

bly_not_i64:
        ld e,8
        jr bly_not_i32.go
bly_not_i32:
        ld e,4
.go:    ld a,(hl)
        cpl
        ld (bc),a
        inc hl
        inc bc
        dec e
        jr nz,.go
        ret

bly_i_shprep:
        bit 7,d
        jp nz,bly_neg_shift
        push de                     ; the count
        ld d,b
        ld e,c
        push de                     ; &r
        ld c,a
        ld b,0
        push bc                     ; N
        ldir                        ; r = a (a no-op when r is a)
        dec hl
        ld a,(hl)                   ; a's top byte, read after the copy so that r being a doesn't matter
        pop bc                      ; C = N
        pop hl                      ; &r
        pop de                      ; the count
        push af
        ld a,d
        or a
        jr nz,.all                  ; 256 or more
        ld a,e
        and 7
        ld b,a
        ld a,e
        rrca
        rrca
        rrca
        and 1Fh                     ; whole bytes
        cp c
        jr nc,.all
        ld e,b                      ; E = bits
        ld b,a                      ; B = bytes
        pop af
        ret
.all:   ld b,c                      ; every byte shifts out
        ld e,0
        pop af
        ret

bly_shl_i32:
        ld a,4
        jr bly_shl_i64.go
bly_shl_i64:
        ld a,8
.go:    bit 7,d
        jp nz,bly_neg_shift
        ld (.n),a
        ld a,d
        or a
        jr nz,.slow
        ld a,e
        dec a
        cp 7
        jr nc,.slow                 ; 0, or 8 and more
        push bc                     ; 1 to 7 bits: the first pass copies a to r a bit up, the rest shift r
        ld a,(.n)
        ld d,a
        or a
.p1:    ld a,(hl)
        rla
        ld (bc),a
        inc hl
        inc bc
        dec d                       ; DEC keeps the carry
        jr nz,.p1
        pop hl
        dec e
        ret z
.pn:    push hl
        ld a,(.n)
        ld b,a
        or a
.rl1:   rl (hl)
        inc hl
        djnz .rl1
        pop hl
        dec e
        jr nz,.pn
        ret
.n:     db 0
.slow:  ld a,(.n)
        call bly_i_shprep           ; HL=&r C=N B=bytes E=bits
        push hl
        push de
        push bc
        ld a,b
        or a
        jr z,.bits
        ld a,c                      ; DE = &r + N - 1 (the top), HL = DE - bytes
        dec a
        add a,l
        ld l,a
        jr nc,.n1
        inc h
.n1:    ld d,h
        ld e,l
        ld a,l
        sub b
        ld l,a
        jr nc,.n2
        dec h
.n2:    ld a,c
        sub b                       ; the bytes that stay: N - bytes
        jr z,.zero
        push bc
        ld c,a
        ld b,0
        lddr                        ; up by whole bytes, from the top down; DE ends below the moved ones
        pop bc
.zero:  xor a
.z:     ld (de),a
        dec de
        djnz .z
.bits:  pop bc                      ; C = N
        pop de                      ; E = bits
        pop hl                      ; &r
        ld a,e
        or a
        ret z
.pass:  push hl
        ld b,c
        or a
.rl:    rl (hl)
        inc hl
        djnz .rl
        pop hl
        dec e
        jr nz,.pass
        ret

bly_shr_i32:
        ld a,4
        jr bly_shr_i64.go
bly_shr_i64:
        ld a,8
.go:    bit 7,d
        jp nz,bly_neg_shift
        ld (.n),a
        ld a,d
        or a
        jr nz,.slow
        ld a,e
        dec a
        cp 7
        jr nc,.slow                 ; 0, or 8 and more
        ld a,(.n)                   ; 1 to 7 bits: from the top down, so r may be a
        dec a
        ld d,a                      ; D = N - 1
        add a,l
        ld l,a
        jr nc,.t1
        inc h
.t1:    ld a,d
        add a,c
        ld c,a
        jr nc,.t2
        inc b                       ; HL = a's top byte, BC = r's
.t2:    push bc
        ld a,(hl)
        sra a                       ; the first pass copies a to r a bit down, keeping the sign
        ld (bc),a
.p1:    dec hl
        dec bc
        ld a,(hl)
        rra
        ld (bc),a
        dec d
        jr nz,.p1
        pop hl                      ; r's top byte
        dec e
        ret z
.pn:    push hl                     ; the rest shift r in place
        ld a,(.n)
        dec a
        ld b,a
        sra (hl)
.rr1:   dec hl
        rr (hl)
        djnz .rr1
        pop hl
        dec e
        jr nz,.pn
        ret
.n:     db 0
.slow:  ld a,(.n)
        call bly_i_shprep           ; HL=&r C=N B=bytes E=bits A=a's top byte
        rla
        sbc a,a
        ld d,a                      ; D = the fill: 00h or FFh
        push hl
        push de
        push bc
        ld a,b
        or a
        jr z,.bits
        push bc
        ld a,c
        sub b
        ld c,a                      ; C = the bytes that stay: N - bytes
        ld a,d                      ; A = the fill, kept through LDIR
        ex de,hl                    ; DE = &r
        ld l,b
        ld h,0
        add hl,de                   ; HL = &r + bytes
        ld b,0
        inc c
        dec c
        jr z,.fill
        ldir                        ; down by whole bytes; DE ends above the moved ones
.fill:  pop bc                      ; B = bytes
.f:     ld (de),a
        inc de
        djnz .f
.bits:  pop bc                      ; C = N
        pop de                      ; E = bits
        pop hl                      ; &r
        ld a,e
        or a
        ret z
        ld a,c                      ; HL = &r + N - 1, the top
        dec a
        add a,l
        ld l,a
        jr nc,.pass
        inc h
.pass:  push hl
        ld b,c
        dec b
        sra (hl)
.rr:    dec hl
        rr (hl)
        djnz .rr
        pop hl
        dec e
        jr nz,.pass
        ret
