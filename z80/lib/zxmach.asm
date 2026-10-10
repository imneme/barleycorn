;; provides: bly_zx_addr64 bly_fail_addr_i16 bly_fail_port_i16
;; needs: bly_pr_cstr bly_pr_i16 bly_pr_i64 bly_fail_end
;; targets: zx48
;; The machine's memory and ports: peek, poke, inp and outp are a plain LD, IN or OUT in the generated code
;; (z80gen.py, machine_call), the ROM ignoring writes as it always does. This is their checking: an address or a
;; port is any whole number, checked as an index is, and only a type that can hold one out of range gets here.
;; bly_zx_addr64      in: HL=&a (a quad)  A=0 for an address, 1 for a port   out: HL = a   clobbers: AF BC DE
;;                    fails: address {a} is outside 0..65536 (or port {a})
;; bly_fail_addr_i16  in: DE = a, an int that's negative   fails: address {a} is outside 0..65536
;; bly_fail_port_i16  in: DE = a, an int that's negative   fails: port {a} is outside 0..65536

bly_zx_addr64:                      ; (num_chk.asm's bly_n_q2w would do, but brings 346 bytes it doesn't need)
        push hl
        ld c,a
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld b,6
.top:   inc hl                      ; the top six bytes must be 0
        ld a,(hl)
        or a
        jr nz,.fail
        djnz .top
        pop hl
        ex de,hl
        ret
.fail:  ld a,c
        ld hl,.addr
        or a
        jr z,.what
        ld hl,.port
.what:  call bly_pr_cstr
        pop hl
        call bly_pr_i64
.rest:  ld hl,.outside
        call bly_pr_cstr
        jp bly_fail_end
.addr:    db "address ",0
.port:    db "port ",0
.outside: db " is outside 0..65536",0

bly_fail_addr_i16:
        ld hl,bly_zx_addr64.addr
        jr bly_fail_port_i16.what
bly_fail_port_i16:
        ld hl,bly_zx_addr64.port
.what:  push de
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        jr bly_zx_addr64.rest
