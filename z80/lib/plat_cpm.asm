;; provides: bly_putc bly_exit bly_failed bly_start bly_text bly_tlen
;; needs: bly_atop bly_alimit bly_fail
;; uses: bly_program bly_bss bly_bss_end
;; targets: cpm
;; bly_start  the .COM's first jump: zeroes the program's slots, reads the input named on the command line (the CCP's
;;            FCB at 005Ch) to just above them, stopping at ^Z, puts the arena above that, then jumps to bly_program
;; bly_putc   in: A=byte; a newline (0Ah) goes out as CR LF                       clobbers: AF BC DE HL
;; bly_exit   the end of the program, normal or failed: JP 0, the warm boot
;; bly_text, bly_tlen   the input's address and length

BDOS    equ 5
FCB     equ 5Ch
STACKROOM equ 1024                  ; bytes kept for the stack below the BDOS

bly_text: dw 0
bly_tlen: dw 0

bly_start:
        ld hl,(6)                   ; the BDOS's address: the top of the TPA
        ld sp,hl
        ld hl,bly_bss               ; the program's slots start at zero
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
.input: ld (bly_text),de            ; the input goes just above the slots
        ld hl,0
        ld (bly_tlen),hl
        ld a,(FCB+1)
        cp ' '
        jr z,.arena                 ; no file named: an empty input
        ld de,FCB
        ld c,15                     ; open
        call BDOS
        inc a
        jr z,.missing
        xor a
        ld (FCB+32),a               ; from record 0
.read:  ld hl,(bly_text)
        ld de,(bly_tlen)
        add hl,de                   ; where this record goes
        push hl
        ld de,128
        add hl,de
        ex de,hl                    ; DE = its end
        ld hl,(6)
        ld bc,-STACKROOM
        add hl,bc
        or a
        sbc hl,de
        pop de
        jr c,.toobig
        ld c,26                     ; DMA = DE
        call BDOS
        ld de,FCB
        ld c,20                     ; read the next 128 bytes
        call BDOS
        or a
        jr nz,.eof
        ld hl,(bly_tlen)
        ld de,128
        add hl,de
        ld (bly_tlen),hl
        jr .read
.eof:   ld hl,(bly_text)            ; the text ends at the first ^Z, if there is one
        ld bc,(bly_tlen)
.find:  ld a,b
        or c
        jr z,.arena
        ld a,(hl)
        cp 1Ah
        jr z,.cut
        inc hl
        dec bc
        jr .find
.cut:   ld de,(bly_text)
        or a
        sbc hl,de
        ld (bly_tlen),hl
.arena: ld hl,(bly_text)
        ld de,(bly_tlen)
        add hl,de
        ld (bly_atop),hl
        ld hl,(6)
        ld de,-STACKROOM
        add hl,de
        ld (bly_alimit),hl
        ld hl,0080h                 ; the CCP's default DMA, as a program expects it
        ex de,hl
        ld c,26
        call BDOS
        jp bly_program
.missing:
        ld hl,.nofile
        jp bly_fail
.toobig:
        ld hl,.big
        jp bly_fail
.nofile: db "can't read the input",0
.big:    db "the input doesn't fit in memory",0

bly_putc:
        cp 10
        jr nz,.one
        ld e,13
        ld c,2
        call BDOS
        ld a,10
.one:   ld e,a
        ld c,2
        jp BDOS

bly_failed:                         ; a failure's words are out: nothing more to do here
        ret

bly_exit:
        jp 0
