"""A rig for library routines that need the real ROM: a 48K on omse-ai, loaded once, then driven call by call.

    from fprig import Rig
    rig = Rig(['bly_fadd'])                      # gathers the fragments, builds a tape, loads it, waits at the start
    r = rig.call('bly_fadd', hl=rig.X, de=rig.Y, bc=rig.R, mem={rig.X: a5, rig.Y: b5})
    r.mem(rig.R, 5), r.out, r.failed, r.t        # the result, what it printed, whether it failed, T-states

The program the tape carries is a loop (rig_ready) that loads HL DE BC A from a block, calls the routine whose
address Python poked in, and stores A back. Python stops it at rig_ready with a breakpoint, writes the next call,
and runs it on to rig_ready again. Interrupts are off around the call, so the T-states are the routine's own.
A routine that fails ends in bly_exit, whose return to BASIC is pointed back at rig_ready (bly_basic_sp is poked,
and its RST 8, the report after a failure, made a RET), so failures cost nothing either. After every call the rig checks what BASIC needs kept: IY, HL', ERR_SP, ERR_NR,
an empty calculator stack, MEM, X_PTR and CH_ADD.
Run with a Python that can import omse-ai (paths.py's OMSE_AI_PYTHON).
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
Z80 = os.path.dirname(HERE)
sys.path.insert(0, Z80)
sys.path.insert(0, os.path.join(Z80, '..'))
import paths                                            # noqa: E402
paths.omse_ai()
from link import gather                                 # noqa: E402
import zxbuild                                          # noqa: E402

SJASM = paths.SJASMPLUS
ORG = 0xC000
BSS = 0xBF00
ERR_SP, ERR_NR, STKBOT, STKEND, MEM, CH_ADD = 0x5C3D, 0x5C3A, 0x5C63, 0x5C65, 0x5C68, 0x5C5D

RIG = f"""
        org {ORG}
        jp bly_start
bly_program:
rig_ready:
        ld sp,rig_top
        ld hl,(rig_hl)
        ld de,(rig_de)
        ld bc,(rig_bc)
        ld a,(rig_a)
        di
rig_call:
        call rig_nop
rig_back:
        ei
        ld (rig_ra),a
        ld (rig_rhl),hl
        jr rig_ready
rig_nop: ret
rig_hl: dw 0
rig_de: dw 0
rig_bc: dw 0
rig_a:  db 0
rig_ra: db 0
rig_rhl: dw 0
rig_x:  ds 16
rig_y:  ds 16
rig_r:  ds 32
        ds 512
rig_top:                        ; the calls' stack grows down from here, under
rig_restart: dw rig_ready       ; bly_exit's return to BASIC (see bly_basic_sp): above a stack of its own, as
                                ; bly_exit turns interrupts on, and the ROM's handler pushes below it
"""


def assemble(src):
    with tempfile.TemporaryDirectory() as d:
        a, b, s = (os.path.join(d, n) for n in ('p.asm', 'p.bin', 'p.sym'))
        open(a, 'w').write(src)
        p = subprocess.run([SJASM, '--nologo', f'--raw={b}', f'--sym={s}', a], capture_output=True, text=True)
        if p.returncode:
            raise SystemExit('sjasmplus: ' + '\n'.join(l for l in (p.stdout + p.stderr).splitlines() if 'rror' in l))
        sym = {}
        for line in open(s):
            m = re.match(r'(\S+):\s+EQU\s+0x([0-9A-Fa-f]+)', line)
            if m:
                sym[m.group(1)] = int(m.group(2), 16)
        return open(b, 'rb').read(), sym


class Result:
    def __init__(self, rig, a, hl, t, out, failed):
        self.rig, self.a, self.hl, self.t, self.out, self.failed = rig, a, hl, t, out, failed

    def mem(self, addr, n):
        return self.rig.zx.read(addr, n)


class Rig:
    def __init__(self, symbols, lib_dir=None, extra_asm=''):
        from speccy import Speccy
        kw = {'lib': lib_dir} if lib_dir else {}
        _, lib = gather(sorted(set(symbols) | {'bly_start', 'bly_exit', 'bly_fail'}), 'zx48', **kw)
        src = RIG + extra_asm + lib + f'\nbly_code_end:\nbly_bss equ {BSS}\nbly_bss_end equ {BSS + 16}\n' + \
            'bly_input_at equ 8000h\n'                  # zxbuild says where the input goes; the rig has none
        code, self.sym = assemble(src)
        code = code[:self.sym['bly_code_end'] - ORG]
        self.code_bytes = len(code)
        prog = zxbuild.loader(ORG)
        tap = zxbuild.header(0, 'rig', len(prog), zxbuild.AUTOSTART, len(prog)) + zxbuild.block(0xFF, prog)
        inp = (0).to_bytes(2, 'little')
        tap += zxbuild.header(3, 'input', len(inp), 0x8000, 32768) + zxbuild.block(0xFF, inp)
        tap += zxbuild.header(3, 'rig', len(code), ORG, 32768) + zxbuild.block(0xFF, code)
        self.zx = zx = Speccy()
        zx.wait_ready()
        zx.insert_tape(tap)
        zx.type('LOAD ""\n')
        if zx.run_until(self.sym['rig_ready'], frames=600) is None:
            raise RuntimeError('the rig never reached rig_ready: ' + zx.printed())
        s = self.sym
        self.X, self.Y, self.R = s['rig_x'], s['rig_y'], s['rig_r']
        self.poke16(s['bly_basic_sp'], s['rig_restart'])  # a failure's way back to BASIC comes back to the rig
        self.zx.poke(s['zxp_stop'], 0xC9)                 # by RET: not RST 8's report, which would leave the rig
        self.keep = self.state()
        zx.printed(clear=True)

    def poke16(self, a, v):
        self.zx.poke(a, v & 0xFF)
        self.zx.poke(a + 1, (v >> 8) & 0xFF)

    def state(self):
        z = self.zx
        r = z.regs()
        return {'iy': r['iy'], "hl'": r["hl'"], 'ERR_SP': z.peek16(ERR_SP), 'ERR_NR': z.peek(ERR_NR),
                'STKEND-STKBOT': z.peek16(STKEND) - z.peek16(STKBOT), 'MEM': z.peek16(MEM),
                'X_PTR': z.peek16(0x5C5F), 'CH_ADD': z.peek16(CH_ADD)}

    def call(self, routine, hl=0, de=0, bc=0, a=0, mem=None, frames=200):
        z, s = self.zx, self.sym
        for addr, data in (mem or {}).items():
            z.write(addr, data)
        self.poke16(s['rig_hl'], hl)
        self.poke16(s['rig_de'], de)
        self.poke16(s['rig_bc'], bc)
        z.poke(s['rig_a'], a)
        self.poke16(s['rig_call'] + 1, s[routine] if isinstance(routine, str) else routine)
        if z.run_until(s['rig_call'], frames=5) is None:
            raise RuntimeError('lost before the call')
        t0 = z.lib.zx_tstates(z.z)
        pc = z.run_until(s['rig_back'], s['rig_ready'], frames=frames)
        if pc is None:
            raise RuntimeError(f'{routine} never came back (PC {z.pc:04X})')
        t = z.lib.zx_tstates(z.z) - t0
        failed = pc == s['rig_ready']                     # through bly_exit, not back to rig_back
        if not failed:
            z.run_until(s['rig_ready'], frames=5)
        out = z.printed(clear=True)
        st = self.state()
        bad = {k: (v, st[k]) for k, v in self.keep.items() if st[k] != v}
        if bad:
            raise AssertionError(f'{routine} left BASIC broken: {bad} (kept, now)')
        return Result(self, z.peek(s['rig_ra']), z.peek16(s['rig_rhl']), t, out, failed)
