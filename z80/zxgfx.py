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
  lower    print #0 and #1: the lower screen, rows 22 and 23, as the ROM's channel K prints there. It starts on
           the bottom line (CLS-LOWER leaves it there, and so does loading), at 0 is row 22, newlines and wrapping
           are lazy, and the text is in BORDCR's colours with no INVERSE or OVER (TEMPS gives the lower screen
           those). Barley keeps it two lines: where the ROM would grow it upwards (a character after a newline
           from the bottom line, say), it fails instead. cls and ask() (CLS-LOWER) put it back on the bottom line.
  fzx      print #4: proportional text in an FZX font (Andrew Owen's format), drawn as Einar Saukas's FZX
           driver draws it (FZXdriver.asm, 2013), which the 48K runs, adapted. The position is in pixels: x
           0..255 from the left, and the driver's line, 191 at the top down to 0. at y, x is pixels too (the
           line is 191 - y). A newline goes back to x 0 and down the font's height. A character the font
           hasn't got prints as ?. Kerning moves a character left, though not past 0; one that won't fit on
           the line goes to the next first; one that won't fit above the bottom fails, where the driver
           reports Out of screen. Pixels are ORed in, and the attributes left alone. One change from the
           driver: it writes three screen bytes a row with only the low byte of the address counted, so at
           the right edge the third can land on the next text row's left. Bits there are only ever a font's
           stray bits past a character's width, so the adapted driver, and this, write nothing past x 255.
  ports    as omse-ai's 48K answers them. An even port is the ULA's: reading it gives BFh with no key held, and bit
           6 is the EAR line, which echoes bit 4 of the last thing written there; writing it shows the border in
           bits 0-2 (BORDCR, which cls and the lower screen use, is border()'s alone). An odd port with bits 5-7
           clear is the Kempston joystick, 0 when nothing's pushed; any other reads FFh. border() and a beep
           long enough to sound write it too: the ROM's BEEPER finishes with the speaker off and BORDCR's border.
  keys     the model has no keyboard of its own: a Keys (keys) gives what was typed, or nothing. key() is the next
           key; inkey() sees each key held for one look and released for the next. ask() on the 48K is display:
           each key it takes clicks (BEEPER again), and it ends by clearing the lower screen (CLS-LOWER), so
           asked() does both. (A line long enough to grow the lower screen past its two rows also writes over
           the upper screen there, which the model doesn't follow.)
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


class Keys:
    """what was typed, as the interpreter and C have it: keys on a stream (stdin, when it isn't a terminal; the
    suite's `--- keys`), a newline being ENTER (13). A terminal has none to give key() and inkey(), which find
    none held, but ask() reads its lines.

    Each key is pressed, then let go, as on the 48K, where the ROM registers a key while it's down. inkey() sees
    the key down for one look and up for the next, then takes the next key typed. key() is a new keypress: the
    latest key registered if key() hasn't had it yet (inkey() seeing one doesn't take it from key(), as on the
    48K, where both see every key the ROM takes and key() keeps only the latest), or else the next key typed,
    which is still down for inkey()'s next look. ask()'s editor takes its own keys, and starts and ends with
    none down or waiting."""
    def __init__(self, stream=None, terminal=False):
        self.stream, self.terminal = stream, terminal
        self.down, self.up = 0, False               # the key being typed, and whether inkey() has seen it down
        self.pending = 0                            # the latest key registered that key() hasn't had

    def take(self):
        """the next key typed, now down, or 0"""
        if self.stream is None or self.terminal:
            return 0
        b = self.stream.read(1)
        k = 0 if not b else 13 if b == b'\n' else b[0]
        if k:
            self.down, self.up, self.pending = k, False, k
        return k

    def key(self):
        if self.pending:
            k, self.pending = self.pending, 0
            return k
        k = self.take()
        self.pending = 0
        return k

    def inkey(self):
        if not self.down and not self.take():
            return 0
        if not self.up:
            self.up = True
            return self.down
        self.down = 0
        return 0

    def line(self):
        """the rest of the line, without its end, or None if the keys have run out"""
        self.down = self.pending = 0
        s = self.stream.readline() if self.stream is not None else b''
        if not s:
            return None
        return s[:-1] if s.endswith(b'\n') else s


def fzx_problem(f):
    """what's wrong with f as an FZX font, or None. It has to have a ?, to print for what it hasn't got, and each
    character's rows have to lie in it, whole"""
    if len(f) < 3:
        return 'it is shorter than the 3 bytes of its header'
    if f[2] < ord('?'):
        return 'it has no ? (its last character is below it)'
    n = f[2] - 31
    if len(f) < 3 + 3 * n + 2:
        return f'its table of {n} characters runs past its {len(f)} bytes'
    at = lambda i: 3 + 3 * i + ((f[3 + 3 * i] | f[4 + 3 * i] << 8) & 0x3FFF)
    for i in range(n):
        start, end = at(i), at(i + 1)
        if not 3 + 3 * n + 2 <= start <= end <= len(f) or (f[5 + 3 * i] & 15) >= 8 and (end - start) % 2:
            return f'character {i + 32} is not where its table says'
    return None


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
        self.border_colour = 7                        # BORDCR's
        self.shown_border, self.ear = 7, 0            # what the ULA was last told: the border showing, and bit 4
        self.keys = None                              # the keyboard (Keys), if anything's been typed
        self.row = self.col = 0
        self.lrow, self.lcol = 23, 0                  # the lower screen's print position: its bottom line
        self.fzx_font, self.fzx_x, self.fzx_line = None, 0, 191     # print #4: the font, and where it goes
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
        self.shown_border, self.ear = self.border_colour, 0

    def inp(self, port):
        if port % 2 == 0:
            return 0xBF | self.ear << 6
        return 0 if port & 0xE0 == 0 else 0xFF

    def outp(self, port, v):
        if port % 2 == 0:
            self.shown_border, self.ear = v & 7, v >> 4 & 1

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
        self.lrow, self.lcol = 23, 0

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
    def fzx(self, font):
        """fzx(font): the font print #4 uses (the checker has seen that it is one: fzx_problem)"""
        self.fzx_font = bytes(font)

    def fzx_at(self, y, x):
        if not (0 <= y <= 191 and 0 <= x <= 255):
            raise ScreenError(f'print #4; at ({y}, {x}) is off the screen (192 by 256 pixels)')
        self.fzx_line, self.fzx_x = 191 - y, x

    def fzx_newline(self):
        f = self.fzx_font
        self.fzx_x, self.fzx_line = 0, (self.fzx_line - f[0]) & 0xFF

    def fzx_out(self, ch):
        """one byte printed to stream 4, as FZXdriver.asm's START draws it"""
        f = self.fzx_font
        if f is None:
            raise ScreenError('print #4 needs a font: fzx(font) first')
        if ch == 10:
            self.fzx_newline()
            return
        if not 32 <= ch <= f[2]:
            ch = ord('?')
        e = 3 + 3 * (ch - 32)                         # its entry: offset and kern, then shift and width
        word = f[e] | f[e + 1] << 8
        start, kern = e + (word & 0x3FFF), word >> 14
        shift, width = f[e + 2] >> 4, (f[e + 2] & 15) + 1
        nxt = f[e + 3] | f[e + 4] << 8                # the next entry's offset (or the table's last word)
        end = e + 3 + (nxt & 0x3FFF)
        self.fzx_x = max(self.fzx_x - kern, 0)
        if self.fzx_x + width - 1 > 255:
            self.fzx_newline()
        if (1 - f[0]) % 256 + self.fzx_line < 256 or self.fzx_line > 191:   # (a line wrapped past 0: below too)
            raise ScreenError('print #4 would go below the screen')
        y, per = 191 - self.fzx_line + shift, 1 if width <= 8 else 2
        for k, at in enumerate(range(start, end, per)):
            bits = (f[at] << 16 | (f[at + 1] << 8 if per == 2 else 0)) >> (self.fzx_x & 7)
            row = y + k
            if row > 191:
                break
            for j in range(3):                        # three bytes of the row, not past x 255
                if (self.fzx_x >> 3) + j <= 31:
                    self.mem[self.cell(row >> 3, row & 7, (self.fzx_x >> 3) + j)] |= (bits >> (16 - 8 * j)) & 0xFF
        x = self.fzx_x + width + f[1]
        if x > 255:
            self.fzx_newline()
        else:
            self.fzx_x = x

    def lat(self, r, c):
        """at, in a print to the lower screen: its two rows"""
        if not (0 <= r <= 1 and 0 <= c <= 31):
            raise ScreenError(f'print at ({r}, {c}) is off the lower screen')
        self.lrow, self.lcol = 22 + r, c

    def lout(self, ch):
        """one byte printed to the lower screen (print #0 or #1). Row 24 is pending, below the bottom line"""
        if ch == 10:
            if self.lrow == 24:
                raise ScreenError('print would grow the lower screen past its two lines')
            self.lrow, self.lcol = self.lrow + 1, 0
            return
        if self.lcol == 32:
            self.lrow, self.lcol = self.lrow + 1, 0
        if self.lrow == 24:
            raise ScreenError('print would grow the lower screen past its two lines')
        g = self.glyph(ch)
        for i in range(8):
            self.mem[self.cell(self.lrow, i, self.lcol)] = g[i]
        self.mem[6144 + self.lrow * 32 + self.lcol] = self.bordcr()
        self.lcol += 1

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

    def failed(self, n):
        """a failure's words, the last n printed, made readable as the 48K's runtime makes them (plat_zx.asm's
        bly_failed): their squares paper 7, ink 0, whatever the program's colours were"""
        end = self.row * 32 + self.col
        for i in range(max(0, end - n), end):
            self.mem[6144 + i] = 0x38

    # -- sound and time ----------------------------------------------------------------------------------------
    def beep(self, ms, semitone):
        if not -60 <= semitone <= 69:
            raise ScreenError(f'beep pitch {semitone} is outside -60..69')
        if ms < 0:
            raise ScreenError(f'beep length {ms} is negative')
        self.sound.append((ms, semitone))      # and no frames pass: the ROM's BEEPER plays with interrupts off, so
                                               # FRAMES stands still (a 1-second beep on omse-ai's 48K: 0 frames)
        f4 = round(4 * 440 * 2 ** ((semitone - 9) / 12))      # zxbeep.asm's table: the frequency, times 4
        if f4 * ms // 4000:                                    # cycles: zero is too short to hear, and isn't played
            self.shown_border, self.ear = self.border_colour, 0

    def ticks(self):
        """the Spectrum's FRAMES is 24 bits: it wraps after 16,777,216 frames (about three days and a quarter)"""
        self.frames = (self.frames + 1) % (1 << 24)
        return self.frames

    def pause(self, n):
        if n < 0:
            raise ScreenError(f'pause {n} is negative')
        self.frames = (self.frames + n) % (1 << 24)

    def key(self):
        return self.keys.key() if self.keys else 0

    def inkey(self):
        return self.keys.inkey() if self.keys else 0

    def asked(self):
        """after ask(): the editor's clicks and INPUT's CLS-LOWER"""
        self.shown_border, self.ear = self.border_colour, 0
        for row in (22, 23):
            for line in range(8):
                start = ((row & 0x18) << 8) | (line << 8) | ((row & 7) << 5)
                self.mem[start:start + 32] = bytes(32)
            self.mem[6144 + 32 * row:6144 + 32 * row + 32] = bytes([self.bordcr()]) * 32
        self.lrow, self.lcol = 23, 0

    # -- saving ------------------------------------------------------------------------------------------------
    def scr(self):
        return bytes(self.mem)

    def png(self, path, scale=2, border=32):
        w, h = 256 + 2 * border, 192 + 2 * border
        pal = [(0, 0, 0), (0, 0, 0xD7), (0xD7, 0, 0), (0xD7, 0, 0xD7), (0, 0xD7, 0), (0, 0xD7, 0xD7),
               (0xD7, 0xD7, 0), (0xD7, 0xD7, 0xD7)]
        bright = [tuple(0xFF if v else 0 for v in p) for p in pal]
        rows = []
        bc = pal[self.shown_border]
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
