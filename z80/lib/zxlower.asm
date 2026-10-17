;; provides: bly_zx_lower bly_zx_upper bly_zx_lat
;; needs: bly_putc bly_col bly_fail bly_pr_cstr bly_pr_i16 bly_zx_chan_k
;; targets: zx48
;; print #0 and #1: the lower screen's two rows, through the ROM's channel K (zxgfx.py's lat and lout are the
;; meaning). The generated code brackets each piece of such a print (an item, a zone, the newline) with
;; bly_zx_lower and bly_zx_upper, after working the item out, so a failure working it out is printed upstairs, as
;; output, like any other. The ROM grows the lower screen upwards when it fills; Barley keeps it two lines, so
;; the bytes go through zxl_putc, which reads the ROM's own position (S_POSNL) and fails first.
;; bly_zx_lower  channel K; print's column the lower screen's (for the zones); bly_putc's first three bytes kept
;;               and a jump to zxl_putc put in their place                               clobbers: AF BC DE HL
;; bly_zx_upper  all three put back, and stream 2 again                                 clobbers: AF BC DE HL
;; bly_zx_lat    in: HL=r DE=c (ints)   print at, on the lower screen (rows 0 and 1)    clobbers: AF BC DE HL
;;               fails: print at ({r}, {c}) is off the lower screen

ZXL_S_POSNL equ 5C8Ah               ; the lower screen's position: 33 - its column, then its line, which with two
                                    ; lines is 24 for row 22, 23 for row 23, 22 for pending below the bottom
bly_zx_lower:
        call bly_zx_chan_k          ; channel K, a key not yet looked at kept for key()
        ld hl,(bly_col)
        ld (.col),hl
        ld a,(ZXL_S_POSNL)
        ld l,a
        ld a,33
        sub l
        ld l,a
        ld h,0
        ld (bly_col),hl             ; the lower screen's column, 0..32
        ld hl,bly_putc
        ld de,.keep
        ld bc,3
        ldir
        ld a,0C3h                   ; jp zxl_putc
        ld (bly_putc),a
        ld hl,zxl_putc
        ld (bly_putc+1),hl
        ret
.col:   dw 0
.keep:  ds 3

bly_zx_upper:
        ld hl,bly_zx_lower.keep
        ld de,bly_putc
        ld bc,3
        ldir
        ld hl,(bly_zx_lower.col)
        ld (bly_col),hl
        ld a,2
        jp 1601h                    ; CHAN-OPEN: stream 2, the screen

zxl_putc:                           ; bly_putc, on the lower screen: A = the byte
        ld hl,(ZXL_S_POSNL)         ; L = 33 - the column, H = the line
        cp 10
        jr nz,.char
        ld a,h
        cp 23
        jr c,.grow                  ; a newline while pending below the bottom line
        ld a,13
        rst 10h
        ret
.char:  cp 32                       ; a control code or a keyword token prints as ?, as bly_putc's do
        jr c,.q
        cp 0A5h
        jr c,.out
.q:     ld a,'?'
.out:   ld b,a
        ld a,h
        cp 23
        jr c,.grow                  ; pending below: this would be a third line
        jr nz,.ok                   ; row 22 can wrap onto row 23
        ld a,l
        cp 2
        jr c,.grow                  ; column 32 of the bottom line: wrapping would be a third line
.ok:    ld a,b
        rst 10h
        ret
.grow:  call bly_zx_upper           ; the failure's words are output, upstairs
        ld hl,.msg
        jp bly_fail
.msg:   db "print would grow the lower screen past its two lines",0

bly_zx_lat:
        ld a,h
        or d
        jr nz,.bad
        ld a,l
        cp 2
        jr nc,.bad
        ld a,e
        cp 32
        jr nc,.bad
        push de
        push hl
        call bly_zx_chan_k          ; channel K, AT row, column, and back
        ld a,22
        rst 10h
        pop hl
        ld a,l
        rst 10h
        pop de
        ld a,e
        rst 10h
        ld a,2
        jp 1601h
.bad:   push de
        push hl
        ld hl,.m1
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        ld hl,.m2
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        ld hl,.m3
        jp bly_fail
.m1:    db "print at (",0
.m2:    db ", ",0
.m3:    db ") is off the lower screen",0
