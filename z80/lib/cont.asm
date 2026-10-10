;; provides: bly_changed bly_cn_kind bly_cn_cap bly_cn_full bly_cn_afull bly_cn_mul bly_cn_cmul bly_cn_new
;; needs: bly_pr_cstr bly_pr_u16 bly_fail bly_alloc
;; targets: cpm zx48 test
;; bly_changed   in: A=kind (0 list, 1 queue, 2 heap, 3 map, 4 set)   the {kind} changed while for was walking it   never returns
;; bly_cn_kind   in: A=kind               prints the kind's name                                     clobbers: AF BC DE HL
;; bly_cn_cap    in: HL=&cap (quad) A=kind   out: HL=cap (1..65535); fails: a {kind} needs a capacity of at least 1, a {kind} holds at most 65535   clobbers: AF BC DE HL
;; bly_cn_full   in: A=kind HL=cap        {kind} full ({cap})                                        never returns
;; bly_cn_afull  in: -                    arena full (a size that can't even be counted in 16 bits)    never returns
;; bly_cn_mul    in: BC DE                out: HL = BC*DE mod 65536 (fast when D=0)                  clobbers: AF BC DE HL
;; bly_cn_cmul   in: BC DE                out: HL = BC*DE, carry set if it passed 65535               clobbers: AF DE HL
;; bly_cn_new    in: HL=&block (+0 cap quad, +8 esize) A=kind B=header bytes C=offset of the a field
;;               out: HL = a zeroed header with cap at a-6, esize at a-2, and a pointing past the header
;;               (and past one more element, the heap's tmp, when A=2); fails: the capacity messages, arena full   clobbers: AF BC DE HL IX
;;
;; Shared by the containers (list, queue, heap, map, set). The bly_cn_ names are the containers' own helpers,
;; not part of ABI.md; only bly_changed is.

bly_cn_kind:                        ; skip A names, then print one
        ld hl,.names
        or a
        jr z,.go
        ld b,a
.skip:  ld a,(hl)
        inc hl
        or a
        jr nz,.skip
        djnz .skip
.go:    jp bly_pr_cstr
.names: db "list",0,"queue",0,"heap",0,"map",0,"set",0

bly_changed:
        push af
        ld hl,.the
        call bly_pr_cstr
        pop af
        call bly_cn_kind
        ld hl,.rest
        jp bly_fail
.the:   db "the ",0
.rest:  db " changed while for was walking it",0

bly_cn_cap:                         ; HL=&cap (a quad), A=kind
        ld (.kind),a                ; scratch
        ld bc,7
        add hl,bc                   ; the top byte
        bit 7,(hl)
        jr nz,.small                ; negative
        ld b,6
        xor a
.hi:    or (hl)                     ; bytes 7..2 (DEC HL and DJNZ leave the flags alone)
        dec hl
        djnz .hi
        jr nz,.big
        ld a,(hl)
        dec hl
        ld l,(hl)
        ld h,a                      ; HL = the low word
        ld a,h
        or l
        ret nz
.small: ld hl,.needs
        jr .say
.big:   ld hl,.holds
.say:   push hl
        ld hl,.a
        call bly_pr_cstr
        ld a,(.kind)
        call bly_cn_kind
        pop hl
        jp bly_fail
.a:     db "a ",0
.needs: db " needs a capacity of at least 1",0
.holds: db " holds at most 65535",0
.kind:  db 0

bly_cn_full:                        ; A=kind, HL=cap
        push hl
        call bly_cn_kind
        ld hl,.open
        call bly_pr_cstr
        pop hl
        call bly_pr_u16
        ld hl,.close
        jp bly_fail
.open:  db " full (",0
.close: db ")",0

bly_cn_afull:
        ld hl,.msg
        jp bly_fail
.msg:   db "arena full",0

bly_cn_mul:                         ; HL = BC*DE, walking DE's bits from the bottom
        ld hl,0
        ld a,d
        or a
        jr nz,.wide
        or e                        ; A = E, the usual case (an element size)
        ret z
.loop8: srl a
        jr nc,.skip8
        add hl,bc
        ret z                       ; Z is still SRL's: no bits left
.skip8: sla c
        rl b
        jr .loop8
.wide:  ld a,16                     ; top bit first
.lw:    add hl,hl
        ex de,hl
        add hl,hl
        ex de,hl
        jr nc,.nw
        add hl,bc
.nw:    dec a
        jr nz,.lw
        ret

bly_cn_cmul:                        ; HL = BC*DE, carry if it doesn't fit. Top bit first, so any carry is real.
        ld hl,0
        ld a,16
.l:     add hl,hl
        ret c
        ex de,hl
        add hl,hl
        ex de,hl
        jr nc,.n
        add hl,bc
        ret c
.n:     dec a
        jr nz,.l
        or a
        ret

bly_cn_new:                         ; HL=&block A=kind B=header bytes C=offset of the a field
        ld (.hb),bc                 ; scratch: .hb = C, .hb+1 = B
        ld (.kind),a
        push hl
        call bly_cn_cap
        ld (.cap),hl
        pop hl
        ld de,8
        add hl,de
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld (.es),de
        ld bc,(.cap)
        ld a,(.kind)
        cp 2
        jr nz,.count
        inc bc                      ; a heap holds one more element: tmp
        ld a,b
        or c
        jp z,bly_cn_afull
.count: call bly_cn_cmul            ; HL = elements * esize
        jp c,bly_cn_afull
        ld a,(.hb+1)
        ld e,a
        ld d,0
        add hl,de
        jp c,bly_cn_afull
        call bly_alloc              ; HL = the header, zeroed
        push hl
        ld a,(.hb)
        sub 6
        ld e,a
        ld d,0
        add hl,de
        push hl
        pop ix                      ; IX = header + a - 6: cap at +0, esize at +4, a at +6
        ld de,(.cap)
        ld (ix+0),e
        ld (ix+1),d
        ld de,(.es)
        ld (ix+4),e
        ld (ix+5),d
        pop hl
        push hl
        ld a,(.hb+1)
        ld c,a
        ld b,0
        add hl,bc                   ; past the header
        ld a,(.kind)
        cp 2
        jr nz,.a
        add hl,de                   ; and past the heap's tmp
.a:     ld (ix+6),l
        ld (ix+7),h
        pop hl
        ret
.hb:    dw 0
.kind:  db 0
.cap:   dw 0
.es:    dw 0
