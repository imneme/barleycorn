;; provides: fortytwo   targets: zx48
;; fortytwo   out: HL = 42      clobbers: HL
; For the suite's case where a fragment isn't for every target: CP/M runs fortytwo's twin instead.

fortytwo:
        ld hl,42
        ret
