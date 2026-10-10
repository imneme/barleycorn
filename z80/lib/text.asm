;; provides: bly_cmp_str bly_slice bly_find bly_starts bly_trim bly_split_init bly_split_next
;; needs: bly_fail bly_ovf_int
;; targets: cpm zx48 test
;; bly_cmp_str     in: HL=&a DE=&b             out: A = FFh, 0, 1 (a <, =, > b), flags as after OR A   clobbers: AF BC DE HL
;; bly_slice       in: HL=&s DE=a BC=b IX=&dest   out: (IX) = s[a..b] (already checked)              clobbers: AF HL
;; bly_find        in: HL=&s DE=&t             out: HL = where t first starts in s, or -1   fails: int overflow   clobbers: AF BC DE HL
;; bly_starts      in: HL=&s DE=&t             out: A = 1 if s starts with t, else 0                    clobbers: AF BC DE HL
;; bly_trim        in: HL=&s DE=&dest          out: (DE) = s less its spaces and tabs at both ends      clobbers: AF BC DE HL
;; bly_split_init  in: HL=&state DE=&s BC=&sep   (an 11-byte state; 9 are used)   fails: split needs a separator   clobbers: AF BC DE HL
;; bly_split_next  in: HL=&state DE=&piece     out: A = 1 and (DE) = the next piece, or A = 0 when there are none   clobbers: AF BC DE HL
;
; Text: strs are (p, n) and never own their bytes, so every result here is a slice of an argument.
; A str with n = 0 may have p = 0: nothing here reads through p unless n says there's a byte there.
; The search shared by find and split keeps the pattern in scratch words and one self-modified
; instruction (bly_find.first), which is safe because no call is left half-done across another.

; -- comparing ------------------------------------------------------------------------------------------------

bly_cmp_str:                        ; byte by byte, unsigned; a shorter prefix comes first
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = a.p
        inc hl
        push bc
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = a.n
        ex de,hl
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; DE = b.p
        inc hl
        push de
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                      ; HL = b.n
        or a
        sbc hl,bc                   ; b.n - a.n
        ld a,0                      ; the same length: 0 if the bytes agree, and all of a is compared
        jr z,.common
        ld a,0FFh                   ; a is shorter: it comes first if its bytes agree
        jr nc,.common
        add hl,bc                   ; b is shorter: a comes after it, and all of b is compared
        ld b,h
        ld c,l
        ld a,1
.common:                            ; A = the answer if the first BC bytes agree
        pop hl                      ; HL = b.p
        pop de                      ; DE = a.p
        push af
        ld a,b
        or c
        jr z,.lens
.loop:  ld a,(de)                   ; a's byte, against b's at HL
        inc de
        cpi
        jr nz,.diff
        jp pe,.loop
.lens:  pop af
        or a
        ret
.diff:  pop bc                      ; (the lengths' answer, not wanted now)
        dec hl
        cp (hl)                     ; a's byte - b's byte: carry if a's is the smaller
        sbc a,a                     ; FFh if it is, else 0
        or 1                        ; FFh or 1, with S and Z as OR A leaves them
        ret

bly_starts:                         ; t.n <= s.n, and s's first t.n bytes are t's
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = s.p
        inc hl
        push bc
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = s.n
        ex de,hl
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; DE = t.p
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                      ; HL = t.n
        or a
        sbc hl,bc                   ; t.n - s.n
        jr z,.fits
        jr nc,.no                   ; t is longer than s
.fits:  add hl,bc
        ld b,h
        ld c,l                      ; BC = t.n
        pop hl                      ; HL = s.p
        ld a,b
        or c
        jr z,.yes                   ; everything starts with ""
.loop:  ld a,(de)                   ; t's byte, against s's at HL
        inc de
        cpi
        jr nz,.no2
        jp pe,.loop
.yes:   ld a,1
        ret
.no:    pop hl
.no2:   xor a
        ret

; -- making slices --------------------------------------------------------------------------------------------

bly_slice:                          ; (p + a, b - a); p isn't read, so a zero str's p = 0 is fine
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                      ; HL = s.p
        add hl,de
        ld (ix+0),l
        ld (ix+1),h
        ld h,b
        ld l,c
        or a
        sbc hl,de
        ld (ix+2),l
        ld (ix+3),h
        ret

bly_trim:                           ; Python's s.strip(b' \t')
        push de
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld c,(hl)
        inc hl
        ld b,(hl)
        ex de,hl                    ; HL = p, BC = n
.front: ld a,b
        or c
        jr z,.done                  ; nothing left (or nothing to start with)
        ld a,(hl)
        cp ' '
        jr z,.skip
        cp 9
        jr nz,.back
.skip:  inc hl
        dec bc
        jr .front
.back:  push hl                     ; (HL) isn't blank, so the walk back stops there at the latest
        add hl,bc
.bloop: dec hl
        ld a,(hl)
        cp ' '
        jr z,.bskip
        cp 9
        jr nz,.bdone
.bskip: dec bc
        jr .bloop
.bdone: pop hl
.done:  pop de
        ex de,hl                    ; HL = &dest, DE = p
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld (hl),c
        inc hl
        ld (hl),b
        ret

; -- finding --------------------------------------------------------------------------------------------------

bly_find:                           ; the first place t starts in s; "" is found at once, at 0
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = s.p
        inc hl
        push bc
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = s.n
        ex de,hl
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; DE = t.p
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a                      ; HL = t.n
        ld a,h
        or l
        jr z,.empty
        call .setpat
        pop hl                      ; HL = s.p
        push hl
        call .search
        pop de                      ; DE = s.p
        jr c,.absent
        or a
        sbc hl,de                   ; the index
        bit 7,h
        ret z
        jp bly_ovf_int              ; past 32767: find returns an int
.empty: pop hl
        ld hl,0
        ret
.absent:
        ld hl,-1
        ret

; The search, shared with split.  .setpat: DE = the pattern's p, HL = its n (at least 1).
.setpat:
        ld (.k),hl
        dec hl
        ld (.k1),hl
        ld a,(de)
        ld (.first+1),a             ; self-modifying: the CPIR below hunts for the first byte
        inc de
        ld (.p1),de
        ret

; .search: HL = where to look, BC = how many bytes are there.
; Out: NC and HL = the first place the pattern starts, or C if it's nowhere. Leaves IX alone.
.search:
        push hl
        ld hl,(.k)
        ld a,c
        sub l
        ld c,a
        ld a,b
        sbc a,h
        ld b,a                      ; BC = n - k
        pop hl
        ret c                       ; shorter than the pattern
        inc bc                      ; the places it could start (at most 65535, since k >= 1)
.next:
.first: ld a,0                      ; (self-modified: the pattern's first byte)
        cpir
        scf
        ret nz                      ; that byte isn't in what's left
        push hl                     ; one past the candidate
        push bc                     ; the places still to try after it
        ld de,(.p1)
        ld bc,(.k1)
        ld a,b
        or c
        jr z,.found                 ; a one-byte pattern: found
.cmp:   ld a,(de)
        inc de
        cpi
        jr nz,.miss
        jp pe,.cmp
.found: pop bc
        pop hl
        dec hl
        or a
        ret
.miss:  pop bc
        pop hl
        ld a,b
        or c
        jr nz,.next
        scf
        ret
.k:     dw 0                        ; the pattern's length
.k1:    dw 0                        ; and one less
.p1:    dw 0                        ; and where its second byte is

; -- split(): Python's bytes.split(sep), as an iterator -------------------------------------------------------
; The state, in the order bly_split_next walks it: +0 done (1 once the last piece has gone), +1 cur (where the
; next piece starts), +3 end (s.p + s.n, mod 65536), +5 sep.n, +7 sep.p. Nine of the eleven bytes.
; A one-byte separator (most of AoC's) is a CPIR, straight, and a two-byte one (", ") a CPIR and a compare;
; a longer one goes through find's search.

bly_split_init:
        push hl                     ; &state
        ld h,b
        ld l,c
        inc hl
        inc hl
        ld a,(hl)
        inc hl
        or (hl)
        jr z,.nosep
        pop hl
        ld (hl),0                   ; not done
        inc hl
        ex de,hl                    ; HL = &s, DE = &cur
        push bc                     ; &sep
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = s.p
        inc hl
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        add hl,bc                   ; HL = s.p + s.n
        ex de,hl
        ld (hl),c
        inc hl
        ld (hl),b                   ; cur
        inc hl
        ld (hl),e
        inc hl
        ld (hl),d                   ; end
        inc hl
        ex de,hl                    ; DE = &sep.n in the state
        pop hl                      ; &sep
        ld c,(hl)
        inc hl
        ld b,(hl)                   ; BC = sep.p
        inc hl
        ld a,(hl)                   ; (not LDI: it would count BC down)
        ld (de),a
        inc hl
        inc de
        ld a,(hl)
        ld (de),a                   ; sep.n
        inc de
        ex de,hl
        ld (hl),c
        inc hl
        ld (hl),b                   ; sep.p
        ret
.nosep: ld hl,.msg
        jp bly_fail
.msg:   db "split needs a separator",0

bly_split_next:
        ld a,(hl)
        or a
        jp nz,.none                 ; the last piece has gone
        push de                     ; &piece
        inc hl
        push hl                     ; &cur
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; DE = cur
        inc hl
        ld a,(hl)
        inc hl
        push hl
        ld h,(hl)
        ld l,a
        or a
        sbc hl,de
        ld b,h
        ld c,l                      ; BC = what's left
        pop hl
        inc hl                      ; &sep.n
        ld a,(hl)
        inc hl
        dec a
        or (hl)                     ; zero only for a one-byte separator
        inc hl                      ; &sep.p
        jr z,.one
        dec hl
        dec hl
        ld a,(hl)
        sub 2
        inc hl
        or (hl)                     ; zero only for a two-byte one
        inc hl
        jp z,.two
        jr .long
.one:   ld a,b
        or c
        jr z,.last                  ; nothing left: the last piece is ""
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        ld a,(hl)                   ; the separator
        ld h,d
        ld l,e
        push bc
        cpir
        pop bc
        jr nz,.last                 ; not there: the rest is the last piece
        dec hl
        ld bc,1
.cut:   push hl                     ; HL = the separator's place, BC = its length, DE = cur
        add hl,bc
        ex (sp),hl                  ; HL = the place, and the next piece starts past the separator
        or a
        sbc hl,de
        ld b,h
        ld c,l                      ; BC = the piece's length
        pop hl
        ex de,hl                    ; DE = the next cur, HL = cur
        ex (sp),hl                  ; HL = &cur
        ld (hl),e
        inc hl
        ld (hl),d
        pop de                      ; DE = cur
        jr .out
.long:  push bc                     ; what's left
        push de                     ; cur
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; DE = sep.p
        dec hl
        dec hl
        ld a,(hl)
        dec hl
        ld l,(hl)
        ld h,a                      ; HL = sep.n
        call bly_find.setpat
        pop hl                      ; cur
        pop bc                      ; what's left
        push bc
        push hl
        call bly_find.search
        pop de                      ; DE = cur
        pop bc                      ; what's left
        jr c,.last
        ld bc,(bly_find.k)
        jr .cut
.two:   ld a,b                      ; a two-byte separator: CPIR for its first byte, then one compare
        or c
        jr z,.last
        push bc                     ; what's left
        dec bc                      ; the places it could start: never the last byte
        ld a,b
        or c
        jr z,.no2
        push de                     ; cur
        ld a,(hl)
        inc hl
        ld h,(hl)
        ld l,a
        ld a,(hl)
        inc hl
        ld e,(hl)                   ; E = the second byte
        pop hl                      ; HL = cur
        push hl
        ld d,a                      ; D = the first
.loop2: ld a,d
        cpir
        jr nz,.not2
        ld a,(hl)                   ; the byte after: inside s, since the count stopped one short
        cp e
        jr z,.yes2
        ld a,b
        or c
        jr nz,.loop2
.not2:  pop de                      ; cur
.no2:   pop bc                      ; what's left
        jr .last
.yes2:  dec hl                      ; the separator's place
        pop de                      ; cur
        pop bc
        ld bc,2
        jr .cut
.last:  pop hl                      ; &cur
        dec hl
        ld (hl),1                   ; done
.out:   pop hl                      ; &piece: (DE, BC)
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ld (hl),c
        inc hl
        ld (hl),b
        ld a,1
        ret
.none:  xor a
        ret
