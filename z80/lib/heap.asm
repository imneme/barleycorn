;; provides: bly_heap_new bly_heap_push bly_heap_pop
;; needs: bly_cn_new bly_cn_full bly_cn_mul bly_fail
;; targets: cpm zx48 test
;; bly_heap_new    in: HL=&block (+0 cap quad, +8 esize, +10 cmp)   out: HL=heap   fails: the capacity messages, arena full   clobbers: AF BC DE HL IX
;; bly_heap_push   in: HL=heap DE=&v       fails: heap full ({cap})                                 clobbers: AF BC DE HL IX
;; bly_heap_pop    in: HL=heap DE=&dest    the smallest by cmp      fails: heap empty               clobbers: AF BC DE HL IX
;;
;; The header (ABI.md 6): +0 n, +2 cap, +4 ver, +6 esize, +8 a, +10 cmp, +12 tmp. A binary min-heap, as bly_heap.h,
;; moving a hole instead of swapping, so each level costs one move, not three.
;; - push moves each parent bigger than v down a level and writes v once.
;; - pop is bottom-up (Floyd's): it writes the top out, then moves the smaller child up into the hole all the way to
;;   the bottom (one cmp a level, not two), then lets the last element climb back from there, which it rarely does
;;   far. On a Z80 a cmp is a CALL into generated code and costs more than a move, so this is the cheaper trade:
;;   about half the cmps of bly_heap.h's pop for a couple more moves.
;; Neither needs tmp: v stays where the caller has it, and the last element sits just past the shrunken heap until
;; it's placed. tmp is allocated anyway, as the header says.
;; Byte offsets replace indices and multiplies: off(child) = 2*off + esize; push's parent is (off - esize, or - 2*esize
;; when the index is even) / 2; pop keeps the path down (the holes' addresses) on the stack and climbs it.
;; cmp may clobber every register, so the state lives in scratch words. Self-modifying: the CALLs to cmp, and in pop
;; the immediates marked "patched", set on entry (esize, -n*esize, a and &last), which keep pop's bookkeeping lean.

bly_heap_new:
        push hl
        ld a,2                      ; kind 2, heap
        ld bc,12*256+8              ; a 12-byte header (then tmp), a at +8
        call bly_cn_new
        pop de
        ex de,hl                    ; HL = block, DE = heap
        ld bc,10
        add hl,bc
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; cmp
        ld hl,10
        add hl,de
        ld (hl),c
        inc hl
        ld (hl),b
        ex de,hl
        ret

bly_heap_push:                      ; HL=heap DE=&v
        ld (.v),de
        push hl
        pop ix
        ld e,(ix+0)
        ld d,(ix+1)                 ; n
        ld l,(ix+2)
        ld h,(ix+3)                 ; cap
        scf
        sbc hl,de                   ; cap - n - 1: carry if n >= cap
        jp c,.full
        ld (.i),de                  ; the hole starts at n
        inc de
        ld (ix+0),e
        ld (ix+1),d
        inc (ix+4)                  ; ver
        jr nz,.v1
        inc (ix+5)
.v1:    ld l,(ix+10)
        ld h,(ix+11)
        ld (.cmp+1),hl
        ld l,(ix+8)
        ld h,(ix+9)
        ld (.a),hl
        ld e,(ix+6)
        ld d,(ix+7)
        ld (.es),de
        ld bc,(.i)
        call bly_cn_mul
        ld (.off),hl                ; off(hole)
.up:    ld hl,(.i)
        ld a,h
        or l
        jr z,.place                 ; the hole is the root
        ld a,l                      ; bit 0: the hole is a left child
        dec hl
        srl h
        rr l
        ld (.p),hl                  ; parent = (i - 1) / 2
        ld hl,(.off)
        ld de,(.es)
        or a
        sbc hl,de
        rrca
        jr c,.odd
        sbc hl,de                   ; carry is clear here
.odd:   srl h
        rr l
        ld (.poff),hl
        ld de,(.a)
        add hl,de
        ex de,hl                    ; DE = &a[parent]
        ld hl,(.v)
.cmp:   call 0                      ; self-modified: cmp(v, parent)
        or a
        jp p,.place                 ; v >= parent: the hole is v's place
        ld hl,(.a)
        ld de,(.off)
        add hl,de
        ex de,hl                    ; DE = &a[hole]
        ld hl,(.a)
        ld bc,(.poff)
        add hl,bc                   ; HL = &a[parent]
        ld bc,(.es)
        ldir                        ; the parent moves down
        ld hl,(.p)
        ld (.i),hl
        ld hl,(.poff)
        ld (.off),hl
        jr .up
.place: ld hl,(.a)
        ld de,(.off)
        add hl,de
        ex de,hl
        ld hl,(.v)
        ld bc,(.es)
        ldir
        ret
.full:  ld a,2
        ld l,(ix+2)
        ld h,(ix+3)
        jp bly_cn_full
.v:     dw 0
.i:     dw 0
.p:     dw 0
.off:   dw 0
.poff:  dw 0
.a:     dw 0
.es:    dw 0

bly_heap_pop:                       ; HL=heap DE=&dest
        push hl
        pop ix
        ld l,(ix+0)
        ld h,(ix+1)
        ld a,h
        or l
        jp z,.empty
        dec hl
        ld (ix+0),l
        ld (ix+1),h
        inc (ix+4)                  ; ver
        jr nz,.v1
        inc (ix+5)
.v1:    ld c,(ix+10)
        ld b,(ix+11)
        ld (.cmp1+1),bc
        ld (.cmp2+1),bc
        ld c,(ix+6)
        ld b,(ix+7)                 ; BC = esize
        ld (.es1+1),bc
        ld (.es2+1),bc
        ld (.es3+1),bc
        ld (.es4+1),bc
        ld (.es5+1),bc
        ld (.es6+1),bc
        ld (.es7+1),bc
        push hl                     ; the new n
        ld l,(ix+8)
        ld h,(ix+9)
        ld (.a1+1),hl
        ld (.a2+1),hl
        ld (.hp),hl                 ; the hole starts at the root
        ldir                        ; the top goes out (HL = a, DE = dest)
        pop bc
        ld a,b
        or c
        ret z                       ; that was the only one
        ld de,(.es1+1)
        call bly_cn_mul             ; n * esize: offsets below it are in the heap
        ex de,hl
        ld hl,(.a1+1)
        add hl,de
        ld (.last1+1),hl            ; &a[n], just past the heap now, so it stays put
        ld (.last2+1),hl
        ld hl,0
        or a
        sbc hl,de
        ld (.nlim+1),hl
        ld (.sp),sp                 ; the path goes on the stack, and this is where it ends
        ld hl,0                     ; the hole's offset
.down:  add hl,hl
        jr c,.climb
.es1:   ld de,0                     ; patched: esize
        add hl,de
        jr c,.climb
        ld b,h
        ld c,l                      ; BC = the left child's offset
.nlim:  ld de,0                     ; patched: -n*esize
        add hl,de
        jr c,.climb                 ; no child: the hole is at the bottom
.es2:   ld de,0                     ; patched: esize
        add hl,de                   ; carry: no right child
        ld h,b
        ld l,c
        ld (.coff),hl
        jr c,.one
.a1:    ld de,0                     ; patched: a
        add hl,de
        ld d,h
        ld e,l                      ; DE = &left
.es3:   ld bc,0                     ; patched: esize
        add hl,bc                   ; HL = &right
.cmp1:  call 0                      ; self-modified: cmp(right, left)
        or a
        ld hl,(.coff)
        jp p,.one
.es4:   ld de,0                     ; patched: esize
        add hl,de
        ld (.coff),hl               ; the right child is smaller
.one:
.a2:    ld de,0                     ; patched: a
        add hl,de                   ; HL = &child
        ld de,(.hp)
        push de                     ; the path
        ld (.hp),hl                 ; the child's place is the hole now
.es5:   ld bc,0                     ; patched: esize
        ldir                        ; the child moves up
        ld hl,(.coff)
        jp .down
.climb: ld hl,(.sp)                 ; the last element climbs from the hole while it's below its parent
        or a
        sbc hl,sp
        jr z,.place                 ; the hole is the root
        pop de
        ld (.pp),de                 ; DE = &parent
.last1: ld hl,0                     ; patched: &last
.cmp2:  call 0                      ; self-modified: cmp(last, parent)
        or a
        jp p,.place                 ; last >= parent: here
        ld hl,(.pp)
        ld de,(.hp)
.es6:   ld bc,0                     ; patched: esize
        ldir                        ; the parent comes back down
        ld hl,(.pp)
        ld (.hp),hl
        jr .climb
.place: ld sp,(.sp)                 ; drop what's left of the path
        ld de,(.hp)
.last2: ld hl,0                     ; patched: &last
.es7:   ld bc,0                     ; patched: esize
        ldir
        ret
.empty: ld hl,.msg
        jp bly_fail
.msg:   db "heap empty",0
.coff:  dw 0
.hp:    dw 0
.pp:    dw 0
.sp:    dw 0
