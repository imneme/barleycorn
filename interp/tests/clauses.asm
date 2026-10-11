;; provides: bump add3 lsum odd word2 nonneg
;; needs: bly_add_i32 bly_assert
;; targets: zx48 cpm
;; The suite's asm clauses (semantics.txt, "an asm clause's fragment runs on the Z80"): one function for each way
;; ABI.md section 2 passes a value, each with its twin in the case. Arguments in HL, DE, BC, IX; a byte in the low
;; half, and the first one in A too; anything wider by its slot's address; a wide result to the address after the
;; arguments; a 16-bit result in HL, a byte or bool in A.
;; bump    in: L = A = b (byte)              out: A = b + 1
;; add3    in: HL DE BC (words)              out: HL = their sum, wrapping as a word does
;; lsum    in: HL = &a, DE = &b (longs), BC = &result   out: (BC) = a + b   fails: long overflow
;; odd     in: HL (int)                      out: A = 1 if it's odd, else 0 (a bool)
;; word2   in: L = hi, E = lo (bytes)        out: HL = hi * 256 + lo
;; nonneg  in: HL (int)                      fails: assertion failed, unless it's 0 or more
;; clobbers: AF BC DE HL

bump:
        inc a                       ; the first argument's a byte: it's in A as well as L
        ret

add3:
        add hl,de
        add hl,bc
        ret

lsum:
        jp bly_add_i32              ; its own convention already: HL = &a, DE = &b, BC = &r

odd:
        ld a,l
        and 1
        ret

word2:
        ld h,l
        ld l,e
        ret

nonneg:
        bit 7,h
        ret z
        jp bly_assert
