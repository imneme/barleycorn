;; provides: bly_chr
;; needs: (none)
;; targets: cpm zx48 test
;; bly_chr  in: A=byte DE=&dest   out: (DE) = the one-byte str chr(A), a slice of a fixed table (nothing allocated)   clobbers: AF DE HL
;
; Its own fragment because of the table: 256 bytes that a program without chr() shouldn't carry.

bly_chr:
        ld hl,.table
        add a,l
        ld l,a
        adc a,h
        sub l
        ld h,a                      ; HL = .table + A, which holds A
        ex de,hl
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld (hl),1
        inc hl
        ld (hl),0
        ret
.table:                             ; .table + b holds b
        DUP 256, .b
        db .b
        EDUP
