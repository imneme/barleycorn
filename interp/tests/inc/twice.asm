;; provides: twice   targets: zx48 cpm
;; twice   in: HL (int)   out: HL = 2 * it, wrapping (the suite only asks for small ones)   clobbers: HL
; Beside inc/twice.bly, which says asm "twice.asm": an included file's clause looks beside it.

twice:
        add hl,hl
        ret
