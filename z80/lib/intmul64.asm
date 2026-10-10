;; provides: bly_mul_i64 bly_i_mulmag bly_i_mx bly_i_my
;; needs: bly_i_copyabs bly_i_sig bly_i_negn bly_i_mul16x8 bly_ovf_n
;; targets: cpm zx48 test
;; bly_mul_i64   in: HL=&a DE=&b BC=&r   out: (BC) = a * b   fails: quad overflow   clobbers: AF BC DE HL IX
;; bly_i_mulmag  (internal) in: bly_i_mx, bly_i_my = two unsigned N-byte magnitudes; A = N, plus 80h when the
;;               product is negative; BC=&r   out: (BC) = the signed product   fails: long or quad overflow
;;               clobbers: AF BC DE HL IX
;; bly_i_mx, bly_i_my  (internal) the magnitudes, 8 bytes each
;
; Checked multiplication on magnitudes (as z88dk does it, by byte widths):
; - Count the significant bytes of each, na and nb. If na + nb > N + 1 the product is at least 2^(8N): overflow,
;   with no multiplying at all. Otherwise it fits in N + 1 bytes, and the top bit of byte N - 1 settles the rest,
;   allowing exactly 2^(8N-1) when the product is negative.
; - Schoolbook rows, one per significant byte of the narrower operand (the multiplier byte m), each running along
;   the wider one in 16-bit digits X: P[i..i+1] += X*m + carry. X*m + two bytes + a carry byte fits 24 bits exactly.
; - So quad * (something under 256) is one row of at most four digits; quad * quad is at most 8 rows of 4.
; Self-modifying: each row patches the multiplier into `.m` and moves the displacements in `.digit` (from IX, which
; walks the product, back to the digits of X) down by one. Scratch lives at the end of the fragment.

; (A long product is intmul32.asm's, in registers.)

bly_mul_i64:
        ld a,8
        ld (bly_i_mulmag.n),a
        push bc                     ; &r
        push de                     ; &b
        ld de,bly_i_mx
        ld b,a
        call bly_i_copyabs          ; mx = |a|; A = a's top byte
        ld (bly_i_mulmag.sign),a
        pop hl
        ld de,bly_i_my
        ld a,(bly_i_mulmag.n)
        ld b,a
        call bly_i_copyabs          ; my = |b|
        ld hl,bly_i_mulmag.sign
        xor (hl)
        and 80h                     ; the product's sign
        ld hl,bly_i_mulmag.n
        or (hl)
        pop bc
bly_i_mulmag:
        ld (.dst),bc
        ld (.sign),a
        and 0Fh
        ld (.n),a
        ld hl,bly_i_mx
        ld b,a
        call bly_i_sig
        or a
        jp z,.zero
        ld e,a                      ; E = na
        ld hl,bly_i_my
        ld a,(.n)
        ld b,a
        call bly_i_sig
        or a
        jp z,.zero
        ld d,a                      ; D = nb
        add a,e
        dec a                       ; na + nb - 1, against N
        ld hl,.n
        cp (hl)
        jr z,.fits
        jp nc,.ovf
.fits:  ld a,e                      ; the rows run over the narrower operand: y; the digits over the wider: x
        cp d
        ld hl,bly_i_mx
        ld bc,bly_i_my
        jr nc,.ord
        ld hl,bly_i_my
        ld bc,bly_i_mx
        ld a,d
        ld d,e
        ld e,a
.ord:   ld (.yp),bc
        ld a,l                      ; the displacement from P to x (all of it is in this fragment, close by)
        sub .p & 0FFh
        ld (.digit+2),a             ; self-modifying: ld e,(ix+d)
        inc a
        ld (.digit+5),a             ; and ld d,(ix+d+1)
        ld a,e
        inc a
        srl a
        ld (.digits),a              ; 16-bit digits of x
        ld a,d
        ld (.rows),a
        ld hl,0                     ; the product starts at 0: N + 2 bytes, in words
        ld (.p),hl
        ld (.p+2),hl
        ld (.p+4),hl
        ld (.p+6),hl
        ld (.p+8),hl
        ld ix,.p                    ; P + j, for row j
.row:   ld hl,(.yp)
        ld a,(hl)                   ; m = y[j]
        inc hl
        ld (.yp),hl
        or a
        jr z,.next
        ld (.m+1),a                 ; self-modifying: the multiplier
        ld a,(.digits)
        ld (.cnt),a
        push ix
        ld c,0                      ; the carry byte between digits
.digit: ld e,(ix+0)                 ; X = x[2d], x[2d+1] (the displacements are patched)
        ld d,(ix+1)
.m:     ld a,0
        call bly_i_mul16x8          ; A:HL = X * m
        ld b,a
        ld a,(ix+0)
        add a,l
        ld l,a
        ld a,(ix+1)
        adc a,h
        ld h,a
        jr nc,.c1
        inc b
.c1:    ld a,l
        add a,c
        ld (ix+0),a
        ld a,h
        adc a,0
        ld (ix+1),a
        ld a,b
        adc a,0
        ld c,a
        inc ix
        inc ix
        ld hl,.cnt
        dec (hl)
        jr nz,.digit
        ld (ix+0),c                 ; the row's top byte: no earlier row reached it
        pop ix
.next:  inc ix
        ld hl,.digit+2
        dec (hl)
        ld hl,.digit+5
        dec (hl)
        ld hl,.rows
        dec (hl)
        jr nz,.row
        ld a,(.n)                   ; P[N] must be 0
        ld e,a
        ld d,0
        ld hl,.p
        add hl,de
        ld a,(hl)
        or a
        jr nz,.ovf
        dec hl
        ld a,(hl)                   ; P[N-1]
        or a
        jp p,.ok
        ld a,(.sign)                ; the top bit is set: only -2^(8N-1) fits
        or a
        jp p,.ovf
        ld a,(hl)
        cp 80h
        jr nz,.ovf
        ld b,e
        dec b
.low:   dec hl
        ld a,(hl)
        or a
        jr nz,.ovf
        djnz .low
.ok:    ld a,(.sign)
        or a
        jp p,.copy
        ld hl,.p
        ld a,(.n)
        ld b,a
        call bly_i_negn
.copy:  ld hl,.p
        ld de,(.dst)
        ld a,(.n)
        ld c,a
        ld b,0
        ldir
        ret
.zero:  ld hl,(.dst)
        ld a,(.n)
        ld b,a
        xor a
.z:     ld (hl),a
        inc hl
        djnz .z
        ret
.ovf:   ld a,(.n)
        jp bly_ovf_n

.n:      db 0
.sign:   db 0                       ; bit 7: the product is negative
.dst:    dw 0
.yp:     dw 0
.digits: db 0
.rows:   db 0
.cnt:    db 0
.p:      ds 10                      ; the product: N + 2 bytes
bly_i_mx: ds 8
bly_i_my: ds 8
