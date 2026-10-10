;; provides: bly_grid_input
;; needs: bly_lns bly_nln bly_alloc bly_alloc_raw bly_pr_cstr bly_pr_u16 bly_fail_end bly_cmp_byte bly_pr_byte
;; targets: cpm zx48 test
;; bly_grid_input  in: -   out: HL = a grid[byte] of the input's lines (ABI.md section 6's header)
;;                 fails: the input is not a grid: line {r} is {len} long, not {cols}; arena full   clobbers: AF BC DE HL IX
;
; Every line is checked against the first before anything is allocated, so ragged input says so even when it
; wouldn't fit. The cells are a copy, row after row, since the text has line ends between its rows.
; rows x cols is the sum of the lines' lengths, so it fits a word and needs no multiply. The cells aren't zeroed
; first (bly_alloc_raw), since the copy fills them all.

bly_grid_input:
        ld ix,0                     ; IX = the cells, counted
        ld bc,0                     ; BC = cols
        ld de,(bly_nln)             ; DE = the lines still to check
        ld a,d
        or e
        jr z,.make                  ; no lines: 0 x 0
        ld hl,(bly_lns)
        inc hl
        inc hl                      ; HL = &lns[0].n
        ld c,(hl)
        inc hl
        ld b,(hl)
        dec hl                      ; cols = the first line's length
.check: ld a,(hl)
        cp c
        jr nz,.ragged
        inc hl
        ld a,(hl)
        cp b
        jr nz,.ragged
        add ix,bc
        inc hl
        inc hl
        inc hl                      ; the next line's n
        dec de
        ld a,d
        or e
        jr nz,.check
.make:  push bc                     ; cols
        push ix                     ; cells
        ld hl,12
        call bly_alloc              ; the header
        push hl
        pop ix
        pop hl
        call bly_alloc_raw          ; the cells, every one about to be written
        ld (ix+6),l
        ld (ix+7),h                 ; a
        ex de,hl                    ; DE = the cells
        pop bc
        ld (ix+2),c
        ld (ix+3),b                 ; cols
        ld hl,(bly_nln)
        ld (ix+0),l
        ld (ix+1),h                 ; rows
        ld (ix+4),1                 ; esize (its high byte is zero already)
        ld (ix+8),low bly_cmp_byte
        ld (ix+9),high bly_cmp_byte
        ld (ix+10),low bly_pr_byte
        ld (ix+11),high bly_pr_byte
        ld a,b
        or c
        jr z,.done                  ; no columns (or no rows): nothing to copy
        ld (.cols),bc
        ld (.left),hl
        ld hl,(bly_lns)
.copy:  ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = the line's p
        inc hl
        inc hl
        inc hl
        push hl                     ; the next line's str
        ld h,b
        ld l,c
        ld bc,(.cols)
        ldir
        pop hl
        ld bc,(.left)
        dec bc
        ld (.left),bc
        ld a,b
        or c
        jr nz,.copy
.done:  push ix
        pop hl
        ret
.ragged:                            ; DE = the lines left, this one among them
        ld hl,(bly_nln)
        or a
        sbc hl,de                   ; r, from 0
        push bc                     ; cols
        push hl
        add hl,hl
        add hl,hl
        ld de,(bly_lns)
        add hl,de
        inc hl
        inc hl
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; its length
        pop hl
        push de
        inc hl                      ; its number, from 1
        push hl
        ld hl,.m1
        call bly_pr_cstr
        pop hl
        call bly_pr_u16
        ld hl,.m2
        call bly_pr_cstr
        pop hl
        call bly_pr_u16
        ld hl,.m3
        call bly_pr_cstr
        pop hl
        call bly_pr_u16
        jp bly_fail_end
.m1:    db "the input is not a grid: line ",0
.m2:    db " is ",0
.m3:    db " long, not ",0
.cols:  dw 0
.left:  dw 0
