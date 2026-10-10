;; provides: bly_zx_plot bly_zx_point bly_zx_attr bly_zx_udg
;; needs: bly_out bly_pr_cstr bly_pr_i16 bly_pr_u16 bly_fail bly_fail_end
;; targets: zx48 test
;; The Spectrum's drawing (ABI.md section 10; the meaning is ../zxgfx.py), in three fragments so a program links only
;; what it draws with: zxgfx.asm (plot, point, attr, udg, and the pieces the others share), zxline.asm, zxcircle.asm.
;; The screen is memory: bitmap at 4000h, attributes at 5800h. Colours come from ATTR_P (5C8Dh), OVER and INVERSE from
;; P_FLAG's permanent bits 1 and 3 (5C91h), and the UDGs' address from UDG (5C7Bh). Coordinates are BASIC's: x 0..255,
;; y 0..175 from the bottom.
;; bly_zx_plot    in: HL=x DE=y (ints)               fails: ({x}, {y}) is off the screen               clobbers: AF BC DE HL
;; bly_zx_point   in: HL=x DE=y                      out: A=0/1   fails: as plot                        clobbers: AF BC DE HL
;; bly_zx_attr    in: HL=r DE=c C=a                  fails: attr ({r}, {c}) is off the screen           clobbers: AF BC DE HL
;; bly_zx_udg     in: HL=n DE=&view (byte[]: address, length)
;;                fails: udg {n} is not one of 0..20 (A to U); a udg is 8 rows, not {len}           clobbers: AF BC DE HL
;; For zxline and zxcircle: bly_zx_plot.chk (the check and its message), .addr (a pixel's byte and mask), .ops and
;; .opsd (the pixel's operation, for patching), .masks.

ZXG_ATTR_P equ 5C8Dh
ZXG_P_FLAG equ 5C91h
ZXG_UDG    equ 5C7Bh

; ---- plot, and the pieces everything shares ------------------------------------------------------------------
; A pixel's operation, with M its mask: plain sets it (OR M), INVERSE clears it ((OR M) XOR M), OVER flips it (XOR M),
; and both together leave it. So line and circle patch two instructions, "or" unless OVER and "xor" when exactly one
; of OVER and INVERSE is on, and never test the mode per pixel.

bly_zx_plot:                        ; HL = x, DE = y
        ld a,h
        or d
        jp nz,.off
        ld a,e
        cp 176
        jp nc,.off
        ld c,l                      ; C = x
        ld a,175
        sub e                       ; A = 175 - y = TT RRR SSS, the row from the top; no borrow
        ld h,a
        rra                         ; carry in 0
        scf
        rra                         ; carry in 1
        or a
        rra                         ; carry in 0: A = 010 TT RRR
        ld l,a
        xor h
        and 0F8h
        xor h
        ld h,a                      ; H = 010 TT SSS
        ld a,l
        xor c
        and 7
        xor c                       ; x's top five bits, then RRR
        rrca
        rrca
        rrca
        ld l,a                      ; L = RRR, then x's top five bits
        ld a,c
        and 7
        add a,low .masks
        ld e,a
        adc a,high .masks
        sub e
        ld d,a
        ld a,(de)
        ld d,a                      ; D = the mask
        ld a,(ZXG_P_FLAG)
        and 0Ah                     ; bit 1 OVER, bit 3 INVERSE (the permanent ones)
        jr nz,.modes
        ld a,d
        or (hl)
.store: ld (hl),a
.colour:                            ; HL = a bitmap byte: its cell gets ATTR_P
        ld a,h
        rrca
        rrca
        rrca
        and 3
        or 58h
        ld h,a
        ld a,(ZXG_ATTR_P)
        ld (hl),a
        ret
.modes: cp 2
        jr z,.over
        cp 8
        jr nz,.colour               ; OVER and INVERSE together leave the pixel alone
        ld a,d                      ; INVERSE: clear it
        cpl
        and (hl)
        jr .store
.over:  ld a,d                      ; OVER: flip it
        xor (hl)
        jr .store

.addr:  ; C = x, B = y -> HL = the bitmap byte, A = the bit's mask.  keeps BC, IX; clobbers DE
        ld a,175
        sub b
        ld h,a
        rra
        scf
        rra
        or a
        rra
        ld l,a
        xor h
        and 0F8h
        xor h
        ld h,a
        ld a,l
        xor c
        and 7
        xor c
        rrca
        rrca
        rrca
        ld l,a
        ld a,c
        and 7
        add a,low .masks
        ld e,a
        adc a,high .masks
        sub e
        ld d,a
        ld a,(de)
        ret

.ops:   ; the pixel's operation for patching: D = "or c" (B1h) or nop, E = "xor c" (A9h) or nop.  clobbers AF
        ld a,(ZXG_P_FLAG)
        ld d,0B1h
        bit 1,a
        jr z,.ops1
        ld d,0                      ; OVER: no or
.ops1:  ld e,a
        rrca
        rrca
        xor e                       ; bit 1 = INVERSE xor OVER
        ld e,0
        and 2
        ret z
        ld e,0A9h
        ret

.opsd:  ; as .ops, on register D: "or d" (B2h), "xor d" (AAh)
        call .ops
        ld a,d
        or a
        jr z,.od1
        inc d
.od1:   ld a,e
        or a
        ret z
        inc e
        ret

.chk:   ; HL = x, DE = y (ints): returns if (x, y) is on the screen (then L = x, E = y); otherwise fails
        ld a,h
        or d
        jr nz,.off
        ld a,e
        cp 176
        ret c
.off:   push de
        push hl
        ld a,'('
        call bly_out
        pop hl
        call bly_pr_i16
        ld hl,.comma
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        ld hl,.offmsg
        jp bly_fail
.comma: db ", ",0
.offmsg: db ") is off the screen",0

.masks: db 80h,40h,20h,10h,08h,04h,02h,01h     ; not aligned: zxbuild.py assembles twice at different origins,
                                                ; so no fragment's size may depend on where it lands

; ---- point ----------------------------------------------------------------------------------------------------

bly_zx_point:                       ; HL = x, DE = y -> A = 1 if the pixel is set
        call bly_zx_plot.chk
        ld c,l
        ld b,e
        call bly_zx_plot.addr
        and (hl)
        ret z
        ld a,1
        ret

; ---- attr -----------------------------------------------------------------------------------------------------

bly_zx_attr:                        ; HL = r, DE = c (ints), C = a
        ld a,h
        or d
        jr nz,.off
        ld a,l
        cp 24
        jr nc,.off
        ld a,e
        cp 32
        jr nc,.off
        ld a,l                      ; r = 000 r4 r3 r2 r1 r0
        rrca
        rrca
        rrca                        ; r2 r1 r0 0 0 0 r4 r3
        ld l,a
        and 0E0h
        or e
        ld e,a                      ; the low byte: r's low three bits, then c
        ld a,l
        and 3
        or 58h
        ld d,a                      ; 58h + r / 8
        ld a,c
        ld (de),a
        ret
.off:   push de
        push hl
        ld hl,.msg
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        ld hl,bly_zx_plot.comma
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        ld hl,bly_zx_plot.offmsg
        jp bly_fail
.msg:   db "attr (",0

; ---- udg ------------------------------------------------------------------------------------------------------

bly_zx_udg:                         ; HL = n (int), DE = &view: +0 address, +2 length
        ld a,h
        or a
        jr nz,.badn
        ld a,l
        cp 21
        jr nc,.badn
        ex de,hl                    ; HL = &view, DE = n
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = the rows
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                      ; HL = how many
        ld a,h
        or a
        jr nz,.badlen
        ld a,l
        cp 8
        jr nz,.badlen
        ex de,hl                    ; HL = n
        add hl,hl
        add hl,hl
        add hl,hl
        ld de,(ZXG_UDG)
        add hl,de
        ex de,hl                    ; DE = UDG + 8n
        ld h,b
        ld l,c
        ld bc,8
        ldir
        ret
.badn:  push hl
        ld hl,.m_udg
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        ld hl,.m_range
        jp bly_fail
.badlen:
        push hl
        ld hl,.m_rows
        call bly_pr_cstr
        pop hl
        call bly_pr_u16
        jp bly_fail_end
.m_udg:   db "udg ",0
.m_range: db " is not one of 0..20 (A to U)",0
.m_rows:  db "a udg is 8 rows, not ",0

