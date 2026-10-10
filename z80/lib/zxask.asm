;; provides: bly_ask bly_zx_inkey
;; needs: bly_putc bly_alloc_raw bly_basic_sp bly_fail
;; targets: zx48
;; Keys and lines from the keyboard, through the ROM, as BASIC's INKEY$ and INPUT LINE do it. The way in is
;; Melissa's spectrum-minilib (MIT; zx_input_line.asm and call_with_errhandler.asm), which she worked out from
;; the HiSoft BASIC compiler; the steps are the ROM's own INPUT LINE (2089h, IN-ITEM at 20C1h), checked against it.
;; bly_ask       in: HL=&prompt DE=&dest (strs)   out: (DE) = the line typed, without its ENTER, new in the arena
;;               fails: STOP in ask (cursor down, which is INPUT LINE's "H STOP in INPUT")   clobbers: all but IY
;; bly_zx_inkey  out: A = the key held down now, as INKEY$ decodes it, or 0                 clobbers: AF BC DE HL
;;
;; ask() is display, not output: the prompt and the typing are on the lower screen (channel K, stream 1), which
;; the transcript leaves out, and that's cleared afterwards, as INPUT clears it. The editor runs on BASIC's own
;; stack, not ours: its room check (TEST-ROOM) measures against SP, and ours is high, above the input and the
;; arena, so a long enough line would grow the workspace over them. Every key the editor takes clicks (BEEPER),
;; which leaves the border BORDCR's and the speaker off. A key pressed before ask() (one inkey() saw, say) isn't
;; the answer's first letter: opening channel K clears FLAGS bit 5 (CHAN-K, 1634h), for INPUT as for us. One
;; thing INPUT doesn't do: ask() returns only once ENTER (or cursor down) is let go, so an inkey() straight
;; afterwards doesn't find it still held.

ZXA_ERR_SP equ 5C3Dh
ZXA_K_CUR  equ 5C5Bh
ZXA_WORKSP equ 5C61h
ZXA_FLAGX  equ 5C71h
ZXA_ECHO_E equ 5C82h
ZXA_SCR_CT equ 5C8Ch

bly_zx_inkey:                       ; S-INKEY$ (2634h), without the string
        call 028Eh                  ; KEY-SCAN: DE = the keys held; NZ if none, or too many
        jr nz,.none
        call 031Eh                  ; K-TEST: A = the key's main code; NC if it isn't a key on its own
        jr nc,.none
        ld c,0                      ; K-DECODE as INKEY$ calls it: mode 0, D = FFh (L mode), E = the code
        ld d,0FFh
        ld e,a
        jp 0333h                    ; A = the character
.none:  xor a
        ret

bly_ask:
        ld (.dest),de
        ld (.sp),sp
        ld sp,(bly_basic_sp)
        push hl
        ld a,1                      ; as INPUT (2090h): CHAN-OPEN stream 1, channel K, the lower screen, though
        call 1601h                  ; CLS-LOWER opens it too (as stream FDh), so this is INPUT's belt and braces
        call 0D6Eh                  ; CLS-LOWER
        ld (iy+2),1                 ; TV_FLAG: the lower screen is in use
        pop hl
        ld e,(hl)                   ; the prompt, a byte at a time through bly_putc (a control code prints as ?)
        inc hl
        ld d,(hl)
        inc hl
        ld c,(hl)
        inc hl
        ld b,(hl)
.pr:    ld a,b
        or c
        jr z,.edit
        ld a,(de)
        push bc
        push de
        call bly_putc
        pop de
        pop bc
        inc de
        dec bc
        jr .pr
.edit:  ld hl,ZXA_FLAGX
        set 7,(hl)                  ; INPUT LINE
        call 16BFh                  ; SET-WORK: an empty workspace
        ld hl,ZXA_FLAGX
        res 6,(hl)
        set 5,(hl)                  ; input mode, in which cursor down stops it
        ld bc,1
        rst 30h                     ; BC-SPACES: room for the ENTER, at DE = HL
        ld (hl),13
        ld (ZXA_K_CUR),hl
        ld (iy+0),0FFh              ; ERR_NR: no error
        ld hl,(ZXA_ERR_SP)          ; on a STOP the editor leaves through ERR_SP (ED-END, 1024h): to .stop
        push hl
        ld hl,.stop
        push hl
        ld (ZXA_ERR_SP),sp
        call 0F2Ch                  ; EDITOR
        pop hl
        pop hl
        ld (ZXA_ERR_SP),hl
        call .tidy
        ld hl,(ZXA_WORKSP)          ; the line, up to its ENTER
        ld bc,0
.len:   ld a,(hl)
        cp 13
        jr z,.copy
        inc hl
        inc bc
        jr .len
.copy:  ld (.n),bc
        ld h,b
        ld l,c
        call bly_alloc_raw          ; HL = its room in the arena
        ld (.p),hl
        ex de,hl
        ld hl,(ZXA_WORKSP)
        ld bc,(.n)
        ld a,b
        or c
        jr z,.store
        ldir
.store: ld hl,(.dest)
        ld de,(.p)
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld de,(.n)
        ld (hl),e
        inc hl
        ld (hl),d
        call 16BFh                  ; SET-WORK: the workspace given back
        ld sp,(.sp)
        ret
.stop:  pop hl                      ; here from ED-END with ERR_NR = 10h, SP on the old ERR_SP
        ld (ZXA_ERR_SP),hl
        ld (iy+0),0FFh              ; or BASIC would report it at the end
        call .tidy
        call 16BFh
        ld sp,(.sp)
        ld hl,.stopped
        jp bly_fail
.tidy:  xor a                       ; until every key is let go: the top byte 0 reads all eight half-rows
        in a,(254)
        cpl
        and 1Fh
        jr nz,.tidy
        ld (iy+34),0                ; as INPUT does after the editor (2161h): K_CUR's high byte 0, so no cursor,
        call 111Dh                  ; ED-COPY: the line on the lower screen as typed
        ld bc,(ZXA_ECHO_E)
        call 0DD9h                  ; CL-SET
        ld hl,ZXA_FLAGX
        res 5,(hl)
        res 7,(hl)
        call 20A0h                  ; INPUT's end: the upper screen's print position if the lower one grew over it,
        ld a,2                      ; SCR_CT, and CLS-LOWER
        call 1601h                  ; CHAN-OPEN: stream 2, the upper screen, again
        ld a,255
        ld (ZXA_SCR_CT),a           ; and "scroll?" stays away
        ret
.stopped: db "STOP in ask",0
.dest:  dw 0
.sp:    dw 0
.n:     dw 0
.p:     dw 0
