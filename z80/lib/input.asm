;; provides: bly_lns bly_nln bly_split_input bly_lines_new bly_lines_next bly_input
;; needs: bly_text bly_tlen bly_atop bly_alimit bly_alloc bly_fail
;; targets: cpm zx48 test
;; bly_split_input  in: -  (bly_text, bly_tlen)   out: bly_lns, bly_nln   fails: arena full   clobbers: AF BC DE HL IX
;; bly_lines_new    in: -              out: HL = a lines iterator (+0 i)   fails: arena full   clobbers: AF BC DE
;; bly_lines_next   in: HL=it DE=&dest   out: (DE) = the next line   fails: no more input lines   clobbers: AF BC DE HL
;; bly_input        in: DE=&dest         out: (DE) = the whole input as one str                  clobbers: DE HL
;
; The input's lines are strs pointing into the text, where it lies: nothing is copied.
; bly_lns is the address of an array of bly_nln strs, in the arena.
; A line ends at LF, CR LF or CR, and a final line end doesn't make an empty last line (Interp.__init__'s
; re.split, then dropping a last empty piece). bly_tlen is a word, so no line can be longer than 65535 and the
; input always fits one str: those two failures can't happen here.

bly_lns: dw 0
bly_nln: dw 0

; One pass, writing the strs straight to the arena's top and moving bly_atop past them at the end: the number of
; lines isn't known until the end, and a second pass over the text would cost as much as the first.
; About 40 T a byte, and 300 more a line.
bly_split_input:
        ld ix,(bly_atop)
        ld (bly_lns),ix
        ld hl,(bly_alimit)
        ld de,(bly_atop)
        or a
        sbc hl,de
        srl h
        rr l
        srl h
        rr l
        ld (.room),hl               ; how many strs fit
        ld hl,(bly_text)
        dec hl
        ld (.crend),hl              ; where an LF would be part of a CR LF: nowhere in the text yet
        inc hl
        ld d,h
        ld e,l                      ; DE = where this line starts
        ld bc,(bly_tlen)
        ld a,b
        or c
        jr z,.done
        ld a,c                      ; B = the length's low byte, C = how many times B runs out (B = 0 is 256)
        ld c,b
        ld b,a
        or a
        jr z,.scan
        inc c
.scan:  ld a,(hl)
        cp 14                       ; CR (13) and LF (10) are both below 14
        jr c,.ctl
.next:  inc hl
        djnz .scan
        dec c
        jr nz,.scan
        or a                        ; the end: a last line, unless a line end came just before it
        sbc hl,de
        add hl,de
        call nz,.rec
.done:  ld (bly_atop),ix            ; the strs are now the arena's
        push ix
        pop hl
        ld de,(bly_lns)
        or a
        sbc hl,de
        srl h
        rr l
        srl h
        rr l
        ld (bly_nln),hl
        ret
.ctl:   cp 10
        jr z,.lf
        cp 13
        jr nz,.next                 ; another control byte, part of the line
        call .rec                   ; CR ends the line
        inc hl
        ld (.crend),hl              ; and an LF right after it belongs to it
        jr .start
.lf:    push de
        ld de,(.crend)
        or a
        sbc hl,de
        add hl,de
        pop de
        call nz,.rec                ; LF ends the line, unless it's the second half of a CR LF
        inc hl
.start: ld d,h
        ld e,l                      ; the next line starts after the line end
        dec hl
        jr .next

; .rec: the line from DE to HL, as a str at IX. Keeps BC, DE and HL.
.rec:   push hl
        ld hl,(.room)
        ld a,h
        or l
        jr z,.full
        dec hl
        ld (.room),hl
        pop hl
        push hl
        or a
        sbc hl,de
        ld (ix+0),e
        ld (ix+1),d
        ld (ix+2),l
        ld (ix+3),h
        inc ix
        inc ix
        inc ix
        inc ix
        pop hl
        ret
.full:  push ix                     ; ask bly_alloc for what's needed, which isn't there:
        pop hl                      ; it says "arena full" and never returns
        ld de,(bly_lns)
        or a
        sbc hl,de
        ld de,4
        add hl,de
        jp bly_alloc
.room:  dw 0
.crend: dw 0

bly_lines_new:
        ld hl,2
        jp bly_alloc                ; i = 0

bly_lines_next:
        push de                     ; &dest
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; DE = i
        push hl
        ld hl,(bly_nln)
        scf
        sbc hl,de                   ; nln - i - 1: carry if i >= nln
        jr c,.end
        pop hl
        inc de
        ld (hl),d
        dec hl
        ld (hl),e                   ; i + 1
        ex de,hl
        dec hl
        add hl,hl
        add hl,hl
        ld de,(bly_lns)
        add hl,de                   ; &bly_lns[i]
        pop de
        ld bc,4
        ldir
        ret
.end:   ld hl,.msg
        jp bly_fail
.msg:   db "no more input lines",0

bly_input:
        ld hl,(bly_text)
        ex de,hl
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld de,(bly_tlen)
        ld (hl),e
        inc hl
        ld (hl),d
        ret
