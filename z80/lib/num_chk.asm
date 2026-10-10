;; provides: bly_chk_index64 bly_chk_slice64 bly_grid_chk64 bly_n_q2w
;; needs: bly_out bly_pr_cstr bly_pr_u16 bly_pr_i64 bly_fail bly_fail_end
;; targets: cpm zx48 test
;; bly_chk_index64  in: HL=&i (a quad) DE=n   out: DE=i   fails: index {i} is outside 0..{n}      clobbers: AF
;; bly_chk_slice64  in: HL=&a DE=&b (quads) BC=n   out: DE=a BC=b   fails: slice {a}..{b} is outside 0..{n}
;;                  clobbers: AF HL
;; bly_grid_chk64   in: HL=grid DE=&r BC=&c (quads)   out: HL=grid DE=r BC=c, ready for bly_grid_ref
;;                  fails: ({r}, {c}) is off the grid ({rows} x {cols})                      clobbers: AF
;; bly_n_q2w        in: HL=&q (a quad)   out: DE=its low word, Z if q is 0..65535, NZ if not   clobbers: AF HL
;
; The general index checks: an index of any type arrives widened to a quad (ABI.md section 2), so the message prints
; the true value. The quick test is that the top six bytes are zero; then one 16-bit compare.
; Scratch: bly_chk_slice64's .pa .pb .n, bly_grid_chk64's .g .pr .pc.

bly_n_q2w:
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld a,(hl)
        inc hl
        or (hl)
        inc hl
        or (hl)
        inc hl
        or (hl)
        inc hl
        or (hl)
        inc hl
        or (hl)
        ret

bly_chk_index64:                    ; 0 <= i < n
        push hl
        inc hl
        inc hl
        ld a,(hl)
        inc hl
        or (hl)
        inc hl
        or (hl)
        inc hl
        or (hl)
        inc hl
        or (hl)
        inc hl
        or (hl)
        pop hl
        jr nz,.fail                 ; negative, or 65536 or more
        ld a,(hl)
        sub e
        inc hl
        ld a,(hl)
        sbc a,d
        jr nc,.fail1                ; i >= n
        ld d,(hl)
        dec hl
        ld e,(hl)
        ret
.fail1: dec hl
.fail:  push de
        push hl
        ld hl,.index
        call bly_pr_cstr
        pop hl
        call bly_pr_i64
        ld hl,.outside
        call bly_pr_cstr
        pop hl
        call bly_pr_u16
        jp bly_fail_end
.index:   db "index ",0
.outside: db " is outside 0..",0

bly_chk_slice64:                    ; 0 <= a <= b <= n
        ld (.pa),hl
        ld (.pb),de
        ld (.n),bc
        call bly_n_q2w
        jr nz,.fail
        push de                     ; a
        ld hl,(.pb)
        call bly_n_q2w              ; DE = b
        pop hl                      ; HL = a
        jr nz,.fail
        ex de,hl                    ; HL = b, DE = a
        or a
        sbc hl,de
        jr c,.fail                  ; b < a
        add hl,de
        ld b,h
        ld c,l                      ; BC = b
        ld hl,(.n)
        or a
        sbc hl,bc
        ret nc                      ; b <= n
.fail:  ld hl,.slice
        call bly_pr_cstr
        ld hl,(.pa)
        call bly_pr_i64
        ld hl,.dots
        call bly_pr_cstr
        ld hl,(.pb)
        call bly_pr_i64
        ld hl,bly_chk_index64.outside
        call bly_pr_cstr
        ld hl,(.n)
        call bly_pr_u16
        jp bly_fail_end
.slice: db "slice ",0
.dots:  db "..",0
.pa:    dw 0
.pb:    dw 0
.n:     dw 0

bly_grid_chk64:                     ; 0 <= r < rows and 0 <= c < cols
        ld (.g),hl
        ld (.pr),de
        ld (.pc),bc
        ex de,hl
        call bly_n_q2w              ; DE = r
        jr nz,.fail
        ld hl,(.g)
        ld a,e
        sub (hl)
        inc hl
        ld a,d
        sbc a,(hl)
        jr nc,.fail                 ; r >= rows
        push de
        ld hl,(.pc)
        call bly_n_q2w              ; DE = c
        pop bc                      ; BC = r
        jr nz,.fail
        ld hl,(.g)
        inc hl
        inc hl
        ld a,e
        sub (hl)
        inc hl
        ld a,d
        sbc a,(hl)
        jr nc,.fail                 ; c >= cols
        ld h,b
        ld l,c
        ld b,d
        ld c,e
        ex de,hl                    ; DE = r, BC = c
        ld hl,(.g)
        ret
.fail:  ld a,'('
        call bly_out
        ld hl,(.pr)
        call bly_pr_i64
        ld hl,.comma
        call bly_pr_cstr
        ld hl,(.pc)
        call bly_pr_i64
        ld hl,.off
        call bly_pr_cstr
        ld hl,(.g)
        ld e,(hl)
        inc hl
        ld d,(hl)
        ex de,hl
        call bly_pr_u16             ; rows
        ld hl,.x
        call bly_pr_cstr
        ld hl,(.g)
        inc hl
        inc hl
        ld e,(hl)
        inc hl
        ld d,(hl)
        ex de,hl
        call bly_pr_u16             ; cols
        ld hl,.close
        jp bly_fail
.comma: db ", ",0
.off:   db ") is off the grid (",0
.x:     db " x ",0
.close: db ")",0
.g:     dw 0
.pr:    dw 0
.pc:    dw 0
