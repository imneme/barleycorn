;; provides: bly_zx_ink bly_zx_paper bly_zx_border bly_zx_bright bly_zx_flash bly_zx_inverse bly_zx_over
;; needs: bly_fail bly_pr_cstr bly_pr_i16 bly_out
;; targets: zx48
;; The colours, as BASIC's INK, PAPER, BRIGHT and FLASH set them (the ROM's CO-TEMP, 2211h): ATTR_P/ATTR_T,
;; MASK_P/MASK_T and P_FLAG, permanent and temporary alike, so the ROM's text and our drawing agree (ABI.md section
;; 10; zxgfx.py is their meaning, and co_temp_check.py holds it to BASIC). Out of plat_zx.asm since 10 October, so a
;; program that never sets a colour doesn't carry them.
;; bly_zx_ink, _paper  in: HL=n   fails: {name} {n} is not a colour 0..9 (8: transparent, 9: contrast)
;;                                                                                         clobbers: AF BC DE HL
;; bly_zx_border      in: HL=n   fails: border {n} is not a colour 0..7                    clobbers: AF BC DE HL
;; bly_zx_bright, _flash  in: HL=n   fails: {name} {n} is not 0, 1 or 8 (8: transparent)   clobbers: AF BC DE HL
;; bly_zx_inverse, _over  in: A=0 or 1                                                     clobbers: AF HL

ZXC_ATTR_P equ 5C8Dh
ZXC_MASK_P equ 5C8Eh
ZXC_ATTR_T equ 5C8Fh
ZXC_MASK_T equ 5C90h
ZXC_P_FLAG equ 5C91h
ZXC_BORDCR equ 5C48h

zxc_col9: ld c,10                   ; HL = n, DE = the name: fail unless 0..9; else A = n
        jr zxc_colour.colck
zxc_colour:                         ; HL = n, DE = the name: fail unless 0..7; else A = n
        ld c,8
.colck: ld a,h
        or a
        jr nz,.bad
        ld a,l
        cp c
        ret c
.bad:   push bc
        push hl
        ex de,hl
        call bly_pr_cstr
        ld a,' '
        call bly_out
        pop hl
        call bly_pr_i16
        pop bc
        ld hl,.notc
        ld a,c
        cp 8
        jp z,bly_fail
        ld hl,.notc9
        jp bly_fail
.notc:  db " is not a colour 0..7",0
.notc9: db " is not a colour 0..9",0

bly_zx_ink:
        ld de,.name
        call zxc_col9
        ld d,a                      ; n, in place
        ld bc,0730h                 ; B = ink's bits, C = INK 9's bits in P_FLAG
        ld e,20h                    ; the paper's top bit: dark or light
        jr bly_zx_paper.cset
.name:  db "ink",0
bly_zx_paper:
        ld de,.name
        call zxc_col9
        ld l,a
        add a,a
        add a,a
        add a,a
        ld d,a                      ; n, in place
        ld a,l
        ld bc,38C0h                 ; B = paper's bits, C = PAPER 9's bits in P_FLAG
        ld e,04h                    ; the ink's top bit: dark or light
.cset:  ; A = n 0..9, D = n in place, B = the colour's bits, C = its 9 bits in P_FLAG, E = the other colour's top
        ; bit. As CO-TEMP: 0..7 the colour, no mask, no 9; 8 the mask's bits set; 9 the mask's bits set too, the
        ; colour white if the other is dark, else black, and the 9 bits set.
        cp 8
        jr c,.c07
        jr z,.c8
        ld a,(ZXC_ATTR_P)               ; 9
        and e
        ld d,b                      ; white on a dark other
        jr z,.c07
        ld d,0                      ; black on a light one
.c07:   ld a,b
        cpl
        ld h,a                      ; H = everything but the colour's bits
        ld a,(ZXC_ATTR_P)
        and h
        or d
        ld (ZXC_ATTR_P),a
        ld (ZXC_ATTR_T),a
        ld a,l                      ; was it 9?
        cp 9
        jr z,.c8
        ld a,(ZXC_MASK_P)
        and h
        ld (ZXC_MASK_P),a
        ld (ZXC_MASK_T),a
        ld a,c                      ; no 9
        cpl
        ld h,a
        ld a,(ZXC_P_FLAG)
        and h
        ld (ZXC_P_FLAG),a
        ret
.c8:    ld a,(ZXC_MASK_P)               ; 8 and 9: the mask's bits
        or b
        ld (ZXC_MASK_P),a
        ld (ZXC_MASK_T),a
        ld a,l
        cp 9
        ld a,(ZXC_P_FLAG)
        jr z,.c9
        ld h,a
        ld a,c
        cpl
        and h                       ; 8: no 9
        ld (ZXC_P_FLAG),a
        ret
.c9:    or c                        ; 9: its bits in P_FLAG
        ld (ZXC_P_FLAG),a
        ret
.name:  db "paper",0
bly_zx_border:
        ld de,.name
        call zxc_colour
        out (254),a
        ld c,a
        add a,a
        add a,a
        add a,a
        bit 2,c                     ; a dark border gets white writing below, as the ROM's BORDER does
        jr nz,.light
        or 7
.light: ld (ZXC_BORDCR),a
        ret
.name:  db "border",0

bly_zx_bright:                      ; HL = n
        ld de,.name
        ld c,40h
        jr bly_zx_flash.lvl
.name:  db "bright",0
bly_zx_flash:                       ; HL = n
        ld de,.name
        ld c,80h
.lvl:   ; C = the bit. As CO-TEMP: 0 off, 1 on, 8 off with the mask's bit on (transparent); anything else fails
        ld a,h
        or a
        jr nz,.bad
        ld a,l
        cp 2
        jr c,.ok
        cp 8
        jr nz,.bad
.ok:    ld a,c
        cpl
        ld e,a                      ; E = everything but the bit
        ld a,(ZXC_ATTR_P)
        and e
        bit 0,l                     ; 1: on
        jr z,.l1
        or c
.l1:    ld (ZXC_ATTR_P),a
        ld (ZXC_ATTR_T),a
        ld a,(ZXC_MASK_P)
        and e
        bit 3,l                     ; 8: transparent
        jr z,.l2
        or c
.l2:    ld (ZXC_MASK_P),a
        ld (ZXC_MASK_T),a
        ret
.bad:   push hl
        ex de,hl
        call bly_pr_cstr
        ld a,' '
        call bly_out
        pop hl
        call bly_pr_i16
        ld hl,.notl
        jp bly_fail
.notl:  db " is not 0, 1 or 8",0
.name:  db "flash",0
bly_zx_inverse:
        ld l,0Ch                    ; P_FLAG bits 2 and 3
        jr bly_zx_over.bits
bly_zx_over:
        ld l,03h                    ; P_FLAG bits 0 and 1
.bits:  ld h,a
        ld a,(ZXC_P_FLAG)
        or l
        xor l
        dec h
        jr nz,.store
        or l
.store: ld (ZXC_P_FLAG),a
        ret
