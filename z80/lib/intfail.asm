;; provides: bly_ovf_n bly_mod0
;; needs: bly_ovf_int bly_ovf_long bly_ovf_quad bly_fail
;; targets: cpm zx48 test
;; bly_ovf_n   in: A=the width in bytes (2, 4 or 8)   fails: int, long or quad overflow   never returns
;; bly_mod0    in: -                                  fails: mod by zero                  never returns
;
; The integer library's failures that gen.asm doesn't already have. The rest (bly_ovf_int, bly_ovf_long,
; bly_ovf_quad, bly_div0, bly_neg_shift) are gen.asm's, so each message is in a program once.

bly_ovf_n:
        cp 4
        jp c,bly_ovf_int
        jp z,bly_ovf_long
        jp bly_ovf_quad

bly_mod0:
        ld hl,.m
        jp bly_fail
.m:     db "mod by zero",0
