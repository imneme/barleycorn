;; provides: bly_zx_scr_on bly_zx_scr_off
;; targets: zx48
;; bly_zx_scr_on, _off   around each piece of text a print prints at a place: INVERSE and OVER at the values they
;;              have, straight to RST 10, so nothing changes on the screen but a transcript can tell the screen's
;;              text from the program's output (z80/transcript.py drops what lies between)   clobbers: AF BC DE HL
;; Its own fragment, so a program that never prints at a place doesn't carry it.

ZXA_P_FLAG equ 5C91h

bly_zx_scr_on:
        ld a,14h                    ; INVERSE, then its own value (the permanent bit, which the temporary one equals)
        rst 10h
        ld a,(ZXA_P_FLAG)
        and 08h
        rrca
        rrca
        rrca
        rst 10h
        ret
bly_zx_scr_off:
        ld a,15h                    ; OVER, then its own value
        rst 10h
        ld a,(ZXA_P_FLAG)
        and 02h
        rrca
        rst 10h
        ret
