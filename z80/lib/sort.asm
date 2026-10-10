;; provides: bly_sort bly_list_sort
;; needs: bly_cn_mul
;; targets: cpm zx48 test
;; bly_sort        in: HL=&first DE=n BC=esize IX=cmp    sorts n elements in place, ascending by cmp     clobbers: AF BC DE HL IX
;; bly_list_sort   in: HL=list DE=cmp                    sorts the list in place; ver + 1                 clobbers: AF BC DE HL IX
;;
;; Heapsort, as bly_sort.h (a max-heap built by sifting from n/2 - 1, then the top moved to the end), with a
;; bottom-up sift (Floyd's): the element being placed waits in tmp, the hole goes all the way down taking the bigger
;; child up (one cmp a level, not two), and then the element climbs back from the bottom, which it rarely does far.
;; A cmp is a CALL into generated code, dearer than a move, so this is the better trade on a Z80.
;; tmp is esize bytes on the stack, given back before RET; the path down goes on the stack too (at most 16 words).
;; Equal elements are equal values in Barley, so it needn't be stable. Byte offsets replace indices.
;; cmp may clobber every register, so the state lives in scratch words. Self-modifying: the CALLs to cmp, and the
;; immediates marked "patched" (esize, a, &tmp once a sort, -limit once a sift), which keep the sift's bookkeeping lean.

bly_list_sort:                      ; HL=list DE=cmp
        push de
        pop ix
        push hl
        ld bc,4
        add hl,bc
        inc (hl)                    ; ver
        jr nz,.v
        inc hl
        inc (hl)
.v:     pop hl
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; n
        ld bc,5
        add hl,bc
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; esize
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                      ; a
        ; fall into bly_sort

bly_sort:                           ; HL=&first DE=n BC=esize IX=cmp
        ld (.cmp1+1),ix
        ld (.cmp2+1),ix
        ld (.a1+1),hl
        ld (.a2+1),hl
        ld (.a3+1),hl
        ld (.a4+1),hl
        ld (.a5+1),hl
        ld (.es1+1),bc
        ld (.es2+1),bc
        ld (.es3+1),bc
        ld (.es4+1),bc
        ld (.es5+1),bc
        ld (.es6+1),bc
        ld (.es7+1),bc
        ld (.es8+1),bc
        ld (.es9+1),bc
        ld (.es10+1),bc
        ld (.es11+1),bc
        ld a,d
        or a
        jr nz,.go
        ld a,e
        cp 2
        ret c                       ; fewer than two
.go:    ld (.sp0),sp
        ld hl,0
        or a
        sbc hl,bc
        add hl,sp
        ld sp,hl                    ; tmp: esize bytes on the stack
        ld (.tmp1+1),hl
        ld (.tmp2+1),hl
        ld (.tmp3+1),hl
        ld (.tmp4+1),hl
        push de                     ; n
        ld b,d
        ld c,e
        ld de,(.es1+1)
        call bly_cn_mul
        ld (.end),hl                ; n * esize
        call .limit                 ; building, the heap is everything
        pop hl
        srl h
        rr l                        ; n / 2
        ld b,h
        ld c,l
        ld de,(.es1+1)
        call bly_cn_mul
.heap:                              ; for i = n/2 - 1 down to 0
.es1:   ld de,0                     ; patched: esize
        or a
        sbc hl,de
        ld (.i),hl
.a1:    ld de,0                     ; patched: a
        add hl,de
.tmp1:  ld de,0                     ; patched: &tmp
.es2:   ld bc,0                     ; patched: esize
        ldir                        ; tmp = a[i]
        ld hl,(.i)
        call .sift
        ld hl,(.i)
        ld a,h
        or l
        jr nz,.heap
        ld hl,(.end)
.down:                              ; for m = n down to 2
.es3:   ld de,0                     ; patched: esize
        or a
        sbc hl,de
        jr z,.done
        ld (.m),hl                  ; (m - 1) * esize
        call .limit
        ld hl,(.m)
.a2:    ld de,0                     ; patched: a
        add hl,de
        push hl
.tmp2:  ld de,0                     ; patched: &tmp
.es4:   ld bc,0                     ; patched: esize
        ldir                        ; tmp = a[m-1]
        pop de
.a3:    ld hl,0                     ; patched: a
.es5:   ld bc,0                     ; patched: esize
        ldir                        ; a[m-1] = a[0], the biggest
        ld hl,0
        call .sift                  ; tmp into the heap of m - 1, from a hole at the root
        ld hl,(.m)
        jr .down
.done:  ld sp,(.sp0)
        ret

.limit:                             ; HL = the heap's size in bytes: patch its negative in
        ex de,hl
        ld hl,0
        or a
        sbc hl,de
        ld (.nlim+1),hl
        ret

.sift:                              ; HL = the hole's offset; tmp goes into the heap
        ld (.base),sp
        push hl
.a4:    ld de,0                     ; patched: a
        add hl,de
        ld (.hp),hl                 ; the hole's address
        pop hl
.sdown: add hl,hl
        jr c,.climb
.es6:   ld de,0                     ; patched: esize
        add hl,de
        jr c,.climb
        ld b,h
        ld c,l                      ; BC = the left child's offset
.nlim:  ld de,0                     ; patched: -the heap's size
        add hl,de
        jr c,.climb                 ; no child: the hole is at the bottom
.es7:   ld de,0                     ; patched: esize
        add hl,de                   ; carry: no right child
        ld h,b
        ld l,c
        ld (.coff),hl
        jr c,.one
.a5:    ld de,0                     ; patched: a
        add hl,de
        ld d,h
        ld e,l                      ; DE = &left
.es8:   ld bc,0                     ; patched: esize
        add hl,bc                   ; HL = &right
.cmp1:  call 0                      ; self-modified: cmp(right, left)
        or a
        ld hl,(.coff)
        jr z,.one
        jp m,.one
.es9:   ld de,0                     ; patched: esize
        add hl,de
        ld (.coff),hl               ; the right child is bigger
.one:   ld de,(.a5+1)
        add hl,de                   ; HL = &child
        ld de,(.hp)
        push de                     ; the path
        ld (.hp),hl                 ; the child's place is the hole now
.es10:  ld bc,0                     ; patched: esize
        ldir                        ; the child moves up
        ld hl,(.coff)
        jp .sdown
.climb: ld hl,(.base)               ; tmp climbs while it's bigger than its parent
        or a
        sbc hl,sp
        jr z,.place                 ; back at the subtree's root
        pop de
        ld (.pp),de                 ; DE = &parent
.tmp3:  ld hl,0                     ; patched: &tmp
.cmp2:  call 0                      ; self-modified: cmp(tmp, parent)
        or a
        jr z,.place
        jp m,.place                 ; tmp <= parent: here
        ld hl,(.pp)
        ld de,(.hp)
.es11:  ld bc,0                     ; patched: esize
        ldir                        ; the parent comes back down
        ld hl,(.pp)
        ld (.hp),hl
        jr .climb
.place: ld sp,(.base)               ; drop the rest of the path
        ld de,(.hp)
.tmp4:  ld hl,0                     ; patched: &tmp
        ld bc,(.es1+1)
        ldir
        ret

.sp0:   dw 0
.base:  dw 0
.end:   dw 0
.m:     dw 0
.i:     dw 0
.coff:  dw 0
.hp:    dw 0
.pp:    dw 0
