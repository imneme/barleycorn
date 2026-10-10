;; provides: bly_num bly_str_int bly_str_intk bly_ints_init bly_ints_next bly_ints_val
;; needs: bly_out bly_pr_cstr bly_pr_str bly_fail bly_fail_end bly_pr_i64
;; targets: cpm zx48 test
;; bly_num        in: HL=&digits BC=count A=type (0 byte 1 word 2 int 3 long 4 quad 5 dword, +80h if negative) DE=&dest
;;                out: (DE) = the number, in the type's width   fails: {digits} doesn't fit in {a type}
;;                clobbers: AF BC DE HL IX
;; bly_str_int    in: HL=&str A=type DE=&dest   fails: "{s}" doesn't start with an integer, and as bly_num
;;                clobbers: AF BC DE HL IX
;; bly_str_intk   in: HL=&str BC=&k (a quad) A=type DE=&dest   fails: there is no integer {k} in "{s}", and as
;;                bly_num   clobbers: AF BC DE HL IX
;; bly_ints_init  in: HL=&state (12 bytes) DE=&str                                        clobbers: AF BC DE HL
;; bly_ints_next  in: HL=&state   out: A=1 (NZ) and the next number found, or A=0 (Z) at the end
;;                clobbers: AF BC DE HL IX
;; bly_ints_val   in: HL=&state A=type DE=&dest   out, fails: as bly_num                  clobbers: AF BC DE HL IX
;
; Numbers in. The digits stay text until they're known to fit, so a number too big for anything is reported exactly
; (barley.h's bly_num). Leading zeros go first; then a run longer than the type's widest (3, 5, 5, 10, 19 digits)
; fails without arithmetic. What's left can't overflow 64 bits, so the stages need no overflow tests at all:
; digits 1-4 in HL (unrolled), the fifth into DE:HL through its carry, 6-9 in DE:HL, 10-19 in a quad in memory;
; and the range is checked once, at the end.
; The ints() state: +0 p (the str's start) +2 cur +4 rem (bytes left from cur) +6 st (the digits found) +8 their
; count +10 sign (0 or 80h) +11 unused.
; Scratch: bly_num's .code .dest .dig .n .acc, bly_str_int's .s .dst .ty, bly_str_intk's .s .k .st.

bly_num:
        ld (.code),a
        ld (.dest),de
        ld a,(hl)
        cp '0'
        jp z,.strip                 ; leading zeros go first (rare)
.go:    ld (.dig),hl                ; .dig and .n: the digits as a str, for the message
        ld (.n),bc
        ld a,b
        or a
        jp nz,.toobig               ; 256 digits or more
        ld a,c
        cp 4
        jr c,.short                 ; three digits fit every type's width
        ld de,.maxd
        ld a,(.code)
        and 7
        add a,e
        ld e,a
        adc a,d
        sub e
        ld d,a
        ld a,(de)
        cp c
        jp c,.toobig                ; more digits than the type ever holds
.short: ex de,hl                    ; DE = the digits, C = how many
        ld hl,0
        ld a,c
        or a
        jp z,.fit16                 ; no digits: 0
        ld a,(de)                   ; the first digit is the value
        inc de
        sub '0'
        ld l,a
        dec c
        jp z,.fit16
        dec c
        jr z,.u1
        dec c
        jr z,.u2
.u3:    ld a,(de)                   ; digits 2-4, unrolled: HL = HL*10 + digit
        inc de
        sub '0'
        ld b,h
        ld c,l
        add hl,hl
        add hl,hl
        add hl,bc
        add hl,hl
        add a,l
        ld l,a
        adc a,h
        sub l
        ld h,a
.u2:    ld a,(de)
        inc de
        sub '0'
        ld b,h
        ld c,l
        add hl,hl
        add hl,hl
        add hl,bc
        add hl,hl
        add a,l
        ld l,a
        adc a,h
        sub l
        ld h,a
.u1:    ld a,(de)
        inc de
        sub '0'
        ld b,h
        ld c,l
        add hl,hl
        add hl,hl
        add hl,bc
        add hl,hl
        add a,l
        ld l,a
        adc a,h
        sub l
        ld h,a
        ld a,(.n)
        cp 5
        jp c,.fit16
        push de
        pop ix                      ; IX = the digits from the fifth
        ld a,(ix+0)                 ; the fifth digit: HL*10 + d is below 2^17, so its carry is the high word
        inc ix
        sub '0'
        ld b,h
        ld c,l
        add hl,hl
        add hl,hl
        add hl,bc
        ld de,0
        add hl,hl
        rl e
        add a,l
        ld l,a
        jr nc,.d5
        inc h
        jr nz,.d5
        inc e
.d5:    ld a,(.n)
        sub 5
        jr z,.fit32
        cp 5
        jr c,.k32
        ld a,4
.k32:   ld b,a                      ; B = digits 6..9, 1 to 4 of them, in DE:HL
.l32:   ld a,(ix+0)
        inc ix
        sub '0'
        push bc
        push de                     ; *10 as (x*4 + x)*2
        push hl
        add hl,hl
        rl e
        rl d
        add hl,hl
        rl e
        rl d
        pop bc
        add hl,bc
        ex de,hl
        pop bc
        adc hl,bc
        ex de,hl
        add hl,hl
        rl e
        rl d
        ld c,a
        ld b,0
        add hl,bc
        jr nc,.nc32
        inc de
.nc32:  pop bc
        djnz .l32
        ld a,(.n)
        cp 10
        jp nc,.s64
        jr .fit32
.fit16: ld de,0
.fit32: ld a,(.code)                ; the magnitude is DE:HL, nine digits or fewer
        ld c,a
        and 7
        cp 3
        jr nc,.wide                 ; a long or a quad: nine digits always fit
        ld b,a                      ; B = 0 byte, 1 word, 2 int
        ld a,d
        or e
        jp nz,.toobig
        bit 7,c
        jr nz,.nsmall
        ld a,b                      ; positive
        or a
        jr nz,.pword
        or h                        ; a byte: up to 255
        jp nz,.toobig
        ld a,l
        ld hl,(.dest)
        ld (hl),a
        ret
.pword: dec a
        jr z,.st2                   ; a word: anything in 16 bits
        bit 7,h                     ; an int: up to 32767
        jp nz,.toobig
.st2:   ex de,hl
        ld hl,(.dest)
        ld (hl),e
        inc hl
        ld (hl),d
        ret
.nsmall:
        ld a,h                      ; negative: zero fits anything
        or l
        jr z,.zero
        ld a,b
        cp 2
        jp nz,.toobig               ; a byte or a word: nothing else
        ld a,h                      ; an int: down to -32768
        cp 80h
        jr c,.negw
        jp nz,.toobig
        ld a,l
        or a
        jp nz,.toobig
.negw:  xor a
        sub l
        ld l,a
        sbc a,a
        sub h
        ld h,a
        jr .st2
.zero:  ld hl,(.dest)
        ld (hl),a
        ld a,b
        or a
        ret z
        inc hl
        ld (hl),0
        ret
.wide:  bit 7,c                     ; a long, a quad or a dword, DE:HL < 10^9
        jr z,.wpos
        ld a,c
        and 7
        cp 5
        jr nz,.wneg                 ; a dword: nothing negative fits, but -0 is 0
        ld a,d
        or e
        or h
        or l
        jp nz,.toobig
.wneg:
        xor a                       ; DE:HL = -DE:HL
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
.wpos:  ld b,h
        ld c,l
        ld hl,(.dest)
        ld (hl),c
        inc hl
        ld (hl),b
        inc hl
        ld (hl),e
        inc hl
        ld (hl),d
        ld a,(.code)
        and 7
        cp 4
        ret nz
        ld a,d                      ; a quad: the sign, extended
        add a,a
        sbc a,a
        ld b,4
.ext:   inc hl
        ld (hl),a
        djnz .ext
        ret

.strip: ld a,b                      ; HL points at a '0': drop it, unless it's the last digit
        or a
        jr nz,.sz
        ld a,c
        cp 2
        jp c,.go
.sz:    inc hl
        dec bc
        ld a,(hl)
        cp '0'
        jr z,.strip
        jp .go

.toobig:                            ; {digits} doesn't fit in a {type}
        ld a,(.code)
        bit 7,a                     ; (a zero always fits, so a minus here is never "-0")
        jr z,.tb1
        ld a,'-'
        call bly_out
.tb1:   ld hl,.dig                  ; .dig and .n make a str
        call bly_pr_str
        ld hl,.fit
        call bly_pr_cstr
        ld a,(.code)
        and 7
        add a,a
        ld e,a
        ld d,0
        ld hl,.names
        add hl,de
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        jp bly_fail

.s64:   ld (.acc),hl                ; digits 10..19: a quad in memory, a word at a time
        ld (.acc+2),de
        ld hl,0
        ld (.acc+4),hl
        ld (.acc+6),hl
        sub 9
        ld b,a                      ; B = 1..10
.l64:   ld a,(ix+0)
        inc ix
        sub '0'
        ld c,a                      ; C carries: the digit, then each word's spill (at most 10)
        ld hl,(.acc)
        ld e,l
        ld d,h
        xor a
        add hl,hl
        adc a,a
        add hl,hl
        adc a,a
        add hl,de
        adc a,0
        add hl,hl
        adc a,a                     ; A:HL = the word times ten
        ld e,c
        ld d,0
        add hl,de
        adc a,d
        ld (.acc),hl
        ld c,a
        ld hl,(.acc+2)
        ld e,l
        ld d,h
        xor a
        add hl,hl
        adc a,a
        add hl,hl
        adc a,a
        add hl,de
        adc a,0
        add hl,hl
        adc a,a                     ; A:HL = the word times ten
        ld e,c
        ld d,0
        add hl,de
        adc a,d
        ld (.acc+2),hl
        ld c,a
        ld hl,(.acc+4)
        ld e,l
        ld d,h
        xor a
        add hl,hl
        adc a,a
        add hl,hl
        adc a,a
        add hl,de
        adc a,0
        add hl,hl
        adc a,a                     ; A:HL = the word times ten
        ld e,c
        ld d,0
        add hl,de
        adc a,d
        ld (.acc+4),hl
        ld c,a
        ld hl,(.acc+6)
        ld e,l
        ld d,h
        xor a
        add hl,hl
        adc a,a
        add hl,hl
        adc a,a
        add hl,de
        adc a,0
        add hl,hl
        adc a,a                     ; A:HL = the word times ten
        ld e,c
        ld d,0
        add hl,de
        adc a,d
        ld (.acc+6),hl
        djnz .l64                   ; (nothing spills from the top: 19 digits are below 2^64)
        ld a,(.code)                ; a long or a dword (ten digits) or a quad (10..19)
        ld c,a
        and 7
        cp 4
        jr z,.q64
        cp 5
        jr nz,.lchk
        ld a,(.acc+4)               ; a dword: the magnitude fits 32 bits, and ten digits aren't 0, so not negative
        or a
        jp nz,.toobig
        bit 7,c
        jp nz,.toobig
        jr .l64ok
.lchk:  ld a,(.acc+4)               ; a long: the magnitude fits 31 bits, or is exactly 2^31 and negative
        or a                        ; (ten digits are below 2^34, so bytes 5-7 are zero)
        jp nz,.toobig
        ld a,(.acc+3)
        cp 80h
        jr c,.l64ok
        jp nz,.toobig
        bit 7,c
        jp z,.toobig
        ld hl,(.acc)
        ld a,(.acc+2)
        or h
        or l
        jp nz,.toobig
.l64ok: ld b,4
        jr .store
.q64:   ld a,(.n)                   ; a quad: 18 digits always fit; 19 must fit 63 bits, or be 2^63 and negative
        cp 19
        jr c,.q64ok
        ld a,(.acc+7)
        cp 80h
        jr c,.q64ok
        jp nz,.toobig
        bit 7,c
        jp z,.toobig
        ld hl,.acc
        xor a
        ld b,7
.q0:    or (hl)
        inc hl
        djnz .q0
        jp nz,.toobig
.q64ok: ld b,8
.store: bit 7,c                     ; B bytes of .acc to (.dest), negated if negative
        ld hl,.acc
        ld de,(.dest)
        jr nz,.sneg
.scp:   ld a,(hl)
        ld (de),a
        inc hl
        inc de
        djnz .scp
        ret
.sneg:  or a
.sn:    ld a,0
        sbc a,(hl)
        ld (de),a
        inc hl
        inc de
        djnz .sn
        ret

.maxd:  db 3, 5, 5, 10, 19, 10
.names: dw .nbyte, .nword, .nint, .nlong, .nquad, .ndword
.nbyte: db "a byte",0
.nword: db "a word",0
.nint:  db "an int",0
.nlong: db "a long",0
.nquad: db "a quad",0
.ndword: db "a dword",0
.fit:   db " doesn't fit in ",0
.code:  db 0
.dest:  dw 0
.dig:   dw 0                        ; .dig and .n together are a str
.n:     dw 0
.acc:   ds 8

bly_str_int:                        ; \s*[-+]?\d+, as the interpreter's re.match
        ld (.s),hl
        ld (.dst),de
        ld (.ty),a                  ; the type; a minus sets its bit 7 for bly_num
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld c,(hl)
        inc hl
        ld b,(hl)
        ex de,hl                    ; HL = p, BC = n (p is never read when n is 0)
        ld a,b
        or c
        jr z,.bad
.ws:    ld a,(hl)                   ; BC >= 1
        sub '0'
        cp 10
        jr c,.num                   ; a digit straight away: the usual case
        add a,'0'
        cp ' '
        jr z,.skip
        sub 9
        cp 5
        jr nc,.sign                 ; not tab, LF, VT, FF or CR
.skip:  inc hl
        dec bc
        ld a,b
        or c
        jr nz,.ws
        jr .bad
.sign:  add a,9                     ; A = the byte again
        cp '+'
        jr z,.signed
        cp '-'
        jr nz,.bad
        ld a,(.ty)
        or 80h
        ld (.ty),a
.signed:
        inc hl
        dec bc
        ld a,b
        or c
        jr z,.bad
        ld a,(hl)                   ; a digit must follow the sign
        sub '0'
        cp 10
        jr nc,.bad
.num:   ld d,h
        ld e,l                      ; DE = the first digit
.dl:    inc hl                      ; the byte at HL is a digit
        dec bc
        ld a,b
        or c
        jr z,.dend
        ld a,(hl)
        sub '0'
        cp 10
        jr c,.dl
.dend:  or a
        sbc hl,de                   ; HL = how many digits
        ld b,h
        ld c,l
        ex de,hl                    ; HL = the digits
        ld de,(.dst)
        ld a,(.ty)
        jp bly_num
.bad:   ld a,'"'
        call bly_out
        ld hl,(.s)
        call bly_pr_str
        ld hl,.msg
        jp bly_fail
.msg:   db 34," doesn't start with an integer",0
.s:     dw 0
.dst:   dw 0
.ty:    db 0

bly_ints_init:                      ; HL = &state, DE = &str
        ex de,hl
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = p
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                      ; HL = n
        ex de,hl
        ld (hl),c                   ; +0 p
        inc hl
        ld (hl),b
        inc hl
        ld (hl),c                   ; +2 cur
        inc hl
        ld (hl),b
        inc hl
        ld (hl),e                   ; +4 rem
        inc hl
        ld (hl),d
        ret

bly_ints_next:                      ; HL = &state
        push hl
        pop ix
        ld l,(ix+2)
        ld h,(ix+3)                 ; HL = cur
        ld c,(ix+4)
        ld b,(ix+5)                 ; BC = rem
        ld a,b
        or c
        jr z,.none
.skip:  ld a,(hl)                   ; past what isn't a digit
        sub '0'
        cp 10
        jr c,.found
        inc hl
        dec bc
        ld a,b
        or c
        jr nz,.skip
.none:  ld (ix+2),l
        ld (ix+3),h
        ld (ix+4),c
        ld (ix+5),b
        xor a
        ret
.found: ld (ix+6),l                 ; st
        ld (ix+7),h
        ld e,0                      ; the sign: a minus just before, unless a digit is just before that
        push hl
        ld a,l
        sub (ix+0)
        ld d,a
        ld a,h
        sbc a,(ix+1)                ; A:D = how far in the digits start
        jr nz,.far
        or d
        jr z,.sgn                   ; at the very start
        dec hl
        ld a,(hl)
        cp '-'
        jr nz,.sgn
        dec d
        jr z,.minus                 ; the minus is the first byte
        jr .before
.far:   dec hl
        ld a,(hl)
        cp '-'
        jr nz,.sgn
.before:
        dec hl
        ld a,(hl)
        sub '0'
        cp 10
        jr c,.sgn                   ; 2-4: the minus follows a digit, so it's not a sign
.minus: ld e,80h
.sgn:   pop hl
        ld (ix+10),e
        ld de,0
.dl:    inc hl                      ; the digits: HL = cur, BC = rem, DE = how many
        inc de
        dec bc
        ld a,b
        or c
        jr z,.end
        ld a,(hl)
        sub '0'
        cp 10
        jr c,.dl
.end:   ld (ix+2),l
        ld (ix+3),h
        ld (ix+4),c
        ld (ix+5),b
        ld (ix+8),e
        ld (ix+9),d
        ld a,1
        or a
        ret

bly_ints_val:                       ; HL = &state, A = type, DE = &dest
        push hl
        pop ix
        or (ix+10)
        ld l,(ix+6)
        ld h,(ix+7)
        ld c,(ix+8)
        ld b,(ix+9)
        jp bly_num

bly_str_intk:                       ; HL = &str, BC = &k, A = type, DE = &dest
        ld (.s),hl
        ld (.k),bc
        push af
        push de
        ld h,b
        ld l,c
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; DE = k's low word
        inc hl
        ld a,(hl)
        ld b,5
.hi:    inc hl
        or (hl)
        djnz .hi
        jr nz,.none                 ; negative, or 65536 or more
        push de
        ld de,(.s)
        ld hl,.st
        call bly_ints_init
        pop de
.l:     push de
        ld hl,.st
        call bly_ints_next
        pop de
        jr z,.none
        ld a,d
        or e
        jr z,.got
        dec de
        jr .l
.got:   pop de
        pop af
        ld hl,.st
        jp bly_ints_val
.none:  ld hl,.m1
        call bly_pr_cstr
        ld hl,(.k)
        call bly_pr_i64
        ld hl,.m2
        call bly_pr_cstr
        ld hl,(.s)
        call bly_pr_str
        ld hl,.m3
        jp bly_fail
.m1:    db "there is no integer ",0
.m2:    db " in ",34,0
.m3:    db 34,0
.s:     dw 0
.k:     dw 0
.st:    ds 12
