;; provides: bly_ask
;; needs: bly_pr_str bly_nl bly_alloc_raw bly_atop bly_alimit bly_fail
;; targets: cpm
;; bly_ask   in: HL=&prompt DE=&dest (strs)   out: (DE) = the line typed, without its end, new in the arena
;;           fails: STOP in ask (^C, or the input ending before anything is typed)       clobbers: all
;;
;; CP/M has one console, so here the prompt and what's typed are output, and a newline ends them (print's column
;; is 0 again). Not BDOS 10: it echoes the end of the input as ^Z after ^Z until its buffer fills (tnylpo reads
;; the end of stdin as 1Ah, and a newline as 0Dh), and ^C there is a warm boot, out of the program with no word
;; said. So a key at a time, through BDOS 6, which echoes nothing: a printable key is taken and echoed; DELETE or
;; backspace rubs one out; ENTER ends the line, and so does 1Ah after something's typed; ^C, or 1Ah first, is a
;; STOP; any other control key isn't taken. The line goes straight into the arena's free room, then is allocated
;; there (bly_alloc_raw hands out bly_atop), so it can be as long as the arena has room for, as on the Spectrum.

bly_ask:
        ld (.dest),de
        call bly_pr_str             ; the prompt
        ld hl,(bly_atop)
        ld (.p),hl
        ld hl,0
        ld (.n),hl
.key:   ld e,0FFh
        ld c,6
        call 5                      ; direct console input: A = the key, or 0 if none has come
        or a
        jr z,.key
        cp 13
        jr z,.done
        cp 3
        jr z,.stop                  ; ^C
        cp 1Ah
        jr z,.end                   ; the end of the input
        cp 8
        jr z,.rub
        cp 7Fh
        jr z,.rub
        cp 32
        jr c,.key                   ; another control key: not taken
        ld (.ch),a
        ld hl,(.p)                  ; room for it below bly_alimit?
        ld de,(.n)
        add hl,de
        push hl
        inc hl
        ex de,hl
        ld hl,(bly_alimit)
        or a
        sbc hl,de
        pop hl
        jr c,.key                   ; no: not taken
        ld a,(.ch)
        ld (hl),a
        ld hl,(.n)
        inc hl
        ld (.n),hl
        ld e,a
        ld c,2
        call 5                      ; its echo
        jr .key
.rub:   ld hl,(.n)
        ld a,h
        or l
        jr z,.key
        dec hl
        ld (.n),hl
        ld de,.bs
        ld c,9
        call 5
        jr .key
.end:   ld hl,(.n)
        ld a,h
        or l
        jr z,.stop
.done:  ld hl,(.n)
        call bly_alloc_raw          ; HL = .p: the line, now its own
        ex de,hl
        ld hl,(.dest)
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld de,(.n)
        ld (hl),e
        inc hl
        ld (hl),d
        jp bly_nl
.stop:  ld hl,.stopped
        jp bly_fail
.stopped: db "STOP in ask",0
.bs:    db 8," ",8,"$"
.dest:  dw 0
.p:     dw 0
.n:     dw 0
.ch:    db 0
