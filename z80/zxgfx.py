"""The meaning of Barley's screen and sound, as a model of the Spectrum's screen memory.

This file is the reference. The interpreter draws with it directly; the C runtime and the Z80 library must produce the
same 6,912 bytes (bitmap at offset 0, attributes at 6144, exactly the Spectrum's layout at 4000h), and the same
sound log. Coordinates are BASIC's: x 0..255 from the left, y 0..175 from the bottom of the upper screen; text rows
0..21 and columns 0..31 from the top left.

Every algorithm here is written to be followed exactly:
  colours  as BASIC's: ink and paper 0..7, 8 (transparent: a square keeps its own) or 9 (contrast: white on dark,
           black on light); bright and flash 0, 1 or 8. A square printed or plotted on gets them as the ROM's PO-ATTR
           gives them (0BDBh): (old AND mask) OR (colours AND NOT mask), then the contrasts. cls and the new line a
           scroll brings in take the colours as they are (CL-LINE), mask or not; cls gives the lower screen's two
           rows the border's colours instead (BORDCR: the border's colour as paper, and a white ink on a dark one),
           as the ROM's CLS does.
  plot     sets the pixel (INVERSE 1: clears it; OVER 1: XORs it; both: leaves it), and gives its cell the colours
  line     Bresenham, from (x0, y0) to (x1, y1), both ends plotted, every pixel once
  circle   the midpoint algorithm, its eight-way points deduplicated per step (so OVER can't cancel itself), and
           clipped: points off the screen are skipped
  text     the ROM's font (48.rom at 3D00h) for 20h-7Fh, so 60h is the pound sign and 7Fh the copyright; 80h-8Fh the
           block graphics; 90h-A4h the UDGs; anything else prints as '?'. Past column 31, a line wraps; past row 21,
           the 22 upper rows scroll up one and the new bottom row is cleared in the permanent colours. Both are
           lazy, as the ROM's are: they happen when the next character is printed, not at the newline.
"""

import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import paths                                  # noqa: E402

ROM = os.path.join(paths.OMSE_AI_ROMS, '48.rom')


def rom():
    """the 48K ROM's 16K: only a program that draws, sounds, prints at, peeks or pokes needs it"""
    if not os.path.exists(ROM):
        sys.exit(f'this program uses the Spectrum\'s screen or memory, so it needs the 48K ROM ({ROM}). '
                 'Bring your own, as omse-ai does (its roms/README.md), and set OMSE_AI_ROMS to its folder.')
    data = open(ROM, 'rb').read()
    if len(data) != 0x4000:
        sys.exit(f'{ROM} is {len(data)} bytes, not a 48K ROM\'s 16384')
    return data
WHITE_ON_BLACK = 0x38                         # paper 7, ink 0: the Spectrum's own start


class ScreenError(Exception):
    """a mistake in a drawing call: the interpreter turns it into "... at line N" """


def font():
    return rom()[0x3D00:0x3D00 + 96 * 8]


class Screen:
    def __init__(self, glyphs=None):
        """glyphs: the font (96 characters of 8 bytes); by default the ROM's. A program that never looks at the screen
        can pass bytes(768), and needs no ROM: what it prints still moves the cursor, and nothing can see the rest"""
        self.mem = bytearray(6912)
        self.attr_p = WHITE_ON_BLACK          # ATTR_P, and ATTR_T, which the runtime keeps the same
        self.mask = 0                         # MASK_P (and MASK_T): the attribute bits a square keeps (8: transparent)
        self.ink9 = self.paper9 = False       # P_FLAG's INK 9 and PAPER 9 (contrast) bits
        for i in range(768):
            self.mem[6144 + i] = self.attr_p
        self.inverse = self.over = False
        self.border_colour = 7
        self.row = self.col = 0
        self.font = font() if glyphs is None else glyphs
        self.udgs = bytearray(self.font[(ord('A') - 32) * 8:(ord('U') - 31) * 8])     # A..U, as at power-on
        self.sound = []                       # (ms, semitone), in order
        self.frames = 0                       # ticks(): the frames that have passed, as far as the model knows
        self.drawn = False

    # -- colours -----------------------------------------------------------------------------------------------
    def colour(self, name, n, top=7):
        if not 0 <= n <= top:
            raise ScreenError(f'{name} {n} is not a colour 0..{top}')
        return n

    def set_colour(self, name, n, bits, shift):
        """ink or paper, as the ROM's CO-TEMP sets them (2234h): 0..7 a colour; 8 transparent, the mask's bits set;
        9 the contrast: the mask's bits set too, the colour white if the other one is dark (0..3), else black, and
        P_FLAG's bit set, so each square gets its own contrast as it's drawn on"""
        n = self.colour(name, n, 9)
        if n < 8:
            self.attr_p = (self.attr_p & ~bits & 0xFF) | (n << shift)
        elif n == 9:
            other_dark = not self.attr_p & (0x20 if name == 'ink' else 0x04)
            self.attr_p = (self.attr_p & ~bits & 0xFF) | (bits if other_dark else 0)
        self.mask = (self.mask & ~bits & 0xFF) | (bits if n >= 8 else 0)
        return n == 9

    def ink(self, n):
        self.ink9 = self.set_colour('ink', n, 0x07, 0)

    def paper(self, n):
        self.paper9 = self.set_colour('paper', n, 0x38, 3)

    def level(self, name, v, bit):
        """bright and flash, as CO-TEMP sets them (2273h): 0 off, 1 on, 8 transparent (the bit off, the mask's on)"""
        n = int(v)
        if n not in (0, 1, 8):
            raise ScreenError(f'{name} {n} is not 0, 1 or 8')
        self.attr_p = (self.attr_p & ~bit & 0xFF) | (bit if n == 1 else 0)
        self.mask = (self.mask & ~bit & 0xFF) | (bit if n == 8 else 0)

    def bright(self, v):
        self.level('bright', v, 0x40)

    def flash(self, v):
        self.level('flash', v, 0x80)

    def paint(self, cell):
        """a square printed or plotted on gets the colours, as the ROM's PO-ATTR gives them (0BDBh)"""
        a = ((self.mem[6144 + cell] ^ self.attr_p) & self.mask) ^ self.attr_p
        if self.paper9:
            a &= 0xC7
            if not a & 0x04:                  # a dark ink gets a white paper
                a ^= 0x38
        if self.ink9:
            a &= 0xF8
            if not a & 0x20:                  # a dark paper gets a white ink
                a ^= 0x07
        self.mem[6144 + cell] = a

    def set_inverse(self, b):
        self.inverse = bool(b)

    def set_over(self, b):
        self.over = bool(b)

    def border(self, n):
        self.border_colour = self.colour('border', n)

    def bordcr(self):
        """the lower screen's colours, as the runtime keeps BORDCR: the border as paper, a white ink on a dark one"""
        return (self.border_colour << 3) | (0 if self.border_colour & 4 else 7)

    def cls(self):
        """the ROM's CLS: the upper 22 rows in the colours as they are, the lower screen's 2 in the border's"""
        self.drawn = True
        for i in range(6144):
            self.mem[i] = 0
        for i in range(704):
            self.mem[6144 + i] = self.attr_p
        for i in range(704, 768):
            self.mem[6144 + i] = self.bordcr()
        self.row = self.col = 0

    # -- pixels ------------------------------------------------------------------------------------------------
    @staticmethod
    def pixel(x, y):
        """the offset of (x, y)'s byte, and its bit"""
        ys = 175 - y
        return ((ys & 0xC0) << 5) | ((ys & 0x07) << 8) | ((ys & 0x38) << 2) | (x >> 3), 0x80 >> (x & 7)

    @staticmethod
    def on_screen(x, y):
        return 0 <= x <= 255 and 0 <= y <= 175

    def check(self, x, y):
        if not self.on_screen(x, y):
            raise ScreenError(f'({x}, {y}) is off the screen')

    def put(self, x, y):
        """plot an on-screen point: no checking"""
        self.drawn = True
        off, bit = self.pixel(x, y)
        value = 0 if self.inverse else bit
        if self.over:
            self.mem[off] ^= value
        else:
            self.mem[off] = (self.mem[off] & ~bit & 0xFF) | value
        self.paint(((175 - y) >> 3) * 32 + (x >> 3))

    def plot(self, x, y):
        self.check(x, y)
        self.put(x, y)

    def point(self, x, y):
        self.check(x, y)
        off, bit = self.pixel(x, y)
        return bool(self.mem[off] & bit)

    def line(self, x0, y0, x1, y1):
        self.check(x0, y0)
        self.check(x1, y1)
        dx, sx = abs(x1 - x0), (1 if x0 < x1 else -1)
        dy, sy = -abs(y1 - y0), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.put(x0, y0)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def circle(self, cx, cy, r):
        if r < 0:
            raise ScreenError('a circle needs a radius of at least 0')
        x, y, err = r, 0, 1 - r
        while x >= y:
            seen = []
            for px, py in ((cx + x, cy + y), (cx + y, cy + x), (cx - y, cy + x), (cx - x, cy + y),
                           (cx - x, cy - y), (cx - y, cy - x), (cx + y, cy - x), (cx + x, cy - y)):
                if (px, py) not in seen:
                    seen.append((px, py))
                    if self.on_screen(px, py):
                        self.put(px, py)
            y += 1
            if err < 0:
                err += 2 * y + 1
            else:
                x -= 1
                err += 2 * (y - x) + 1

    def attr(self, r, c, a=None):
        """a square's attribute byte: set it, or with no a, read it (BASIC's ATTR)"""
        if not (0 <= r <= 23 and 0 <= c <= 31):
            raise ScreenError(f'attr ({r}, {c}) is off the screen')
        if a is None:
            return self.mem[6144 + r * 32 + c]
        self.drawn = True
        self.mem[6144 + r * 32 + c] = a & 0xFF

    def udg(self, n, rows):
        if not 0 <= n <= 20:
            raise ScreenError(f'udg {n} is not one of 0..20 (A to U)')
        if len(rows) != 8:
            raise ScreenError(f'a udg is 8 rows, not {len(rows)}')
        self.udgs[n * 8:n * 8 + 8] = bytes(rows)

    # -- text --------------------------------------------------------------------------------------------------
    def at(self, r, c):
        if not (0 <= r <= 21 and 0 <= c <= 31):
            raise ScreenError(f'print at ({r}, {c}) is off the screen')
        self.row, self.col = r, c

    def glyph(self, ch):
        if 0x20 <= ch <= 0x7F:
            return self.font[(ch - 32) * 8:(ch - 31) * 8]
        if 0x80 <= ch <= 0x8F:
            b = ch - 0x80
            top = (0xF0 if b & 2 else 0) | (0x0F if b & 1 else 0)
            bottom = (0xF0 if b & 8 else 0) | (0x0F if b & 4 else 0)
            return bytes([top] * 4 + [bottom] * 4)
        if 0x90 <= ch <= 0xA4:
            return bytes(self.udgs[(ch - 0x90) * 8:(ch - 0x8F) * 8])
        return self.glyph(ord('?'))

    def scroll(self):
        """the 22 upper rows move up one; the new bottom row is cleared in the permanent colours"""
        old = bytes(self.mem)
        for r in range(21):
            for i in range(8):
                for c in range(32):
                    self.mem[self.cell(r, i, c)] = old[self.cell(r + 1, i, c)]
            self.mem[6144 + r * 32:6144 + r * 32 + 32] = old[6144 + (r + 1) * 32:6144 + (r + 1) * 32 + 32]
        for i in range(8):
            for c in range(32):
                self.mem[self.cell(21, i, c)] = 0
        self.mem[6144 + 21 * 32:6144 + 22 * 32] = bytes([self.attr_p]) * 32

    @staticmethod
    def cell(r, i, c):
        return ((r & 0x18) << 8) | (i << 8) | ((r & 7) << 5) | c

    def out(self, ch):
        """one byte of print's output, drawn where text goes next. Scrolling is lazy, as the ROM's is: a newline from
        the last row leaves the position pending below it, and only a character printed there scrolls first. (A
        newline while pending scrolls once and stays pending.) Wrapping past column 31 is lazy the same way."""
        if ch == 10:
            if self.row == 22:
                self.scroll()
            else:
                self.row += 1
            self.col = 0
            return
        if self.col == 32:
            self.col = 0
            if self.row == 22:
                self.scroll()
            else:
                self.row += 1
        if self.row == 22:
            self.scroll()
            self.row = 21
        g = self.glyph(ch)
        for i in range(8):
            v = (~g[i] & 0xFF) if self.inverse else g[i]
            k = self.cell(self.row, i, self.col)
            self.mem[k] = (self.mem[k] ^ v) if self.over else v
        self.paint(self.row * 32 + self.col)
        self.col += 1

    # -- sound and time ----------------------------------------------------------------------------------------
    def beep(self, ms, semitone):
        if not -60 <= semitone <= 69:
            raise ScreenError(f'beep pitch {semitone} is outside -60..69')
        if ms < 0:
            raise ScreenError(f'beep length {ms} is negative')
        self.sound.append((ms, semitone))      # and no frames pass: the ROM's BEEPER plays with interrupts off, so
                                               # FRAMES stands still (a 1-second beep on omse-ai's 48K: 0 frames)

    def ticks(self):
        """the Spectrum's FRAMES is 24 bits: it wraps after 16,777,216 frames (about three days and a quarter)"""
        self.frames = (self.frames + 1) % (1 << 24)
        return self.frames

    def pause(self, n):
        if n < 0:
            raise ScreenError(f'pause {n} is negative')
        self.frames = (self.frames + n) % (1 << 24)

    def key(self):
        return 0

    # -- saving ------------------------------------------------------------------------------------------------
    def scr(self):
        return bytes(self.mem)

    def png(self, path, scale=2, border=32):
        w, h = 256 + 2 * border, 192 + 2 * border
        pal = [(0, 0, 0), (0, 0, 0xD7), (0xD7, 0, 0), (0xD7, 0, 0xD7), (0, 0xD7, 0), (0, 0xD7, 0xD7),
               (0xD7, 0xD7, 0), (0xD7, 0xD7, 0xD7)]
        bright = [tuple(0xFF if v else 0 for v in p) for p in pal]
        rows = []
        bc = pal[self.border_colour]
        for py in range(h):
            line = bytearray()
            for px in range(w):
                x, y = px - border, py - border
                if 0 <= x < 256 and 0 <= y < 192:
                    off = ((y & 0xC0) << 5) | ((y & 0x07) << 8) | ((y & 0x38) << 2) | (x >> 3)
                    a = self.mem[6144 + (y >> 3) * 32 + (x >> 3)]
                    on = self.mem[off] & (0x80 >> (x & 7))
                    p = (bright if a & 0x40 else pal)[(a & 7) if on else ((a >> 3) & 7)]
                else:
                    p = bc
                line += bytes(p) * scale
            for _ in range(scale):
                rows.append(b'\0' + bytes(line))
        raw = zlib.compress(b''.join(rows), 9)

        def chunk(t, d):
            c = t + d
            return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)
        data = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w * scale, h * scale, 8, 2, 0, 0, 0)) +
                chunk(b'IDAT', raw) + chunk(b'IEND', b''))
        open(path, 'wb').write(data)
