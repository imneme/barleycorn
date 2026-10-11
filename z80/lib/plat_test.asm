;; provides: bly_putc bly_exit bly_failed bly_test_init bly_test_out bly_test_outp bly_test_failed bly_text bly_tlen
;; needs: bly_atop bly_alimit bly_line bly_col
;; targets: test
;; bly_putc       in: A=byte       appends to bly_test_out          clobbers: AF BC DE HL
;; bly_exit       in: -            marks the run failed and stops at the harness's bly_test_halt
;; bly_text, bly_tlen               the input's address and length (the platform's, per ABI.md section 8)
;; bly_test_init  in: -            resets the output, the arena (A000h-DFFFh), bly_line, bly_col   clobbers: AF HL

bly_test_failed: db 0
bly_text:        dw 0E800h          ; the input, for tests: set with set16 and mem
bly_tlen:        dw 0
bly_test_outp:   dw bly_test_out
bly_test_out:    ds 1024

bly_putc:
        ld hl,(bly_test_outp)
        ld (hl),a
        inc hl
        ld (bly_test_outp),hl
        ret

bly_failed:                         ; a failure's words are out: nothing more to do here
        ret

bly_exit:
        ld a,1
        ld (bly_test_failed),a
        jp bly_test_halt

bly_test_init:
        xor a
        ld (bly_test_failed),a
        ld hl,bly_test_out
        ld (bly_test_outp),hl
        ld hl,0A000h
        ld (bly_atop),hl
        ld hl,0E000h
        ld (bly_alimit),hl
        ld hl,0
        ld (bly_line),hl
        ld (bly_col),hl
        ret
