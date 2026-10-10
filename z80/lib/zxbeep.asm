;; provides: bly_zx_beep
;; needs: bly_fail bly_pr_cstr bly_pr_i16 bly_mul_i32 bly_divmod_i32
;; targets: zx48
;; bly_zx_beep  in: HL=ms DE=semitone  fails: beep pitch {p} is outside -60..69; beep length {ms} is negative
;;              (ABI.md section 10; zxgfx.py is its meaning)
;; Out of plat_zx.asm since 9 October, so a program that never beeps doesn't carry the tables (520 bytes) or
;; the 32-bit multiply and divide (about 1.3K) that turn a semitone and a length into the ROM's period and cycles.

bly_zx_beep:                        ; HL = ms, DE = semitone
        push hl
        ld hl,60                    ; semitone + 60 must be 0..129
        add hl,de
        ld a,h
        or a
        jr nz,.badp
        ld a,l
        cp 130
        jr nc,.badp
        pop bc                      ; BC = ms
        bit 7,b
        jr nz,.badms
        push bc
        add hl,hl                   ; HL = (semitone + 60) * 2: the tables' offset
        push hl
        ld de,.f4
        add hl,de
        ld e,(hl)
        inc hl
        ld d,(hl)                   ; DE = f * 4
        ld (.a),de
        ld hl,0
        ld (.a+2),hl
        pop hl
        ld de,.period
        add hl,de
        ld e,(hl)
        inc hl
        ld d,(hl)
        ld (.per),de
        pop bc
        ld (.b),bc
        ld hl,0
        ld (.b+2),hl
        ld hl,.a                    ; cycles = f * 4 * ms / 4000
        ld de,.b
        ld bc,.a
        call bly_mul_i32
        ld hl,4000
        ld (.b),hl
        ld hl,0
        ld (.b+2),hl
        ld hl,.a
        ld de,.b
        ld bc,.a
        ld ix,.b
        call bly_divmod_i32
        ld de,(.a)
        ld a,d
        or e
        ret z                       ; too short to hear
        ld hl,(.per)
        push ix
        call 03B5h                  ; the ROM's BEEPER: HL = period, DE = cycles
        pop ix
        ret
.badp:  pop hl
        ld hl,.mp1
        call bly_pr_cstr
        ex de,hl
        call bly_pr_i16
        ld hl,.mp2
        jp bly_fail
.badms: ld hl,.mm1
        push bc
        call bly_pr_cstr
        pop hl
        call bly_pr_i16
        ld hl,.mm2
        jp bly_fail
.mp1:   db "beep pitch ",0
.mp2:   db " is outside -60..69",0
.mm1:   db "beep length ",0
.mm2:   db " is negative",0
.a:     ds 4
.b:     ds 4
.per:   dw 0
.period:
        dw 53481, 50478, 47643, 44968, 42442, 40058, 37808, 35685, 33680, 31788
        dw 30002, 28317, 26726, 25224, 23807, 22469, 21206, 20014, 18889, 17827
        dw 16825, 15879, 14986, 14143, 13348, 12597, 11888, 11219, 10588, 9992
        dw 9429, 8899, 8397, 7924, 7478, 7057, 6659, 6283, 5929, 5595
        dw 5279, 4981, 4700, 4434, 4184, 3947, 3724, 3513, 3314, 3127
        dw 2949, 2782, 2624, 2475, 2335, 2202, 2077, 1959, 1847, 1742
        dw 1642, 1548, 1460, 1376, 1297, 1223, 1152, 1086, 1023, 964
        dw 908, 856, 806, 759, 715, 673, 634, 596, 561, 528
        dw 497, 467, 439, 413, 388, 364, 342, 321, 302, 283
        dw 265, 249, 233, 218, 205, 191, 179, 167, 156, 146
        dw 136, 126, 118, 109, 102, 94, 87, 81, 74, 69
        dw 63, 58, 53, 48, 44, 40, 36, 32, 29, 25
        dw 22, 19, 16, 14, 11, 9, 7, 5, 3, 1
.f4:
        dw 33, 35, 37, 39, 41, 44, 46, 49, 52, 55
        dw 58, 62, 65, 69, 73, 78, 82, 87, 92, 98
        dw 104, 110, 117, 123, 131, 139, 147, 156, 165, 175
        dw 185, 196, 208, 220, 233, 247, 262, 277, 294, 311
        dw 330, 349, 370, 392, 415, 440, 466, 494, 523, 554
        dw 587, 622, 659, 698, 740, 784, 831, 880, 932, 988
        dw 1047, 1109, 1175, 1245, 1319, 1397, 1480, 1568, 1661, 1760
        dw 1865, 1976, 2093, 2217, 2349, 2489, 2637, 2794, 2960, 3136
        dw 3322, 3520, 3729, 3951, 4186, 4435, 4699, 4978, 5274, 5588
        dw 5920, 6272, 6645, 7040, 7459, 7902, 8372, 8870, 9397, 9956
        dw 10548, 11175, 11840, 12544, 13290, 14080, 14917, 15804, 16744, 17740
        dw 18795, 19912, 21096, 22351, 23680, 25088, 26580, 28160, 29834, 31609
        dw 33488, 35479, 37589, 39824, 42192, 44701, 47359, 50175, 53159, 56320
