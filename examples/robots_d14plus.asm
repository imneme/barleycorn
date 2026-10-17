;; provides: move_on move_back mark sweep rb_views
;; targets: zx48 cpm
;; robots_d14+'s three hot loops in Z80, each the Barley function of its name (robots_d14plus.bly), whose body is its
;; twin. Arrays come as views (ABI.md section 1): the register holds the view's address, and the view is the data's
;; address, then its length. They trust what main checks as it reads the robots: every x below its floor's width,
;; every y below its height, and n no more than the arrays hold. IXL and IXH are undocumented, and every Z80 has them.
;; move_on    in: HL = &xs, DE = &vs (byte[]), BC = n, IX = m   each xs[i] = (xs[i] + vs[i]) mod m, for i below n
;; move_back  in: the same                                      each xs[i] = (xs[i] - vs[i]) mod m
;; mark       in: HL = &xs, DE = &ys (byte[]), BC = &frame (byte[]), IX = n
;;            each robot's bit in the frame, 13 bytes a row: frame[ys[i] * 13 + xs[i] / 8] |= 80h >> (xs[i] & 7)
;; sweep      in: HL = &frame (byte[]), DE = &rows (word[])
;;            the frame onto the screen, 13 bytes to each address in rows, and the frame cleared as it goes
;; clobbers: AF BC DE HL IX

rb_views:                           ; HL = &view, DE = &view: HL, DE = their data's addresses
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        ex de,hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        ex de,hl
        ret

move_on:
        call rb_views
        bit 7,b                     ; n below 1: nothing, as the twin's for does nothing
        ret nz
        ld a,b
        or c
        ret z
.loop:  ld a,(de)
        add a,(hl)                  ; below 2m, so a byte
        cp ixl
        jr c,.ok
        sub ixl
.ok:    ld (hl),a
        inc hl
        inc de
        dec bc
        ld a,b
        or c
        jr nz,.loop
        ret

move_back:
        call rb_views
        bit 7,b
        ret nz
        ld a,b
        or c
        ret z
.loop:  ld a,ixl
        add a,(hl)                  ; x + m - v: from x + 1 to x + m, never below 0
        ex de,hl
        sub (hl)
        ex de,hl
        cp ixl
        jr c,.ok
        sub ixl
.ok:    ld (hl),a
        inc hl
        inc de
        dec bc
        ld a,b
        or c
        jr nz,.loop
        ret

mark:
        call rb_views
        ld (.xs),hl
        ld (.ys),de
        ld h,b
        ld l,c
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        ld (.frame),hl
        ld a,ixh
        bit 7,a
        ret nz
        or ixl
        ret z
.loop:  ld hl,(.ys)
        ld e,(hl)                   ; y
        inc hl
        ld (.ys),hl
        ld d,0
        ld h,d
        ld l,e
        add hl,hl
        add hl,de
        add hl,hl
        add hl,hl
        add hl,de                   ; y * 13
        ld de,(.frame)
        add hl,de
        ex de,hl                    ; DE = the row's first byte
        ld hl,(.xs)
        ld a,(hl)                   ; x
        inc hl
        ld (.xs),hl
        ld c,a
        rrca
        rrca
        rrca
        and 1Fh                     ; x / 8
        add a,e
        ld e,a
        adc a,d
        sub e
        ld d,a                      ; DE = its byte
        ld a,c
        and 7
        ld hl,.bits
        add a,l
        ld l,a
        adc a,h
        sub l
        ld h,a
        ld a,(de)
        or (hl)
        ld (de),a
        dec ix
        ld a,ixh
        or ixl
        jr nz,.loop
        ret
.xs:    dw 0
.ys:    dw 0
.frame: dw 0
.bits:  db 80h, 40h, 20h, 10h, 8, 4, 2, 1

sweep:
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        push hl                     ; the frame's data
        ex de,hl
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; DE = the rows' data
        inc hl
        ld b,(hl)                   ; B = how many rows (103: the length's low byte is enough)
        push de
        pop ix                      ; IX walks the rows' addresses
        pop de                      ; DE walks the frame
        ld a,b
        or a
        ret z
.row:   ld l,(ix+0)
        ld h,(ix+1)                 ; HL = where the row goes on the screen
        inc ix
        inc ix
        rept 13
        ld a,(de)
        ld (hl),a
        xor a
        ld (de),a
        inc de
        inc hl
        endr
        djnz .row
        ret
