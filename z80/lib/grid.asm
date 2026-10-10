;; provides: bly_grid_new bly_grid_ref bly_grid_has bly_grid_find bly_grid_chk16
;; needs: bly_cn_cmul bly_cn_mul bly_cn_afull bly_alloc bly_pr_cstr bly_pr_i16 bly_fail
;; targets: cpm zx48 test
;; bly_grid_new    in: HL=&block (+0 rows quad, +8 cols quad, +16 esize, +18 cmp, +20 pr, +22 &fill)   out: HL=grid
;;                 fails: a grid has no negative sides, a grid side is at most 32767, arena full   clobbers: AF BC DE HL
;; bly_grid_ref    in: HL=grid DE=r BC=c (already checked)   out: HL=&cell                          clobbers: AF BC DE HL
;; bly_grid_has    in: HL=grid DE=&pos                      out: A=0/1                             clobbers: AF BC DE HL
;; bly_grid_find   in: HL=grid DE=&value BC=&dest (a pos)   the first in row-major order   fails: {v} is not on the grid   clobbers: AF BC DE HL IX
;; bly_grid_chk16  in: HL=grid DE=r BC=c (ints)             fails: ({r}, {c}) is off the grid ({rows} x {cols})   clobbers: AF
;;
;; The header (ABI.md 6): +0 rows, +2 cols, +4 esize, +6 a (row-major), +8 cmp, +10 pr; the cells follow it.
;; bly_grid_chk16 keeps HL, DE and BC, so bly_grid_ref can follow it directly.
;; find on a one-byte grid uses CPIR a row at a time (every one-byte type is equal exactly when its bytes are);
;; other grids call cmp on each cell. Self-modifying: the CALLs to cmp and pr.

bly_grid_new:                       ; HL=&block
        ld (.blk),hl
        ld de,7
        add hl,de
        bit 7,(hl)                  ; rows < 0?
        jp nz,.neg
        ld de,8
        add hl,de
        bit 7,(hl)                  ; cols < 0?
        jp nz,.neg
        ld hl,(.blk)
        call .side
        jp c,.big
        ld (.rows),hl
        ld hl,(.blk)
        ld de,8
        add hl,de
        call .side
        jp c,.big
        ld (.cols),hl
        ld hl,(.blk)
        ld de,16
        add hl,de
        ld de,.es                   ; esize, cmp, pr, &fill: 8 bytes, as in the block
        ld bc,8
        ldir
        ld bc,(.rows)
        ld de,(.cols)
        call bly_cn_cmul
        jp c,bly_cn_afull
        ld b,h
        ld c,l
        ld de,(.es)
        call bly_cn_cmul            ; the cells' bytes
        jp c,bly_cn_afull
        ld (.bytes),hl
        ld de,12
        add hl,de
        jp c,bly_cn_afull
        call bly_alloc
        ld (.hdr),hl
        ex de,hl
        ld hl,.rows
        ld bc,6
        ldir                        ; rows, cols, esize
        ld hl,(.hdr)
        ld bc,12
        add hl,bc
        ld (.a),hl
        ex de,hl
        ld (hl),e                   ; a
        inc hl
        ld (hl),d
        inc hl
        ex de,hl
        ld hl,.cmp
        ld bc,4
        ldir                        ; cmp, pr
        ld hl,(.bytes)
        ld a,h
        or l
        jr z,.done                  ; no cells
        ld hl,(.fill)
        ld bc,(.es)
.zero:  ld a,(hl)                   ; a zero fill is already there
        or a
        jr nz,.fillit
        inc hl
        dec bc
        ld a,b
        or c
        jr nz,.zero
        jr .done
.fillit:
        ld hl,(.fill)
        ld de,(.a)
        ld bc,(.es)
        ldir                        ; cell 0
        ld hl,(.bytes)
        ld bc,(.es)
        or a
        sbc hl,bc
        jr z,.done
        ld b,h
        ld c,l
        ld hl,(.a)
        ldir                        ; overlapping: each byte comes from esize bytes back, so cell 0 repeats
.done:  ld hl,(.hdr)
        ret
.neg:   ld hl,.mneg
        jp bly_fail
.big:   ld hl,.mbig
        jp bly_fail
.side:                              ; HL=&side (a quad, not negative) -> HL = it, carry if above 32767
        push hl
        ld bc,7
        add hl,bc
        ld b,6
        xor a
.s:     or (hl)
        dec hl
        djnz .s
        jr nz,.sbig
        bit 7,(hl)
        jr nz,.sbig
        pop hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        or a
        ret
.sbig:  pop hl
        scf
        ret
.mneg:  db "a grid has no negative sides",0
.mbig:  db "a grid side is at most 32767",0
.blk:   dw 0
.hdr:   dw 0
.a:     dw 0
.bytes: dw 0
.rows:  dw 0                        ; rows, cols, esize: the header's order
.cols:  dw 0
.es:    dw 0                        ; esize, cmp, pr, fill: the block's order
.cmp:   dw 0
.pr:    dw 0
.fill:  dw 0

bly_grid_ref:                       ; HL=grid DE=r BC=c -> HL = a + (r*cols + c)*esize
        push bc
        inc hl
        inc hl
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; cols
        inc hl
        push hl
        call bly_cn_mul             ; r * cols, quick when r < 256
        pop de
        pop bc
        add hl,bc
        ex de,hl                    ; DE = the cell's number, HL = &esize
        ld c,(hl)
        inc hl
        ld b,(hl)
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                      ; HL = a
        ld a,b
        or a
        jr nz,.mul
        dec c
        jr nz,.mul1
        add hl,de                   ; esize 1
        ret
.mul1:  inc c
.mul:   push hl
        ld h,b
        ld l,c
        ld b,d
        ld c,e
        ex de,hl
        call bly_cn_mul
        pop de
        add hl,de
        ret

bly_grid_has:                       ; HL=grid DE=&pos -> A
        ex de,hl
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; r
        inc hl
        bit 7,b
        jr nz,.no
        ld a,c
        ex de,hl
        sub (hl)
        inc hl
        ld a,b
        sbc a,(hl)                  ; r - rows
        inc hl
        jr nc,.no
        ex de,hl
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; c
        bit 7,b
        jr nz,.no
        ex de,hl
        ld a,c
        sub (hl)
        inc hl
        ld a,b
        sbc a,(hl)                  ; c - cols
        ld a,0
        ret nc
        inc a
        ret
.no:    xor a
        ret

bly_grid_chk16:                     ; HL=grid DE=r BC=c; keeps HL DE BC
        bit 7,d
        jr nz,.off
        bit 7,b
        jr nz,.off
        push hl
        ld a,e
        sub (hl)
        inc hl
        ld a,d
        sbc a,(hl)                  ; r - rows
        inc hl
        jr nc,.off1
        ld a,c
        sub (hl)
        inc hl
        ld a,b
        sbc a,(hl)                  ; c - cols
        pop hl
        ret c
        jr .off
.off1:  pop hl
.off:   push hl
        push bc
        push de
        ld hl,.open
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        ld hl,.comma
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        ld hl,.offg
        call bly_pr_cstr
        pop hl
        push hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        call bly_pr_i16
        ld hl,.x
        call bly_pr_cstr
        pop hl
        inc hl
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        call bly_pr_i16
        ld hl,.close
        jp bly_fail
.open:  db "(",0
.comma: db ", ",0
.offg:  db ") is off the grid (",0
.x:     db " x ",0
.close: db ")",0

bly_grid_find:                      ; HL=grid DE=&value BC=&dest
        ld (.g),hl
        ld (.val),de
        ld (.dest),bc
        push hl
        pop ix
        ld a,(ix+5)
        or a
        jr nz,.slow
        ld a,(ix+4)
        dec a
        jr nz,.slow
        ld a,(ix+2)                 ; one byte a cell: CPIR along each row
        or (ix+3)
        jp z,.none                  ; no columns
        ld l,(ix+6)
        ld h,(ix+7)
        ld de,0                     ; r
.frow:  ld a,e
        cp (ix+0)
        jr nz,.fscan
        ld a,d
        cp (ix+1)
        jp z,.none                  ; r = rows
.fscan: ld c,(ix+2)
        ld b,(ix+3)
        push hl
        ld hl,(.val)
        ld a,(hl)
        pop hl
        cpir
        jr z,.ffound
        inc de
        jr .frow
.ffound:
        ld l,(ix+2)
        ld h,(ix+3)
        scf
        sbc hl,bc                   ; c = cols - left - 1
        jr .found
.slow:  ld l,(ix+8)
        ld h,(ix+9)
        ld (.cmp+1),hl
        ld l,(ix+6)
        ld h,(ix+7)
        ld (.p),hl
        ld hl,0
        ld (.r),hl
.srow:  ld ix,(.g)
        ld hl,(.r)
        ld e,(ix+0)
        ld d,(ix+1)
        or a
        sbc hl,de
        jr nc,.none
        ld hl,0
        ld (.c),hl
.scol:  ld ix,(.g)
        ld hl,(.c)
        ld e,(ix+2)
        ld d,(ix+3)
        or a
        sbc hl,de
        jr nc,.snext
        ld hl,(.p)
        ld de,(.val)
.cmp:   call 0                      ; self-modified: cmp(cell, value)
        or a
        jr z,.sfound
        ld ix,(.g)
        ld hl,(.p)
        ld e,(ix+4)
        ld d,(ix+5)
        add hl,de
        ld (.p),hl
        ld hl,(.c)
        inc hl
        ld (.c),hl
        jr .scol
.snext: ld hl,(.r)
        inc hl
        ld (.r),hl
        jr .srow
.sfound:
        ld de,(.r)
        ld hl,(.c)
.found: push hl                     ; DE = r, HL = c
        ld hl,(.dest)
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        pop de
        ld (hl),e
        inc hl
        ld (hl),d
        ret
.none:  ld ix,(.g)
        ld l,(ix+10)
        ld h,(ix+11)
        ld (.pr+1),hl
        ld hl,(.val)
.pr:    call 0                      ; self-modified: the element's printer
        ld hl,.msg
        jp bly_fail
.msg:   db " is not on the grid",0
.g:     dw 0
.val:   dw 0
.dest:  dw 0
.p:     dw 0
.r:     dw 0
.c:     dw 0
