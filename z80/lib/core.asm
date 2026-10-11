;; provides: bly_line bly_files bly_col bly_out bly_pr_cstr bly_pr_str bly_nl bly_zone bly_pr_bool bly_pr_u16 bly_pr_i16 bly_fail bly_fail_end bly_fail_index_u16 bly_fail_index_i16 bly_alloc bly_atop bly_alimit
;; needs: bly_putc bly_exit bly_failed
;; targets: cpm zx48 test
;; bly_out            in: A=byte          keeps bly_col, prints through bly_putc          clobbers: AF BC DE HL
;; bly_pr_cstr        in: HL=&cstring     prints up to the zero                           clobbers: AF BC DE HL
;; bly_pr_str         in: HL=&str                                                         clobbers: AF BC DE HL
;; bly_nl, bly_zone   in: -               newline; spaces to the next 16-column zone      clobbers: AF BC DE HL
;; bly_pr_bool        in: A=0/1           true or false                                   clobbers: AF BC DE HL
;; bly_pr_u16         in: HL              unsigned decimal, no division                    clobbers: AF BC DE HL
;; bly_pr_i16         in: HL              signed decimal                                   clobbers: AF BC DE HL
;; bly_fail           in: HL=&cstring     prints it, then as bly_fail_end                  never returns
;; bly_fail_end       in: -               " at line N" (unless bly_line is 0), and " of NAME" in an included file,
;;                                        the platform's bly_failed, newline, bly_exit     never returns
;; bly_fail_index_u16 in: DE=i BC=n       index {i} is outside 0..{n}                      never returns
;; bly_fail_index_i16 in: DE=i BC=n       the same, i signed                               never returns
;; bly_alloc          in: HL=size         out: HL=a zeroed block from the arena; fails: arena full   clobbers: AF BC DE

bly_line:   dw 0                    ; the Barley line being run, for messages: (file << 12) | the line in it
bly_files:  dw 0                    ; the included files' names (a dw table, from entry 1), when there are any
bly_col:    dw 0                    ; print's column: 0 after a newline
bly_atop:   dw 0                    ; the arena's next free byte
bly_alimit: dw 0                    ; the arena ends here

bly_out:                            ; (A stays itself: ld and inc don't touch it)
        cp 10
        jr z,.newline
        ld hl,(bly_col)
        inc hl
        ld (bly_col),hl
        jp bly_putc
.newline:
        ld hl,0
        ld (bly_col),hl
        jp bly_putc

bly_pr_cstr:
        ld a,(hl)
        or a
        ret z
        push hl
        call bly_out
        pop hl
        inc hl
        jr bly_pr_cstr

bly_pr_str:                         ; HL = &str: p at +0, n at +2
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld c,(hl)
        inc hl
        ld b,(hl)
        ex de,hl                    ; HL = p, BC = n
        ld a,b
        or c
        ret z
.loop:  ld a,(hl)
        push hl
        push bc
        call bly_out
        pop bc
        pop hl
        inc hl
        dec bc
        ld a,b
        or c
        jr nz,.loop
        ret

bly_nl:
        ld a,10
        jp bly_out

bly_zone:                           ; at least one space, then on to a multiple of 16
.loop:
        ld a,' '
        call bly_out
        ld a,(bly_col)
        and 15
        jr nz,.loop
        ret

bly_pr_bool:
        or a
        ld hl,.false
        jr z,.go
        ld hl,.true
.go:    jp bly_pr_cstr
.true:  db "true",0
.false: db "false",0

bly_pr_i16:
        bit 7,h
        jr z,bly_pr_u16
        push hl
        ld a,'-'
        call bly_out
        pop hl
        xor a                       ; HL = -HL (and -32768 prints as 32768, unsigned)
        sub l
        ld l,a
        sbc a,a
        sub h
        ld h,a
        ; fall into bly_pr_u16

bly_pr_u16:                         ; subtract powers of ten: no division
        ld e,0                      ; E = 1 once a digit has been printed
        ld bc,-10000
        call .digit
        ld bc,-1000
        call .digit
        ld bc,-100
        call .digit
        ld bc,-10
        call .digit
        ld a,l
        add a,'0'
        jp bly_out
.digit:
        ld a,'0'-1
.sub:   inc a
        add hl,bc
        jr c,.sub
        sbc hl,bc                   ; one too many: put it back (carry is clear here)
        cp '0'
        jr nz,.print
        bit 0,e
        ret z                       ; a leading zero
.print:
        ld e,1
        push hl
        push de
        call bly_out
        pop de
        pop hl
        ret

bly_fail:
        call bly_pr_cstr
bly_fail_end:
        ld hl,(bly_line)
        ld a,h
        or l
        jr z,.nl
        ld hl,.at
        call bly_pr_cstr
        ld hl,(bly_line)
        ld a,h
        and 0Fh
        ld h,a                      ; the line in its file
        call bly_pr_u16
        ld a,(bly_line+1)
        and 0F0h                    ; the file: 0, the program itself
        jr z,.nl
        rrca
        rrca
        rrca                        ; A = the file * 2: its entry's offset
        ld e,a
        ld d,0
        ld hl,(bly_files)
        add hl,de
        ld e,(hl)
        inc hl
        ld d,(hl)
        push de
        ld hl,.of
        call bly_pr_cstr
        pop hl
        call bly_pr_cstr
.nl:    call bly_failed             ; the platform's: the 48K makes the words readable, and says STOP, not OK
        call bly_nl
        jp bly_exit
.at:    db " at line ",0
.of:    db " of ",0

bly_fail_index_u16:
        push bc
        push de
        ld hl,.index
        call bly_pr_cstr
        pop hl
        call bly_pr_u16
.rest:  ld hl,.outside
        call bly_pr_cstr
        pop hl
        call bly_pr_u16
        jp bly_fail_end
.index:   db "index ",0
.outside: db " is outside 0..",0

bly_fail_index_i16:
        push bc
        push de
        ld hl,bly_fail_index_u16.index
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        jr bly_fail_index_u16.rest

bly_alloc:                          ; HL = size -> HL = a zeroed block
        ld de,(bly_atop)
        push de                     ; the block
        push hl                     ; the size
        add hl,de                   ; the new top
        jr c,.full
        ex de,hl                    ; DE = new top
        ld hl,(bly_alimit)
        or a
        sbc hl,de
        jr c,.full
        ld (bly_atop),de
        pop bc                      ; BC = size
        pop hl                      ; HL = block
        ld a,b
        or c
        ret z
        ld (hl),0                   ; zero the first byte, then LDIR carries it along (21 T a byte)
        dec bc
        ld a,b
        or c
        ret z
        push hl
        ld d,h
        ld e,l
        inc de
        ldir
        pop hl
        ret
.full:  ld hl,.msg
        jp bly_fail
.msg:   db "arena full",0
