;; provides: bly_zx_circle
;; needs: bly_zx_plot bly_fail
;; targets: zx48 test
;; bly_zx_circle  in: HL=&block: x y r (ints)        fails: a circle needs a radius of at least 0        clobbers: AF BC DE HL IX
;; Self-modifying code: it patches the pixel's operation and the colours into its plotting code at each call.

; ---- circle ---------------------------------------------------------------------------------------------------
; The reference's midpoint circle: x = r, y = 0, err = 1 - r; while x >= y: the eight points (deduplicated, clipped),
; y += 1, then err += 2y + 1 if err < 0, else x -= 1 and err += 2(y - x) + 1. err needs 17 bits at r = 32767, so it is
; kept halved: err = 2e + p, with p flipping every step (both increments are odd), e += y + p or (y - x) + p, and
; e's sign is err's. (e fits an int for every r: it stays in -32579..23138.)
; A step's points are two groups of four: A = (cx +- x, cy +- y) and B = (cx +- y, cy +- x), B only when x <> y, and
; a zero offset giving one value, not two. Those are exactly the reference's distinct points. Each group is two rows
; by two columns, so a step works out at most four rows and four columns, then makes the eight plots from them.
; Clipping: c + a past 32767 wraps negative, which the clip refuses anyway, but c - a below -32768 would wrap onto
; the screen, so the subtractions check V.
; Exact shortcuts. Nothing is drawn when the bounding box misses the screen. Otherwise only offsets in a window can
; land on the screen: Lx..Mx for the columns (Mx = max(255 - cx, cx), Lx the distance from cx to 0..255) and Ly..My
; for the rows. Group A needs x <= Mx and y <= My, group B y <= Mx and x <= My, and y <= x, so both need
; y <= min(Mx, My); likewise both need x >= max(Lx, Ly). y only grows and x only falls, so the loop stops at the
; first step outside those. A circle wholly on the screen (r <= 87) takes a fast path without clipping.

bly_zx_circle:                      ; HL = &block: cx, cy, r
        ld de,.cx
        ld bc,6
        ldir
        ld de,(.r)
        bit 7,d
        jp nz,.neg
        ld (.x),de
        ld hl,(.cx)                 ; the bounding box: cx + r < 0?
        or a
        adc hl,de
        jp pe,.bb1                  ; past 32767
        ret m
.bb1:   ld hl,(.cx)                 ; cx - r > 255?
        or a
        sbc hl,de
        jp pe,.bb2                  ; below -32768
        jp m,.bb2
        ld a,h
        or a
        ret nz
.bb2:   ld hl,(.cy)                 ; cy + r < 0?
        or a
        adc hl,de
        jp pe,.bb3
        ret m
.bb3:   ld hl,(.cy)                 ; cy - r > 175?
        or a
        sbc hl,de
        jp pe,.bb4
        jp m,.bb4
        ld a,h
        or a
        ret nz
        ld a,l
        cp 176
        ret nc
.bb4:   ld hl,(.cx)                 ; the window of steps that can show anything
        ld de,255
        call .win
        ld (.ystop),hl              ; Mx
        ld (.xstop),de              ; Lx
        ld hl,(.cy)
        ld de,175
        call .win                   ; HL = My, DE = Ly
        push hl
        ld hl,(.xstop)              ; xstop = max(Lx, Ly)
        or a
        sbc hl,de
        jr nc,.w2
        ld (.xstop),de
.w2:    pop de                      ; ystop = min(Mx, My)
        ld hl,(.ystop)
        or a
        sbc hl,de
        jr c,.init
        ld (.ystop),de
.init:  ld hl,0
        ld (.y),hl
        ld de,(.r)
        inc hl
        or a
        sbc hl,de                   ; 1 - r
        ld a,l
        and 1
        ld (.p),a
        sra h
        rr l
        ld (.e),hl                  ; floor((1 - r) / 2)
        call bly_zx_plot.opsd       ; the pixel's operation, and the colours
        ld a,d
        ld (.op1a),a
        ld (.op1b),a
        ld a,e
        ld (.op2a),a
        ld (.op2b),a
        ld a,(ZXG_ATTR_P)
        ld (.cola+1),a
        ld (.colb+1),a
        ld a,d
        ld (.fop1),a
        ld a,e
        ld (.fop2),a
        ld a,(ZXG_ATTR_P)
        ld (.fcol+1),a
        ; wholly on the screen (r <= 87, r <= cx <= 255 - r, r <= cy <= 175 - r)? Then the fast way
        ld a,(.r+1)
        ld hl,.cx+1
        or (hl)
        ld hl,.cy+1
        or (hl)
        jr nz,.gloop
        ld a,(.r)
        cp 88
        jr nc,.gloop
        ld b,a
        ld a,(.cx)
        cp b
        jr c,.gloop
        add a,b
        jr c,.gloop
        ld a,(.cy)
        cp b
        jr c,.gloop
        add a,b
        jr c,.gloop
        cp 176
        jp c,.fast

.gloop: ld hl,(.ystop)
        ld de,(.y)
        or a
        sbc hl,de
        ret c                       ; y > ystop: nothing more can be seen
        ld hl,(.x)
        ld de,(.xstop)
        or a
        sbc hl,de
        ret c                       ; x < xstop: likewise
        call .gstep
        ld hl,(.x)
        ld de,(.y)
        or a
        sbc hl,de
        jp p,.gloop                 ; while x >= y
        ret

.gstep: ; one step from (x, y): its points, clipped and deduplicated; then y, x, e and p move on. A group's columns
        ; come first, and its rows are worked out only if a column is on the screen.
        ld de,(.x)                  ; group A: columns cx + x, and cx - x unless x = 0
        ld hl,(.cx)
        add hl,de
        call .colv
        ld (.qa+2),a
        ld a,l
        ld (.qa+3),a
        xor a
        ld (.qa+4),a
        ld a,d
        or e
        jr z,.g1
        ld hl,(.cx)
        or a
        sbc hl,de
        ld a,0
        call po,.colv
        ld (.qa+4),a
        ld a,l
        ld (.qa+5),a
.g1:    ld a,(.qa+2)
        ld hl,.qa+4
        or (hl)
        jr z,.g2                    ; neither column is on the screen
        ld de,(.y)                  ; rows cy + y, and cy - y unless y = 0
        ld hl,(.cy)
        add hl,de
        call .rowv
        ld (.qa),a
        ld a,0FFh
        ld (.qa+1),a
        ld a,d
        or e
        jr z,.g1a
        ld hl,(.cy)
        or a
        sbc hl,de
        ld a,0FFh
        call po,.rowv
        ld (.qa+1),a
.g1a:   ld ix,.qa
        call .quad
.g2:    ld hl,(.x)                  ; group B, unless x = y (then it is group A again)
        ld de,(.y)
        or a
        sbc hl,de
        jr z,.next
        ld hl,(.cx)                 ; columns cx + y, and cx - y unless y = 0
        add hl,de
        call .colv
        ld (.qb+2),a
        ld a,l
        ld (.qb+3),a
        xor a
        ld (.qb+4),a
        ld a,d
        or e
        jr z,.g3
        ld hl,(.cx)
        or a
        sbc hl,de
        ld a,0
        call po,.colv
        ld (.qb+4),a
        ld a,l
        ld (.qb+5),a
.g3:    ld a,(.qb+2)
        ld hl,.qb+4
        or (hl)
        jr z,.next
        ld de,(.x)                  ; rows cy + x and cy - x (x > y >= 0 here, so x <> 0)
        ld hl,(.cy)
        add hl,de
        call .rowv
        ld (.qb),a
        ld hl,(.cy)
        or a
        sbc hl,de
        ld a,0FFh
        call po,.rowv
        ld (.qb+1),a
        ld ix,.qb
        call .quad
.next:  ld hl,(.y)                  ; y += 1; e += y + p, or after x -= 1, e += (y - x) + p; p flips
        inc hl
        ld (.y),hl
        ld de,(.e)
        bit 7,d
        jr nz,.add                  ; err < 0
        ld de,(.x)
        dec de
        ld (.x),de
        or a
        sbc hl,de
.add:   ld de,(.e)
        ld a,(.p)
        rra
        adc hl,de
        ld (.e),hl
        ld a,(.p)
        xor 1
        ld (.p),a
        ret

.fast:  ; The whole circle is on the screen, so nothing is clipped and x, y and e fit bytes (e stays in -85..63 for
        ; r <= 87, so 8-bit sums give its sign exactly). Step 0 goes the general way; after it 0 < y, and while
        ; y < x all eight points are distinct, so each step is four rows by four columns, kept as records that move
        ; a pixel at a time: rows cy + y up and cy - y down every step, columns cx + y right and cx - y left; and when
        ; x falls, rows cy + x down and cy - x up, columns cx + x left and cx - x right.
        call .gstep
        ld hl,(.x)
        ld de,(.y)
        or a
        sbc hl,de
        ret m                       ; r = 0
        ld a,(.x)
        ld (.fx),a
        ld c,a
        ld a,(.y)
        ld (.fy),a
        ld b,a
        ld a,(.e)
        ld (.fe),a
        ld a,(.cy)                  ; the rows: cy + y, cy - y, cy + x, cy - x
        add a,b
        ld hl,.r1
        call .rrec
        ld a,(.cy)
        sub b
        ld hl,.r2
        call .rrec
        ld a,(.cy)
        add a,c
        ld hl,.r3
        call .rrec
        ld a,(.cy)
        sub c
        ld hl,.r4
        call .rrec
        ld a,(.cx)                  ; the columns: cx + x, cx - x, cx + y, cx - y
        add a,c
        ld hl,.c1
        call .crec
        ld a,(.cx)
        sub c
        ld hl,.c2
        call .crec
        ld a,(.cx)
        add a,b
        ld hl,.c3
        call .crec
        ld a,(.cx)
        sub b
        ld hl,.c4
        call .crec
.floop: ld a,(.fx)
        ld c,a
        ld a,(.fy)
        cp c
        jp z,.flast                 ; y = x: the last step, and its group B is group A again
        ret nc
        call .fgrpa
        ld bc,(.r3)                 ; group B: rows cy +- x, columns cx +- y
        ld a,(.r3+2)
        ld e,a
        ld hl,.c3
        call .fpt
        ld hl,.c4
        call .fpt
        ld bc,(.r4)
        ld a,(.r4+2)
        ld e,a
        ld hl,.c3
        call .fpt
        ld hl,.c4
        call .fpt
        ld hl,.fy                   ; y += 1
        inc (hl)
        ld hl,.r1
        call .rup
        ld hl,.r2
        call .rdown
        ld hl,.c3
        call .cright
        ld hl,.c4
        call .cleft
        ld a,(.fe)                  ; e += y + p, or after x -= 1, e += (y - x) + p
        or a
        ld a,(.fy)
        jp m,.fadd
        ld hl,.fx
        dec (hl)
        sub (hl)
        push af
        ld hl,.r3
        call .rdown
        ld hl,.r4
        call .rup
        ld hl,.c1
        call .cleft
        ld hl,.c2
        call .cright
        pop af
.fadd:  ld b,a
        ld a,(.p)
        rra
        ld a,(.fe)
        adc a,b
        ld (.fe),a
        ld a,(.p)
        xor 1
        ld (.p),a
        jp .floop

.flast:
.fgrpa: ; group A: rows cy +- y, columns cx +- x
        ld bc,(.r1)
        ld a,(.r1+2)
        ld e,a
        ld hl,.c1
        call .fpt
        ld hl,.c2
        call .fpt
        ld bc,(.r2)
        ld a,(.r2+2)
        ld e,a
        ld hl,.c1
        call .fpt
        ld hl,.c2
        jp .fpt

.fpt:   ; B = a row's bitmap high byte, C = its bits of L, E = its attributes' high byte; HL = a column record
        ld a,(hl)
        inc hl
        or c
        ld d,(hl)
        ld l,a
        ld h,b
        ld a,(hl)
.fop1:  or d                        ; patched: or d / nop
.fop2:  xor d                       ; patched: xor d / nop
        ld (hl),a
        ld h,e
.fcol:  ld (hl),0                   ; patched: ATTR_P
        ret

.rrec:  ; A = a row 0..175, HL = its record: +0 its bits of L, +1 the bitmap high byte, +2 the attributes' high byte
        push bc
        ld c,a
        ld a,175
        sub c
        ld b,a
        rra
        scf
        rra
        or a
        rra                         ; 010 TT RRR
        ld c,a
        xor b
        and 0F8h
        xor b
        ld b,a                      ; 010 TT SSS
        ld a,c
        rrca
        rrca
        rrca                        ; RRR 010 TT
        ld c,a
        and 0E0h
        ld (hl),a
        inc hl
        ld (hl),b
        inc hl
        ld a,c
        and 3
        or 58h
        ld (hl),a
        pop bc
        ret

.crec:  ; A = a column, HL = its record (as .colrec), keeping BC
        push bc
        call .colrec
        pop bc
        ret

.rup:   ; HL = a row record: one pixel row up the screen
        inc hl
        ld a,(hl)
        dec (hl)
        and 7
        ret nz                      ; within the row of cells
        dec hl
        ld a,(hl)
        sub 32
        ld (hl),a
        inc hl
        jr c,.rup3                  ; into the third above, which dec has already reached
        ld a,(hl)
        add a,8
        ld (hl),a
        ret
.rup3:  inc hl
        dec (hl)                    ; and the attributes are a third up too
        ret

.rdown: ; HL = a row record: one pixel row down
        inc hl
        inc (hl)
        ld a,(hl)
        and 7
        ret nz
        dec hl
        ld a,(hl)
        add a,32
        ld (hl),a
        inc hl
        jr c,.rdn3                  ; into the next third, which inc has already reached
        ld a,(hl)
        sub 8
        ld (hl),a
        ret
.rdn3:  inc hl
        inc (hl)
        ret

.cright: ; HL = a column record: one pixel right
        inc hl
        rrc (hl)
        ret nc
        dec hl
        inc (hl)
        ret

.cleft: inc hl
        rlc (hl)
        ret nc
        dec hl
        dec (hl)
        ret

.neg:   ld hl,.negmsg
        jp bly_fail
.negmsg: db "a circle needs a radius of at least 0",0

.win:   ; HL = a centre c, DE = the side s (255 or 175) -> HL = M = max(s - c, c), at most 7FFFh; DE = L, the distance
        ; from c to 0..s. Points made from this centre are on the screen only with offsets in L..M.
        bit 7,h
        jr nz,.wneg
        push hl                     ; c >= 0
        ex de,hl
        or a
        sbc hl,de                   ; s - c
        jr c,.wpast
        pop de                      ; 0 <= c <= s: L = 0, M = the larger of s - c and c
        push hl
        or a
        sbc hl,de
        pop hl
        jr nc,.w1
        ex de,hl
.w1:    ld de,0
        ret
.wpast: xor a                       ; c > s: L = c - s, M = c
        sub l
        ld e,a
        sbc a,a
        sub h
        ld d,a
        pop hl
        ret
.wneg:  ex de,hl                    ; c < 0: L = -c (the bounding box has refused c = -32768), M = s - c
        push de
        or a
        sbc hl,de
        jp po,.wn1
        ld hl,7FFFh
.wn1:   ex (sp),hl
        ex de,hl
        ld hl,0
        or a
        sbc hl,de
        ex de,hl
        pop hl
        ret

.rowv:  ; HL = a row, computed without overflow: A = it if 0..175, else FFh.  keeps DE
        ld a,h
        or a
        jr nz,.rv0
        ld a,l
        cp 176
        ret c
.rv0:   ld a,0FFh
        ret

.colv:  ; HL = a column, likewise: A = 1 if it is 0..255 (L), else 0.  keeps DE
        ld a,h
        or a
        ld a,0
        ret nz
        inc a
        ret

.quad:  ; IX = a group: rows at +0 and +1 (FFh: none), columns at +2/+3 and +4/+5 (flag, value). Plots every pair.
        xor a
        ld (.cm1),a
        ld (.cm2),a
        or (ix+2)
        jr z,.qc2
        ld a,(ix+3)
        ld hl,.cb1
        call .colrec
.qc2:   ld a,(ix+4)
        or a
        jr z,.qc3
        ld a,(ix+5)
        ld hl,.cb2
        call .colrec
.qc3:   ld a,(.cm1)
        ld hl,.cm2
        or (hl)
        ret z                       ; neither column is on the screen
        ld a,(ix+0)
        call .qrow
        ld a,(ix+1)
.qrow:  cp 0FFh
        ret z
        ld c,a                      ; A = a row: B = its bitmap high byte, C = its bits of L, E = its attributes' high
        ld a,175
        sub c
        ld b,a
        rra
        scf
        rra
        or a
        rra                         ; 010 TT RRR
        ld c,a
        xor b
        and 0F8h
        xor b
        ld b,a                      ; 010 TT SSS
        ld a,c
        rrca
        rrca
        rrca                        ; RRR 010 TT
        ld c,a
        and 3
        or 58h
        ld e,a
        ld a,c
        and 0E0h
        ld c,a
        ld a,(.cm1)                 ; the first column
        or a
        jr z,.qr2
        ld d,a
        ld a,(.cb1)
        or c
        ld l,a
        ld h,b
        ld a,(hl)
.op1a:  or d                        ; patched: or d / nop
.op2a:  xor d                       ; patched: xor d / nop
        ld (hl),a
        ld h,e
.cola:  ld (hl),0                   ; patched: ATTR_P
.qr2:   ld a,(.cm2)                 ; the second
        or a
        ret z
        ld d,a
        ld a,(.cb2)
        or c
        ld l,a
        ld h,b
        ld a,(hl)
.op1b:  or d                        ; patched
.op2b:  xor d                       ; patched
        ld (hl),a
        ld h,e
.colb:  ld (hl),0                   ; patched
        ret

.colrec: ; A = a column 0..255, HL = its record: +0 its byte in the row (x >> 3), +1 its mask
        ld c,a
        rrca
        rrca
        rrca
        and 1Fh
        ld (hl),a
        inc hl
        ld a,c
        and 7
        add a,low bly_zx_plot.masks
        ld e,a
        adc a,high bly_zx_plot.masks
        sub e
        ld d,a
        ld a,(de)
        ld (hl),a
        ret

.cx:    dw 0
.cy:    dw 0
.r:     dw 0
.x:     dw 0
.y:     dw 0
.e:     dw 0
.ystop: dw 0
.xstop: dw 0
.p:     db 0
.qa:    ds 6
.qb:    ds 6
.cb1:   db 0
.cm1:   db 0
.cb2:   db 0
.cm2:   db 0
.fx:    db 0
.fy:    db 0
.fe:    db 0
.r1:    ds 3
.r2:    ds 3
.r3:    ds 3
.r4:    ds 3
.c1:    ds 2
.c2:    ds 2
.c3:    ds 2
.c4:    ds 2
