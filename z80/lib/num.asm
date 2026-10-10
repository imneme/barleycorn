;; provides: bly_pr_u8 bly_pr_i32 bly_pr_u32 bly_n_dig bly_pr_i64
;; needs: bly_out bly_pr_u16
;; targets: cpm zx48 test
;; bly_pr_u8   in: A                    unsigned decimal                                   clobbers: AF BC DE HL
;; bly_pr_i32  in: HL=&v (a long)       signed decimal, no division                        clobbers: AF BC DE HL IX
;; bly_pr_u32  in: DE:HL (DE high)      unsigned decimal, no division                      clobbers: AF BC DE HL IX
;; bly_pr_i64  in: HL=&v (a quad)       signed decimal                                     clobbers: AF BC DE HL IX
;; bly_n_dig   in: IX=low word HL=high word DE=a power's entry in bly_n_dig.t32   prints from that power down,
;;             zeros included (the value must be below ten times that power)      clobbers: AF BC DE HL IX
;
; Numbers out, division-free (as z88dk does it, done non-restoring). A digit is found by counting how many times a
; power of ten goes into the value. Counting up subtracts the power until the value goes negative; instead of adding
; one back, the next digit counts *down*, adding the next power until the value is back at zero or more. Every step
; is one add, and no step is spent restoring. In 32 bits the value lives in IX (low) and HL (high), so a step is
; ADD IX,BC / ADC HL,DE, 46 T with the loop. After 10^4 the value fits 16 bits and the last three powers go in HL.
; A quad above 32 bits splits at 10^9, q * 10^9 + r, by 32 steps of shift-and-subtract: that needs only v >> 32 <
; 10^9 and q < 2^32, so it serves every quad below 10^9 * 2^32 (about 4.29 * 10^18). Above that (rare), the 10^18
; digit comes off first by subtraction. q and r go through the 32-bit digits, r always as nine.
; Scratch: bly_pr_i64.v, .top. The 16-bit numbers are core's bly_pr_u16.

bly_pr_u8:                          ; A: 0..255, no leading zeros
        cp 100
        jr c,.lt100
        ld c,'1'
        sub 100
        cp 100
        jr c,.hund
        inc c
        sub 100
.hund:  ld b,a                      ; B = what's left, 0..99
        ld a,c
        push bc
        call bly_out
        pop bc
        ld a,b
        jr .tens                    ; the tens print even when 0
.lt100: cp 10
        jr c,.units
.tens:  ld c,'0'-1
.tl:    inc c
        sub 10
        jr nc,.tl
        add a,'0'+10
        ld b,a                      ; B = the units digit
        ld a,c
        push bc
        call bly_out
        pop bc
        ld a,b
        jp bly_out
.units: add a,'0'
        jp bly_out

bly_pr_i32:                         ; HL = &v
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        ex de,hl                    ; DE:HL = v
        bit 7,d
        jr z,bly_pr_u32
        push de
        push hl
        ld a,'-'
        call bly_out
        pop hl
        pop de
        xor a                       ; DE:HL = -v (and -2^31 comes out as 2^31, unsigned)
        sub l
        ld l,a
        ld a,0
        sbc a,h
        ld h,a
        ld a,0
        sbc a,e
        ld e,a
        ld a,0
        sbc a,d
        ld d,a
        ; fall into bly_pr_u32

bly_pr_u32:                         ; DE:HL, unsigned
        ld a,d
        or e
        jp z,bly_pr_u16             ; below 65536: core's
        push hl
        pop ix                      ; IX = the low word
        ex de,hl                    ; HL = the high word
        ld de,bly_n_dig.t32
.skip:  ld a,e                      ; leading zeros: find the first power the value reaches
        cp bly_n_dig.t4 & 0FFh      ; (the value is 65536 or more, so 10^4 needs no test)
        jr z,.go
        push de
        push hl
        ex de,hl                    ; HL = the entry, DE = the high word
        ld c,(hl)
        inc hl
        ld b,(hl)
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                      ; BC:HL = -P
        push ix
        add ix,bc
        pop ix                      ; (POP keeps the flags)
        adc hl,de                   ; carry: the value is at least P
        pop hl
        pop de
        jr c,.go
        ld a,e
        add a,8
        ld e,a
        jr nc,.skip
        inc d
        jr .skip
.go:                                ; fall into bly_n_dig

bly_n_dig:                          ; IX = low word, HL = high word, DE = the entry for the first power
.up:    push de                     ; count up: subtract P until the value goes negative
        ex de,hl
        ld c,(hl)
        inc hl
        ld b,(hl)
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        ex de,hl                    ; BC = -P low, DE = -P high, HL = the value's high word
        ld a,'0'-1
.upl:   inc a
        add ix,bc
        adc hl,de
        jr c,.upl                   ; carry: it was still at least P
        push hl
        call bly_out
        pop hl
        pop de
        ld a,e
        add a,8
        ld e,a
        jr nc,.up1
        inc d
.up1:   cp .t32end & 0FFh
        jr nz,.down
        push ix                     ; past 10^4: the rest fits 16 bits, and it's negative now
        pop hl
        ld de,.t16
        jr .down16
.down:  push de                     ; count down: add P until the value is no longer negative
        ex de,hl
        inc hl
        inc hl
        inc hl
        inc hl
        ld c,(hl)
        inc hl
        ld b,(hl)
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        ex de,hl                    ; BC = P low, DE = P high
        ld a,'0'+10
.dnl:   dec a
        add ix,bc
        adc hl,de
        jr nc,.dnl                  ; no carry: still negative
        push hl
        call bly_out
        pop hl
        pop de
        ld a,e
        add a,8
        ld e,a
        jr nc,.dn1
        inc d
.dn1:   cp .t32end & 0FFh
        jr nz,.up
        push ix                     ; past 10^4, and not negative
        pop hl
        ld de,.t16
.up16:  ex de,hl                    ; HL = the 16-bit value, DE = its entry
        ld c,(hl)
        inc hl
        ld b,(hl)
        inc hl
        inc hl
        inc hl
        ex de,hl                    ; BC = -P
        ld a,'0'-1
.u16:   inc a
        add hl,bc
        jr c,.u16
        push hl
        push de
        call bly_out
        pop de
        pop hl
        ld a,e
        cp .t16end & 0FFh
        jr nz,.down16
        ld a,l                      ; the units: the value is -10..-1, so add the 10 back
        add a,'0'+10
        jp bly_out
.down16:
        ex de,hl
        inc hl
        inc hl
        ld c,(hl)
        inc hl
        ld b,(hl)
        inc hl
        ex de,hl                    ; BC = P
        ld a,'0'+10
.d16:   dec a
        add hl,bc
        jr nc,.d16
        push hl
        push de
        call bly_out
        pop de
        pop hl
        ld a,e
        cp .t16end & 0FFh
        jr nz,.up16
        ld a,l                      ; the units: the value is 0..9
        add a,'0'
        jp bly_out
; each entry: -P then P, as 32-bit words (low word first); the pointer arithmetic above compares only low bytes,
; which is safe because a table spans far less than 256 bytes
.t32:   dd -1000000000, 1000000000
.t8:    dd -100000000, 100000000
        dd -10000000, 10000000
        dd -1000000, 1000000
        dd -100000, 100000
.t4:    dd -10000, 10000
.t32end:
.t16:   dw -1000, 1000
        dw -100, 100
        dw -10, 10
.t16end:

bly_pr_i64:                         ; HL = &v
        ld de,.v
        ld bc,8
        ldir
        ld a,(.v+7)
        or a
        jp p,.mag
        ld a,'-'
        call bly_out
        ld hl,.v                    ; v = -v (-2^63 comes out as 2^63, unsigned)
        ld b,8
        or a
.neg:   ld a,0
        sbc a,(hl)
        ld (hl),a
        inc hl
        djnz .neg
.mag:   ld hl,(.v+4)
        ld a,h
        or l
        ld hl,(.v+6)
        or h
        or l
        jr nz,.big
        ld hl,(.v)                  ; it fits 32 bits
        ld de,(.v+2)
        jp bly_pr_u32
.big:   ld ix,0                     ; IX = the digit for 10^18
        ld a,(.v+7)                 ; below 3B00...h, v < 10^9 * 2^32: then v >> 32 < 10^9 and q < 2^32, and
        cp 3Bh                      ; splitting at 10^9 is enough. Above it (rare), take 10^18's digit first
        jr c,.split
        ld hl,(.v+2)                ; v's top 48 bits: 10^18 = 0DE0B6B3A7640000h has a zero low word,
        ld de,(.v+4)                ; so bytes 0-1 never change
        ld bc,(.v+6)
.e18:   ld a,l                      ; v -= 10^18, as long as it goes
        sub 64h
        ld l,a
        ld a,h
        sbc a,0A7h
        ld h,a
        ld a,e
        sbc a,0B3h
        ld e,a
        ld a,d
        sbc a,0B6h
        ld d,a
        ld a,c
        sbc a,0E0h
        ld c,a
        ld a,b
        sbc a,0Dh
        ld b,a
        jr c,.r18
        inc ix
        jr .e18
.r18:   ld a,l                      ; one too many: put it back
        add a,64h
        ld l,a
        ld a,h
        adc a,0A7h
        ld h,a
        ld a,e
        adc a,0B3h
        ld e,a
        ld a,d
        adc a,0B6h
        ld d,a
        ld a,c
        adc a,0E0h
        ld c,a
        ld a,b
        adc a,0Dh
        ld b,a
        ld (.v+2),hl
        ld (.v+4),de
        ld (.v+6),bc
.split: ld (.top),ix                ; v = q * 10^9 + r, with q < 2^32 (and q < 10^9 when there's a top digit)
        ld hl,(.v+4)                ; R = v >> 32, below 10^9
        ld de,(.v+6)
        ld a,(.v+3)                 ; then a byte at a time, each byte becoming q's
        call .byte
        ld (.v+3),a
        ld a,(.v+2)
        call .byte
        ld (.v+2),a
        ld a,(.v+1)
        call .byte
        ld (.v+1),a
        ld a,(.v)
        call .byte
        ld (.v),a
        ld (.v+4),hl                ; r
        ld (.v+6),de
        ld a,(.top)
        or a
        jr z,.notop
        add a,'0'
        call bly_out
        ld ix,(.v)                  ; q, as nine digits
        ld hl,(.v+2)
        ld de,bly_n_dig.t8
        call bly_n_dig
        jr .low
.notop: ld hl,(.v)                  ; q, as it comes (at least 4, since v >= 2^32)
        ld de,(.v+2)
        call bly_pr_u32
.low:   ld ix,(.v+4)                ; r, as nine digits
        ld hl,(.v+6)
        ld de,bly_n_dig.t8
        jp bly_n_dig
.byte:  ld c,a                      ; A = a dividend byte, DE:HL = R < 10^9; out A = the quotient byte
        ld b,8                      ; restoring, the quotient collected inverted (as z88dk does it)
.bit:   rl c
        adc hl,hl
        rl e
        rl d                        ; R = 2R + the next bit, below 2^31
        ld a,h                      ; R - 10^9 (3B9ACA00h; its low byte is 0)
        sub 0CAh
        ld a,e
        sbc a,9Ah
        ld a,d
        sbc a,3Bh
        jr c,.zero                  ; borrow: the quotient bit is 0, and carry holds its complement
        ld a,h
        sub 0CAh
        ld h,a
        ld a,e
        sbc a,9Ah
        ld e,a
        ld a,d
        sbc a,3Bh
        ld d,a                      ; no borrow: carry 0, the complement of 1
.zero:  djnz .bit
        rl c
        ld a,c
        cpl
        ret
.v:     ds 8                        ; scratch: the value, then q and r
.top:   dw 0                        ; the 10^18 digit (a word: it's stored from IX)
