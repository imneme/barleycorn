;; provides: bly_alloc_raw
;; needs: bly_atop bly_alimit bly_alloc
;; targets: cpm zx48 test
;; bly_alloc_raw  in: HL=size   out: HL = a block from the arena, NOT zeroed   fails: arena full   clobbers: AF DE
;
; bly_alloc without the zeroing, for blocks the caller fills whole straight away (a grid's cells, intern's
; copies). bly_alloc zeroes at about 42 T a byte, which was two thirds of grid(). It belongs in core; it's here
; only because core isn't mine to change. When it doesn't fit, it hands the size to bly_alloc, which says so.

bly_alloc_raw:
        push hl                     ; the size, in case it doesn't fit
        ld de,(bly_atop)
        add hl,de
        jr c,.full
        ex de,hl                    ; DE = the new top, HL = the block
        push hl
        ld hl,(bly_alimit)
        or a
        sbc hl,de
        pop hl
        jr c,.full
        ld (bly_atop),de
        pop de
        ret
.full:  pop hl
        jp bly_alloc                ; "arena full", and never back
