;; provides: bly_randomize_now   needs: bly_randomize_q   targets: cpm
;; bly_randomize_now   randomize() with nothing to say: seeded from R          clobbers: AF B DE HL
; CP/M has no clock, so R, the refresh counter, is all there is to go on: on a real machine it's whatever it had
; got to; under an emulator that starts it the same, the same each run. (rndclock.asm is the 48K's.)

bly_randomize_now:
        ld hl,.q
        ld b,5
.r:     ld a,r
        ld (hl),a
        inc hl
        djnz .r
        ld hl,.q
        jp bly_randomize_q
.q:     ds 8
