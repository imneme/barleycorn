;; provides: bly_cmp_byte bly_pr_byte
;; needs: bly_pr_u16
;; targets: cpm zx48 test
;; bly_cmp_byte  in: HL=&a DE=&b   out: A = FFh, 0, 1 (unsigned), flags as after OR A   clobbers: AF B
;; bly_pr_byte   in: HL=&v         prints the byte as print does (decimal)          clobbers: AF BC DE HL
;
; The element routines (ABI.md section 6) for byte: bly_grid_input puts them in its header, and the code
; generator can use them for any container of bytes.

bly_cmp_byte:
        ld a,(de)
        ld b,a
        ld a,(hl)
        sub b
        ret z
        sbc a,a                     ; FFh if a < b, else 0
        or 1
        ret

bly_pr_byte:
        ld l,(hl)
        ld h,0
        jp bly_pr_u16
