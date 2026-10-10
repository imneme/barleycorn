#!/usr/bin/env python3
"""Make Barleycorn's test font, interp/tests/sprig.fzx: a small FZX font (Andrew Owen's format, fzx.txt) drawn
here for the tests, so none of anyone else's fonts has to live in the repo. Its glyphs are few and plain, and
pick out what the FZX driver has to get right: widths from 1 to 11 pixels (so rows of one byte and of two),
leading (descenders sit lower), kerning (. , and j), tracking, and characters it hasn't got (they print as ?).
Every character it doesn't draw, up to z, is a blank 1 pixel wide. Run it to write the file again.

With --stray it writes interp/tests/stray.fzx instead: a font that breaks the rules on purpose, for the two places
Barleycorn's FZX driver is adapted. Its # has a stray pixel past its width, which at the right edge the stock
driver would put on the next text row's left; its $ runs 12 rows in a font 8 high, and its % starts 9 rows down,
which at the bottom the stock driver would put in the attributes. Barleycorn writes none of them.
"""
import argparse
import os

HEIGHT, TRACKING, LAST = 10, 1, ord('z')

# each glyph: its rows top to bottom, '#' a pixel, on a grid whose row 0 is the top of a capital; a row of dots
# keeps a blank row in place. The glyph's width is its longest row; blank rows above become its leading.
GLYPHS = {
    ' ': ([''], 0, 3),
    '!': (['#', '#', '#', '#', '#', '.', '#'], 0, None),
    '.': (['.', '.', '.', '.', '.', '.', '#'], 1, None),
    ',': (['..', '..', '..', '..', '..', '..', '.#', '#.'], 1, None),
    '?': ([' ### ', '#   #', '    #', '  ## ', '  #  ', '     ', '  #  '], 0, None),
    '0': ([' ### ', '#   #', '#  ##', '# # #', '##  #', '#   #', ' ### '], 0, None),
    '1': ([' # ', '## ', ' # ', ' # ', ' # ', ' # ', '###'], 0, None),
    '2': ([' ### ', '#   #', '    #', '  ## ', ' #   ', '#    ', '#####'], 0, None),
    '3': (['#### ', '    #', '    #', ' ### ', '    #', '    #', '#### '], 0, None),
    '4': (['   # ', '  ## ', ' # # ', '#  # ', '#####', '   # ', '   # '], 0, None),
    '5': (['#####', '#    ', '#### ', '    #', '    #', '#   #', ' ### '], 0, None),
    '6': ([' ### ', '#    ', '#### ', '#   #', '#   #', '#   #', ' ### '], 0, None),
    '7': (['#####', '    #', '   # ', '  #  ', '  #  ', ' #   ', ' #   '], 0, None),
    '8': ([' ### ', '#   #', '#   #', ' ### ', '#   #', '#   #', ' ### '], 0, None),
    '9': ([' ### ', '#   #', '#   #', ' ####', '    #', '    #', ' ### '], 0, None),
    'A': ([' ### ', '#   #', '#   #', '#####', '#   #', '#   #', '#   #'], 0, None),
    'B': (['#### ', '#   #', '#   #', '#### ', '#   #', '#   #', '#### '], 0, None),
    'M': (['#     #', '##   ##', '# # # #', '#  #  #', '#     #', '#     #', '#     #'], 0, None),
    'W': (['#    #    #', '#    #    #', '#    #    #', '#   # #   #', '#  #   #  #', '# #     # #', ' #       # '],
          0, None),
    'a': (['.', '.', ' ### ', '    #', ' ####', '#   #', ' ####'], 0, None),
    'b': (['#    ', '#    ', '#### ', '#   #', '#   #', '#   #', '#### '], 0, None),
    'g': (['.', '.', ' ####', '#   #', '#   #', ' ####', '    #', ' ### '], 0, None),
    'i': (['#', '.', '#', '#', '#', '#', '#'], 0, None),
    'j': (['..#', '...', '..#', '..#', '..#', '..#', '..#', '##.'], 1, None),
    'm': (['.', '.', '#### ### ', '#   #   #', '#   #   #', '#   #   #', '#   #   #'], 0, None),
    'x': (['.', '.', '#   #', ' # # ', '  #  ', ' # # ', '#   #'], 0, None),
    'y': (['.', '.', '#   #', '#   #', '#   #', ' ####', '    #', ' ### '], 0, None),
}


STRAY = {
    '#': (['#..#.#', '#.#..#'], 0, 2),                  # 2 wide, with pixels at 3 and 5: past its width
    '$': (['##'] * 12, 0, None),                         # 12 rows, in a font 8 high
    '%': (['.'] * 9 + ['##', '##'], 0, None),             # leading 9, in a font 8 high: its top can be off the screen
    '?': ([' ## ', '#  #', '  # ', '    ', '  # '], 0, None),
}


def font(glyphs=None, height=HEIGHT, tracking=TRACKING, last=LAST):
    glyphs = GLYPHS if glyphs is None else glyphs
    entries = []
    for code in range(32, last + 1):
        rows, kern, width = glyphs.get(chr(code), ([''], 0, 1))
        rows = [r.replace('.', ' ') for r in rows]
        w = width or max(len(r) for r in rows) or 1
        lead = 0
        if any(r.strip() for r in rows):                # a blank glyph has no rows, and so no leading
            while not rows[0].strip():
                rows, lead = rows[1:], lead + 1
            while not rows[-1].strip():
                rows = rows[:-1]
        else:
            rows = []
        assert 1 <= w <= 16 and lead <= 15 and kern <= 3
        assert all(len(r.rstrip()) <= (8 if w <= 8 else 16) for r in rows), f'{chr(code)!r}: a row past its bytes'
        data = bytearray()
        for r in rows:
            bits = int(r.ljust(16).replace('#', '1').replace(' ', '0'), 2)
            data += bytes([bits >> 8]) if w <= 8 else bytes([bits >> 8, bits & 0xFF])
        if any(len(r.rstrip()) > w for r in rows) and glyphs is GLYPHS:
            raise SystemExit(f'{chr(code)!r} has pixels past its width {w}')
        entries.append((kern, lead, w, bytes(data)))
    n = len(entries)
    table_at = 3                                        # each offset is from its own entry's address
    defs_at = table_at + 3 * n + 2
    blob, at = bytearray([height, tracking, last]), defs_at
    offsets = []
    for i, (kern, lead, w, data) in enumerate(entries):
        offsets.append(at - (table_at + 3 * i))
        at += len(data)
    for i, (kern, lead, w, data) in enumerate(entries):
        v = offsets[i] + 16384 * kern
        blob += bytes([v & 0xFF, v >> 8, 16 * lead + w - 1])
    end = at - (table_at + 3 * n)
    blob += bytes([end & 0xFF, end >> 8])
    for _, _, _, data in entries:
        blob += data
    return bytes(blob)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(prog='make_fzx.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    tests = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'interp', 'tests')
    ap.add_argument('--stray', action='store_true', help='the rule-breaking font, stray.fzx, instead')
    ap.add_argument('-o', dest='out', metavar='OUT.fzx',
                    help='where to write it (default interp/tests/sprig.fzx, or stray.fzx)')
    a = ap.parse_args()
    a.out = a.out or os.path.join(tests, 'stray.fzx' if a.stray else 'sprig.fzx')
    data = font(STRAY, height=8, tracking=1, last=ord('?')) if a.stray else font()
    open(a.out, 'wb').write(data)
    print(f'{a.out}: {len(data)} bytes')
