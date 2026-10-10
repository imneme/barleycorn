;; provides: bly_putc bly_exit bly_start bly_text bly_tlen bly_basic_sp bly_zx_cls bly_zx_at bly_zx_key bly_zx_ticks bly_zx_pause
;; needs: bly_atop bly_alimit bly_fail bly_pr_cstr bly_pr_i16 bly_out bly_col
;; uses: bly_program bly_bss bly_bss_end bly_input_at
;; targets: zx48
;; The 48K Spectrum, called from BASIC by RANDOMIZE USR. Code lives high (the builder puts it flush under the UDGs),
;; the slots just beneath it, our stack beneath those; the input is a tape block at 8000h (a length word, then the
;; text), and the arena runs from the input's end up to the stack's reserve. IY and HL' are BASIC's and stay so.
;; bly_start  saves BASIC's SP, moves the stack, zeroes the slots, finds the input, opens stream 2, runs the program
;; bly_putc   in: A=byte. A newline is ENTER; a byte that would be a control code (below 32) or a keyword token
;;            (A5h and up) prints as ?, so nothing is ever interpreted. The scroll prompt is kept quiet.
;;            clobbers: AF BC DE HL
;; bly_exit   back to BASIC, from anywhere: BASIC's SP, then RET (0 OK)
;; The screen and sound's platform half (ABI.md section 10; zxgfx.py is their meaning). The colours (ink, paper,
;; border, bright, flash, inverse, over) are zxcolour.asm, a fragment of their own, as beep is zxbeep.asm.
;; bly_zx_cls                          the ROM's CLS, then print starts at the top left    clobbers: all but IY
;; bly_zx_at    in: HL=r DE=c          fails: print at ({r}, {c}) is off the screen        clobbers: AF BC DE HL
;; bly_zx_scr_on, _off are zxattext.asm, linked only by a program that prints at a place
;; bly_zx_beep is zxbeep.asm, its own fragment: its tables and 32-bit arithmetic are 2K a program doesn't need
;;            unless it beeps
;; bly_zx_key   out: A = the last key pressed since the last call, or 0                    clobbers: AF HL
;; bly_zx_ticks in: DE=&dest           out: (DE) = FRAMES, as a long                       clobbers: AF HL
;; bly_zx_pause in: HL=n               waits n frames; fails: pause {n} is negative       clobbers: AF BC HL

INPUT   equ bly_input_at              ; 8000h when it fits up there; lower when it doesn't (the builder decides)
SCRCT   equ 23692                   ; the scroll counter: 255 keeps "scroll?" away
STACKROOM equ 1024

bly_text: dw INPUT+2
bly_tlen: dw 0
bly_basic_sp: dw 0

bly_start:
        ld (bly_basic_sp),sp
        ld sp,bly_bss               ; our stack grows down beneath the slots
        ld hl,bly_bss
        ld de,bly_bss_end
.zero:  ld a,l
        cp e
        jr nz,.z1
        ld a,h
        cp d
        jr z,.input
.z1:    ld (hl),0
        inc hl
        jr .zero
.input: ld hl,(INPUT)
        ld (bly_tlen),hl
        ld de,INPUT+2
        add hl,de
        ld (bly_atop),hl
        ex de,hl                    ; DE = the input's end
        ld hl,bly_bss-STACKROOM
        ld (bly_alimit),hl
        or a
        sbc hl,de
        jr c,.toobig
        ld a,2
        call 1601h                  ; CHAN-OPEN: print to the upper screen
        jp bly_program
.toobig:
        ld hl,.big
        jp bly_fail
.big:   db "the input doesn't fit in memory",0

bly_putc:
        ld hl,SCRCT                 ; before every byte: wrapping scrolls too, and "scroll?" must never ask
        ld (hl),255
        cp 10
        jr nz,.notnl
        ld a,13
        rst 10h
        ret
.notnl: cp 32
        jr c,.q
        cp 0A5h
        jr c,.out
.q:     ld a,'?'
.out:   rst 10h
        ret

bly_exit:
        im 1                        ; IM 1, interrupts on: as BASIC needs them, even from a failure inside frame's
        ei                          ; interrupt (zxframes.asm)
        ld sp,(bly_basic_sp)
        ret

; -- the screen and sound -----------------------------------------------------------------------------------------
ATTR_P  equ 5C8Dh
MASK_P  equ 5C8Eh
ATTR_T  equ 5C8Fh
MASK_T  equ 5C90h
P_FLAG  equ 5C91h
BORDCR  equ 5C48h
FLAGS   equ 5C3Bh
LAST_K  equ 5C08h
FRAMES  equ 5C78h

bly_zx_cls:
        call 0D6Bh                  ; the ROM's CLS: the screen in ATTR_P, print back to the top left
        ld a,2
        call 1601h                  ; and printing to the upper screen again
        ld hl,0
        ld (bly_col),hl
        ret

bly_zx_at:
        ld a,h
        or d
        jr nz,.bad
        ld a,l
        cp 22
        jr nc,.bad
        ld a,e
        cp 32
        jr nc,.bad
        push de
        push hl
        ld a,22                     ; AT, row, column: straight to RST 10, past print's filter
        rst 10h
        pop hl
        ld a,l
        rst 10h
        pop de
        ld a,e
        rst 10h
        ld (bly_col),de
        ret
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
.m3:    db ") is off the screen",0

bly_zx_key:
        ld hl,FLAGS
        bit 5,(hl)
        ld a,0
        ret z
        res 5,(hl)
        ld a,(LAST_K)
        ret

bly_zx_ticks:
        di
        ld hl,(FRAMES)
        ld a,(FRAMES+2)
        ei
        ex de,hl
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld (hl),a
        inc hl
        ld (hl),0
        ret

bly_zx_pause:
        bit 7,h
        jr nz,.bad
.loop:  ld a,h
        or l
        ret z
        ei
        halt
        dec hl
        jr .loop
.bad:   push hl
        ld hl,.m1
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        ld hl,.m2
        jp bly_fail
.m1:    db "pause ",0
.m2:    db " is negative",0
