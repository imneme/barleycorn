;; provides: bly_intern bly_name
;; needs: bly_alloc bly_alloc_raw bly_pr_cstr bly_pr_u16 bly_fail_end
;; targets: cpm zx48 test
;; bly_intern  in: HL=&str        out: HL = its number: 0, 1, 2... in order of first sight   fails: arena full   clobbers: AF BC DE HL
;; bly_name    in: HL=id DE=&dest   out: (DE) = the name's str   fails: no name has the number {n}   clobbers: AF BC DE HL
;
; The table lives in the arena and grows by doubling; the old arrays are left behind, since nothing is freed.
;   .names  cap strs, by number. Each one's bytes are a copy in the arena, so a name never changes under us.
;   .slots  2 x cap words, open addressing with linear probing: a name's number + 1, or 0 for an empty slot,
;           so a fresh block from bly_alloc (zeroed) is an empty index. At most half full.
;   .mask   2 x cap - 1;   .cap  0 until the first name, then 16, 32, 64...;   .count  how many names
; The hash is FNV-1a kept to 16 bits: the low half of the 32-bit one, since multiplying by its prime
; 01000193h is, mod 65536, multiplying by 0193h. Its high bits are the well-mixed ones, so a slot is the hash
; with its bytes swapped, masked.
; "too many names: intern holds 65536" can't happen here: 16384 names would need the whole 64K for .names
; alone, so the arena fills first and says so.

bly_intern:
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld (.sp),de
        ld (.sn),bc
        call .hash
        ld (.h),hl
        ld de,(.cap)
        ld a,d
        or e
        jr z,.grow1                 ; no table yet
        call .find
        jr c,.found
        push hl                     ; the empty slot where it goes
        ld hl,(.count)
        ld de,(.cap)
        or a
        sbc hl,de
        pop hl
        jr nz,.add
.grow1: call .grow                  ; full: make room, then find its slot in the new index
        ld hl,(.h)
        call .empty
.add:   push hl                     ; the slot
        ld hl,(.sn)
        ld a,h
        or l
        jr z,.copied                ; "": p = 0, nothing to copy
        call bly_alloc_raw
        push hl
        ex de,hl
        ld hl,(.sp)
        ld bc,(.sn)
        ldir                        ; the name's own copy of its bytes
        pop hl
.copied:
        ex de,hl                    ; DE = its p
        ld hl,(.count)
        add hl,hl
        add hl,hl
        ld bc,(.names)
        add hl,bc                   ; &names[count]
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld bc,(.sn)
        ld (hl),c
        inc hl
        ld (hl),b
        ld hl,(.count)
        inc hl
        ld (.count),hl              ; count + 1, which is the new number + 1
        ex de,hl
        pop hl                      ; the slot
        ld (hl),e
        inc hl
        ld (hl),d
        ex de,hl
.found: dec hl                      ; (HL = the number + 1)
        ret

; .hash: DE = p, BC = n -> HL. Self-modifying: the end address goes into the two compares.
.hash:  ld hl,9DC5h                 ; the low half of FNV-1a's offset basis, 811C9DC5h
        ld a,b
        or c
        ret z
        ld h,d
        ld l,e
        add hl,bc                   ; the end (mod 65536 is fine)
        ld a,l
        ld (.endlo+1),a
        ld a,h
        ld (.endhi+1),a
        ld b,d
        ld c,e                      ; BC = p
        ld hl,9DC5h
.hloop: ld a,(bc)
        inc bc
        xor l
        ld l,a                      ; h ^= the byte
        ld d,h
        ld e,l
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,de                   ; 9h
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,de                   ; 73h
        add hl,hl
        add hl,de                   ; 147h
        ld a,h
        add a,e
        ld h,a                      ; + 256h = 403h, and 403 = 0193h
        ld a,c
.endlo: cp 0                        ; (self-modified)
        jr nz,.hloop
        ld a,b
.endhi: cp 0                        ; (self-modified)
        jr nz,.hloop
        ret

; .start: HL = a hash -> DE = the first slot to try
.start: ld a,(.mask)
        and h
        ld e,a
        ld a,(.mask+1)
        and l
        ld d,a
        ret

; .find: HL = the hash of the name at .sp/.sn.
; Out: C and HL = its number + 1 if it's there; NC and HL = the empty slot where it would go if not.
.find:  call .start
.floop: ld hl,(.slots)
        add hl,de
        add hl,de
        ld a,(hl)
        inc hl
        or (hl)
        jr z,.fempty
        push de                     ; the slot's index
        ld d,(hl)
        dec hl
        ld e,(hl)                   ; DE = a number + 1
        push de
        ex de,hl
        dec hl
        add hl,hl
        add hl,hl
        ld de,(.names)
        add hl,de
        call .same
        pop hl                      ; the number + 1
        pop de                      ; the index
        scf
        ret z
        inc de
        ld a,(.mask)
        and e
        ld e,a
        ld a,(.mask+1)
        and d
        ld d,a
        jr .floop
.fempty:
        dec hl                      ; (NC, from the OR)
        ret

; .same: HL = &a name's str -> Z if it's the one at .sp/.sn
.same:  ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld hl,(.sn)
        or a
        sbc hl,bc
        ret nz
        ld a,b
        or c
        ret z
        ld hl,(.sp)
.sloop: ld a,(de)
        inc de
        cpi
        ret nz
        jp pe,.sloop
        ret

; .empty: HL = a hash -> HL = the first empty slot from its place (for names known not to be there)
.empty: call .start
.eloop: ld hl,(.slots)
        add hl,de
        add hl,de
        ld a,(hl)
        inc hl
        or (hl)
        dec hl
        ret z
        inc de
        ld a,(.mask)
        and e
        ld e,a
        ld a,(.mask+1)
        and d
        ld d,a
        jr .eloop

; .grow: twice the room (or 16 to start), the names copied over, the index built again
.grow:  ld hl,(.cap)
        add hl,hl
        ld a,h
        or l
        jr nz,.g1
        ld hl,16
.g1:    ld (.cap),hl                ; (at most 4096 in practice: 8192 would want two 32K blocks)
        add hl,hl
        dec hl
        ld (.mask),hl
        inc hl
        add hl,hl                   ; 4 x cap: the bytes of the strs, and of the slots
        push hl
        call bly_alloc_raw          ; the new strs (filled before they're read)
        ex de,hl
        ld hl,(.names)
        ld (.names),de
        ld bc,(.count)
        ld a,b
        or c
        jr z,.g2
        sla c
        rl b
        sla c
        rl b
        ldir
.g2:    pop hl
        call bly_alloc              ; the new index, all empty
        ld (.slots),hl
        ld hl,0
.g3:    ld (.i),hl
        ld de,(.count)
        or a
        sbc hl,de
        ret z                       ; every name is back
        add hl,de
        add hl,hl
        add hl,hl
        ld de,(.names)
        add hl,de
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld c,(hl)
        inc hl
        ld b,(hl)
        call .hash
        call .empty
        ld de,(.i)
        inc de
        ld (hl),e
        inc hl
        ld (hl),d
        ex de,hl
        jr .g3

.sp:    dw 0                        ; the name being looked up
.sn:    dw 0
.h:     dw 0                        ; and its hash
.i:     dw 0                        ; .grow's count
.names: dw 0
.slots: dw 0
.mask:  dw 0
.cap:   dw 0
.count: dw 0

bly_name:
        ld bc,(bly_intern.count)
        or a
        sbc hl,bc
        add hl,bc                   ; (carry as the subtraction left it)
        jr nc,.none
        add hl,hl
        add hl,hl
        ld bc,(bly_intern.names)
        add hl,bc
        ld bc,4
        ldir
        ret
.none:  push hl
        ld hl,.msg
        call bly_pr_cstr
        pop hl
        call bly_pr_u16
        jp bly_fail_end
.msg:   db "no name has the number ",0
