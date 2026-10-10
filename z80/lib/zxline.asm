;; provides: bly_zx_line
;; needs: bly_zx_plot
;; targets: zx48 test
;; bly_zx_line    in: HL=&block: x0 y0 x1 y1 (ints)  fails: ({x}, {y}) is off the screen, for the first end that is
;;                                                   off                                             clobbers: AF BC DE HL
;; Self-modifying code: it patches the loop it is about to run (direction, the pixel's operation, colours).

; ---- line -----------------------------------------------------------------------------------------------------
; Bresenham as the reference writes it (Zingl's form, both ends plotted). Along the major axis it rounds half up from
; the start, which is this 8-bit accumulator: u = 256 - ceil(major / 2); each step u += minor, and a carry means
; u -= major and a minor step too. (Checked against the reference for every (dx, dy) on the screen.)
; The address and mask walk with the line, and a cell is coloured only when a step enters a new one. Only the loop
; that will run is patched: its direction, the pixel's operation, and the y step, which is inline (inc h, or dec h)
; with the move to the next row of cells out of line. A horizontal line goes a byte at a time, and a vertical
; one has a loop of its own, without the accumulator.

bly_zx_line:                        ; HL = &block: x0, y0, x1, y1
        ld de,.blk
        ld bc,8
        ldir                        ; a copy, to read at leisure
        ld hl,(.blk)
        ld de,(.blk+2)
        call bly_zx_plot.chk
        ld hl,(.blk+4)
        ld de,(.blk+6)
        call bly_zx_plot.chk
        ld a,(.blk+2)
        ld b,a
        ld a,(.blk+6)
        cp b
        jp z,.horiz
        ld a,(ZXG_ATTR_P)
        ld (.lcol+1),a
        ; x's direction
        ld a,(.blk+4)
        ld c,a
        ld a,(.blk)
        sub c                       ; x0 - x1
        jr c,.right
        ld de,2D01h                 ; leftwards: dec l, and rlc c's second byte
        jr .xdir
.right: neg
        ld de,2C09h                 ; rightwards: inc l, rrc c
.xdir:  ld b,a                      ; B = dx
        ld (.xd),de
        ; y's direction: E = the step (inc h down the screen, dec h up), D = the low bits that mean a new row of
        ; cells, HL = what to do then
        ld a,(.blk+6)
        ld c,a
        ld a,(.blk+2)
        sub c                       ; y0 - y1: y falls, so down the screen
        jr c,.yup
        ld hl,.cdown
        ld de,0024h
        jr .ydir
.yup:   neg
        ld hl,.cup
        ld de,0725h
.ydir:  ld c,a                      ; C = ady
        ld (.sc+1),hl
        ld a,e
        ld (.sv),a
        ld a,d
        ld (.sk+1),a
        ld a,b
        cp c
        jr c,.ymajor
        ; x is the major axis
        ld (.xc+1),hl
        ld a,e
        ld (.xv),a
        ld a,d
        ld (.xk+1),a
        ld a,b
        ld (.xmaj+1),a
        ld a,c
        ld (.xmin+1),a
        ld de,(.xd)
        ld a,d
        ld (.xi1),a
        ld (.xi2),a
        ld a,e
        ld (.xr1+1),a
        ld (.xr2+1),a
        call bly_zx_plot.ops
        ld a,d
        ld (.xop1),a
        ld a,e
        ld (.xop2),a
        ld a,b
        call .start
        jp .xplot
.ymajor:                            ; y is the major axis
        ld a,b
        or a
        jr z,.vert
        ld (.yc+1),hl
        ld a,e
        ld (.yv),a
        ld a,d
        ld (.yk+1),a
        ld a,b
        ld (.ymin+1),a
        ld a,c
        ld (.ymaj+1),a
        ld de,(.xd)
        ld a,d
        ld (.yi),a
        ld a,e
        ld (.yr+1),a
        call bly_zx_plot.ops
        ld a,d
        ld (.yop1),a
        ld a,e
        ld (.yop2),a
        ld a,c
        call .start
        jp .yplot

.vert:  ; dx = 0: no accumulator, only the y step
        ld (.vc+1),hl
        ld a,e
        ld (.vv),a
        ld a,d
        ld (.vk+1),a
        call bly_zx_plot.ops
        ld a,d
        ld (.vop1),a
        ld a,e
        ld (.vop2),a
        ld a,c
        call .start
        jp .vplot

.start: ; A = the major -> E = the accumulator, B = pixels (mod 256), HL and C at the start, its cell coloured
        push af
        ld a,(.blk)
        ld c,a
        ld a,(.blk+2)
        ld b,a
        call bly_zx_plot.addr       ; (uses DE)
        ld c,a
        pop af
        ld b,a
        inc b
        srl a
        adc a,0
        neg
        ld e,a
        ; fall into .lattr

.lattr: ; HL = a bitmap byte: its cell gets the colours.  keeps everything but A
        push hl
        ld a,h
        rrca
        rrca
        rrca
        and 3
        or 58h
        ld h,a
.lcol:  ld (hl),0                   ; patched: ATTR_P
        pop hl
        ret

.xloop: ld a,e
.xmin:  add a,0                     ; patched: the minor
        jr c,.xboth
        ld e,a
.xr1:   rrc c                       ; patched: rrc c / rlc c
        jr c,.xwrap
.xplot: ld a,(hl)
.xop1:  or c                        ; patched: or c / nop
.xop2:  xor c                       ; patched: xor c / nop
        ld (hl),a
        djnz .xloop
        ret
.xwrap:
.xi1:   inc l                       ; patched: inc l / dec l
        call .lattr
        jr .xplot
.xboth:
.xmaj:  sub 0                       ; patched: the major
        ld e,a
.xr2:   rrc c                       ; patched
        jr c,.xbw
.xv:    inc h                       ; patched: inc h / dec h
        ld a,h
        and 7
.xk:    cp 0                        ; patched: 0 down, 7 up
        jr nz,.xplot
.xc:    call .cdown                 ; patched: .cdown / .cup
        call .lattr
        jr .xplot
.xbw:
.xi2:   inc l                       ; patched
        call .ystep
        call .lattr
        jr .xplot

.yloop: ld a,e
.ymin:  add a,0                     ; patched: the minor
        jr c,.yboth
        ld e,a
.yv:    inc h                       ; patched: inc h / dec h
        ld a,h
        and 7
.yk:    cp 0                        ; patched
        jr z,.ycross
.yplot: ld a,(hl)
.yop1:  or c                        ; patched
.yop2:  xor c                       ; patched
        ld (hl),a
        djnz .yloop
        ret
.ycross:
.yc:    call .cdown                 ; patched
        call .lattr
        jr .yplot
.yboth:
.ymaj:  sub 0                       ; patched: the major
        ld e,a
.yr:    rrc c                       ; patched
        jr nc,.yv                   ; x stays in its byte: a plain y step
.yi:    inc l                       ; patched
        call .ystep
        call .lattr
        jr .yplot

.vloop:
.vv:    inc h                       ; patched: inc h / dec h
        ld a,h
        and 7
.vk:    cp 0                        ; patched
        jr z,.vcross
.vplot: ld a,(hl)
.vop1:  or c                        ; patched
.vop2:  xor c                       ; patched
        ld (hl),a
        djnz .vloop
        ret
.vcross:
.vc:    call .cdown                 ; patched
        call .lattr
        jr .vplot

.ystep: ; one row in the line's y direction, whole.  clobbers A
.sv:    inc h                       ; patched
        ld a,h
        and 7
.sk:    cp 0                        ; patched
        ret nz
.sc:    jp .cdown                   ; patched

.cdown: ; inc h has just carried out of the pixel rows into TT: the next row of cells is 32 on in L
        ld a,l
        add a,32
        ld l,a
        ret c                       ; into the next third, which inc h has already reached
        ld a,h
        sub 8
        ld h,a
        ret

.cup:   ; dec h has just borrowed from TT: the row of cells above is 32 back in L
        ld a,l
        sub 32
        ld l,a
        ret c                       ; into the third above, which dec h has already reached
        ld a,h
        add a,8
        ld h,a
        ret

.horiz: ; y0 = y1: a byte at a time, from the left end C to the right end B
        ld a,(.blk)
        ld c,a
        ld a,(.blk+4)
        ld b,a
        cp c
        jr nc,.h1
        ld b,c
        ld c,a
.h1:    ld a,b                      ; the last byte's mask: FFh << (7 - (right & 7)), which is -mask(right)
        and 7
        add a,low bly_zx_plot.masks
        ld e,a
        adc a,high bly_zx_plot.masks
        sub e
        ld d,a
        ld a,(de)
        neg
        ld (.hlast+1),a
        ld a,c                      ; the bytes after the first: (right >> 3) - (left >> 3)
        rrca
        rrca
        rrca
        and 1Fh
        ld e,a
        ld a,b
        rrca
        rrca
        rrca
        and 1Fh
        sub e
        push af
        call bly_zx_plot.opsd
        ld a,d
        ld (.hop1),a
        ld (.hop3),a
        ld a,e
        ld (.hop2),a
        ld (.hop4),a
        ld a,(ZXG_ATTR_P)
        ld (.hcol1+1),a
        ld (.hcol2+1),a
        ld a,(.blk+2)
        ld b,a
        call bly_zx_plot.addr       ; HL at the left end, A = its mask
        add a,a
        dec a
        ld d,a                      ; the first byte's mask: FFh >> (left & 7)
        ld a,h
        rrca
        rrca
        rrca
        and 3
        or 58h
        ld e,a                      ; E = the attributes' high byte
        pop af
        ld b,a
        or a
        jr z,.hlast
.hloop: ld a,(hl)
.hop1:  or d                        ; patched: or d / nop
.hop2:  xor d                       ; patched: xor d / nop
        ld (hl),a
        ld a,h
        ld h,e
.hcol1: ld (hl),0                   ; patched: ATTR_P
        ld h,a
        inc l
        ld d,0FFh
        djnz .hloop
.hlast: ld a,0                      ; patched: the last byte's mask
        and d
        ld d,a
        ld a,(hl)
.hop3:  or d                        ; patched
.hop4:  xor d                       ; patched
        ld (hl),a
        ld h,e
.hcol2: ld (hl),0                   ; patched
        ret

.blk:   ds 8
.xd:    dw 0

