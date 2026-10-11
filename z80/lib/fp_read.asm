;; provides: bly_str_float
;; needs: bly_out bly_pr_str bly_fail
;; targets: zx48
;; bly_str_float  in: HL=&str DE=&dest (5 bytes)   out: (DE) = the number the str starts with, as the ROM reads it
;;                fails: "{s}" doesn't start with a number; {number} doesn't fit in a float (the ROM's "6 Number too big")
;;                clobbers: AF BC DE HL IX, and BC' DE' (the ROM's own scratch, as fp.asm's routines)
;
; s.float(): the number is \s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)? (barley.py's FLOAT_RE), found here, and then read
; by the ROM's own DEC-TO-FP (2C9Bh), as BASIC reads a number typed into a line: the machine's own reading, its
; roundings and its limits (an exponent of 64 or more either way needs 10^64, so it's "too big" even when the number
; is tiny). DEC-TO-FP takes A = the character at CH_ADD and no sign, so CH_ADD points past the sign, and a minus is
; the calculator's negate after. It reads on for as long as the text could be a number, skipping spaces as it goes
; (BASIC's 1 000 is 1000), so the byte after the number is an ENTER while it reads and is put back after, failure or
; not: no copy, however long the number. CH_ADD is BASIC's, saved and put back. The ROM's errors are caught as
; fp.asm catches them (Melissa O'Neill's call_with_errhandler): ERR_SP pointed at a handler, and HL' and X_PTR saved
; in memory, not on the stack. The only report a number found by the pattern can raise is 6 (C, Nonsense, needs
; malformed text; 4, Out of memory, can't happen while Barley keeps the calculator its room).
; Scratch: .s .dst .st .p .neg .after .saved .hlx .xptr .chadd, and .span (a str, for the message).

bly_str_float:
        ld (.s),hl
        ld (.dst),de
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
        jp z,.bad
.ws:    ld a,(hl)                   ; BC >= 1
        cp ' '
        jr z,.skip
        sub 9
        cp 5
        jr nc,.start                ; not tab, LF, VT, FF or CR
.skip:  inc hl
        dec bc
        ld a,b
        or c
        jr nz,.ws
        jp .bad
.start: ld (.st),hl                 ; the number as written starts here, sign and all
        xor a
        ld (.neg),a
        ld a,(hl)
        cp '+'
        jr z,.sign
        cp '-'
        jr nz,.digs
        ld (.neg),a                 ; nonzero: negate after
.sign:  inc hl
        dec bc
.digs:  ld (.p),hl                  ; what the ROM reads: past the sign
        ld d,0                      ; D: a digit seen (a point alone isn't a number)
.d1:    call .dig
        jr nc,.pt
        ld d,a
        inc hl
        dec bc
        jr .d1
.pt:    ld a,b
        or c
        jr z,.whole
        ld a,(hl)
        cp '.'
        jr nz,.whole
        inc hl
        dec bc
.d2:    call .dig
        jr nc,.whole
        ld d,a
        inc hl
        dec bc
        jr .d2
.whole: inc d
        dec d
        jp z,.bad
        ld a,b                      ; an exponent only if it has digits: 3east is 3
        or c
        jr z,.end
        ld a,(hl)
        or 20h
        cp 'e'
        jr nz,.end
        push hl
        push bc
        inc hl
        dec bc
        ld a,b
        or c
        jr z,.noexp
        ld a,(hl)
        cp '+'
        jr z,.esign
        cp '-'
        jr nz,.edig
.esign: inc hl
        dec bc
.edig:  call .dig
        jr nc,.noexp
.e2:    inc hl
        dec bc
        call .dig
        jr c,.e2
        pop af                      ; it is one: forget where it started
        pop af
        jr .end
.noexp: pop bc
        pop hl
.end:   ld (.after),hl              ; HL = the byte after the number
        ld a,(hl)
        ld (.saved),a
        ld (hl),0Dh                 ; an ENTER while the ROM reads
        exx
        ld (.hlx),hl                ; BASIC's HL': the calculator borrows it, and an error leaves it borrowed
        exx
        ld hl,(5C5Fh)               ; X_PTR, which an error overwrites
        ld (.xptr),hl
        ld hl,(5C5Dh)               ; CH_ADD, BASIC's
        ld (.chadd),hl
        ld hl,(5C3Dh)               ; ERR_SP: BASIC's, to put back
        push hl
        ld hl,.caught
        push hl
        ld (5C3Dh),sp               ; a ROM error now unwinds to .caught
        ld hl,(.p)
        ld (5C5Dh),hl
        ld a,(hl)
        call 2C9Bh                  ; DEC-TO-FP: the number, onto the calculator's stack
        ld a,(.neg)
        or a
        jr z,.pos
        rst 28h
        db 1Bh                      ; negate
        db 38h                      ; end-calc
.pos:   pop hl                      ; .caught, unused
        pop hl
        ld (5C3Dh),hl
        call .put
        ld hl,(5C65h)               ; STKEND: the number, off the calculator's stack into (.dst)
        ld de,-5
        add hl,de
        ld (5C65h),hl
        ld de,(.dst)
        ld bc,5
        ldir
        ret

.dig:   ld a,b                      ; C (and A nonzero) if a digit is at HL, before the end
        or c
        ret z                       ; the end: OR leaves NC
        ld a,(hl)
        sub '0'
        cp 10
        ld a,1
        ret

.put:   ld hl,(.chadd)              ; CH_ADD, and the byte after the number, as they were
        ld (5C5Dh),hl
        ld hl,(.after)
        ld a,(.saved)
        ld (hl),a
        ret

.caught:                            ; the ROM failed: SP is just above the handler's push, ERR_NR = the report - 1
        exx
        ld hl,(.hlx)                ; BASIC's HL' back
        exx
        pop hl
        ld (5C3Dh),hl               ; and its ERR_SP
        ld a,0FFh
        ld (5C3Ah),a                ; ERR_NR: no error, as far as BASIC will know
        ld hl,(.xptr)
        ld (5C5Fh),hl               ; ERROR-1 pointed X_PTR at CH_ADD
        call .put
        ld de,(.st)                 ; the number as written: {number} doesn't fit in a float
        ld (.span),de
        ld hl,(.after)
        or a
        sbc hl,de
        ld (.span+2),hl
        ld hl,.span
        call bly_pr_str
        ld hl,.mbig
        jp bly_fail

.bad:   ld a,'"'
        call bly_out
        ld hl,(.s)
        call bly_pr_str
        ld hl,.mno
        jp bly_fail

.mno:   db 34," doesn't start with a number",0
.mbig:  db " doesn't fit in a float",0
.s:     dw 0
.dst:   dw 0
.st:    dw 0
.p:     dw 0
.neg:   db 0
.after: dw 0
.saved: db 0
.hlx:   dw 0
.xptr:  dw 0
.chadd: dw 0
.span:  dw 0,0
