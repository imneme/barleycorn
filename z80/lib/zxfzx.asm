;; provides: bly_zx_fzx bly_zx_fzx_on bly_zx_fzx_off bly_zx_fzx_at
;; needs: bly_putc bly_col bly_fail bly_pr_cstr bly_pr_i16
;; targets: zx48
;; print #4: proportional text in an FZX font, through stream 4 and RST 10, as BASIC's PRINT #4 does it. The
;; drawing is Einar Saukas's FZX driver (FZXdriver.asm, copyright (c) 2013 Einar Saukas; "you can freely use the
;; FZX driver code in your programs ... or adapt this code according to your needs"), adapted; the font format is
;; Andrew Owen's (FZX v1.0, copyright (c) 2013 Andrew Owen, an open standard). zxgfx.py says what it draws.
;; Adapted: the font is a variable, not an address fixed at assembly; the driver's Out of screen (REPORT-5) is our
;; failure, in words, and so is a line wrapped past 0 (which it would take for 255 and report B for); and nothing
;; is written past x 255 or below the screen. (The stock driver writes three bytes
;; a row counting only the low byte of the address, so at the right edge the third can land on the next text
;; row's left, and below row 191 it goes on into the attributes. Only a font's stray bits, past a character's
;; width or below its line, are ever there.)
;; bly_zx_fzx      in: HL = the font (a constant table, which the checker has seen is one); the first time, the
;;                 channel too, made below PROG and given stream 4, as the driver's own installer makes it
;;                                                                                       clobbers: AF BC DE HL
;; bly_zx_fzx_on   stream 4, and bly_putc patched to send bytes on as they are (a newline as ENTER, a control
;;                 code as ?), keeping print's column; fails: print #4 needs a font: fzx(font) first
;; bly_zx_fzx_off  all put back, and stream 2 again                                      clobbers: AF BC DE HL
;; bly_zx_fzx_at   in: HL = y, DE = x (ints, pixels)   fails: print #4; at ({y}, {x}) is off the screen (192 by
;;                 256 pixels)                                                           clobbers: AF BC DE HL

bly_zx_fzx:
        ld (zxf_font),hl
        ld a,(zxf_made)
        or a
        ret nz
        inc a
        ld (zxf_made),a
        ld hl,(5C53h)               ; PROG: the channel goes just below the BASIC program (the driver's DRIVER)
        dec hl
        ld bc,5
        push bc
        call 1655h                  ; MAKE-ROOM
        pop bc
        ld hl,.chan+4
        lddr
        ld hl,(5C4Fh)               ; CHANS
        ex de,hl
        inc hl
        inc hl                      ; HL = the new channel + 1
        sbc hl,de                   ; (carry clear from MAKE-ROOM) its offset from CHANS, + 1
        ld (5C10h+(4+3)*2),hl       ; stream 4's entry in STRMS
        ret
.chan:  dw zxf_start                ; the channel: output, input (the ROM's report J), type S
        dw 15C4h
        db 'S'

bly_zx_fzx_on:
        ld hl,(zxf_font)
        ld a,h
        or l
        jr nz,.font
        ld hl,.none
        jp bly_fail
.font:  ld hl,(bly_col)
        ld (.col),hl
        ld a,4
        call 1601h                  ; CHAN-OPEN: stream 4
        ld hl,bly_putc
        ld de,.keep
        ld bc,3
        ldir
        ld a,0C3h                   ; jp zxf_putc
        ld (bly_putc),a
        ld hl,zxf_putc
        ld (bly_putc+1),hl
        ret
.col:   dw 0
.keep:  ds 3
.none:  db "print #4 needs a font: fzx(font) first",0

bly_zx_fzx_off:
        ld hl,bly_zx_fzx_on.keep
        ld de,bly_putc
        ld bc,3
        ldir
        ld hl,(bly_zx_fzx_on.col)
        ld (bly_col),hl
        ld a,2
        jp 1601h                    ; CHAN-OPEN: stream 2

zxf_putc:                           ; bly_putc, for print #4: A = the byte
        cp 10
        jr nz,.char
        ld a,13
        rst 10h
        ret
.char:  cp 32
        jr nc,.out
        ld a,'?'                    ; a control code would be the driver's AT: ?, as print shows one anywhere
.out:   rst 10h
        ret

bly_zx_fzx_at:
        ld a,h
        or a
        jr nz,.bad
        ld a,l
        cp 192
        jr nc,.bad
        ld a,d
        or a
        jr nz,.bad
        push de
        push hl
        ld a,4
        call 1601h
        ld a,22                     ; AT y, x: the driver takes them as pixels
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
.m1:    db "print #4; at (",0
.m2:    db ", ",0
.m3:    db ") is off the screen (192 by 256 pixels)",0

zxf_below:                          ; the driver's Out of screen: the line can't hold another character. This is
        ld hl,6                     ; inside RST 10, whose PRINT-A-2 did EXX and saved BASIC's HL' (under the
        add hl,sp                   ; driver's two pushes and CALL-SUB's return), so put that back and EXX back,
        ld a,(hl)                   ; as its ending would have; then the failure is an ordinary one. (Without
        inc hl                      ; it, BASIC came back with "C Nonsense in BASIC": zxrun's report check
        ld h,(hl)                   ; saw it)
        ld l,a
        exx
        call bly_zx_fzx_off
        ld hl,.m
        jp bly_fail
.m:     db "print #4 would go below the screen",0

zxf_font: dw 0
zxf_made: db 0

; -- the driver: FZXdriver.asm's START, adapted (see above) ----------------------------------------------------
zxf_start:
        ld hl,zxf_flag              ; initial address of local variables
        dec (hl)                    ; check P_FLAG value by decrementing it
        jp m,.chk_at                ; expecting a regular character?
        jr z,.get_col               ; expecting the AT column?
.get_lin:
        cpl
        add a,192                   ; now A = 191 - char
        inc hl
.get_col:
        inc hl
        ld (hl),a
        ret
.chk_at:
        cp 22                       ; specified keyword 'AT'?
        jr nz,.chk_cr
        ld (hl),2                   ; change P_FLAG to expect line value next time
        ret
.chk_cr:
        inc (hl)                    ; increment P_FLAG to restore previous value
        inc hl
        ld bc,(zxf_font)            ; (adapted: the font is a variable)
        push bc
        pop ix
        cp 13
        jp z,.newline
.chk_char:
        dec a                       ; now A = char - 1
        cp (ix+2)                   ; compare with lastchar
        jr nc,.undef_char
        sub 31                      ; now A = char - 32
        jr nc,.print_char
.undef_char:
        ld a,'?'-32                 ; print '?' instead of invalid character
.print_char:
        inc a                       ; now A = char - 31
        ld l,a
        ld h,0
        ld d,h
        ld e,l
        add hl,hl
        add hl,de                   ; now HL = (char - 31) * 3
        add hl,bc                   ; now HL references offset/kern in char table
        ld e,(hl)
        inc hl
        ld a,(hl)
        and 63
        ld d,a                      ; now DE = offset
        xor (hl)
        rlca
        rlca
        ld c,a                      ; now C = kern
        push hl
        add hl,de
        dec hl                      ; now HL = char definition address
        ex (sp),hl                  ; now HL references offset/kern in char table
        inc hl                      ; now HL references shift/width in char table
        xor a
        rld                         ; now A = char shift
        push af
        rld                         ; now A = (width - 1)
        ld (.width1+1),a
        cp 8                        ; check if char width is larger than 8 bits
        rld                         ; restore char shift/width
        ld de,000Eh                 ; same as "LD C,0"
        jr c,.narrow_char
        ld de,234Eh                 ; same as "LD C,(HL)" and "INC HL"
.narrow_char:
        ld (.smc),de                ; self-modify code to handle narrow/large chars
        inc hl                      ; now HL references next char offset
        ld a,(hl)                   ; now A = LSB of next char offset
        add a,l
        ld e,a                      ; now E = LSB of next char definition address
        ld hl,zxf_col
        ld a,(hl)
        sub c                       ; move left number of pixels specified by kern
        jr nc,.on_screen            ; stop moving if it would fall outside screen
        xor a
.on_screen:
        ld (hl),a
        ld a,(.width1+1)            ; now A = (width - 1)
        add a,(hl)                  ; now A = (width - 1) + column
        call c,.newline             ; if char width won't fit then move to new line
        ld bc,(zxf_col)
        ld a,1
        sub (ix+0)                  ; now A = 1 - height
        add a,b                     ; now A = P_LIN - height + 1
        jp nc,zxf_below             ; (adapted: was REPORT-5, "Out of screen")
        ld a,b                      ; (adapted: and a line that has wrapped past 0 to 255 is below the screen too,
        cp 192                      ; where the stock driver's PIXEL-ADD would report B, Integer out of range)
        jp nc,zxf_below
        pop af                      ; now A = shift
        add a,191                   ; range 0-191
        ld d,a                      ; (adapted: a character whose top is below the screen draws nothing)
        sub b
        cp 192
        jr nc,.done
        ld a,d
        call 22AAh+2                ; call PIXEL-ADD + 2 to calculate screen address
        ex af,af'                   ; now A' = (col % 8)
        jr .chk_loop
.main_loop:
        ld d,(hl)                   ; now D = 1st byte from char definition grid
        inc hl                      ; next character definition
.smc:   ld c,(hl)                   ; now C = 2nd byte from char definition or zero
        inc hl                      ;   (either "LD C,0" or "LD C,(HL)" + "INC HL")
        xor a                       ; now A = zero (since there's no 3rd byte)
        ex (sp),hl                  ; now HL = screen address
        ex af,af'                   ; now A = (col % 8), A' = 0
        jr z,.no_rotate
        ld b,a                      ; now B = (col % 8)
        ex af,af'                   ; now A = 0, A' = (col % 8)
.rotate_pixels:
        srl d                       ; rotate right char definition grid in D,C,A
        rr c
        rra
        djnz .rotate_pixels
.no_rotate:
        ld b,a                      ; (adapted: nothing past x 255) B = the third byte
        ld a,l
        and 1Fh
        cp 31
        jr z,.one                   ; column byte 31: only the first is on the screen
        cp 30
        jr z,.two                   ; 30: the first two
        inc l
        inc l
        ld a,b
        or (hl)
        ld (hl),a                   ; put the 3rd on screen
        dec l
        jr .second
.two:   inc l
.second:
        ld a,c
        or (hl)
        ld (hl),a                   ; put C on screen
        dec l
.one:   ld a,d
        or (hl)
        ld (hl),a                   ; put D on screen
        inc h                       ; move screen address by 1 pixel down
        ld a,h
        and 7
        jr nz,.chk_loop
        ld a,l
        add a,32
        ld l,a
        jr c,.bottom
        ld a,h
        sub 8
        ld h,a
        jr .chk_loop
.bottom:
        ld a,h                      ; (adapted: past row 191 is the attributes, so stop there)
        cp 58h
        jr z,.done
.chk_loop:
        ex (sp),hl                  ; now HL = char definition address
        ld a,l
        cp e                        ; check if reached next char definition address
        jr nz,.main_loop            ; loop otherwise
.done:
        pop hl                      ; discard screen address from stack
        ld hl,zxf_col
        ld a,(hl)                   ; now A = column
.width1:
        add a,0                     ; now A = column + (width - 1)
        scf
        adc a,(ix+1)                ; now A = column + width + tracking
        jr nc,.exit                 ; if didn't fall outside the screen then exit
.newline:
        ld (hl),0                   ; move to initial column at left margin (no margin)
        inc hl
        ld a,(hl)                   ; now A = line
        sub (ix+0)                  ; now A = line - height
.exit:
        ld (hl),a                   ; move down a few pixels specified by height
        ret

zxf_flag: db 0                      ; P_FLAG, P_COL, P_LIN: together, in this order, as the driver's are
zxf_col:  db 0
zxf_lin:  db 191
