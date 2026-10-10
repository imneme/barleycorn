;; provides: bly_queue_new bly_queue_put bly_queue_get bly_queue_at
;; needs: bly_cn_new bly_cn_full bly_cn_mul bly_fail
;; targets: cpm zx48 test
;; bly_queue_new   in: HL=&block (+0 cap quad, +8 esize)   out: HL=queue   fails: the capacity messages, arena full   clobbers: AF BC DE HL IX
;; bly_queue_put   in: HL=queue DE=&v      copies v in at the tail   fails: queue full ({cap})    clobbers: AF BC DE HL IX
;; bly_queue_get   in: HL=queue DE=&dest   moves the head out         fails: queue empty          clobbers: AF BC DE HL IX
;; bly_queue_at    in: HL=queue DE=i       out: HL=&element i from the head (i < n)                clobbers: AF BC DE HL IX
;;
;; The header (ABI.md 6): +0 head, +2 n, +4 cap, +6 ver, +8 esize, +10 a. A ring of cap elements.

bly_queue_new:
        ld a,1                      ; kind 1, queue
        ld bc,12*256+10             ; a 12-byte header, a at +10
        jp bly_cn_new

bly_queue_put:                      ; HL=queue DE=&v
        push hl
        pop ix
        ld l,(ix+2)
        ld h,(ix+3)                 ; n
        ld c,(ix+4)
        ld b,(ix+5)                 ; cap
        or a
        sbc hl,bc
        jr nc,.full
        add hl,bc
        inc hl
        ld (ix+2),l
        ld (ix+3),h
        dec hl
        inc (ix+6)                  ; ver
        jr nz,.v
        inc (ix+7)
.v:     push de
        ex de,hl                    ; DE = n
        call bly_queue_at.slot      ; HL = &a[(head + n) mod cap]
        ex de,hl
        pop hl
        ld c,(ix+8)
        ld b,(ix+9)
        ldir
        ret
.full:  ld a,1
        ld h,b
        ld l,c
        jp bly_cn_full

bly_queue_get:                      ; HL=queue DE=&dest
        push hl
        pop ix
        ld l,(ix+2)
        ld h,(ix+3)
        ld a,h
        or l
        jr z,.empty
        dec hl
        ld (ix+2),l
        ld (ix+3),h
        inc (ix+6)
        jr nz,.v
        inc (ix+7)
.v:     ld c,(ix+0)
        ld b,(ix+1)                 ; BC = head, which goes out
        push de
        ld l,c
        ld h,b
        inc hl                      ; head < cap <= 65535, so no carry
        ld e,(ix+4)
        ld d,(ix+5)
        or a
        sbc hl,de
        jr z,.wrap                  ; head + 1 = cap: back to 0
        add hl,de
.wrap:  ld (ix+0),l
        ld (ix+1),h
        ld e,(ix+8)
        ld d,(ix+9)
        call bly_cn_mul             ; HL = old head * esize
        ld e,(ix+10)
        ld d,(ix+11)
        add hl,de
        pop de
        ld c,(ix+8)
        ld b,(ix+9)
        ldir
        ret
.empty: ld hl,.msg
        jp bly_fail
.msg:   db "queue empty",0

bly_queue_at:                       ; HL=queue DE=i
        push hl
        pop ix
.slot:                              ; IX=queue DE=i < cap -> HL = &a[(head + i) mod cap]
        ld l,(ix+0)
        ld h,(ix+1)
        ld c,(ix+4)
        ld b,(ix+5)
        add hl,de                   ; head + i < 2*cap, which may pass 65535
        jr c,.over
        or a
        sbc hl,bc
        jr nc,.in
        add hl,bc
        jr .in
.over:  or a
        sbc hl,bc                   ; modulo 65536 this is still head + i - cap
.in:    ld b,h
        ld c,l
        ld e,(ix+8)
        ld d,(ix+9)
        call bly_cn_mul
        ld e,(ix+10)
        ld d,(ix+11)
        add hl,de
        ret
