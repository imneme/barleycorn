;; provides: bly_cmp_u8 bly_cmp_u16 bly_cmp_i16 bly_lt bly_le bly_gt bly_ge bly_eq bly_ne bly_shl16 bly_shr_u16 bly_shr_i16 bly_ovf_int bly_ovf_long bly_ovf_quad bly_div0 bly_neg_shift bly_assert
;; needs: bly_fail
;; targets: cpm zx48 test
;; The code generator's own helpers: comparisons for the widths it does inline, turning a comparison into a bool, shifts
;; by a count known only at run time, and the failures its inline arithmetic jumps to.
;; bly_cmp_u8   in: A=x E=y      out: A=FFh/0/1 (x<y, x=y, x>y), flags as after OR A        clobbers: AF
;; bly_cmp_u16  in: HL=x DE=y    out: as bly_cmp_u8                                          clobbers: AF HL
;; bly_cmp_i16  in: HL=x DE=y    out: as bly_cmp_u8, signed                                  clobbers: AF HL
;; bly_lt bly_le bly_gt bly_ge bly_eq bly_ne   in: A=FFh/0/1   out: A=1 if the relation holds, else 0   clobbers: AF
;; bly_shl16    in: HL=x DE=count (signed)   out: HL = x << count, wrapped; fails: negative shift count   clobbers: AF B DE HL
;; bly_shr_u16  in: HL=x DE=count            out: HL = x >> count, zeros in                              clobbers: AF B DE HL
;; bly_shr_i16  in: HL=x DE=count            out: HL = x >> count, the sign in                           clobbers: AF B DE HL
;; bly_ovf_int bly_ovf_long bly_ovf_quad bly_div0 bly_neg_shift bly_assert   fail with their message   never return

bly_cmp_u8:
        cp e
        jr bly_cmp_u16.three
bly_cmp_u16:
        or a
        sbc hl,de
.three: ld a,0
        ret z
        ld a,1
        jr nc,.ret
        ld a,0FFh
.ret:   or a
        ret
bly_cmp_i16:
        ld a,h                      ; signs differ? then the sign decides
        xor d
        jp p,bly_cmp_u16            ; same sign: unsigned order is right
        ld a,h
        rla                         ; carry = x is negative
        ld a,0FFh
        jr c,.done
        ld a,1
.done:  or a
        ret

bly_lt: rlca                        ; FFh -> 1, 0 -> 0, 1 -> 0
        and 1
        ret
bly_ge: call bly_lt
        xor 1
        ret
bly_gt: dec a                       ; 1 -> 0, so ...
        ld a,0
        ret nz
        inc a
        ret
bly_le: call bly_gt
        xor 1
        ret
bly_eq: or a
        ld a,0
        ret nz
        inc a
        ret
bly_ne: or a
        ret z
        ld a,1
        ret

bly_shl16:
        bit 7,d
        jp nz,bly_neg_shift
        ld a,d
        or a
        jr nz,.zero
        ld a,e
        cp 16
        jr nc,.zero
        or a
        ret z
        ld b,a
.loop:  add hl,hl
        djnz .loop
        ret
.zero:  ld hl,0
        ret
bly_shr_u16:
        bit 7,d
        jp nz,bly_neg_shift
        ld a,d
        or a
        jr nz,bly_shl16.zero
        ld a,e
        cp 16
        jr nc,bly_shl16.zero
        or a
        ret z
        ld b,a
.loop:  srl h
        rr l
        djnz .loop
        ret
bly_shr_i16:
        bit 7,d
        jp nz,bly_neg_shift
        ld a,d
        or a
        jr nz,.fill
        ld a,e
        cp 15
        jr nc,.fill
        or a
        ret z
        ld b,a
.loop:  sra h
        rr l
        djnz .loop
        ret
.fill:  ld a,h                      ; 15 or more: all sign
        rla
        sbc a,a
        ld h,a
        ld l,a
        ret

bly_ovf_int:
        ld hl,.m
        jp bly_fail
.m:     db "int overflow",0
bly_ovf_long:
        ld hl,.m
        jp bly_fail
.m:     db "long overflow",0
bly_ovf_quad:
        ld hl,.m
        jp bly_fail
.m:     db "quad overflow",0
bly_div0:
        ld hl,.m
        jp bly_fail
.m:     db "division by zero",0
bly_neg_shift:
        ld hl,.m
        jp bly_fail
.m:     db "negative shift count",0
bly_assert:
        ld hl,.m
        jp bly_fail
.m:     db "assertion failed",0
