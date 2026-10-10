"""A bare Z80 on omse-ai's core, for running library fragments: a 48K snapshot with its own 16K "ROM" (zeros and a
RETN at 0072h), interrupts off. zx_load_sna sets every register from the snapshot's header and then prefetches at
0072h, which pops PC off the snapshot's stack, so no hook in the emulator is needed. omse-ai emulates no contention,
so T-state counts are pure instruction timing."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import paths                                    # noqa: E402

paths.omse_ai()
from speccy import _load_lib                     # noqa: E402

SP0 = 0xFF00                                     # the stack's top after the RETN
STACK_PAINT = 0xEC40                             # painted from here up to SP0, to find the high-water mark
PAINT = 0xA5
_lib = None


def lib():
    global _lib
    if _lib is None:
        _lib = _load_lib()
    return _lib


def bare_rom():
    rom = bytearray(0x4000)
    rom[0x0072:0x0074] = b'\xED\x45'             # RETN
    return bytes(rom)


def make_sna(image, pc, sp=SP0, regs=None):
    """a 48K SNA: image is {address: bytes} for RAM; PC is pushed at sp-2"""
    ram = bytearray(0xC000)
    ram[STACK_PAINT - 0x4000:sp - 0x4000] = bytes([PAINT]) * (sp - STACK_PAINT)
    for addr, data in image.items():
        ram[addr - 0x4000:addr - 0x4000 + len(data)] = data
    s = sp - 2
    ram[s - 0x4000] = pc & 0xFF
    ram[s - 0x4000 + 1] = pc >> 8
    h = bytearray(27)
    r = regs or {}

    def w(o, v):
        h[o] = v & 0xFF
        h[o + 1] = (v >> 8) & 0xFF
    w(9, r.get('hl', 0))
    w(11, r.get('de', 0))
    w(13, r.get('bc', 0))
    w(15, r.get('iy', 0))
    w(17, r.get('ix', 0))
    h[19] = 0x00                                 # IFF2 = 0: interrupts stay off
    w(21, r.get('af', 0))
    w(23, s)
    h[25] = 1                                    # IM 1
    return bytes(h) + bytes(ram)
