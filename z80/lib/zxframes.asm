;; provides: bly_zx_frames
;; needs: bly_line
;; uses: f_frame
;; targets: zx48
;; frame do ... end, every frame, in the interrupt: IM 2, the way Melissa's im2.asm does it (a table of 257
;; equal bytes, so the vector is the same whatever the data bus holds), and then on to the ROM's own handler
;; at 0038h, so FRAMES counts and the keyboard's scanned, and key(), inkey(), ask(), ticks() and pause() carry
;; on as ever. The table is FE00h-FF00h, all FDh, and the vector FDFDh holds a jump to zxr_isr: the builder
;; keeps a program with a frame below FDFDh (the UDGs, from FF58h, are untouched). frame's own code is 16-bit
;; Barley (the checker sees to it), whose arithmetic keeps nothing in memory, so it can't trip over the program
;; it interrupts. A failure in it ends the program from inside the interrupt, as any failure does: bly_exit
;; puts IM 1 back and interrupts on.
;; bly_zx_frames  in: A = 0 (IM 1: frame stops) or not (IM 2: frame runs every frame)    clobbers: AF BC DE HL

bly_zx_frames:
        or a
        jr z,.off
        di
        ld hl,0FE00h                ; the table: FDh, 257 of them
        ld de,0FE01h
        ld bc,256
        ld (hl),0FDh
        ldir
        ld a,0C3h                   ; and at FDFDh, jp zxr_isr
        ld (0FDFDh),a
        ld hl,zxr_isr
        ld (0FDFEh),hl
        ld a,0FEh
        ld i,a
        im 2
        ei
        ret
.off:   di
        im 1
        ei
        ret

zxr_isr:                            ; every frame, interrupts off: the registers, and bly_line (frame's own lines
        push af                     ; mustn't be the program's if it fails later), around frame; then the ROM's
        push bc
        push de
        push hl
        push ix
        ld hl,(bly_line)
        push hl
        call f_frame
        pop hl
        ld (bly_line),hl
        pop ix
        pop hl
        pop de
        pop bc
        pop af
        jp 0038h                    ; the ROM's handler: FRAMES, the keyboard, then EI and RET
