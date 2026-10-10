;; provides: bly_list_new bly_list_push bly_list_pop bly_list_ref bly_list_clear
;; needs: bly_cn_new bly_cn_full bly_cn_mul bly_fail
;; targets: cpm zx48 test
;; bly_list_new    in: HL=&block (+0 cap quad, +8 esize)   out: HL=list   fails: the capacity messages, arena full   clobbers: AF BC DE HL IX
;; bly_list_push   in: HL=list DE=&v       copies v to the end      fails: list full ({cap})      clobbers: AF BC DE HL IX
;; bly_list_pop    in: HL=list DE=&dest    moves the last out       fails: list empty             clobbers: AF BC DE HL IX
;; bly_list_ref    in: HL=list DE=i        out: HL=&element i (i already checked)                 clobbers: AF BC DE HL
;; bly_list_clear  in: HL=list             n = 0                                                   clobbers: AF HL
;;
;; The header (ABI.md 6): +0 n, +2 cap, +4 ver, +6 esize, +8 a. bly_list_sort is in sort.asm.

bly_list_new:
        xor a                       ; kind 0, list
        ld bc,10*256+8              ; a 10-byte header, a at +8
        jp bly_cn_new

bly_list_push:                      ; HL=list DE=&v
        push hl
        pop ix
        ld l,(ix+0)
        ld h,(ix+1)                 ; n
        ld c,(ix+2)
        ld b,(ix+3)                 ; cap
        or a
        sbc hl,bc
        jr nc,.full
        add hl,bc
        ld b,h
        ld c,l                      ; BC = n, where v goes
        inc hl
        ld (ix+0),l
        ld (ix+1),h
        inc (ix+4)                  ; ver
        jr nz,.v
        inc (ix+5)
.v:     push de
        ld e,(ix+6)
        ld d,(ix+7)
        push de
        call bly_cn_mul             ; HL = n * esize
        ld e,(ix+8)
        ld d,(ix+9)
        add hl,de
        ex de,hl
        pop bc                      ; esize
        pop hl                      ; &v
        ldir
        ret
.full:  xor a
        ld h,b
        ld l,c
        jp bly_cn_full

bly_list_pop:                       ; HL=list DE=&dest
        push hl
        pop ix
        ld l,(ix+0)
        ld h,(ix+1)
        ld a,h
        or l
        jr z,.empty
        dec hl
        ld (ix+0),l
        ld (ix+1),h
        inc (ix+4)
        jr nz,.v
        inc (ix+5)
.v:     push de
        ld b,h
        ld c,l
        ld e,(ix+6)
        ld d,(ix+7)
        push de
        call bly_cn_mul
        ld e,(ix+8)
        ld d,(ix+9)
        add hl,de                   ; &a[n-1]
        pop bc
        pop de
        ldir
        ret
.empty: ld hl,.msg
        jp bly_fail
.msg:   db "list empty",0

bly_list_ref:                       ; HL=list DE=i -> HL = a + i*esize
        ld bc,6
        add hl,bc
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; esize
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        push hl                     ; a
        ld h,b
        ld l,c
        ld b,d
        ld c,e                      ; BC = i
        ex de,hl                    ; DE = esize
        call bly_cn_mul
        pop de
        add hl,de
        ret

bly_list_clear:
        xor a
        ld (hl),a
        inc hl
        ld (hl),a
        inc hl
        inc hl
        inc hl
        inc (hl)                    ; ver
        ret nz
        inc hl
        inc (hl)
        ret
