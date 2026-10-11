;; provides: bly_randomize_now   needs: bly_randomize_q   targets: zx48
;; bly_randomize_now   randomize() with nothing to say: seeded from the clock      clobbers: AF DE HL
; The 48K's clock is FRAMES, the frames since it was switched on (three bytes), and R, the refresh counter, adds
; the instruction the program had got to: together a seed that's different every run (random.asm puts it in).

bly_randomize_now:
        ld hl,.q
        ld a,r
        ld (hl),a
        inc hl
        ld a,(5C78h)                ; FRAMES
        ld (hl),a
        inc hl
        ld a,(5C79h)
        ld (hl),a
        inc hl
        ld a,(5C7Ah)
        ld (hl),a
        inc hl
        ld a,r
        ld (hl),a
        ld hl,.q
        jp bly_randomize_q
.q:     ds 8
