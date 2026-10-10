;; provides: bly_map_new bly_map_has bly_map_put bly_map_ref bly_map_getd bly_map_del bly_map_find
;; needs: bly_cn_cap bly_cn_cmul bly_cn_mul bly_cn_full bly_cn_afull bly_alloc bly_pr_cstr bly_fail
;; targets: cpm zx48 test
;; bly_map_new    in: HL=&block (+0 cap quad, +8 ksize, +10 vsize, +12 kpr, +14 kind byte)   out: HL=map
;;                fails: the capacity messages (as a map or a set), arena full                   clobbers: AF BC DE HL IX
;; bly_map_has    in: HL=map DE=&key                     out: A=0/1                              clobbers: AF BC DE HL IX
;; bly_map_put    in: HL=map DE=&key BC=&value (ignored for a set)   fails: map full ({cap}), set full ({cap})   clobbers: AF BC DE HL IX
;; bly_map_ref    in: HL=map DE=&key                     out: HL=&value   fails: no key {k} in the map   clobbers: AF BC DE HL IX
;; bly_map_getd   in: HL=map DE=&key BC=&default IX=&dest   dest = the value, or the default      clobbers: AF BC DE HL IX
;; bly_map_del    in: HL=map DE=&key                     no change if the key is absent          clobbers: AF BC DE HL IX
;; bly_map_find   in: IX=map DE=&key   out: NC: HL=&the key's index slot; C: HL=&the slot an insert would use
;;                (internal to this fragment and the tests)                  preserves DE IX   clobbers: AF BC HL
;;
;; The header (ABI.md 6): +0 ne, +2 live, +4 cap, +6 ver, +8 mask, +10 ksize, +12 vsize, +14 k, +16 v, +18 alive,
;; +20 ix, +22 kpr, +24 kind. As bly_map.h: entries in insertion order in dense arrays, an open-addressed index of
;; entry numbers (FFFFh empty, FFFEh deleted) at least twice cap and a power of two, compaction when ne reaches
;; cap with dead entries among them. One allocation holds the header and all four arrays, and one word more: FFFDh
;; just past the index marks its end, so the probe wraps without comparing addresses (nothing else reads it).
;; Keys are 1, 2, 4 or 8 bytes (integers and pos), hashed and compared as raw bytes. The hash is byte-wise:
;; h = (h xor b) * 33 for each byte, then h xor (h >> 8), and the low bits index. (On AoC-shaped keys, at most
;; half full, it averages under 1.8 probes to find a key and 2.5 to miss one: NOTES.md.)
;; A cap above 8192 can't fit (its index alone would be 64K), so it fails at once with arena full.

bly_map_new:                        ; HL=&block
        ld (.blk),hl
        ld de,14
        add hl,de
        ld a,(hl)
        ld (.kind),a
        add a,3                     ; 3 map, 4 set
        ld hl,(.blk)
        call bly_cn_cap
        ld (.cap),hl
        ld de,8193
        or a
        sbc hl,de
        jp nc,bly_cn_afull
        ld hl,(.cap)
        add hl,hl
        ex de,hl                    ; DE = 2 cap
        ld hl,4
.szl:   or a
        sbc hl,de
        jr nc,.sized
        add hl,de
        add hl,hl
        jr .szl
.sized: add hl,de
        ld (.size),hl               ; the index size: a power of two, at least 4 and 2 cap
        ld hl,(.blk)
        ld de,8
        add hl,de
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld (.ks),de
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld (.vs),de
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld (.kpr),de
        ld bc,(.cap)
        ld de,(.ks)
        call bly_cn_cmul
        jp c,bly_cn_afull
        ld (.kb),hl
        ld bc,(.cap)
        ld de,(.vs)
        call bly_cn_cmul
        jp c,bly_cn_afull
        ld (.vb),hl
        ld de,(.kb)
        add hl,de
        jp c,bly_cn_afull
        ld de,(.cap)
        add hl,de
        jp c,bly_cn_afull
        ld de,(.size)
        add hl,de
        jp c,bly_cn_afull
        add hl,de
        jp c,bly_cn_afull
        ld de,27                    ; the header, and the end mark after the index
        add hl,de
        jp c,bly_cn_afull
        call bly_alloc              ; HL = header, zeroed
        push hl
        pop ix
        ld de,(.cap)
        ld (ix+4),e
        ld (ix+5),d
        ld de,(.size)
        dec de
        ld (ix+8),e
        ld (ix+9),d
        ld de,(.ks)
        ld (ix+10),e
        ld (ix+11),d
        ld de,(.vs)
        ld (ix+12),e
        ld (ix+13),d
        ld de,(.kpr)
        ld (ix+22),e
        ld (ix+23),d
        ld a,(.kind)
        ld (ix+24),a
        ld de,25
        add hl,de
        ld (ix+14),l                ; k
        ld (ix+15),h
        ld de,(.kb)
        add hl,de
        ld (ix+16),l                ; v
        ld (ix+17),h
        ld de,(.vb)
        add hl,de
        ld (ix+18),l                ; alive
        ld (ix+19),h
        ld de,(.cap)
        add hl,de
        ld (ix+20),l                ; ix
        ld (ix+21),h
        call .empty                 ; every slot FFFFh, then FFFDh
        push ix
        pop hl
        ret
.empty:                             ; IX=map: fill the index with FFFFh
        ld l,(ix+20)
        ld h,(ix+21)
        ld c,(ix+8)
        ld b,(ix+9)
        inc bc
        sla c
        rl b
        dec bc                      ; 2 * size - 1 more bytes after the first
        ld (hl),0FFh
        ld d,h
        ld e,l
        inc de
        ldir
        ex de,hl                    ; just past the index: the end mark
        ld (hl),0FDh
        inc hl
        ld (hl),0FFh
        ret
.blk:   dw 0
.kind:  db 0
.cap:   dw 0
.size:  dw 0
.ks:    dw 0
.vs:    dw 0
.kpr:   dw 0
.kb:    dw 0
.vb:    dw 0

bly_map_find:                       ; IX=map DE=&key
        ld hl,0
        ld (.tomb),hl
        push de
        ld a,(ix+10)                ; ksize: 1, 2, 4 or 8
        cp 2
        jr c,.k1
        jr z,.k2
        cp 4
        jr z,.k4
        DUP 4                       ; h = (h xor b) * 33, a byte at a time
        ld a,(de)
        xor l
        ld l,a
        ld b,h
        ld c,l
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,bc
        inc de
        EDUP
.k4:    DUP 2
        ld a,(de)
        xor l
        ld l,a
        ld b,h
        ld c,l
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,bc
        inc de
        EDUP
.k2:    ld a,(de)
        xor l
        ld l,a
        ld b,h
        ld c,l
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,bc
        inc de
.k1:    ld a,(de)
        xor l
        ld l,a
        ld b,h
        ld c,l
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,hl
        add hl,bc
        pop de
        ld a,h                      ; h xor (h >> 8), then the mask
        xor l
        and (ix+8)
        ld l,a
        ld a,h
        and (ix+9)
        ld h,a
        add hl,hl
        ld c,(ix+20)
        ld b,(ix+21)
        add hl,bc                   ; HL = &ix[slot]
.probe: ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = the slot's word; HL = slot + 1
        ld a,b
        inc a
        jr z,.free                  ; FFFDh, FFFEh or FFFFh (entry numbers are below 8192)
        push hl
        ld l,c
        ld h,b
        ld a,(ix+10)
.shift: rra                         ; HL = e * ksize, ksize a power of two
        jr c,.kaddr
        add hl,hl
        jr .shift
.kaddr: ld c,(ix+14)
        ld b,(ix+15)
        add hl,bc                   ; &k[e]
        ld b,(ix+10)
        push de
.cmp:   ld a,(de)
        cp (hl)
        jr nz,.differ
        inc hl
        inc de
        djnz .cmp
        pop de
        pop hl
        dec hl                      ; found: HL = its slot, NC
        or a
        ret
.differ:
        pop de
        pop hl
        jr .next
.free:  ld a,c
        inc a
        jr z,.absent                ; FFFFh: the end of the chain
        inc a
        jr z,.dead
        ld l,(ix+20)                ; FFFDh: the end of the index, so wrap to its start
        ld h,(ix+21)
        jr .probe
.dead:  push hl                     ; FFFEh: keep the first, for an insert
        ld hl,(.tomb)
        ld a,h
        or l
        pop hl
        jr nz,.next
        dec hl
        ld (.tomb),hl
        inc hl
.next:  inc hl
        jr .probe
.absent:
        dec hl
        push hl
        ld hl,(.tomb)
        ld a,h
        or l
        jr z,.here
        pop af                      ; insert at the first deleted slot
        scf
        ret
.here:  pop hl                      ; insert at the empty slot
        scf
        ret
.tomb:  dw 0

bly_map_has:                        ; HL=map DE=&key -> A
        push hl
        pop ix
        call bly_map_find
        ld a,0
        ret c
        inc a
        ret

bly_map_del:                        ; HL=map DE=&key
        push hl
        pop ix
        call bly_map_find
        ret c
        ld c,(hl)
        ld (hl),0FEh                ; the slot becomes deleted
        inc hl
        ld b,(hl)
        ld (hl),0FFh
        ld l,(ix+18)
        ld h,(ix+19)
        add hl,bc
        ld (hl),0                   ; and the entry dead
        ld l,(ix+2)
        ld h,(ix+3)
        dec hl
        ld (ix+2),l                 ; live - 1
        ld (ix+3),h
        inc (ix+6)                  ; ver
        ret nz
        inc (ix+7)
        ret

bly_map_ref:                        ; HL=map DE=&key -> HL=&value
        push hl
        pop ix
        call bly_map_find
        jr c,.missing
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld e,(ix+12)
        ld d,(ix+13)
        call bly_cn_mul
        ld e,(ix+16)
        ld d,(ix+17)
        add hl,de
        ret
.missing:
        push de
        ld l,(ix+22)
        ld h,(ix+23)
        ld (.kpr+1),hl              ; self-modified: the key's printer
        ld hl,.no
        call bly_pr_cstr
        pop hl
.kpr:   call 0
        ld hl,.in
        jp bly_fail
.no:    db "no key ",0
.in:    db " in the map",0

bly_map_getd:                       ; HL=map DE=&key BC=&default IX=&dest
        ld (.dest),ix
        ld (.dflt),bc
        push hl
        pop ix
        call bly_map_find
        jr c,.dflt_
        ld c,(hl)
        inc hl
        ld b,(hl)
        ld e,(ix+12)
        ld d,(ix+13)
        call bly_cn_mul
        ld e,(ix+16)
        ld d,(ix+17)
        add hl,de
        jr .copy
.dflt_: ld hl,(.dflt)
.copy:  ld de,(.dest)
        ld c,(ix+12)
        ld b,(ix+13)
        ld a,b
        or c
        ret z
        ldir
        ret
.dest:  dw 0
.dflt:  dw 0

bly_map_put:                        ; HL=map DE=&key BC=&value
        push hl
        pop ix
        ld (.val),bc
        call bly_map_find
        jr c,.new
        ld a,(ix+12)
        or (ix+13)
        ret z                       ; a set: nothing more to say
        ld c,(hl)
        inc hl
        ld b,(hl)
        call .vaddr
        ex de,hl
        ld hl,(.val)
        ld c,(ix+12)
        ld b,(ix+13)
        ldir                        ; a new value for an old key: ver stays
        ret
.new:   push hl                     ; the slot to use
        ld l,(ix+2)
        ld h,(ix+3)                 ; live
        ld c,(ix+4)
        ld b,(ix+5)                 ; cap
        or a
        sbc hl,bc
        jr nc,.full
        ld l,(ix+0)
        ld h,(ix+1)                 ; ne
        or a                        ; (carry is set here: live < cap)
        sbc hl,bc                   ; ne - cap
        jr nz,.room
        pop hl
        call .compact               ; ne = cap with dead entries: squeeze them out
        call bly_map_find           ; and find the slot again in the new index
        push hl
.room:  pop hl
        ld c,(ix+0)
        ld b,(ix+1)                 ; e = ne
        ld (hl),c
        inc hl
        ld (hl),b                   ; the slot holds e
        ld l,c
        ld h,b
        inc hl
        ld (ix+0),l                 ; ne + 1
        ld (ix+1),h
        ld l,(ix+2)
        ld h,(ix+3)
        inc hl
        ld (ix+2),l                 ; live + 1
        ld (ix+3),h
        inc (ix+6)                  ; ver
        jr nz,.v
        inc (ix+7)
.v:     ld l,(ix+18)
        ld h,(ix+19)
        add hl,bc
        ld (hl),1                   ; alive
        push bc
        call .kaddr
        ex de,hl                    ; DE = &k[e], HL = &key
        ld c,(ix+10)
        ld b,(ix+11)
        ldir
        pop bc
        ld a,(ix+12)
        or (ix+13)
        ret z                       ; a set has no values
        call .vaddr
        ex de,hl
        ld hl,(.val)
        ld c,(ix+12)
        ld b,(ix+13)
        ldir
        ret
.full:  ld l,(ix+4)
        ld h,(ix+5)
        ld a,(ix+24)
        add a,3
        jp bly_cn_full
.kaddr:                             ; BC = e -> HL = &k[e]; keeps DE
        ld l,c
        ld h,b
        ld a,(ix+10)
.ks:    rra
        jr c,.kb
        add hl,hl
        jr .ks
.kb:    ld c,(ix+14)
        ld b,(ix+15)
        add hl,bc
        ret
.vaddr:                             ; BC = e -> HL = &v[e]; keeps DE
        push de
        ld e,(ix+12)
        ld d,(ix+13)
        call bly_cn_mul
        ld e,(ix+16)
        ld d,(ix+17)
        add hl,de
        pop de
        ret
.compact:                           ; keep the live entries, in order, at 0..live-1; then rebuild the index
        push de
        ld hl,0
        ld (.i),hl
        ld (.j),hl
.cl:    ld hl,(.i)
        ld c,(ix+0)
        ld b,(ix+1)
        or a
        sbc hl,bc
        jr nc,.cdone
        ld hl,(.i)
        ld c,(ix+18)
        ld b,(ix+19)
        add hl,bc
        ld a,(hl)
        or a
        jr z,.cnext                 ; dead: skip it
        ld hl,(.i)
        ld de,(.j)
        or a
        sbc hl,de
        jr z,.cmoved                ; already in place
        ld bc,(.j)
        call .kaddr
        push hl
        ld bc,(.i)
        call .kaddr
        pop de
        ld c,(ix+10)
        ld b,(ix+11)
        ldir                        ; k[j] = k[i]
        ld a,(ix+12)
        or (ix+13)
        jr z,.calive
        ld bc,(.j)
        call .vaddr
        push hl
        ld bc,(.i)
        call .vaddr
        pop de
        ld c,(ix+12)
        ld b,(ix+13)
        ldir                        ; v[j] = v[i]
.calive:
        ld hl,(.j)
        ld c,(ix+18)
        ld b,(ix+19)
        add hl,bc
        ld (hl),1
        ld hl,(.i)
        add hl,bc
        ld (hl),0
.cmoved:
        ld hl,(.j)
        inc hl
        ld (.j),hl
.cnext: ld hl,(.i)
        inc hl
        ld (.i),hl
        jp .cl
.cdone: ld hl,(.j)
        ld (ix+0),l                 ; ne = the live count
        ld (ix+1),h
        call bly_map_new.empty
        ld hl,0
        ld (.i),hl
.rl:    ld hl,(.i)                  ; index each entry again
        ld c,(ix+0)
        ld b,(ix+1)
        or a
        sbc hl,bc
        jr nc,.rdone
        ld bc,(.i)
        call .kaddr
        ex de,hl
        call bly_map_find           ; absent, so HL = the first empty slot on its chain
        ld bc,(.i)
        ld (hl),c
        inc hl
        ld (hl),b
        inc bc
        ld (.i),bc
        jr .rl
.rdone: pop de
        ret
.val:   dw 0
.i:     dw 0
.j:     dw 0
