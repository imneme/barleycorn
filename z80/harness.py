"""Run library fragments on a bare Z80 and look at what they did (ABI.md, section 9).

    from harness import Runner
    r = Runner(['bly_add_i32'])                     # gathered and assembled once
    res = r.call('bly_add_i32', regs={'hl': 0xE000, 'de': 0xE008, 'bc': 0xE010}, mem={0xE000: a, 0xE008: b})
    res.mem, res.out, res.failed, res.t, res.regs

The bare Z80 is Barley's harness method: a 48K snapshot with our own 16K "ROM" (zeros and a RETN at 0072h), run on
omse-ai's core, with no contention. Code goes at 8000h; the test platform's arena is A000h-DFFFh; E000h-EFFFh is
free for a test's operands; the stack starts at FF00h.
"""
import ctypes
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
from link import gather                       # noqa: E402
import paths                                  # noqa: E402
import bare as z80run                         # noqa: E402  the bare Z80

SJASM = paths.SJASMPLUS
OPERANDS = 0xE000

DRIVER = '''
        org 8000h
bly_test_entry:
        call bly_test_init
        ld hl,bly_test_sets         ; then the test's own values for library variables (set16=)
.set:   ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld a,d
        or e
        jr z,.go
        ld a,(hl)
        ld (de),a
        inc hl
        inc de
        ld a,(hl)
        ld (de),a
        inc hl
        jr .set
.go:    ld hl,(bly_test_rhl)
        ld de,(bly_test_rde)
        ld bc,(bly_test_rbc)
        ld ix,(bly_test_rix)
        ld a,(bly_test_ra)
bly_test_t0:
        call ROUTINE
bly_test_t1:
        ld (bly_test_ohl),hl
        ld (bly_test_ode),de
        ld (bly_test_obc),bc
        ld (bly_test_oix),ix
        push af
        pop hl
        ld (bly_test_oaf),hl
bly_test_halt:
        nop
bly_test_sets: ds 4*16+2
bly_test_rhl: dw 0
bly_test_rde: dw 0
bly_test_rbc: dw 0
bly_test_rix: dw 0
bly_test_ra: db 0
bly_test_ohl: dw 0
bly_test_ode: dw 0
bly_test_obc: dw 0
bly_test_oix: dw 0
bly_test_oaf: dw 0
'''


class Result:
    pass


def assemble(src):
    with tempfile.TemporaryDirectory() as d:
        a, b, s = (os.path.join(d, n) for n in ('t.asm', 't.bin', 't.sym'))
        Path(a).write_text(src)
        p = subprocess.run([SJASM, '--nologo', f'--raw={b}', f'--sym={s}', a], capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError('sjasmplus:\n' + p.stdout + p.stderr)
        sym = {}
        for line in Path(s).read_text().splitlines():
            m = re.match(r'(\S+):\s+EQU\s+0x([0-9A-Fa-f]+)', line)
            if m:
                sym[m.group(1)] = int(m.group(2), 16)
        return Path(b).read_bytes(), sym


class Runner:
    def __init__(self, needs, extra='', routines=None):
        """needs: the library symbols to gather; extra: more assembly (test helpers such as a cmp routine)"""
        _, lib = gather(list(needs) + ['bly_test_init', 'bly_putc', 'bly_exit'], 'test')
        self.routines = routines
        self.src_tail = lib + '\n' + extra + '\n'
        self.cache = {}

    def build(self, routine):
        if routine not in self.cache:
            code, sym = assemble(DRIVER.replace('ROUTINE', routine) + self.src_tail)
            self.cache[routine] = (code, sym)
        return self.cache[routine]

    def call(self, routine, regs=None, mem=None, max_t=200_000_000, set16=None, stack=0xFF00):
        """set16: {symbol: word} stored after the test platform starts (a library variable such as bly_line);
        stack: where the stack starts, to move it away from memory a test watches"""
        code, sym = self.build(routine)
        regs = regs or {}
        img = bytearray(code)

        def poke16(name, v):
            o = sym[name] - 0x8000
            img[o:o + 2] = (v & 0xFFFF).to_bytes(2, 'little')
        for r in ('hl', 'de', 'bc', 'ix'):
            poke16('bly_test_r' + r, regs.get(r, 0))
        img[sym['bly_test_ra'] - 0x8000] = regs.get('a', 0) & 0xFF
        sets = sym['bly_test_sets'] - 0x8000
        for k, (name, v) in enumerate((set16 or {}).items()):     # applied after bly_test_init, at run time
            if k == 16:
                raise ValueError('set16: at most 16 values')
            img[sets + 4 * k:sets + 4 * k + 4] = sym[name].to_bytes(2, 'little') + (v & 0xFFFF).to_bytes(2, 'little')
        image = {0x8000: bytes(img)}
        for addr, data in (mem or {}).items():
            image[addr] = bytes(data)
        L = z80run.lib()
        z = L.zx_new()
        try:
            rom = z80run.bare_rom()
            L.zx_load_rom(z, rom, len(rom))
            sna = z80run.make_sna(image, sym['bly_test_entry'], sp=stack)
            if L.zx_load_sna(z, sna, len(sna)) != 0:
                raise RuntimeError('SNA refused')
            L.zx_clear_breaks(z)
            L.zx_add_break(z, sym['bly_test_t0'], sym['bly_test_t0'])
            if L.zx_run_until_breaks(z, max_t) != sym['bly_test_t0']:
                raise RuntimeError('never reached the call')
            t0 = L.zx_tstates(z)
            L.zx_clear_breaks(z)
            for stop in (sym['bly_test_t1'], sym['bly_test_halt']):
                L.zx_add_break(z, stop, stop)
            hit = L.zx_run_until_breaks(z, max_t)
            t1 = L.zx_tstates(z)
            if hit == sym['bly_test_t1']:
                L.zx_clear_breaks(z)
                L.zx_add_break(z, sym['bly_test_halt'], sym['bly_test_halt'])
                L.zx_run_until_breaks(z, max_t)
            elif hit != sym['bly_test_halt']:
                raise RuntimeError(f'{routine} ran for {max_t} T-states without finishing')
            m = bytes((ctypes.c_uint8 * 65536).from_address(L.zx_memory(z)))
        finally:
            L.zx_free(z)
        res = Result()
        res.mem, res.sym = m, sym
        res.failed = m[sym['bly_test_failed']] != 0
        res.t = None if res.failed else t1 - t0
        start, end = sym['bly_test_out'], int.from_bytes(m[sym['bly_test_outp']:sym['bly_test_outp'] + 2], 'little')
        res.out = m[start:end]
        rd = lambda name: int.from_bytes(m[sym[name]:sym[name] + 2], 'little')
        res.regs = {'hl': rd('bly_test_ohl'), 'de': rd('bly_test_ode'), 'bc': rd('bly_test_obc'),
                    'ix': rd('bly_test_oix'), 'af': rd('bly_test_oaf')}
        res.regs['a'] = res.regs['af'] >> 8
        res.regs['f'] = res.regs['af'] & 0xFF
        return res


def call(routine, needs=None, regs=None, mem=None, extra='', set16=None, stack=0xFF00):
    return Runner(needs or [routine], extra).call(routine, regs, mem, set16=set16, stack=stack)
