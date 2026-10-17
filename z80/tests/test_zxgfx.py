"""The Spectrum's drawing (lib/zxgfx.asm, zxline.asm, zxcircle.asm) against its
meaning, z80/zxgfx.py.

A test is a script of calls (plot, point, line, circle, attr, udg, and changes
to ATTR_P and P_FLAG), walked on the bare Z80 by a small driver, and the same
calls made on zxgfx.Screen. After the run, these must all agree:
  - the screen, all 6,912 bytes, and the 21 UDGs (at FF58h, where the real
    machine keeps them);
  - every point() result;
  - a failure, if the script ends in one: its words, " at line N", and the
    screen as it was;
  - everything else in memory: untouched, apart from the code's own scratch
    and the stack;
  - IY and the alternate registers: as the driver set them.

The screen and UDGs start random, so every bit a call shouldn't touch is
watched, and P_FLAG's other bits are random too, so only the permanent OVER
and INVERSE bits may count. Run it with omse-ai's Python ($OMSE_AI_PYTHON).
"""
import argparse
import os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import harness                                # noqa: E402
import link                                   # noqa: E402
import zxgfx                                  # noqa: E402
from harness import Runner                     # noqa: E402

LIB = os.path.join(HERE, '..', 'lib')
ap = argparse.ArgumentParser(prog='test_zxgfx.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--seed', type=int, help='the random scripts\' seed (default: a random one, printed first)')
ap.add_argument('--quick', action='store_true', help='fewer random scripts')
ap.add_argument('--lib', metavar='DIR', help='a mutated copy of the library to test instead (how the mutant tests break it on purpose)')
ap.add_argument('--mutants', nargs='?', const='', metavar='NAME',
                help='break the library on purpose and check these tests notice (only the mutants whose names '
                     'contain NAME, if given)')
ap.add_argument('--cost', action='store_true', help='print what each routine costs, instead of testing')
ARGS = ap.parse_args()                         # here: --lib decides which library is gathered
if ARGS.lib:
    LIB = ARGS.lib
    harness.gather = lambda symbols, target: link.gather(symbols, target, lib=LIB)

SCREEN, ATTR_P, ATTR_T, MASK_T, P_FLAG, UDG = 0x4000, 0x5C8D, 0x5C8F, 0x5C90, 0x5C91, 0x5C7B
SCRIPT, DATA, POINTS, UDGS = 0xA000, 0xD000, 0xE000, 0xFF58
STACK_LO, STACK_HI = 0xEC40, 0xFF00            # the harness paints this and the stack lives in it
ROUTINES = ['bly_zx_plot', 'bly_zx_point', 'bly_zx_line', 'bly_zx_circle', 'bly_zx_attr', 'bly_zx_attr_read',
            'bly_zx_udg']
MARKS = {'iy': 0x5C3A, 'bc': 0xB1B2, 'de': 0xD1D2, 'hl': 0xE1E2, 'af': 0xA1F1}

DRIVER = r'''
tz_run:                             ; walks the script at A000h; marks IY and the alternates first
        ld iy,5C3Ah
        exx
        ld bc,0B1B2h
        ld de,0D1D2h
        ld hl,0E1E2h
        exx
        ex af,af'
        ld hl,0A1F1h
        push hl
        pop af
        ex af,af'
        ld hl,0A000h
        ld (tz_sp),hl
        ld hl,0E000h
        ld (tz_pp),hl
tz_next:
        ld hl,(tz_sp)
        ld a,(hl)
        inc hl
        or a
        jp z,tz_end
        dec a
        jp z,tz_plot
        dec a
        jp z,tz_line
        dec a
        jp z,tz_circle
        dec a
        jp z,tz_attr
        dec a
        jp z,tz_udg
        dec a
        jp z,tz_point
        dec a
        jp z,tz_setattr
        dec a
        jp z,tz_setflag
        dec a
        jp z,tz_setmask
        call tz_xy                  ; 10: attr read, into the points
        call bly_zx_attr_read
        ld hl,(tz_pp)
        ld (hl),a
        inc hl
        ld (tz_pp),hl
        jp tz_next
tz_setflag:
        ld a,(hl)                   ; P_FLAG
        inc hl
        ld (tz_sp),hl
        ld (5C91h),a
        jp tz_next
tz_setmask:
        ld a,(hl)                   ; MASK_T
        inc hl
        ld (tz_sp),hl
        ld (5C90h),a
        jp tz_next
tz_setattr:
        ld a,(hl)                   ; ATTR_T
        inc hl
        ld (tz_sp),hl
        ld (5C8Fh),a
        jp tz_next
tz_plot:
        call tz_xy
        call bly_zx_plot
        jp tz_next
tz_point:
        call tz_xy
        call bly_zx_point
        ld hl,(tz_pp)
        ld (hl),a
        inc hl
        ld (tz_pp),hl
        jp tz_next
tz_xy:  ld c,(hl)                   ; two words from the script: HL = the first, DE = the second
        inc hl
        ld b,(hl)
        inc hl
        ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl
        ld (tz_sp),hl
        ld h,b
        ld l,c
        ret
tz_line:
        push hl
        ld de,8
        add hl,de
        ld (tz_sp),hl
        pop hl
        call bly_zx_line
        jp tz_next
tz_circle:
        push hl
        ld de,6
        add hl,de
        ld (tz_sp),hl
        pop hl
        call bly_zx_circle
        jp tz_next
tz_attr:
        call tz_xy
        push hl
        ld hl,(tz_sp)
        ld c,(hl)
        inc hl
        ld (tz_sp),hl
        pop hl
        call bly_zx_attr
        jp tz_next
tz_udg: ld e,(hl)
        inc hl
        ld d,(hl)
        inc hl                      ; DE = n, HL = the view, in the script
        push hl
        ld bc,4
        add hl,bc
        ld (tz_sp),hl
        pop hl
        ex de,hl
        call bly_zx_udg
        jp tz_next
tz_end: ld (tz_iy),iy
        exx
        ld (tz_alt),bc
        ld (tz_alt+2),de
        ld (tz_alt+4),hl
        exx
        ex af,af'
        push af
        pop hl
        ld (tz_alt+6),hl
        ex af,af'
        ret
tz_sp:  dw 0
tz_pp:  dw 0
tz_iy:  dw 0
tz_alt: ds 8
'''

R = Runner(ROUTINES, DRIVER)
w16 = lambda v: (v & 0xFFFF).to_bytes(2, 'little')


def build(ops):
    """the script's bytes, and the data its udg views point at"""
    s, data = bytearray(), bytearray()
    for op in ops:
        k = op[0]
        if k == 'plot':
            s += b'\x01' + w16(op[1]) + w16(op[2])
        elif k == 'line':
            s += b'\x02' + b''.join(w16(v) for v in op[1:5])
        elif k == 'circle':
            s += b'\x03' + b''.join(w16(v) for v in op[1:4])
        elif k == 'attr':
            s += b'\x04' + w16(op[1]) + w16(op[2]) + bytes([op[3]])
        elif k == 'udg':
            rows = bytes(op[2])
            s += b'\x05' + w16(op[1]) + w16(DATA + len(data)) + w16(len(rows))
            data += rows
        elif k == 'udgv':                      # a view by address and length (one that must fail before reading)
            s += b'\x05' + w16(op[1]) + w16(op[2]) + w16(op[3])
        elif k == 'point':
            s += b'\x06' + w16(op[1]) + w16(op[2])
        elif k == 'ink':                       # ATTR_T, the whole byte
            s += b'\x07' + bytes([op[1]])
        elif k == 'flag':                      # P_FLAG, the whole byte
            s += b'\x08' + bytes([op[1]])
        elif k == 'mask':                      # MASK_T, the whole byte
            s += b'\x09' + bytes([op[1]])
        elif k == 'attrr':                     # attr(r, c), read into the points
            s += b'\x0a' + w16(op[1]) + w16(op[2])
    s += b'\x00'
    assert SCRIPT + len(s) <= DATA and DATA + len(data) <= POINTS, 'script too long'
    return bytes(s), bytes(data)


def set_flag(sc, f):
    """P_FLAG's bits that count: OVER and INVERSE (permanent, 1 and 3), INK 9 and PAPER 9 (temporary, 4 and 6)"""
    sc.over, sc.inverse, sc.ink9_t, sc.paper9_t = bool(f & 2), bool(f & 8), bool(f & 0x10), bool(f & 0x40)


def model(ops, scr0, udgs0, attr0, flag0, mask0=0):
    """the reference, driven the same way: (screen, udgs, points, failure message or None)"""
    sc = zxgfx.Screen()
    sc.mem[:] = scr0
    sc.udgs[:] = udgs0
    sc.attr_t, sc.mask_t = attr0, mask0               # ATTR_T and MASK_T, as the Z80's are set
    set_flag(sc, flag0)
    points = []
    try:
        for op in ops:
            k, a = op[0], op[1:]
            if k == 'point':
                points.append(int(sc.point(*a)))
            elif k == 'attrr':
                points.append(sc.attr(*a))
            elif k == 'ink':
                sc.attr_t = a[0]
            elif k == 'mask':
                sc.mask_t = a[0]
            elif k == 'flag':
                set_flag(sc, a[0])
            elif k == 'udg':
                sc.udg(a[0], list(a[1]))
            elif k == 'udgv':
                sc.udg(a[0], [0] * a[2])
            else:
                getattr(sc, k)(*a)
    except zxgfx.ScreenError as err:
        return bytes(sc.mem), bytes(sc.udgs), points, str(err)
    return bytes(sc.mem), bytes(sc.udgs), points, None


def run(ops, rng, line=0, why=''):
    """one script, on both; returns a list of what disagreed"""
    scr0 = bytes(rng.getrandbits(8) for _ in range(6912))
    udgs0 = bytes(rng.getrandbits(8) for _ in range(168))
    attr0 = rng.getrandbits(8)
    flag0 = noisy(rng, rng.choice(FLAGS) | rng.choice([0, 0, 0, 0x10, 0x40, 0x50]))
    mask0 = rng.choice([0, 0, 0, rng.getrandbits(8), rng.choice([0x07, 0x38, 0xC0])])
    want_scr, want_udgs, want_pts, want_msg = model(ops, scr0, udgs0, attr0, flag0, mask0)
    script, data = build(ops)
    mem = {SCREEN: scr0, UDG: w16(UDGS), ATTR_T: bytes([attr0, mask0, flag0]), SCRIPT: script, DATA: data,
           UDGS: udgs0}
    res = R.call('tz_run', mem=mem, set16={'bly_line': line} if line else None, max_t=2_000_000_000)
    m, sym = res.mem, res.sym
    bad = []
    if want_msg is None:
        if res.failed:
            bad.append(f'failed: {res.out!r}')
    else:
        want = want_msg + (f' at line {line}' if line else '') + '\n'
        if not res.failed or res.out.decode('latin-1') != want:
            bad.append(f'failure: got {res.out!r}, want {want!r}')
    if m[SCREEN:SCREEN + 6912] != want_scr:
        diff = [i for i in range(6912) if m[SCREEN + i] != want_scr[i]]
        bad.append(f'screen: {len(diff)} bytes differ, first at {SCREEN + diff[0]:04X}h '
                   f'(got {m[SCREEN + diff[0]]:02X}h, want {want_scr[diff[0]]:02X}h)')
    if m[UDGS:UDGS + 168] != want_udgs:
        bad.append('udgs differ')
    got_pts = list(m[POINTS:POINTS + len(want_pts)])
    if got_pts != want_pts:
        bad.append(f'points: got {got_pts[:12]}, want {want_pts[:12]}')
    if not res.failed:
        rd = lambda a: int.from_bytes(m[a:a + 2], 'little')
        got = {'iy': rd(sym['tz_iy']), 'bc': rd(sym['tz_alt']), 'de': rd(sym['tz_alt'] + 2),
               'hl': rd(sym['tz_alt'] + 4), 'af': rd(sym['tz_alt'] + 6)}
        if got != MARKS:
            bad.append(f'IY or the alternates changed: {got}')
    # the rest of memory: as it started, apart from the code (and its scratch), the stack, and the points. The
    # system variables end as the script's last ink and flag left them.
    init = bytearray(0x10000)
    init[STACK_LO:STACK_HI] = b'\xA5' * (STACK_HI - STACK_LO)
    for addr, d in mem.items():
        init[addr:addr + len(d)] = d
    for op in ops:
        if op[0] in ('ink', 'mask', 'flag'):
            init[{'ink': ATTR_T, 'mask': MASK_T, 'flag': P_FLAG}[op[0]]] = op[1]
    code_end = 0x8000 + len(R.build('tz_run')[0])
    for lo, hi in ((SCREEN + 6912, 0x8000), (code_end, POINTS), (POINTS + len(want_pts), STACK_LO),
                   (STACK_HI, UDGS)):
        if m[lo:hi] != init[lo:hi]:
            where = next(i for i in range(lo, hi) if m[i] != init[i])
            bad.append(f'memory at {where:04X}h changed ({init[where]:02X}h -> {m[where]:02X}h)')
            break
    return [f'{why}: {b}' for b in bad]


# ---- what to run ------------------------------------------------------------------------------------------------
FLAGS = [0, 2, 8, 10]                          # plain, OVER, INVERSE, both (the permanent bits)


def noisy(rng, f):
    """a P_FLAG with these bits (OVER and INVERSE's permanent 1 and 3, INK 9 and PAPER 9's temporary 4 and 6), and
    noise in every bit that must not count"""
    return f | (rng.getrandbits(8) & ~0x5A)


def edges(rng):
    """hand-picked scripts: (why, ops, line)"""
    out = []
    corners = [(0, 0), (255, 0), (0, 175), (255, 175)]
    near = [(1, 1), (254, 1), (1, 174), (254, 174), (128, 88), (7, 8), (8, 7), (247, 167), (248, 168)]
    for f in FLAGS:
        ops = [('flag', noisy(rng, f)), ('ink', rng.getrandbits(8))]
        for x, y in corners + near:
            ops += [('point', x, y), ('plot', x, y), ('point', x, y), ('plot', x, y), ('point', x, y)]
        out.append((f'plot corners, flag {f}', ops, 0))
    # every attribute cell: one pixel in each (the cell's bottom-left and top-right alternately), then attr on each
    ops = [('flag', noisy(rng, 0))]
    for r in range(22):
        for c in range(32):
            ops += [('ink', (r * 32 + c) & 0xFF), ('plot', c * 8 + 7 * ((r + c) & 1), 175 - r * 8 - 7 * ((r + c) & 1))]
    out.append(('a pixel in every cell', ops, 0))
    out.append(('attr on every cell', [('attr', r, c, rng.getrandbits(8)) for r in range(24) for c in range(32)], 0))
    # every pixel of the edge rows and columns, and of two rows that cross thirds
    for f in (0, 2):
        ops = [('flag', noisy(rng, f))]
        ops += [('plot', x, y) for y in (0, 175, 111, 112, 63, 64) for x in range(256)]
        ops += [('plot', x, y) for x in (0, 255, 7, 8) for y in range(176)]
        out.append((f'edge rows and columns, flag {f}', ops, 0))
    # lines: zero length, the edges, the diagonals both ways, the eight octants, slopes one off the diagonal
    for f in FLAGS:
        ops = [('flag', noisy(rng, f))]
        ops += [('line', x, y, x, y) for x, y in corners + near]
        ops += [('line', 0, 0, 255, 0), ('line', 255, 175, 0, 175), ('line', 0, 175, 0, 0), ('line', 255, 0, 255, 175),
                ('line', 0, 0, 255, 175), ('line', 255, 175, 0, 0), ('line', 0, 175, 255, 0), ('line', 255, 0, 0, 175),
                ('line', 0, 0, 175, 175), ('line', 175, 175, 0, 0), ('line', 80, 0, 255, 175), ('line', 255, 0, 80, 175)]
        out.append((f'lines on the edges and diagonals, flag {f}', ops, 0))
    ops = [('flag', noisy(rng, 2))]
    cx, cy = 128, 88
    for dx, dy in ((60, 0), (60, 20), (60, 59), (60, 60), (59, 60), (20, 60), (0, 60), (60, 61), (61, 60),
                   (1, 0), (0, 1), (1, 1), (2, 1), (1, 2), (3, 1), (1, 3), (255 - 128, 1), (1, 87)):
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            ops.append(('line', cx, cy, max(0, min(255, cx + sx * dx)), max(0, min(175, cy + sy * dy))))
    out.append(('lines in every octant (OVER: a pixel twice would vanish)', ops, 0))
    # circles: radius 0, small, touching each edge exactly, past each edge, centred off the screen
    for f in FLAGS:
        ops = [('flag', noisy(rng, f))]
        ops += [('circle', x, y, 0) for x, y in corners + near]
        ops += [('circle', 128, 88, r) for r in (1, 2, 3, 4, 5, 87)]
        ops += [('circle', 87, 87, 87), ('circle', 168, 88, 87), ('circle', 88, 88, 88), ('circle', 167, 88, 88),
                ('circle', -1, -1, 1), ('circle', 256, 176, 1), ('circle', -1, 88, 1), ('circle', 128, 176, 1),
                ('circle', -10, -10, 30), ('circle', 300, 200, 100), ('circle', 128, 88, 200), ('circle', 0, 0, 255)]
        out.append((f'circles at the edges, flag {f}', ops, 0))
    # huge radii, where a sum past 16 bits must not wrap back onto the screen
    out.append(('huge radii', [('flag', noisy(rng, 2)),
                               ('circle', -32768, 88, 32767), ('circle', 32767, 88, 32767),
                               ('circle', 128, -32768, 32767), ('circle', 128, 32767, 32767),
                               ('circle', -32768, -32768, 32767), ('circle', 32767 - 255, 88, 32767),
                               ('circle', 128, 88, 32767), ('circle', 32000, 32000, 32767)], 0))
    # where c - a passes -32768 (and must not wrap onto the screen), and where a window's edge is exactly reached
    out.append(('huge radii past -32768', [('flag', noisy(rng, 2)),
                                           ('circle', 128, -32700, 32767), ('circle', -32700, 88, 32767),
                                           ('circle', -32767, 88, 32767), ('circle', 128, -32767, 32767),
                                           ('circle', -32600, -32600, 32767)], 0))
    ops = [('flag', noisy(rng, 2))]                # the fast way's edges: wholly on the screen, or one pixel not
    for cx, cy, r in ((87, 88, 87), (168, 88, 87), (128, 87, 87), (128, 88, 87), (128, 89, 87), (86, 88, 87),
                      (169, 88, 87), (40, 40, 40), (215, 135, 40), (40, 136, 40), (216, 40, 40), (1, 1, 1), (254, 174, 1)):
        ops.append(('circle', cx, cy, r))
    out.append(('circles at the edges of the fast way', ops, 0))
    ops = [('flag', noisy(rng, 2))]
    for cx, cy, r in ((300, 88, 60), (-45, 88, 60), (128, 250, 100), (128, -60, 70), (310, 200, 80),
                      (-60, -50, 90), (0, 0, 175), (255, 175, 175), (128, 0, 200), (128, 175, 200)):
        ops.append(('circle', cx, cy, r))
    out.append(('circles reaching the window edges', ops, 0))
    out.append(('every udg', [('udg', n, [rng.getrandbits(8) for _ in range(8)]) for n in range(21)], 0))
    # colours with a mask (ink, paper, bright, flash 8) and contrasts (ink and paper 9), on squares that all differ:
    # plot, lines (the general way, horizontal, vertical) and circles (fast and clipped), and reading squares back
    for mask, contrast in ((0x07, 0), (0x38, 0), (0xC0, 0), (0xFF, 0), (0x3F, 0x10), (0x07, 0x40), (0x38, 0x10),
                           (0, 0x10), (0, 0x40), (0, 0x50), (0xC7, 0x50)):
        ops = [('attr', r, c, rng.getrandbits(8)) for r in range(22) for c in range(32)]
        ops += [('mask', mask), ('flag', noisy(rng, rng.choice(FLAGS) | contrast)), ('ink', rng.getrandbits(8))]
        ops += [('plot', x, y) for x, y in corners + near]
        ops += [('line', 0, 5, 255, 170), ('line', 3, 100, 250, 100), ('line', 40, 0, 40, 175), ('line', 9, 9, 9, 9),
                ('circle', 128, 88, 60), ('circle', 10, 10, 30), ('circle', 128, 88, 0)]
        ops += [('attrr', r, c) for r in (0, 10, 12, 21, 23) for c in (0, 5, 16, 31)]
        out.append((f'mask {mask:02X}h, contrast bits {contrast:02X}h', ops, 0))
    return out


def failures(rng):
    """scripts that end in a failure, after drawing something; some with a line number to print"""
    out = []
    pre = lambda: [('plot', rng.randint(0, 255), rng.randint(0, 175)), ('line', 0, 0, rng.randint(0, 255), 175)]
    line = lambda: rng.choice([0, 1, 9, 10, 4095, rng.randint(1, 4095)])     # the program's own: (file << 12) | line
    offs = [(-1, 0), (256, 0), (0, -1), (0, 176), (255, 176), (-1, 175), (-32768, 32767), (32767, -32768),
            (300, 300), (-256, 88), (128, 432), (65535 - 65536, 65535 - 65536)]
    for x, y in offs:
        out.append((f'plot ({x}, {y})', pre() + [('plot', x, y)], line()))
        out.append((f'point ({x}, {y})', pre() + [('point', x, y)], line()))
        out.append((f'line from ({x}, {y})', pre() + [('line', x, y, 5, 5)], line()))
        out.append((f'line to ({x}, {y})', pre() + [('line', 5, 5, x, y)], line()))
        out.append((f'line both off', pre() + [('line', x, y, -x - 1, y + 300)], line()))
    for r in (-1, -2, -32768):
        out.append((f'circle radius {r}', pre() + [('circle', 128, 88, r)], line()))
    for r, c in ((-1, 0), (24, 0), (0, -1), (0, 32), (-32768, -32768), (32767, 5), (23, 32), (24, 31), (256, 0)):
        out.append((f'attr ({r}, {c})', pre() + [('attr', r, c, 7)], line()))
        out.append((f'attr read ({r}, {c})', pre() + [('attrr', r, c)], line()))
    for n in (-1, 21, 22, -32768, 32767, 256):
        out.append((f'udg {n}', pre() + [('udg', n, [1] * rng.choice([8, 3]))], line()))
    for n, k in ((5, 264), (20, 32768), (0, 65535), (21, 7), (-1, 264)):
        out.append((f'udg {n} of {k} rows', pre() + [('udgv', n, 0x1234, k)], line()))
    for k in (0, 1, 7, 9, 16, 255, 256, 1000):
        out.append((f'udg of {k} rows', pre() + [('udg', rng.randint(0, 20), [rng.getrandbits(8) for _ in range(k)])],
                    line()))
    return out


def coord(rng, hi):
    k = rng.random()
    if k < 0.7:
        return rng.randint(0, hi)
    if k < 0.9:
        return rng.choice([0, 1, 7, 8, hi - 8, hi - 7, hi - 1, hi])
    return rng.randint(max(0, hi // 2 - 10), hi // 2 + 10)


def random_op(rng, big):
    k = rng.random()
    if k < 0.25:
        return ('plot', coord(rng, 255), coord(rng, 175))
    if k < 0.33:
        return ('point', coord(rng, 255), coord(rng, 175))
    if k < 0.58:
        x0, y0 = coord(rng, 255), coord(rng, 175)
        s = rng.random()
        if s < 0.15:
            x1, y1 = x0, y0
        elif s < 0.3:
            x1, y1 = x0, coord(rng, 175)
        elif s < 0.45:
            x1, y1 = coord(rng, 255), y0
        elif s < 0.6:                          # near a diagonal
            d = rng.randint(0, 175)
            x1 = max(0, min(255, x0 + rng.choice([-1, 1]) * (d + rng.randint(-1, 1))))
            y1 = max(0, min(175, y0 + rng.choice([-1, 1]) * d))
        elif s < 0.8:                          # short
            x1 = max(0, min(255, x0 + rng.randint(-12, 12)))
            y1 = max(0, min(175, y0 + rng.randint(-12, 12)))
        else:
            x1, y1 = coord(rng, 255), coord(rng, 175)
        return ('line', x0, y0, x1, y1)
    if k < 0.72:
        s = rng.random()
        if s < 0.6:
            cx, cy, r = coord(rng, 255), coord(rng, 175), rng.choice([0, 1, 2, rng.randint(0, 20), rng.randint(0, 90)])
        elif s < 0.95:
            cx, cy, r = rng.randint(-300, 555), rng.randint(-300, 475), rng.randint(0, 400)
        else:
            cx, cy = rng.randint(-32768, 32767), rng.randint(-32768, 32767)
            r = rng.randint(0, 32767) if big else rng.randint(0, 1000)
        return ('circle', cx, cy, r)
    if k < 0.8:
        return ('attr', rng.randint(0, 23), rng.randint(0, 31), rng.getrandbits(8))
    if k < 0.83:
        return ('udg', rng.randint(0, 20), [rng.getrandbits(8) for _ in range(8)])
    if k < 0.86:
        return ('attrr', rng.randint(0, 23), rng.randint(0, 31))
    if k < 0.91:
        return ('ink', rng.getrandbits(8))
    if k < 0.94:
        return ('mask', rng.choice([0, 0, 0x07, 0x38, 0xC0, rng.getrandbits(8)]))
    return ('flag', noisy(rng, rng.choice(FLAGS) | rng.choice([0, 0, 0, 0x10, 0x40, 0x50])))


def random_script(rng, n, big=False):
    ops = [random_op(rng, big) for _ in range(n)]
    line = 0
    if rng.random() < 0.15:                    # end in a failure
        x, y = rng.choice([(rng.randint(-32768, 32767), rng.randint(-32768, 32767)),
                           (rng.choice([-1, 256]), rng.randint(0, 175)), (rng.randint(0, 255), rng.choice([-1, 176]))])
        ops.append(rng.choice([('plot', x, y), ('point', x, y), ('line', 0, 0, x, y), ('line', x, y, 9, 9),
                               ('circle', x, y, -rng.randint(1, 32768)), ('attr', y, x, 0),
                               ('udg', x, [0] * 8), ('udg', 3, [0] * rng.randint(0, 20))]))
        line = rng.randint(0, 3000)
    return ops, line


# ---- watching the tests fail: each mutant plants one bug in a copy of lib/, and the suite must notice. A CONTROL is
# a change that alters nothing on the screen (a shortcut not taken, a check that can't matter), so it must pass.
MUTANTS = [
    # plot, point, and what they share
    ('cp 176\n        jp nc,.off', 'cp 177\n        jp nc,.off', 'plot lets y = 176 by'),
    ('ld a,e\n        cp 176\n        ret c', 'ld a,e\n        cp 177\n        ret c', 'point and line let y = 176 by'),
    ('ld a,h\n        or d\n        jp nz,.off', 'ld a,h\n        nop\n        jp nz,.off', "plot ignores y's high byte"),
    ('ld a,h\n        or d\n        jr nz,.off\n        ld a,e', 'ld a,h\n        nop\n        jr nz,.off\n        ld a,e',
     "point and line ignore y's high byte"),
    ('and 0Ah                     ; bit 1', 'and 02h                     ; bit 1', 'plot ignores INVERSE'),
    ('and 0Ah                     ; bit 1', 'and 05h                     ; bit 1', 'plot reads the temporary bits'),
    ('cp 8\n        jr nz,.colour', 'cp 8\n        nop\n        nop', 'OVER with INVERSE clears'),
    ('rra                         ; carry in 0\n        scf', 'rra                         ; carry in 0\n        or a',
     'plot forgets 4000h'),
    ('sub b\n        ld h,a\n        rra\n        scf', 'sub b\n        ld h,a\n        rra\n        or a',
     'point and line forget 4000h'),
    ('and 0F8h\n        xor h\n        ld h,a                      ; H = 010 TT SSS',
     'and 0F0h\n        xor h\n        ld h,a', 'plot splices badly'),
    ('db 80h,40h,20h,10h', 'db 80h,20h,40h,10h', 'two masks swapped'),
    ('or 58h\n        ld h,a\n        ld de,(ZXG_MASK_T)', 'or 59h\n        ld h,a\n        ld de,(ZXG_MASK_T)',
     "plot colours the wrong third's cell"),
    ('and (hl)\n        ret z\n        ld a,1', 'or (hl)\n        ret z\n        ld a,1', 'point ors'),
    # attr and udg
    ('cp 24\n        jr nc,.off', 'cp 25\n        jr nc,.off', 'attr lets r = 24 by'),
    ('cp 32\n        jr nc,.off', 'cp 33\n        jr nc,.off', 'attr lets c = 32 by'),
    ('rrca                        ; r2 r1 r0 0 0 0 r4 r3', 'nop', "attr's row is wrong"),
    ('db "attr (",0', 'db "attr(",0', "attr's message"),
    ('cp 21\n        jr nc,.badn', 'cp 20\n        jr nc,.badn', 'udg refuses 20'),
    ('cp 8\n        jr nz,.badlen', 'cp 8\n        jr c,.badlen', 'udg takes more than 8 rows'),
    ('ld a,h\n        or a\n        jr nz,.badlen', 'ld a,h\n        or a\n        nop\n        nop', 'udg takes 264 rows'),
    ('ex de,hl                    ; HL = n\n        add hl,hl', 'ex de,hl\n        nop', 'udg n * 4'),
    ('call bly_pr_u16\n        jp bly_fail_end', 'call bly_pr_i16\n        jp bly_fail_end', 'udg prints the length signed'),
    # line
    ('ld d,0B1h', 'ld d,0B0h', 'line ors the wrong register'),
    ('ld e,0A9h', 'ld e,0A8h', 'line xors the wrong register'),
    ('ld de,2D01h', 'ld de,2C01h', 'line leftwards steps right a byte'),
    ('srl a\n        adc a,0', 'srl a\n        or a', 'line rounds half down'),
    ('ld b,a\n        inc b\n        srl a', 'ld b,a\n        nop\n        srl a', 'line loses its last pixel'),
    ('.yc:    call .cdown                 ; patched\n        call .lattr',
     '.yc:    call .cdown                 ; patched\n        nop\n        nop\n        nop', 'steep lines miss cells'),
    ('ret c                       ; into the next third, which inc h has already reached', 'nop',
     'line down across a third'),
    ('add a,8\n        ld h,a\n        ret\n\n.horiz:', 'add a,0\n        ld h,a\n        ret\n\n.horiz:',
     'line up into a row of cells'),
    ('ld hl,(.blk+4)\n        ld de,(.blk+6)\n        call bly_zx_plot.chk', 'ld hl,(.blk+4)\n        ld de,(.blk+6)',
     'line never checks its second end'),
    ('ld hl,.lcol                 ; the colours: a plain store, or through .paint\n        ld de,.lpaint\n'
     '        call bly_zx_plot.site', 'nop', 'line keeps old colours'),
    ('ld (.xop2),a', 'nop\n        nop\n        nop', 'shallow lines keep an old operation'),
    ('ld (.vk+1),a', 'nop\n        nop\n        nop', 'vertical lines mistake their rows of cells'),
    ('ld (.vop1),a', 'nop\n        nop\n        nop', 'vertical lines keep an old operation'),
    ('neg\n        ld (.hlast+1),a', 'nop\n        ld (.hlast+1),a', 'horizontal: the last mask'),
    ('add a,a\n        dec a\n        ld d,a', 'add a,a\n        nop\n        ld d,a', 'horizontal: the first mask'),
    ('ld d,0FFh', 'ld d,0FEh', 'horizontal: a middle byte misses a pixel'),
    ('jr nc,.h1', 'jr .h1', 'horizontal: right to left'),
    ('ld hl,.hcol2\n        ld de,.hpaint2\n        call bly_zx_plot.site', 'nop',
     'horizontal: the last cell keeps old colours'),
    ('ld (.hop3),a', 'nop\n        nop\n        nop', 'horizontal: the last byte keeps an old operation'),
    ('cp b\n        jp z,.horiz', 'cp b\n        nop\n        nop\n        nop', 'CONTROL: horizontal lines the general way'),
    ('ld a,b\n        or a\n        jr z,.vert', 'ld a,b\n        or a\n        nop\n        nop',
     'CONTROL: vertical lines the general way'),
    # circle, the general way
    ('or a\n        sbc hl,de\n        jr z,.next', 'or a\n        sbc hl,de\n        nop\n        nop', 'circle plots x = y twice'),
    ('ld a,d\n        or e\n        jr z,.g1\n', 'ld a,d\n        or e\n        nop\n        nop\n', 'circle plots cx - 0 too'),
    ('ld a,d\n        or e\n        jr z,.g1a', 'ld a,d\n        or e\n        nop\n        nop', 'circle plots cy - 0 too'),
    ('or e\n        jr z,.g3', 'or e\n        nop\n        nop', 'circle plots cx - 0 in group B too'),
    ('ld a,0\n        call po,.colv\n        ld (.qa+4),a', 'ld a,0\n        call .colv\n        ld (.qa+4),a',
     'circle wraps a column onto the screen'),
    ('ld a,0FFh\n        call po,.rowv\n        ld (.qb+1),a', 'ld a,0FFh\n        call .rowv\n        ld (.qb+1),a',
     'circle wraps a row onto the screen'),
    ('ld a,0FFh\n        call po,.rowv\n        ld (.qa+1),a', 'ld a,0FFh\n        call .rowv\n        ld (.qa+1),a',
     'CONTROL: cy - y cannot wrap (y < 23171)'),
    ('ld a,0\n        call po,.colv\n        ld (.qb+4),a', 'ld a,0\n        call .colv\n        ld (.qb+4),a',
     'CONTROL: cx - y cannot wrap'),
    ('ld a,(.p)\n        rra\n        adc hl,de', 'ld a,(.p)\n        or a\n        adc hl,de', 'circle forgets the halved bit'),
    ('sra h\n        rr l', 'srl h\n        rr l', 'circle starts e unsigned'),
    ('cp 176\n        ret c\n.rv0:', 'cp 177\n        ret c\n.rv0:', 'circle keeps row 176'),
    ('bit 7,d\n        jp nz,.neg', 'bit 6,d\n        jp nz,.neg', 'circle: the radius test'),
    ('or a\n        sbc hl,de\n        jp p,.gloop', 'scf\n        sbc hl,de\n        jp p,.gloop', 'circle stops before x = y'),
    ('ret m\n.bb1:', 'ret p\n.bb1:', 'circle: the bounding box backwards'),
    ('jp pe,.bb1                  ; past 32767\n        ret m', 'jp pe,.bb1\n        nop', 'CONTROL: no left edge to the box'),
    ('jr nc,.w1', 'jr .w1', 'circle window: M is always s - c'),
    ('ld d,a\n        pop hl\n        ret\n.wneg:', 'ld d,a\n        inc de\n        pop hl\n        ret\n.wneg:',
     'circle window: L one too big'),
    ('ld de,175\n        call .win', 'ld de,174\n        call .win', 'circle window: the rows one short'),
    ('ret c                       ; y > ystop: nothing more can be seen', 'nop', 'CONTROL: no y stop'),
    ('ret c                       ; x < xstop: likewise', 'nop', 'CONTROL: no x stop'),
    # circle, the fast way
    ('cp 176\n        jp c,.fast', 'cp 177\n        jp c,.fast', 'circle goes the fast way at cy + r = 176'),
    ('add a,8\n        ld (hl),a\n        ret\n.rup3:', 'add a,0\n        ld (hl),a\n        ret\n.rup3:', 'fast circle: up into a row of cells'),
    ('dec (hl)                    ; and the attributes are a third up too', 'nop', 'fast circle: up across a third'),
    ('sub 8\n        ld (hl),a\n        ret\n.rdn3:', 'sub 0\n        ld (hl),a\n        ret\n.rdn3:', 'fast circle: down into a row of cells'),
    ('.rdn3:  inc hl\n        inc (hl)', '.rdn3:  inc hl\n        nop', 'fast circle: down across a third'),
    ('rrc (hl)\n        ret nc\n        dec hl\n        inc (hl)', 'rrc (hl)\n        ret nc\n        dec hl\n        nop',
     'fast circle: right across a byte'),
    ('rlc (hl)\n        ret nc\n        dec hl\n        dec (hl)', 'rlc (hl)\n        ret nc\n        dec hl\n        nop',
     'fast circle: left across a byte'),
    ('ld a,(.p)\n        rra\n        ld a,(.fe)', 'ld a,(.p)\n        or a\n        ld a,(.fe)', 'fast circle forgets the halved bit'),
    ('ld hl,.r4\n        call .rup\n        ld hl,.c1', 'ld hl,.r4\n        call .rdown\n        ld hl,.c1',
     'fast circle: row cy - x goes the wrong way'),
    ('jp z,.flast                 ; y = x', 'ret z                       ; y = x', 'fast circle skips its last step'),
    ('ld (.fop2),a', 'nop\n        nop\n        nop', 'fast circle keeps an old operation'),
    ('ld hl,.fcol\n        ld de,.fpaint\n        call bly_zx_plot.site', 'nop', 'fast circle keeps old colours'),
    # colours with a mask or a contrast (the PO-ATTR way)
    ('and d\n        xor e                       ; the square', 'and 0\n        xor e                       ; the square',
     'paint ignores the mask'),
    ('xor 38h\n.pa1:', 'xor 30h\n.pa1:', 'PAPER 9 makes the wrong paper'),
    ('bit 2,a\n        jr nz,.pa1', 'bit 1,a\n        jr nz,.pa1', "PAPER 9 looks at the wrong bit of the ink"),
    ('bit 4,e                     ; INK 9', 'bit 5,e                     ; INK 9', 'INK 9 reads the permanent bit'),
    ('bit 5,a\n        jr nz,.pa2', 'bit 4,a\n        jr nz,.pa2', 'INK 9 looks at the wrong bit of the paper'),
    ('ld a,d\n        and 50h\n        or e', 'ld a,d\n        and 40h\n        or e', 'plot misses INK 9 on its own'),
    ('and 50h\n        or e\n        jr nz,.paint', 'and 50h\n        nop\n        jr nz,.paint', 'plot ignores the mask'),
    ('call .fancy\n        jr nz,.sjr', 'xor a\n        jr nz,.sjr', 'line and circle never paint'),
    ('call .fancy\n        jr nz,.sjr', 'or 1\n        jr nz,.sjr', 'CONTROL: line and circle always paint'),
    ('scf\n        sbc hl,de                   ; the trampoline', 'or a\n        sbc hl,de                   ; the trampoline',
     'a patched jump lands a byte late'),
    ('.hpaint1: push af', '.hpaint1: nop', 'horizontal painting loses A'),
    ('jr .qr2\n.qpaint:', 'ret\n.qpaint:', "a circle's painted first column skips the second"),
    ('or 58h\n        ld d,a\n        ld a,(de)\n        ret', 'or 58h\n        ld d,a\n        ld a,(hl)\n        ret',
     'attr read reads the wrong place'),
    ('cp 176\n        jp c,.fast', 'cp 176\n        jp .gloop', 'CONTROL: never the fast way'),
    ('.masks: db 80h', '        db 0\n.masks: db 80h', 'CONTROL: the mask table a byte further on'),
    ('.masks: db 80h', '        ds {PAD}\n.masks: db 80h', 'CONTROL: the mask table across a page'),
    ('.masks: db 80h', '        align 8\n.masks: db 80h', 'the size depends on where it lands'),
]


def mutants(only=''):
    import shutil, subprocess, tempfile
    lib = os.path.join(HERE, '..', 'lib')
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
    import paths
    scratch = paths.build_dir('screen-tests')
    missed = 0
    for old, new_, why in MUTANTS:
        if only not in why:
            continue
        with tempfile.TemporaryDirectory(dir=scratch) as d:
            for name in os.listdir(lib):
                if name.endswith('.asm'):
                    shutil.copy(os.path.join(lib, name), d)
            texts = {f: open(os.path.join(d, f)).read() for f in FILES}
            assert sum(x.count(old) for x in texts.values()) == 1, (old, why)
            f = next(f for f, x in texts.items() if old in x)
            if '{PAD}' in new_:                 # a fixed pad (the size mustn't depend on the origin) that puts the
                at = R.build('tz_run')[1]['bly_zx_plot.masks']     # table at xxFCh in the test's own layout
                new_ = new_.replace('{PAD}', str((0xFC - at) & 0xFF or 256))
            open(os.path.join(d, f), 'w').write(texts[f].replace(old, new_))
            p = subprocess.run([sys.executable, __file__, '--quick', '--seed', '1', '--lib', d],
                               capture_output=True, text=True)
            if 'sjasmplus' in p.stderr:
                print('BAD MUTANT (it does not assemble):', why)
                missed += 1
                continue
            caught = p.returncode != 0
            control = why.startswith('CONTROL')
            ok = caught != control
            missed += not ok
            first = next((l for l in p.stdout.splitlines() if l.startswith('WRONG')),
                         (p.stdout + p.stderr).strip().splitlines()[-1])
            print(f'{"ok  " if ok else "MISS"} {why:42} {first[:100]}')
    print('mutants:', 'every one caught' if not missed else f'{missed} not caught')
    return missed


# ---- what it costs ------------------------------------------------------------------------------------------------
FILES = ('zxgfx.asm', 'zxline.asm', 'zxcircle.asm')


def code_bytes():
    """each fragment's size: zxgfx alone (with what it needs stubbed), then what line and circle add to it"""
    text = {f: open(os.path.join(LIB, f)).read() for f in FILES}
    stubs = ''.join(f'{s} equ 0\n' for s in ('bly_out', 'bly_pr_cstr', 'bly_pr_i16', 'bly_pr_u16', 'bly_fail',
                                              'bly_fail_end'))
    size = lambda *fs: harness.assemble('        org 8000h\n' + stubs + '\n'.join(text[f] for f in fs) +
                                        '\nzz_end:\n')[1]['zz_end'] - 0x8000
    base = size('zxgfx.asm')
    return {'zxgfx.asm': base, 'zxline.asm': size('zxgfx.asm', 'zxline.asm') - base,
            'zxcircle.asm': size('zxgfx.asm', 'zxcircle.asm') - base}


def same_size():
    """zxbuild.py assembles twice, at 8000h and then flush under the UDGs, and keeps the first size: so no fragment's
    size may depend on its origin. The three, assembled at eight origins, must be the same size at each."""
    text = '\n'.join(open(os.path.join(LIB, f)).read() for f in FILES)
    stubs = ''.join(f'{s} equ 0\n' for s in ('bly_out', 'bly_pr_cstr', 'bly_pr_i16', 'bly_pr_u16', 'bly_fail',
                                              'bly_fail_end'))
    sizes = {harness.assemble(f'        org {org}\n' + stubs + text + '\nzz_end:\n')[1]['zz_end'] - org
             for org in range(0x8000, 0x8008)}
    return [] if len(sizes) == 1 else [f'the size depends on the origin: {sorted(sizes)}']


def cost(rng):
    import z80run
    base = {UDG: w16(UDGS), ATTR_P: b'\x38'}
    rows = []

    def measure(routine, cases, flag=0):
        ts, depth = [], 0
        for regs, mem in cases:
            res = R.call(routine, regs=regs, mem={**base, P_FLAG: bytes([flag]), **mem}, max_t=2_000_000_000)
            assert not res.failed, (routine, regs, res.out)
            ts.append(res.t)
            depth = max(depth, z80run.stack_depth(res.mem))
        return ts, depth

    def blk(*v):
        return {0xE000: b''.join(w16(x) for x in v)}

    pts = [(rng.randint(0, 255), rng.randint(0, 175)) for _ in range(300)]
    for f, name in ((0, 'plain'), (2, 'OVER'), (8, 'INVERSE'), (10, 'OVER and INVERSE')):
        ts, d = measure('bly_zx_plot', [({'hl': x, 'de': y}, {}) for x, y in pts], f)
        rows.append((f'`bly_zx_plot`, {name}', sum(ts) / len(ts), max(ts), d, '300 random points'))
    ts, d = measure('bly_zx_point', [({'hl': x, 'de': y}, {}) for x, y in pts])
    rows.append(('`bly_zx_point`', sum(ts) / len(ts), max(ts), d, ''))
    for what, ends, n in (('horizontal, full width', (0, 88, 255, 88), 256), ('vertical, full height', (128, 0, 128, 175), 176),
                          ('diagonal', (0, 0, 175, 175), 176), ('shallow (255 x 100)', (0, 0, 255, 100), 256),
                          ('steep (100 x 175)', (0, 0, 100, 175), 176), ('one pixel', (9, 9, 9, 9), 1),
                          ('short (5 x 3)', (100, 100, 105, 103), 6)):
        ts, d = measure('bly_zx_line', [({'hl': 0xE000}, blk(*ends))])
        rows.append((f'`bly_zx_line`, {what}', ts[0], ts[0] / n, d, f'{n} pixels; the middle column is T a pixel'))
    for what, c in (('r = 0', (128, 88, 0)), ('r = 10', (128, 88, 10)), ('r = 50', (128, 88, 50)),
                    ('r = 87, the biggest whole one', (128, 88, 87)), ('r = 150, clipped', (128, 88, 150)),
                    ('r = 1000, an arc across the screen', (128, -900, 1000)),
                    ('r = 32767, an arc across the screen', (128, -32600, 32767)),
                    ('r = 32767, nothing on the screen', (-32768, -32768, 32767))):
        ts, d = measure('bly_zx_circle', [({'hl': 0xE000}, blk(*c))])
        rows.append((f'`bly_zx_circle`, {what}', ts[0], None, d, ''))
    ts, d = measure('bly_zx_attr', [({'hl': rng.randint(0, 23), 'de': rng.randint(0, 31), 'bc': 7}, {})
                                   for _ in range(50)])
    rows.append(('`bly_zx_attr`', sum(ts) / len(ts), max(ts), d, ''))
    ts, d = measure('bly_zx_udg', [({'hl': rng.randint(0, 20), 'de': 0xE000}, {0xE000: w16(0xE010) + w16(8)})
                                  for _ in range(20)])
    rows.append(('`bly_zx_udg`', sum(ts) / len(ts), max(ts), d, ''))
    print('| routine | T | T (worst, or a pixel) | stack | |')
    print('|---|---:|---:|---:|---|')
    for name, a, b, d, note in rows:
        fmt = lambda v: '' if v is None else f'{v:,.0f}' if v >= 100 else f'{v:.1f}'
        print(f'| {name} | {fmt(a)} | {fmt(b)} | {d} | {note} |')
    sizes = code_bytes()
    print('code:', ', '.join(f'{f} {n} bytes' for f, n in sizes.items()), f'({sum(sizes.values())} in all)')


def main():
    if ARGS.cost:
        cost(random.Random(1))
        return 0
    if ARGS.mutants is not None:
        return 1 if mutants(ARGS.mutants) else 0
    quick = ARGS.quick
    seed = ARGS.seed if ARGS.seed is not None else random.randrange(10 ** 6)
    rng = random.Random(seed)
    print(f'seed {seed}')
    bad = []
    bad += same_size()
    cases = edges(rng) + failures(rng)
    for why, ops, line in cases:
        bad += run(ops, rng, line, why)
    print(f'edges and failures: {len(cases)} scripts', 'all right' if not bad else f'{len(bad)} WRONG')
    n_scripts, n_ops = (40, 60) if quick else (400, 120)
    before = len(bad)
    for i in range(n_scripts):
        ops, line = random_script(rng, n_ops, big=(i % 50 == 0 and not quick))
        bad += run(ops, rng, line, f'random script {i} (seed {seed})')
    print(f'random: {n_scripts} scripts of {n_ops} calls', 'all right' if len(bad) == before else
          f'{len(bad) - before} WRONG')
    for b in bad[:20]:
        print('WRONG', b)
    print('zxgfx:', 'all right' if not bad else f'{len(bad)} wrong')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
