/* bly_zx.h: the Spectrum's screen and sound, off the Spectrum. Included by barley.h, at its end.
 *
 * The meaning is ../../z80/zxgfx.py, and this follows it line for line: the same 6,912 bytes (bitmap at 0,
 * attributes at 6144, the layout at 4000h), the same algorithms step for step, the same checks in the same order with
 * the same words. Coordinates are BASIC's: x 0..255 from the left, y 0..175 from the bottom; text rows 0..21 and
 * columns 0..31 from the top left.
 *
 * Only print's own output lands on the screen (bly_showing, set by the generated code around each item), never a
 * failure's message, as in the interpreter, where only write() draws. At exit, and on failure too (the interpreter
 * saves in a finally), BARLEY_SCREEN=path.scr gets the 6,912 bytes and a PNG beside it, and BARLEY_SOUND=path.txt the
 * beep log, one "ms semitone" a line.
 *
 * The font is the ROM's (48.rom at 3D00h, 96 characters): cgen.py reads it at compile time and defines BLY_ZX_FONT
 * before including barley.h, so a program carries its own copy.
 */
#ifndef BLY_ZX_H
#define BLY_ZX_H

#ifndef BLY_ZX_FONT
#error "BLY_ZX_FONT: the ROM's font, which cgen.py defines before including barley.h"
#endif
static const u8 bly_zx_font[96 * 8] = BLY_ZX_FONT;

/* the machine's 64K, which peek and poke see: the 48K's ROM at 0000h (poke there does nothing; its bytes are here
 * only when the program peeks, since nothing else can see them: cgen.py defines BLY_ZX_ROM then), the screen's 6,912
 * bytes at 4000h and the 21 UDGs at FF58h, which the screen draws into and reads from */
static u8 bly_mem[65536];
#ifdef BLY_ZX_ROM
static const u8 bly_zx_rom[0x4000] = BLY_ZX_ROM;
#endif
static u8 *const bly_zx_mem = bly_mem + 0x4000;
static u8 bly_zx_attr_p = 0x38;                 /* paper 7, ink 0: the Spectrum's own start (ATTR_P, = ATTR_T) */
static u8 bly_zx_mask;                           /* MASK_P: the bits a square keeps (8: transparent) */
static b8 bly_zx_ink9, bly_zx_paper9;            /* P_FLAG's INK 9 and PAPER 9: contrast */
static b8 bly_zx_inv, bly_zx_ovr;
static u8 bly_zx_border_c = 7;                   /* BORDCR's */
static u8 bly_zx_shown = 7, bly_zx_ear;          /* what the ULA was last told: the border showing, and bit 4 */
static i32 bly_zx_row, bly_zx_col;               /* the print position; row 22 and column 32 are "pending" */
static i32 bly_zx_lrow = 23, bly_zx_lcol;        /* the lower screen's (print #0, #1): its bottom line at first */
static u8 *const bly_zx_udgs = bly_mem + 0xFF58;  /* A..U, as at power-on: the font's capitals */
static b8 bly_frames_on;                         /* frames(true): frame do ... end runs as frames pass */
static u32 bly_zx_frames;                        /* ticks(): the frames that have passed, as far as the model knows;
                                                    24 bits, as the Spectrum's FRAMES, so it wraps at 16,777,216 */
#define BLY_ZX_FRAMES(x) ((u32)(x) & 0xFFFFFFu)
static i16 *bly_zx_snd;                          /* the beep log: ms, semitone, ms, semitone... */
static size_t bly_zx_nsnd, bly_zx_capsnd;

static void bly_zx_init(void) {
    for (int i = 0; i < 768; i++) bly_zx_mem[6144 + i] = bly_zx_attr_p;
    memcpy(bly_zx_udgs, bly_zx_font + ('A' - 32) * 8, 21 * 8);
#ifdef BLY_ZX_ROM
    memcpy(bly_mem, bly_zx_rom, 0x4000);
#endif
}

/* -- failing: the reference's words, then " at line N" ---------------------------------------------------------- */

_Noreturn static void bly_zx_off(const char *pre, i64 a, i64 b, const char *post, int l) {
    bly_pr_cstr(pre);
    bly_pr_cstr("(");
    bly_pr_int(a);
    bly_pr_cstr(", ");
    bly_pr_int(b);
    bly_pr_cstr(")");
    bly_fail(post, l);
}

_Noreturn static void bly_zx_fail1(const char *pre, i64 a, const char *post, int l) {
    bly_pr_cstr(pre);
    bly_pr_int(a);
    bly_fail(post, l);
}

/* -- colours ------------------------------------------------------------------------------------------------------ */

static u8 bly_zx_colour(const char *name, i16 n, i16 top, int l) {
    if (!(0 <= n && n <= top)) {
        bly_pr_cstr(name);
        bly_zx_fail1(" ", n, top == 9 ? " is not a colour 0..9" : " is not a colour 0..7", l);
    }
    return (u8)n;
}

/* ink or paper, as the ROM's CO-TEMP sets them: 0..7 a colour; 8 transparent (the mask's bits set); 9 the contrast
 * (the mask's bits set too, the colour white if the other is dark, else black, and P_FLAG's bit set) */
static b8 bly_zx_set_colour(const char *name, i16 n, u8 bits, int shift, int l) {
    u8 v = bly_zx_colour(name, n, 9, l);
    if (v < 8) bly_zx_attr_p = (u8)((bly_zx_attr_p & ~bits) | (v << shift));
    else if (v == 9) {
        b8 other_dark = !(bly_zx_attr_p & (shift == 0 ? 0x20 : 0x04));
        bly_zx_attr_p = (u8)((bly_zx_attr_p & ~bits) | (other_dark ? bits : 0));
    }
    bly_zx_mask = (u8)((bly_zx_mask & ~bits) | (v >= 8 ? bits : 0));
    return v == 9;
}

static void bly_zx_ink(i16 n, int l) { bly_zx_ink9 = bly_zx_set_colour("ink", n, 0x07, 0, l); }
static void bly_zx_paper(i16 n, int l) { bly_zx_paper9 = bly_zx_set_colour("paper", n, 0x38, 3, l); }

/* bright and flash, as CO-TEMP sets them: 0 off, 1 on, 8 transparent (the bit off, the mask's on) */
static void bly_zx_level(const char *name, i16 n, u8 bit, int l) {
    if (!(n == 0 || n == 1 || n == 8)) {
        bly_pr_cstr(name);
        bly_zx_fail1(" ", n, " is not 0, 1 or 8", l);
    }
    bly_zx_attr_p = (u8)((bly_zx_attr_p & ~bit) | (n == 1 ? bit : 0));
    bly_zx_mask = (u8)((bly_zx_mask & ~bit) | (n == 8 ? bit : 0));
}

static void bly_zx_bright(i16 n, int l) { bly_zx_level("bright", n, 0x40, l); }
static void bly_zx_flash(i16 n, int l) { bly_zx_level("flash", n, 0x80, l); }

/* a square printed or plotted on gets the colours, as the ROM's PO-ATTR gives them (0BDBh) */
static void bly_zx_paint(i32 cell) {
    u8 a = (u8)(((bly_zx_mem[6144 + cell] ^ bly_zx_attr_p) & bly_zx_mask) ^ bly_zx_attr_p);
    if (bly_zx_paper9) {
        a &= 0xC7;
        if (!(a & 0x04)) a ^= 0x38;                /* a dark ink gets a white paper */
    }
    if (bly_zx_ink9) {
        a &= 0xF8;
        if (!(a & 0x20)) a ^= 0x07;                /* a dark paper gets a white ink */
    }
    bly_zx_mem[6144 + cell] = a;
}
static void bly_zx_inverse(b8 b) { bly_zx_inv = b ? 1 : 0; }
static void bly_zx_over(b8 b) { bly_zx_ovr = b ? 1 : 0; }
static void bly_zx_border(i16 n, int l) {
    bly_zx_shown = bly_zx_border_c = bly_zx_colour("border", n, 7, l);
    bly_zx_ear = 0;
}

/* the ROM's CLS: the upper 22 rows in the colours as they are, the lower screen's 2 in the border's (BORDCR: the border
 * as paper, a white ink on a dark one) */
static void bly_zx_cls(void) {
    memset(bly_zx_mem, 0, 6144);
    memset(bly_zx_mem + 6144, bly_zx_attr_p, 704);
    memset(bly_zx_mem + 6144 + 704, (bly_zx_border_c << 3) | ((bly_zx_border_c & 4) ? 0 : 7), 64);
    bly_zx_row = bly_zx_col = 0;
    bly_zx_lrow = 23;
    bly_zx_lcol = 0;
}

/* -- pixels ------------------------------------------------------------------------------------------------------- */

static inline i32 bly_zx_onscreen(i32 x, i32 y) { return 0 <= x && x <= 255 && 0 <= y && y <= 175; }

static void bly_zx_check(i32 x, i32 y, int l) {
    if (!bly_zx_onscreen(x, y)) bly_zx_off("", x, y, " is off the screen", l);
}

/* plot an on-screen point: no checking */
static void bly_zx_put(i32 x, i32 y) {
    i32 ys = 175 - y;
    i32 off = ((ys & 0xC0) << 5) | ((ys & 0x07) << 8) | ((ys & 0x38) << 2) | (x >> 3);
    u8 bit = (u8)(0x80 >> (x & 7));
    u8 value = bly_zx_inv ? 0 : bit;
    if (bly_zx_ovr) bly_zx_mem[off] ^= value;
    else bly_zx_mem[off] = (u8)((bly_zx_mem[off] & ~bit & 0xFF) | value);
    bly_zx_paint((ys >> 3) * 32 + (x >> 3));
}

static void bly_zx_plot(i16 x, i16 y, int l) {
    bly_zx_check(x, y, l);
    bly_zx_put(x, y);
}

static b8 bly_zx_point(i16 x, i16 y, int l) {
    bly_zx_check(x, y, l);
    i32 ys = 175 - y;
    i32 off = ((ys & 0xC0) << 5) | ((ys & 0x07) << 8) | ((ys & 0x38) << 2) | (x >> 3);
    return (bly_zx_mem[off] & (0x80 >> (x & 7))) ? 1 : 0;
}

/* Bresenham, both ends plotted, every pixel once */
static void bly_zx_line(i16 ax, i16 ay, i16 bx, i16 by, int l) {
    bly_zx_check(ax, ay, l);
    bly_zx_check(bx, by, l);
    i32 x0 = ax, y0 = ay, x1 = bx, y1 = by;
    i32 dx = x1 > x0 ? x1 - x0 : x0 - x1, sx = x0 < x1 ? 1 : -1;
    i32 dy = -(y1 > y0 ? y1 - y0 : y0 - y1), sy = y0 < y1 ? 1 : -1;
    i32 err = dx + dy;
    for (;;) {
        bly_zx_put(x0, y0);
        if (x0 == x1 && y0 == y1) return;
        i32 e2 = 2 * err;
        if (e2 >= dy) { err += dy; x0 += sx; }
        if (e2 <= dx) { err += dx; y0 += sy; }
    }
}

/* the midpoint circle: each step's eight points deduplicated (so OVER can't cancel itself), off-screen ones skipped */
static void bly_zx_circle(i16 icx, i16 icy, i16 r, int l) {
    if (r < 0) bly_fail("a circle needs a radius of at least 0", l);
    i32 cx = icx, cy = icy, x = r, y = 0, err = 1 - (i32)r;
    while (x >= y) {
        i32 pts[8][2] = {{cx + x, cy + y}, {cx + y, cy + x}, {cx - y, cy + x}, {cx - x, cy + y},
                         {cx - x, cy - y}, {cx - y, cy - x}, {cx + y, cy - x}, {cx + x, cy - y}};
        for (int i = 0; i < 8; i++) {
            int seen = 0;
            for (int j = 0; j < i && !seen; j++) seen = pts[j][0] == pts[i][0] && pts[j][1] == pts[i][1];
            if (!seen && bly_zx_onscreen(pts[i][0], pts[i][1])) bly_zx_put(pts[i][0], pts[i][1]);
        }
        y += 1;
        if (err < 0) err += 2 * y + 1;
        else {
            x -= 1;
            err += 2 * (y - x) + 1;
        }
    }
}

static void bly_zx_attr(i16 r, i16 c, u8 a, int l) {
    if (!(0 <= r && r <= 23 && 0 <= c && c <= 31)) bly_zx_off("attr ", r, c, " is off the screen", l);
    bly_zx_mem[6144 + r * 32 + c] = a;
}

/* attr(r, c): a square's attribute byte, as BASIC's ATTR */
static u8 bly_zx_attr_read(i16 r, i16 c, int l) {
    if (!(0 <= r && r <= 23 && 0 <= c && c <= 31)) bly_zx_off("attr ", r, c, " is off the screen", l);
    return bly_zx_mem[6144 + r * 32 + c];
}

static void bly_zx_udg(i16 n, const u8 *rows, u16 len, int l) {
    if (!(0 <= n && n <= 20)) bly_zx_fail1("udg ", n, " is not one of 0..20 (A to U)", l);
    if (len != 8) bly_zx_fail1("a udg is 8 rows, not ", len, "", l);
    memcpy(bly_zx_udgs + n * 8, rows, 8);
}

/* -- text --------------------------------------------------------------------------------------------------------- */

/* the lower screen, print #0 and #1: its two rows, as zxgfx.py's lat and lout say. Row 24 is pending below */
static long bly_zx_saved_col;
static int bly_zx_lline;
static void bly_zx_lower(int l) {
    bly_zx_saved_col = bly_col;
    bly_col = bly_zx_lcol;
    bly_zx_lline = l;
    bly_showing = 3;
}
static void bly_zx_upper(void) {
    bly_showing = 0;
    bly_col = bly_zx_saved_col;
}
static void bly_zx_lat(i16 r, i16 c, int l) {
    if (!(0 <= r && r <= 1 && 0 <= c && c <= 31)) bly_zx_off("print at ", r, c, " is off the lower screen", l);
    bly_zx_lrow = 22 + r;
    bly_zx_lcol = c;
}
static void bly_zx_glyph(u8 ch, u8 g[8]);
static inline i32 bly_zx_cell(i32 r, i32 i, i32 c);
static void bly_zx_lout(u8 ch) {
    if (ch == 10) {
        if (bly_zx_lrow == 24) goto grow;
        bly_zx_lrow++;
        bly_zx_lcol = 0;
        return;
    }
    if (bly_zx_lcol == 32) {
        bly_zx_lrow++;
        bly_zx_lcol = 0;
    }
    if (bly_zx_lrow == 24) goto grow;
    u8 g[8];
    bly_zx_glyph(ch, g);
    for (int i = 0; i < 8; i++) bly_zx_mem[bly_zx_cell(bly_zx_lrow, i, bly_zx_lcol)] = g[i];
    bly_zx_mem[6144 + bly_zx_lrow * 32 + bly_zx_lcol] = (u8)((bly_zx_border_c << 3) | ((bly_zx_border_c & 4) ? 0 : 7));
    bly_zx_lcol++;
    return;
grow:
    bly_zx_upper();                                          /* the failure's words are output, not the lower screen's */
    bly_fail("print would grow the lower screen past its two lines", bly_zx_lline);
}

/* print #4: FZX text, as zxgfx.py draws it (Einar Saukas's FZX driver, adapted: nothing written past x 255 or
 * below the screen). The font is a constant table, which the checker has seen is one */
static const u8 *bly_zx_fzxf;
static i32 bly_zx_fzx_x, bly_zx_fzx_line = 191;
static void bly_zx_fzx(const u8 *f, u16 n, int l) {
    (void)n;
    (void)l;
    bly_zx_fzxf = f;
}
static void bly_zx_fzx_at(i16 y, i16 x, int l) {
    if (!(0 <= y && y <= 191 && 0 <= x && x <= 255)) bly_zx_off("print #4; at ", y, x, " is off the screen (192 by 256 pixels)", l);
    bly_zx_fzx_line = 191 - y;
    bly_zx_fzx_x = x;
}
static void bly_zx_fzx_newline(void) {
    bly_zx_fzx_x = 0;
    bly_zx_fzx_line = (bly_zx_fzx_line - bly_zx_fzxf[0]) & 0xFF;
}
static inline i32 bly_zx_cell(i32 r, i32 i, i32 c);
static void bly_zx_fzx_end(void) { bly_showing = 0; }
static int bly_zx_fzx_l;
static void bly_zx_fzx_begin(int l) {
    bly_zx_fzx_l = l;
    bly_showing = 4;
}
static void bly_zx_fzx_out(u8 ch, int l) {
    const u8 *f = bly_zx_fzxf;
    if (!f) {
        bly_zx_fzx_end();                                    /* the failure's words are output */
        bly_fail("print #4 needs a font: fzx(font) first", l);
    }
    if (ch == 10) {
        bly_zx_fzx_newline();
        return;
    }
    if (!(32 <= ch && ch <= f[2])) ch = '?';
    i32 e = 3 + 3 * (ch - 32);
    i32 word = f[e] | f[e + 1] << 8, nxt = f[e + 3] | f[e + 4] << 8;
    i32 start = e + (word & 0x3FFF), kern = word >> 14, end = e + 3 + (nxt & 0x3FFF);
    i32 shift = f[e + 2] >> 4, width = (f[e + 2] & 15) + 1, per = width <= 8 ? 1 : 2;
    bly_zx_fzx_x = bly_zx_fzx_x - kern < 0 ? 0 : bly_zx_fzx_x - kern;
    if (bly_zx_fzx_x + width - 1 > 255) bly_zx_fzx_newline();
    if (((1 - f[0]) & 0xFF) + bly_zx_fzx_line < 256 || bly_zx_fzx_line > 191) {   /* room for its height */
        bly_zx_fzx_end();
        bly_fail("print #4 would go below the screen", l);
    }
    i32 y = 191 - bly_zx_fzx_line + shift, x = bly_zx_fzx_x;
    for (i32 at = start, k = 0; at < end; at += per, k++) {
        i32 row = y + k;
        if (row > 191) break;
        u32 bits = ((u32)f[at] << 16 | (per == 2 ? (u32)f[at + 1] << 8 : 0)) >> (x & 7);
        for (i32 j = 0; j < 3; j++)
            if ((x >> 3) + j <= 31) bly_zx_mem[bly_zx_cell(row >> 3, row & 7, (x >> 3) + j)] |= (u8)(bits >> (16 - 8 * j));
    }
    x += width + f[1];
    if (x > 255) bly_zx_fzx_newline();
    else bly_zx_fzx_x = x;
}
static void bly_zx_fzx_put(u8 ch) { bly_zx_fzx_out(ch, bly_zx_fzx_l); }

static void bly_zx_at(i16 r, i16 c, int l) {
    if (!(0 <= r && r <= 21 && 0 <= c && c <= 31)) bly_zx_off("print at ", r, c, " is off the screen", l);
    bly_zx_row = r;
    bly_zx_col = c;
}

static void bly_zx_glyph(u8 ch, u8 g[8]) {
    if (0x20 <= ch && ch <= 0x7F) memcpy(g, bly_zx_font + (ch - 32) * 8, 8);
    else if (0x80 <= ch && ch <= 0x8F) {
        int b = ch - 0x80;
        u8 top = (u8)((b & 2 ? 0xF0 : 0) | (b & 1 ? 0x0F : 0));
        u8 bottom = (u8)((b & 8 ? 0xF0 : 0) | (b & 4 ? 0x0F : 0));
        for (int i = 0; i < 8; i++) g[i] = i < 4 ? top : bottom;
    } else if (0x90 <= ch && ch <= 0xA4) memcpy(g, bly_zx_udgs + (ch - 0x90) * 8, 8);
    else memcpy(g, bly_zx_font + ('?' - 32) * 8, 8);
}

static inline i32 bly_zx_cell(i32 r, i32 i, i32 c) { return ((r & 0x18) << 8) | (i << 8) | ((r & 7) << 5) | c; }

/* the 22 upper rows move up one; the new bottom row is cleared in the permanent colours. (Moving it by thirds, seven
 * rows at a time, measured no faster: the cost is the 5.4K moved, not the number of moves. See z80/lib/NOTES.md.) */
static void bly_zx_scroll(void) {
    for (i32 r = 0; r < 21; r++) {
        for (i32 i = 0; i < 8; i++) memcpy(bly_zx_mem + bly_zx_cell(r, i, 0), bly_zx_mem + bly_zx_cell(r + 1, i, 0), 32);
        memcpy(bly_zx_mem + 6144 + r * 32, bly_zx_mem + 6144 + (r + 1) * 32, 32);
    }
    for (i32 i = 0; i < 8; i++) memset(bly_zx_mem + bly_zx_cell(21, i, 0), 0, 32);
    memset(bly_zx_mem + 6144 + 21 * 32, bly_zx_attr_p, 32);
}

/* one byte of print's output, drawn where text goes next. Scrolling is lazy, as the ROM's is: a newline from the last
 * row leaves the position pending below it, and only a character printed there scrolls first (a newline while pending
 * scrolls once and stays pending). Wrapping past column 31 is lazy the same way. */
static void bly_zx_out(u8 ch) {
    if (ch == 10) {
        if (bly_zx_row == 22) bly_zx_scroll();
        else bly_zx_row += 1;
        bly_zx_col = 0;
        return;
    }
    if (bly_zx_col == 32) {
        bly_zx_col = 0;
        if (bly_zx_row == 22) bly_zx_scroll();
        else bly_zx_row += 1;
    }
    if (bly_zx_row == 22) {
        bly_zx_scroll();
        bly_zx_row = 21;
    }
    u8 g[8];
    bly_zx_glyph(ch, g);
    for (i32 i = 0; i < 8; i++) {
        u8 v = bly_zx_inv ? (u8)(~g[i] & 0xFF) : g[i];
        i32 k = bly_zx_cell(bly_zx_row, i, bly_zx_col);
        bly_zx_mem[k] = bly_zx_ovr ? (u8)(bly_zx_mem[k] ^ v) : v;
    }
    bly_zx_paint(bly_zx_row * 32 + bly_zx_col);
    bly_zx_col += 1;
}

/* -- sound and time ----------------------------------------------------------------------------------------------- */

static void bly_zx_beep(i16 ms, i16 semitone, int l) {
    if (!(-60 <= semitone && semitone <= 69)) bly_zx_fail1("beep pitch ", semitone, " is outside -60..69", l);
    if (ms < 0) bly_zx_fail1("beep length ", ms, " is negative", l);
    if (bly_zx_nsnd + 2 > bly_zx_capsnd) {
        size_t cap = bly_zx_capsnd ? 2 * bly_zx_capsnd : 256;
        i16 *p = (i16 *)realloc(bly_zx_snd, cap * sizeof *p);
        if (!p) bly_fail("no memory for the sound log", l);
        bly_zx_snd = p;
        bly_zx_capsnd = cap;
    }
    bly_zx_snd[bly_zx_nsnd++] = ms;
    bly_zx_snd[bly_zx_nsnd++] = semitone;
    /* no frames pass: the ROM's BEEPER plays with interrupts off, so FRAMES stands still (a 1-second beep on
       omse-ai's 48K: 0 frames) */
    i32 f4 = (i32)floor(1760.0 * pow(2.0, (semitone - 9) / 12.0) + 0.5);    /* zxbeep.asm's table */
    if (f4 * (i32)ms / 4000) {                   /* it plays: the speaker ends off, the border is BORDCR's */
        bly_zx_shown = bly_zx_border_c;
        bly_zx_ear = 0;
    }
}

static i32 bly_zx_ticks(void) {
    bly_zx_frames = BLY_ZX_FRAMES(bly_zx_frames + 1);
    return (i32)bly_zx_frames;
}

static void bly_zx_pause(i16 n, int l) {
    if (n < 0) bly_zx_fail1("pause ", n, " is negative", l);
    bly_zx_frames = BLY_ZX_FRAMES(bly_zx_frames + (u32)n);
}

/* the keys, as zxgfx.py's Keys has them: each pressed, then let go. inkey() sees it down for one look and up for
 * the next; key() is the latest key registered if it hasn't had it, or else the next typed (down for inkey()) */
static u8 bly_zx_down, bly_zx_pending;
static b8 bly_zx_up;
static u8 bly_zx_take(void) {
    if (bly_keys_terminal()) return 0;
    int c = getchar();
    u8 k = c == EOF ? 0 : c == '\n' ? 13 : (u8)c;
    if (k) {
        bly_zx_down = bly_zx_pending = k;
        bly_zx_up = 0;
    }
    return k;
}
static u8 bly_zx_key(void) {
    u8 k = bly_zx_pending;
    if (k) {
        bly_zx_pending = 0;
        return k;
    }
    k = bly_zx_take();
    bly_zx_pending = 0;
    return k;
}
static u8 bly_zx_inkey(void) {
    if (!bly_zx_down && !bly_zx_take()) return 0;
    if (!bly_zx_up) {
        bly_zx_up = 1;
        return bly_zx_down;
    }
    return bly_zx_down = 0;
}

/* after ask(), on the 48K: each key the editor took clicked (BEEPER: BORDCR's border, the speaker off), and INPUT's
 * end cleared the lower screen (CLS-LOWER) */
static void bly_zx_asked(void) {
    bly_zx_down = bly_zx_pending = 0;            /* the editor took its keys for itself */
    bly_zx_shown = bly_zx_border_c;
    bly_zx_ear = 0;
    for (int row = 22; row < 24; row++) {
        for (int line = 0; line < 8; line++) memset(bly_zx_mem + (((row & 0x18) << 8) | (line << 8) | ((row & 7) << 5)), 0, 32);
        memset(bly_zx_mem + 6144 + 32 * row, (bly_zx_border_c << 3) | ((bly_zx_border_c & 4) ? 0 : 7), 32);
    }
    bly_zx_lrow = 23;
    bly_zx_lcol = 0;
}

/* -- the machine's memory: an address is any whole number, checked as an index is ------------------------------- */

static void bly_addr(i64 a, int l) {
    if (a < 0 || a > 65535) bly_zx_fail1("address ", a, " is outside 0..65536", l);
}
static u8 bly_peek(i64 a, int l) {
    bly_addr(a, l);
    return bly_mem[a];
}
static void bly_poke(i64 a, u8 v, int l) {
    bly_addr(a, l);
    if (a >= 0x4000) bly_mem[a] = v;                          /* the ROM can't be written */
}

/* and its ports, as zxgfx.py says: the ULA's (even), the Kempston joystick's, and nothing's */
static void bly_port(i64 a, int l) {
    if (a < 0 || a > 65535) bly_zx_fail1("port ", a, " is outside 0..65536", l);
}
static u8 bly_inp(i64 a, int l) {
    bly_port(a, l);
    if (a % 2 == 0) return 0xBF | bly_zx_ear << 6;
    return (a & 0xE0) == 0 ? 0 : 0xFF;
}
static void bly_outp(i64 a, u8 v, int l) {
    bly_port(a, l);
    if (a % 2 == 0) {
        bly_zx_shown = v & 7;
        bly_zx_ear = v >> 4 & 1;
    }
}

/* -- saving: the .scr, a PNG beside it, and the sound log ---------------------------------------------------------- */

static u32 bly_zx_crc(u32 crc, const u8 *p, size_t n) {
    crc = ~crc;
    for (size_t i = 0; i < n; i++) {
        crc ^= p[i];
        for (int k = 0; k < 8; k++) crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static void bly_zx_be32(u8 *p, u32 v) { p[0] = (u8)(v >> 24); p[1] = (u8)(v >> 16); p[2] = (u8)(v >> 8); p[3] = (u8)v; }

static void bly_zx_chunk(FILE *f, const char *type, const u8 *data, u32 n) {
    u8 hd[8];
    bly_zx_be32(hd, n);
    memcpy(hd + 4, type, 4);
    u32 crc = bly_zx_crc(bly_zx_crc(0, hd + 4, 4), data, n);
    u8 tl[4];
    bly_zx_be32(tl, crc);
    fwrite(hd, 1, 8, f);
    if (n) fwrite(data, 1, n, f);
    fwrite(tl, 1, 4, f);
}

/* the picture as the interpreter draws it (a 32-pixel border, doubled), in 16 indexed colours (bright is +8), with
 * the image data in stored deflate blocks: no compressor needed */
static void bly_zx_png(const char *path) {
    enum { SCALE = 2, BORDER = 32, W = (256 + 2 * BORDER) * SCALE, H = (192 + 2 * BORDER) * SCALE, ROW = 1 + W / 2 };
    size_t raw_n = (size_t)ROW * H, nblk = (raw_n + 65534) / 65535;
    u8 *raw = (u8 *)malloc(raw_n), *z = (u8 *)malloc(2 + raw_n + 5 * nblk + 4);
    FILE *f = fopen(path, "wb");
    if (!raw || !z || !f) {
        fprintf(stderr, "can't write %s\n", path);
        if (f) fclose(f);
        free(raw);
        free(z);
        return;
    }
    for (int py = 0; py < H; py++) {
        u8 *row = raw + (size_t)py * ROW;
        row[0] = 0;
        memset(row + 1, 0, ROW - 1);
        for (int px = 0; px < W; px++) {
            int x = px / SCALE - BORDER, y = py / SCALE - BORDER, c = bly_zx_shown;
            if (0 <= x && x < 256 && 0 <= y && y < 192) {
                int off = ((y & 0xC0) << 5) | ((y & 0x07) << 8) | ((y & 0x38) << 2) | (x >> 3);
                u8 a = bly_zx_mem[6144 + (y >> 3) * 32 + (x >> 3)];
                int on = bly_zx_mem[off] & (0x80 >> (x & 7));
                c = (on ? (a & 7) : ((a >> 3) & 7)) + (a & 0x40 ? 8 : 0);
            }
            row[1 + px / 2] |= (u8)(px & 1 ? c : c << 4);
        }
    }
    size_t zn = 0;
    z[zn++] = 0x78;
    z[zn++] = 0x01;
    u32 s1 = 1, s2 = 0;
    for (size_t at = 0; at < raw_n; at += 65535) {
        size_t n = raw_n - at < 65535 ? raw_n - at : 65535;
        z[zn++] = at + n == raw_n ? 1 : 0;
        z[zn++] = (u8)n;
        z[zn++] = (u8)(n >> 8);
        z[zn++] = (u8)~n;
        z[zn++] = (u8)(~n >> 8);
        memcpy(z + zn, raw + at, n);
        zn += n;
        for (size_t i = 0; i < n; i++) {
            s1 = (s1 + raw[at + i]) % 65521;
            s2 = (s2 + s1) % 65521;
        }
    }
    bly_zx_be32(z + zn, (s2 << 16) | s1);
    zn += 4;
    static const u8 pal[8][3] = {{0, 0, 0}, {0, 0, 0xD7}, {0xD7, 0, 0}, {0xD7, 0, 0xD7},
                                 {0, 0xD7, 0}, {0, 0xD7, 0xD7}, {0xD7, 0xD7, 0}, {0xD7, 0xD7, 0xD7}};
    u8 plte[16 * 3];
    for (int i = 0; i < 16; i++)
        for (int k = 0; k < 3; k++) plte[i * 3 + k] = i < 8 ? pal[i][k] : (pal[i - 8][k] ? 0xFF : 0);
    u8 ihdr[13];
    bly_zx_be32(ihdr, W);
    bly_zx_be32(ihdr + 4, H);
    ihdr[8] = 4;                                  /* 4 bits a pixel */
    ihdr[9] = 3;                                  /* indexed */
    ihdr[10] = ihdr[11] = ihdr[12] = 0;
    fwrite("\x89PNG\r\n\x1a\n", 1, 8, f);
    bly_zx_chunk(f, "IHDR", ihdr, 13);
    bly_zx_chunk(f, "PLTE", plte, sizeof plte);
    bly_zx_chunk(f, "IDAT", z, (u32)zn);
    bly_zx_chunk(f, "IEND", z, 0);
    fclose(f);
    free(raw);
    free(z);
}

static void bly_zx_save(void) {
    const char *scr = getenv("BARLEY_SCREEN");
    if (scr && *scr) {
        FILE *f = fopen(scr, "wb");
        if (!f || fwrite(bly_zx_mem, 1, 6912, f) != 6912) fprintf(stderr, "can't write %s\n", scr);
        if (f) fclose(f);
        /* the PNG beside it: the same name with .png for its extension, as Python's splitext would find it */
        size_t n = strlen(scr), dot = n, base = 0;
        for (size_t i = 0; i < n; i++)
            if (scr[i] == '/') base = i + 1;
        for (size_t i = n; i > base; i--)
            if (scr[i - 1] == '.') { dot = i - 1; break; }
        if (dot < n) {                                     /* only dots before it (".scr") means no extension */
            size_t i = base;
            while (i < dot && scr[i] == '.') i++;
            if (i == dot) dot = n;
        }
        char *png = (char *)malloc(dot + 5);
        if (png) {
            memcpy(png, scr, dot);
            memcpy(png + dot, ".png", 5);
            bly_zx_png(png);
            free(png);
        }
    }
    const char *snd = getenv("BARLEY_SOUND");
    if (snd && *snd) {
        FILE *f = fopen(snd, "w");
        if (!f) {
            fprintf(stderr, "can't write %s\n", snd);
            return;
        }
        for (size_t i = 0; i < bly_zx_nsnd; i += 2) fprintf(f, "%d %d\n", (int)bly_zx_snd[i], (int)bly_zx_snd[i + 1]);
        fclose(f);
    }
}

#endif
