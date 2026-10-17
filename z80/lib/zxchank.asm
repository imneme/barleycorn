;; provides: bly_zx_chan_k
;; targets: zx48
;; Channel K, the lower screen, opened as CHAN-OPEN opens stream 1 (1601h), but for one line: the ROM's CHAN-K (1634h)
;; also clears FLAGS bit 5, the key pressed and not yet looked at. INPUT wants that, and ask() keeps it (zxask.asm);
;; key() doesn't, since print #0 between two looks mustn't lose the key pressed between them. The interpreter keeps
;; it, and the 48K lost it: Melissa's Sokoban, which prints its boxes left on the lower screen as it waits, saw a
;; few of the 34 keys typed. Done here in full rather than saving the bit around 1601h, as a key arriving between
;; the save and CHAN-K's RES would be lost all the same.
;; bly_zx_chan_k                                                                      clobbers: AF BC DE HL
bly_zx_chan_k:
        ld a,3                      ; CHAN-OPEN of stream 3 first, as fp.asm's bly_pr_f does: omse-ai's text log
        call 1601h                  ; follows CHAN-OPEN, not CURCHL, and leaves out all but streams 2 and FEh (on a
                                    ; real 48K it's only tidy: CHAN-P sets FLAGS bit 1, cleared again below)
        ld hl,(5C18h)               ; STRMS, stream 1: its channel's offset in CHANS, plus one
        dec hl
        ld de,(5C4Fh)               ; CHANS
        add hl,de
        ld (5C51h),hl               ; CURCHL
        ld hl,5C3Ch                 ; TV_FLAG bit 0: the lower screen
        set 0,(hl)
        ld hl,5C3Bh                 ; FLAGS bit 1: not the printer (and bit 5 as it was)
        res 1,(hl)
        ld hl,5C6Ah                 ; FLAGS2 bit 4: channel K in use (CHAN-FLAG clears it and CHAN-K sets it again)
        set 4,(hl)
        jp 0D4Dh                    ; TEMPS, as CHAN-K ends
