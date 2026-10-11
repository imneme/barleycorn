/* barley.h: the runtime for Barley's C backend.
 *
 * The C this goes with is deliberately dumb: every subexpression in a temporary, in the interpreter's order, and
 * every operation a call to something in here. Two rules shape everything:
 *   - No undefined behaviour from our side. Arithmetic is done in explicitly wider types and checked; values are
 *     wrapped into signed types by arithmetic, never by implementation-defined conversion; shifts are bounded.
 *   - Every check the interpreter makes, made here too, with the same words, so the two print the same thing.
 * The data structures are the ones the Z80 library will use (an arena; an insertion-ordered map as an entries array
 * beside a hash index; a ring-buffer queue; version counters), so this is also that library's design, in C first.
 */
#ifndef BARLEY_H
#define BARLEY_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <unistd.h>               /* isatty: typed keys, or a terminal */
#include <time.h>                 /* randomize(): the clock */

typedef uint8_t u8;
typedef uint16_t u16;
typedef int16_t i16;
typedef int32_t i32;
typedef int64_t i64;
typedef uint32_t u32;
typedef uint64_t u64;
typedef __int128 i128;
typedef u8 b8;                    /* bool, and bit when it's an element: 0 or 1 */
typedef double f64;

#define BLY_CAT_(a, b) a##b
#define BLY_CAT(a, b) BLY_CAT_(a, b)

/* -- output, as BASIC prints: a column is tracked for print's zones ------------------------------------------- */

static unsigned char bly_obuf[1 << 16];
static size_t bly_on;
static long bly_col;

/* the virtual screen (bly_zx.h, at the end): print's own output lands on it too, and only print's, so the generated
 * code sets bly_showing around each item, zone and newline it prints (BLY_SHOW), never around a failure's message.
 * Text printed at a place (a print, from its first at on) is the screen's alone: BLY_ATTEXT, showing 2, keeps it
 * out of the output */
static int bly_showing;
#define BLY_SHOW(x) do { bly_showing = 1; x; bly_showing = 0; } while (0)
#define BLY_ATTEXT(x) do { bly_showing = 2; x; bly_showing = 0; } while (0)
/* print #0 and #1: the lower screen's alone, showing 3, with print's column the lower screen's (for the zones) */
#define BLY_LOWER(x, l) do { bly_zx_lower(l); x; bly_zx_upper(); } while (0)
/* print #4: FZX text, the screen's alone, showing 4 */
#define BLY_FZX(x, l) do { bly_zx_fzx_begin(l); x; bly_zx_fzx_end(); } while (0)
static void bly_zx_out(u8 ch);
static void bly_zx_lout(u8 ch);
static void bly_zx_fzx_put(u8 ch);
static void bly_zx_fzx_begin(int l);
static void bly_zx_fzx_end(void);
static void bly_zx_lower(int l);
static void bly_zx_upper(void);
static void bly_zx_init(void);
static void bly_zx_save(void);
static void bly_zx_failed(void);

static void bly_flush(void) {
    fwrite(bly_obuf, 1, bly_on, stdout);
    fflush(stdout);
    bly_on = 0;
}

static void bly_out(const void *p, size_t n) {
    const unsigned char *s = (const unsigned char *)p;
    for (size_t i = 0; i < n; i++) {
        if (bly_showing == 3) {
            bly_col++;
            bly_zx_lout(s[i]);
            continue;
        }
        if (bly_showing == 4) {
            bly_zx_fzx_put(s[i]);
            continue;
        }
        if (bly_showing != 2) {
            if (bly_on == sizeof bly_obuf) bly_flush();
            bly_obuf[bly_on++] = s[i];
        }
        bly_col = s[i] == '\n' ? 0 : bly_col + 1;
        bly_zx_out(s[i]);             /* print's text, and a failure's words, which the 48K shows too */
    }
}

static void bly_pr_cstr(const char *s) { bly_out(s, strlen(s)); }

static void bly_pr_i128(i128 v) {
    char buf[48];
    int i = 47;
    buf[i] = 0;
    int neg = v < 0;
    unsigned __int128 u = neg ? (unsigned __int128)0 - (unsigned __int128)v : (unsigned __int128)v;
    do {
        buf[--i] = (char)('0' + (int)(u % 10));
        u /= 10;
    } while (u);
    if (neg) buf[--i] = '-';
    bly_pr_cstr(buf + i);
}

static void bly_pr_int(i64 v) { bly_pr_i128(v); }
static void bly_zone(void) { long pad = 16 - bly_col % 16; while (pad--) bly_out(" ", 1); }
static void bly_nl(void) { bly_out("\n", 1); }

/* -- failure: what happened, then " at line N", as the Spectrum would print it -------------------------------- */

static int bly_asm_line;              /* inside an asm function's twin: its clause's line, where a failure is */
static const char *const *bly_files;  /* the included files' names, [1] on: a line is (file << 12) | its line */

_Noreturn static void bly_fail_end(int line) {
    if (bly_asm_line) line = bly_asm_line;
    if (line > 0) {
        bly_pr_cstr(" at line ");
        bly_pr_int(line & 4095);
        if (line >> 12) {             /* in an included file: say which, as barley.py's where() does */
            bly_pr_cstr(" of ");
            bly_pr_cstr(bly_files[line >> 12]);
        }
    }
    bly_zx_failed();
    bly_nl();
    bly_flush();
    bly_zx_save();                    /* the screen and sound as they were, as the interpreter's finally saves them */
    exit(1);
}

_Noreturn static void bly_fail(const char *msg, int line) {
    bly_pr_cstr(msg);
    bly_fail_end(line);
}

_Noreturn static void bly_overflow(const char *tname, i128 v, int line) {
    (void)v;                          /* the value isn't shown: a Z80 can't afford a 128-bit product for a message */
    bly_pr_cstr(tname);
    bly_pr_cstr(" overflow");
    bly_fail_end(line);
}

_Noreturn static void bly_divzero(int line) { bly_fail("division by zero", line); }

/* -- random numbers: Melissa's chaotic generator, as barley.py's rng_ functions (DESIGN.md, "Random numbers") ---- */

static u32 bly_rnd_s = 0x48300000u;   /* BCDE: perm32 permutes it */
static u16 bly_rnd_h;                 /* HL: each step's BC and DE feed it, and it's the output */

static u16 bly_rand16(void) {
    u8 b = (u8)(bly_rnd_s >> 24), c = (u8)(bly_rnd_s >> 16), d = (u8)(bly_rnd_s >> 8), e = (u8)bly_rnd_s;
    d = (u8)(((b << 1) | (b >> 7)) ^ d);
    c = (u8)(((d << 1) | (d >> 7)) + c);
    e = (u8)(((c >> 3) | (c << 5)) ^ e);
    b = (u8)(((e >> 1) | (e << 7)) - b);
    bly_rnd_s = (u32)b << 24 | (u32)c << 16 | (u32)d << 8 | e;
    u16 h = (u16)(bly_rnd_h + (bly_rnd_s >> 16));
    h ^= h >> 8;
    bly_rnd_h = (u16)(h + (u16)bly_rnd_s);
    return bly_rnd_h;
}

static i64 bly_random(i64 n, int line) {   /* 0..n-1: 1, 2 or 4 words a try, by n - 1's size, masked, kept if below n */
    if (n <= 0) { bly_pr_cstr("random("); bly_pr_int(n); bly_fail(") has nothing to choose from", line); }
    u64 m = (u64)n - 1, mask = 0;
    while (mask < m) mask = mask << 1 | 1;
    int k = m < 1ull << 16 ? 1 : m < 1ull << 32 ? 2 : 4;
    for (;;) {
        u64 v = 0;
        for (int i = 0; i < k; i++) v = v << 16 | bly_rand16();
        v &= mask;
        if (v <= m) return (i64)v;
    }
}

static void bly_randomize(i64 seed) {    /* its low 36 bits: 20 into BCDE, inside the long cycles' run, 16 into HL */
    u64 s = (u64)seed & ((1ull << 36) - 1);
    bly_rnd_s = 0x48300000u | (u32)(s >> 16);
    bly_rnd_h = (u16)s;
}

static void bly_randomize_clock(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    bly_randomize((i64)ts.tv_sec * 1000000 + ts.tv_nsec / 1000);
}

/* -- integers ------------------------------------------------------------------------------------------------ */

/* wrapping a 64-bit pattern into each type, by arithmetic */
static inline u8 bly_wrap_u8(u64 x) { return (u8)x; }
static inline u16 bly_wrap_u16(u64 x) { return (u16)x; }
static inline u32 bly_wrap_u32(u64 x) { return (u32)x; }
static inline i16 bly_wrap_i16(u64 x) { u16 v = (u16)x; return v >= 0x8000u ? (i16)((i32)v - 65536) : (i16)v; }
static inline i32 bly_wrap_i32(u64 x) { u32 v = (u32)x; return v >= 0x80000000u ? (i32)((i64)v - 4294967296LL) : (i32)v; }
static inline i64 bly_wrap_i64(u64 x) {
    return x >= 0x8000000000000000ull ? (i64)(x - 0x8000000000000000ull) - INT64_MAX - 1 : (i64)x;
}

/* unsigned: wrap, in a wider unsigned type (never u16 * u16, which C would do in signed int) */
#define BLY_UOPS(N, T, W)                                                                                         \
    static inline T add_##N(T a, T b, int l) { (void)l; return (T)((W)a + (W)b); }                             \
    static inline T sub_##N(T a, T b, int l) { (void)l; return (T)((W)a - (W)b); }                             \
    static inline T mul_##N(T a, T b, int l) { (void)l; return (T)((W)a * (W)b); }                             \
    static inline T div_##N(T a, T b, int l) { if (!b) bly_divzero(l); return (T)((W)a / (W)b); }              \
    static inline T rem_##N(T a, T b, int l) { if (!b) bly_divzero(l); return (T)((W)a % (W)b); }              \
    static inline T neg_##N(T a, int l) { (void)l; return (T)((W)0 - (W)a); }
BLY_UOPS(u8, u8, u32)
BLY_UOPS(u16, u16, u32)
BLY_UOPS(u32, u32, u64)

/* signed: computed wider, and trapped if it doesn't fit; C's / and % truncate, as Barley's do */
#define BLY_SOPS(N, T, W, LO, HI, TN)                                                                             \
    static inline T add_##N(T a, T b, int l) { W r = (W)a + (W)b; if (r < (LO) || r > (HI)) bly_overflow(TN, r, l); return (T)r; } \
    static inline T sub_##N(T a, T b, int l) { W r = (W)a - (W)b; if (r < (LO) || r > (HI)) bly_overflow(TN, r, l); return (T)r; } \
    static inline T mul_##N(T a, T b, int l) { W r = (W)a * (W)b; if (r < (LO) || r > (HI)) bly_overflow(TN, r, l); return (T)r; } \
    static inline T div_##N(T a, T b, int l) { if (!b) bly_divzero(l); W r = (W)a / (W)b; if (r < (LO) || r > (HI)) bly_overflow(TN, r, l); return (T)r; } \
    static inline T rem_##N(T a, T b, int l) { if (!b) bly_divzero(l); return (T)((W)a % (W)b); }             \
    static inline T neg_##N(T a, int l) { W r = -(W)a; if (r < (LO) || r > (HI)) bly_overflow(TN, r, l); return (T)r; }
BLY_SOPS(i16, i16, i32, INT16_MIN, INT16_MAX, "int")
BLY_SOPS(i32, i32, i64, INT32_MIN, INT32_MAX, "long")
BLY_SOPS(i64, i64, i128, INT64_MIN, INT64_MAX, "quad")

/* bit operations: on the two's-complement pattern, then wrapped; shifts are bit operations, so they wrap too */
#define BLY_BITOPS(N, T, BITS)                                                                                    \
    static inline T and_##N(T a, T b) { return bly_wrap_##N((u64)(i64)a & (u64)(i64)b); }                       \
    static inline T or_##N(T a, T b) { return bly_wrap_##N((u64)(i64)a | (u64)(i64)b); }                        \
    static inline T xor_##N(T a, T b) { return bly_wrap_##N((u64)(i64)a ^ (u64)(i64)b); }                       \
    static inline T not_##N(T a) { return bly_wrap_##N(~(u64)(i64)a); }                                         \
    static inline T shl_##N(T a, i64 b, int l) {                                                                \
        if (b < 0) bly_fail("negative shift count", l);                                                           \
        return b >= 64 ? (T)0 : bly_wrap_##N((u64)(i64)a << b);                                                  \
    }                                                                                                             \
    static inline T shr_##N(T a, i64 b, int l) {                                                                \
        if (b < 0) bly_fail("negative shift count", l);                                                           \
        i64 x = (i64)a;                                                                                           \
        if (b >= 63) return (T)(x < 0 ? -1 : 0);                                                                  \
        return x >= 0 ? (T)(x >> b) : (T)~((~x) >> b);                                                            \
    }
BLY_BITOPS(u8, u8, 8)
BLY_BITOPS(u16, u16, 16)
BLY_BITOPS(u32, u32, 32)
BLY_BITOPS(i16, i16, 16)
BLY_BITOPS(i32, i32, 32)
BLY_BITOPS(i64, i64, 64)

/* comparisons, equality, hashing and printing, per element kind, for the containers and records */
#define BLY_INTKIND(N, T)                                                                                         \
    static inline int bly_cmp_##N(T a, T b) { return (a > b) - (a < b); }                                       \
    static inline int bly_eq_##N(T a, T b) { return a == b; }                                                   \
    static inline u64 bly_hash_##N(T a) { u64 x = (u64)(i64)a * 0x9E3779B97F4A7C15ull; return x ^ (x >> 29); } \
    static inline void bly_pr_##N(T a) { bly_pr_int((i64)a); }
BLY_INTKIND(u8, u8)
BLY_INTKIND(u16, u16)
BLY_INTKIND(u32, u32)
BLY_INTKIND(i16, i16)
BLY_INTKIND(i32, i32)
BLY_INTKIND(i64, i64)
static inline int bly_cmp_b8(b8 a, b8 b) { return (a > b) - (a < b); }
static inline int bly_eq_b8(b8 a, b8 b) { return a == b; }
static inline void bly_pr_b8(b8 a) { bly_pr_cstr(a ? "true" : "false"); }

/* casts: wrap; a float truncates and must fit */
static inline i64 bly_trunc_fits(f64 v, f64 lo, f64 hi_excl, const char *tname, int l) {
    f64 t = trunc(v);
    if (!(t >= lo && t < hi_excl)) {
        char buf[64];
        snprintf(buf, sizeof buf, "%.10g", v);
        bly_pr_cstr(buf);
        bly_pr_cstr(tname[0] == 'i' ? " doesn't fit in an " : " doesn't fit in a ");
        bly_pr_cstr(tname);
        bly_fail_end(l);
    }
    return (i64)t;
}

/* gcd, lcm and mod, in the widest type, then checked into the result's */
static inline i128 bly_gcd128(i128 a, i128 b) {
    if (a < 0) a = -a;
    if (b < 0) b = -b;
    while (b) { i128 t = a % b; a = b; b = t; }
    return a;
}
static inline i128 bly_lcm128(i128 a, i128 b) {
    if (a < 0) a = -a;
    if (b < 0) b = -b;
    if (!a || !b) return 0;
    return a / bly_gcd128(a, b) * b;
}
static inline i128 bly_mod128(i128 a, i128 m, int l) {
    if (!m) bly_fail("mod by zero", l);
    i128 r = a % m;
    if (r != 0 && ((r < 0) != (m < 0))) r += m;
    return r;
}
static inline i128 bly_fit(i128 v, i128 lo, i128 hi, const char *tname, int l) {
    if (v < lo || v > hi) bly_overflow(tname, v, l);
    return v;
}

/* -- floats: what the machine gives (here, the C library's doubles, as Python's are) ---------------------------- */

static inline void bly_pr_f64(f64 v) {
    char buf[64];
    snprintf(buf, sizeof buf, "%.10g", v == 0 ? 0.0 : v);       /* the ROM has no negative zero: -0.0 prints as 0 */
    bly_pr_cstr(buf);
}
static inline int bly_cmp_f64(f64 a, f64 b) { return (a > b) - (a < b); }
static inline int bly_eq_f64(f64 a, f64 b) { return a == b; }
static inline f64 bly_fdiv(f64 a, f64 b, int l) { if (b == 0) bly_divzero(l); return a / b; }
static inline f64 bly_fpow(f64 a, f64 b, int l) {
    if (a == 0 && b < 0) bly_fail("float ** has no answer", l);
    f64 r = pow(a, b);
    if (isnan(r) && !isnan(a) && !isnan(b)) bly_fail("float ** has no answer", l);
    if (isinf(r) && isfinite(a) && isfinite(b)) bly_fail("float overflow", l);
    return r;
}
static inline f64 bly_ffun(const char *name, f64 (*f)(f64), f64 x, int l) {
    f64 r = f(x);
    int bad = (isnan(r) && !isnan(x)) || (isinf(r) && isfinite(x));
    if (!strcmp(name, "ln") && x <= 0) bad = 1;
    if ((!strcmp(name, "trunc") || !strcmp(name, "floor") || !strcmp(name, "round")) && !isfinite(x)) bad = 1;
    if (bad) {
        char buf[64];
        snprintf(buf, sizeof buf, "%.10g", x);
        bly_pr_cstr(name);
        bly_pr_cstr("(");
        bly_pr_cstr(buf);
        bly_pr_cstr(") has no answer");
        bly_fail_end(l);
    }
    return r;
}
static inline f64 bly_floor_(f64 x) { return floor(x); }
static inline f64 bly_round_(f64 x) { return floor(x + 0.5); }

/* -- the arena: containers, interned names, the input; nothing is ever freed but by release ------------------- */

#ifndef BLY_ARENA
#define BLY_ARENA (256u << 20)
#endif
static u8 *bly_arena;
static size_t bly_atop;

static void *bly_alloc(size_t n, int l) {
    if (!bly_arena) {
        bly_arena = (u8 *)malloc(BLY_ARENA);
        if (!bly_arena) bly_fail("no memory for the arena", l);
    }
    size_t at = (bly_atop + 7) & ~(size_t)7;
    if (n > BLY_ARENA || at > BLY_ARENA - n) bly_fail("arena full", l);
    bly_atop = at + n;
    memset(bly_arena + at, 0, n);
    return bly_arena + at;
}

static u32 bly_capacity(i64 cap, const char *kind, int l) {
    if (cap < 1) {
        bly_pr_cstr("a ");
        bly_pr_cstr(kind);
        bly_fail(" needs a capacity of at least 1", l);
    }
    if (cap > 65535) {
        bly_pr_cstr("a ");
        bly_pr_cstr(kind);
        bly_fail(" holds at most 65535", l);
    }
    return (u32)cap;
}

/* -- text ---------------------------------------------------------------------------------------------------- */

typedef struct { const u8 *p; u16 n; } bly_str;
static const u8 bly_nothing[1];
static u8 bly_chars[256];

static inline bly_str bly_s(const u8 *p, u16 n) { bly_str s; s.p = n ? p : bly_nothing; s.n = n; return s; }
/* a piece of s: the pointer arithmetic happens only when there's something to point at (a zero str's p is NULL,
 * and even NULL + 0 is undefined in C) */
static inline bly_str bly_sub(bly_str s, u32 a, u32 n) { return n ? bly_s(s.p + a, (u16)n) : bly_s(bly_nothing, 0); }
static inline int bly_cmp_str(bly_str a, bly_str b) {
    u16 m = a.n < b.n ? a.n : b.n;
    int c = m ? memcmp(a.p, b.p, m) : 0;
    if (c) return c < 0 ? -1 : 1;
    return (a.n > b.n) - (a.n < b.n);
}
static inline int bly_eq_str(bly_str a, bly_str b) { return bly_cmp_str(a, b) == 0; }
static inline void bly_pr_str(bly_str s) { bly_out(s.p, s.n); }
static inline bly_str bly_chr(u8 b) { bly_chars[b] = b; return bly_s(&bly_chars[b], 1); }

static void bly_pr_range_fail(const char *what, i64 a, i64 b, i64 n, int l) {
    bly_pr_cstr(what);
    bly_pr_int(a);
    if (b != INT64_MIN) { bly_pr_cstr(".."); bly_pr_int(b); }
    bly_pr_cstr(" is outside 0..");
    bly_pr_int(n);
    bly_fail_end(l);
}
static inline void bly_chk_index(i64 i, i64 n, int l) {
    if (i < 0 || i >= n) bly_pr_range_fail("index ", i, INT64_MIN, n, l);
}
static inline u8 bly_str_at(bly_str s, i64 i, int l) { bly_chk_index(i, s.n, l); return s.p[i]; }
static inline bly_str bly_slice(bly_str s, i64 a, i64 b, int l) {
    if (!(0 <= a && a <= b && b <= s.n)) bly_pr_range_fail("slice ", a, b, s.n, l);
    return bly_sub(s, (u32)a, (u32)(b - a));
}
static inline b8 bly_starts(bly_str s, bly_str t) { return t.n <= s.n && (t.n == 0 || !memcmp(s.p, t.p, t.n)); }
static inline i16 bly_find(bly_str s, bly_str t, int l) {
    for (u32 i = 0; i + t.n <= s.n; i++)
        if (t.n == 0 || !memcmp(s.p + i, t.p, t.n)) {
            if (i > 32767) bly_overflow("int", i, l);
            return (i16)i;
        }
    return -1;
}
static inline bly_str bly_trim(bly_str s) {
    u16 a = 0, b = s.n;
    while (a < b && (s.p[a] == ' ' || s.p[a] == '\t')) a++;
    while (b > a && (s.p[b - 1] == ' ' || s.p[b - 1] == '\t')) b--;
    return bly_sub(s, a, (u32)(b - a));
}

/* numbers read from text: the digits are kept as text until they're known to fit, so a number too big for anything
 * is still reported exactly */
static int bly_isdigit(u8 c) { return c >= '0' && c <= '9'; }
static int bly_isspace(u8 c) { return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v'; }

static i64 bly_num(const u8 *d, u32 n, int neg, i64 lo, i64 hi, const char *tname, int l) {
    while (n > 1 && d[0] == '0') { d++; n--; }
    i128 v = 0;
    int big = 0;
    for (u32 i = 0; i < n; i++) {
        if (v > ((i128)1 << 100)) big = 1;
        else v = v * 10 + (d[i] - '0');
    }
    if (neg) v = -v;
    if (big || v < lo || v > hi) {
        if (neg && !(n == 1 && d[0] == '0')) bly_pr_cstr("-");
        bly_out(d, n);
        bly_pr_cstr(tname[0] == 'i' ? " doesn't fit in an " : " doesn't fit in a ");
        bly_pr_cstr(tname);
        bly_fail_end(l);
    }
    return (i64)v;
}

static i64 bly_str_int(bly_str s, i64 lo, i64 hi, const char *tname, int l) {
    u32 i = 0;
    while (i < s.n && bly_isspace(s.p[i])) i++;
    int neg = 0;
    if (i < s.n && (s.p[i] == '-' || s.p[i] == '+')) neg = s.p[i++] == '-';
    u32 st = i;
    while (i < s.n && bly_isdigit(s.p[i])) i++;
    if (i == st) {
        bly_pr_cstr("\"");
        bly_pr_str(s);
        bly_fail("\" doesn't start with an integer", l);
    }
    return bly_num(s.p + st, i - st, neg, lo, hi, tname, l);
}

/* s.float(): \s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?, as the interpreter's FLOAT_RE, and strtod of just that */
static f64 bly_str_float(bly_str s, int l) {
    u32 i = 0;
    while (i < s.n && bly_isspace(s.p[i])) i++;
    u32 st = i;
    if (i < s.n && (s.p[i] == '-' || s.p[i] == '+')) i++;
    u32 d = i;
    while (i < s.n && bly_isdigit(s.p[i])) i++;
    u32 nd = i - d;                   /* digits, before the point and after: a point alone isn't a number */
    if (i < s.n && s.p[i] == '.') {
        u32 f = ++i;
        while (i < s.n && bly_isdigit(s.p[i])) i++;
        nd += i - f;
    }
    if (nd == 0) {
        bly_pr_cstr("\"");
        bly_pr_str(s);
        bly_fail("\" doesn't start with a number", l);
    }
    if (i < s.n && (s.p[i] == 'e' || s.p[i] == 'E')) {   /* an exponent only if it has digits: 3east is 3 */
        u32 j = i + 1;
        if (j < s.n && (s.p[j] == '-' || s.p[j] == '+')) j++;
        u32 e = j;
        while (j < s.n && bly_isdigit(s.p[j])) j++;
        if (j > e) i = j;
    }
    u32 n = i - st;
    char buf[64], *b = n < sizeof buf ? buf : (char *)malloc(n + 1);
    memcpy(b, s.p + st, n);
    b[n] = 0;
    f64 v = strtod(b, 0);
    if (b != buf) free(b);
    if (isinf(v)) {                   /* too big for the machine's float: a double's, here */
        bly_out(s.p + st, n);
        bly_fail(" doesn't fit in a float", l);
    }
    return v;
}

/* ints(): every run of digits; a minus is a sign unless it follows a digit, so 2-4 is two numbers */
typedef struct { bly_str s; u32 i; u32 st, n; int neg; } bly_ints_it;
static inline void bly_ints_init(bly_ints_it *it, bly_str s) { it->s = s; it->i = 0; }
static int bly_ints_next(bly_ints_it *it) {
    const u8 *p = it->s.p;
    u32 n = it->s.n, i = it->i;
    while (i < n && !bly_isdigit(p[i])) i++;
    if (i >= n) { it->i = i; return 0; }
    it->st = i;
    it->neg = i > 0 && p[i - 1] == '-' && !(i > 1 && bly_isdigit(p[i - 2]));
    while (i < n && bly_isdigit(p[i])) i++;
    it->n = i - it->st;
    it->i = i;
    return 1;
}
static i64 bly_ints_val(bly_ints_it *it, i64 lo, i64 hi, const char *tname, int l) {
    return bly_num(it->s.p + it->st, it->n, it->neg, lo, hi, tname, l);
}
static i64 bly_str_intk(bly_str s, i64 k, i64 lo, i64 hi, const char *tname, int l) {
    bly_ints_it it;
    bly_ints_init(&it, s);
    for (i64 j = 0; bly_ints_next(&it); j++)
        if (j == k) return bly_ints_val(&it, lo, hi, tname, l);
    bly_pr_cstr("there is no integer ");
    bly_pr_int(k);
    bly_pr_cstr(" in \"");
    bly_pr_str(s);
    bly_fail("\"", l);
}

/* split(): the pieces between separators, empty ones included, as Python's bytes.split */
typedef struct { bly_str s, sep; u32 i; int done; } bly_split_it;
static inline void bly_split_init(bly_split_it *it, bly_str s, bly_str sep, int l) {
    if (sep.n == 0) bly_fail("split needs a separator", l);
    it->s = s; it->sep = sep; it->i = 0; it->done = 0;
}
static int bly_split_next(bly_split_it *it, bly_str *piece) {
    if (it->done) return 0;
    u32 n = it->s.n, k = it->sep.n;
    for (u32 j = it->i; j + k <= n; j++)
        if (!memcmp(it->s.p + j, it->sep.p, k)) {
            *piece = bly_sub(it->s, it->i, j - it->i);
            it->i = j + k;
            return 1;
        }
    *piece = bly_sub(it->s, it->i, n - it->i);
    it->done = 1;
    return 1;
}

/* -- positions ----------------------------------------------------------------------------------------------- */

typedef struct { i16 r, c; } bly_pos;
static inline bly_pos bly_pos_make(i16 r, i16 c) { bly_pos p; p.r = r; p.c = c; return p; }
static inline bly_pos bly_pos_add(bly_pos a, bly_pos b, int l) { return bly_pos_make(add_i16(a.r, b.r, l), add_i16(a.c, b.c, l)); }
static inline bly_pos bly_pos_sub(bly_pos a, bly_pos b, int l) { return bly_pos_make(sub_i16(a.r, b.r, l), sub_i16(a.c, b.c, l)); }
static inline int bly_cmp_pos(bly_pos a, bly_pos b) { int c = bly_cmp_i16(a.r, b.r); return c ? c : bly_cmp_i16(a.c, b.c); }
static inline int bly_eq_pos(bly_pos a, bly_pos b) { return a.r == b.r && a.c == b.c; }
static inline u64 bly_hash_pos(bly_pos a) { return bly_hash_i32((i32)(((u32)(u16)a.r << 16) | (u16)a.c)); }
static inline void bly_pr_pos(bly_pos a) { bly_pr_cstr("("); bly_pr_int(a.r); bly_pr_cstr(", "); bly_pr_int(a.c); bly_pr_cstr(")"); }
static bly_pos bly_dirs4[4] = {{-1, 0}, {0, 1}, {1, 0}, {0, -1}};
static bly_pos bly_dirs8[8] = {{-1, 0}, {-1, 1}, {0, 1}, {1, 1}, {1, 0}, {1, -1}, {0, -1}, {-1, -1}};

/* -- the input: read whole, split into lines once; lines are slices of it ------------------------------------ */

static u8 *bly_text;
static size_t bly_tlen;
static bly_str *bly_lns;
static u32 bly_nln;

static void bly_load(const char *path) {
    bly_text = (u8 *)malloc(1);
    bly_tlen = 0;
    if (path) {
        FILE *f = fopen(path, "rb");
        if (!f) { bly_pr_cstr("can't read "); bly_pr_cstr(path); bly_fail_end(0); }
        size_t cap = 1 << 16;
        bly_text = (u8 *)realloc(bly_text, cap);
        size_t got;
        while ((got = fread(bly_text + bly_tlen, 1, cap - bly_tlen, f)) > 0) {
            bly_tlen += got;
            if (bly_tlen == cap) bly_text = (u8 *)realloc(bly_text, cap *= 2);
        }
        fclose(f);
    }
    u32 cap = 16;
    bly_lns = (bly_str *)malloc(cap * sizeof *bly_lns);
    size_t st = 0;
    for (size_t i = 0; i <= bly_tlen; i++) {
        int end = i == bly_tlen, cr = !end && bly_text[i] == '\r', lf = !end && bly_text[i] == '\n';
        if (!(end || cr || lf)) continue;
        if (end && st == bly_tlen) break;                 /* the empty line after a final line end */
        if (i - st > 65535) {
            bly_pr_cstr("input line ");
            bly_pr_int(bly_nln + 1);
            bly_fail(" is longer than 65535", 0);
        }
        if (bly_nln == cap) bly_lns = (bly_str *)realloc(bly_lns, (cap *= 2) * sizeof *bly_lns);
        bly_lns[bly_nln++] = bly_s(bly_text + st, (u16)(i - st));
        if (cr && i + 1 < bly_tlen && bly_text[i + 1] == '\n') i++;
        st = i + 1;
    }
}

typedef struct { u32 i; } bly_lines;
static bly_lines *bly_lines_new(int l) { return (bly_lines *)bly_alloc(sizeof(bly_lines), l); }
static bly_str bly_lines_next(bly_lines *it, int l) {
    if (it->i >= bly_nln) bly_fail("no more input lines", l);
    return bly_lns[it->i++];
}
static bly_str bly_input(int l) {
    if (bly_tlen > 65535) bly_fail("the input is longer than 65535, too long for one str", l);
    return bly_s(bly_text, (u16)bly_tlen);
}

/* -- the keyboard: what's typed comes on stdin (zxgfx.py's Keys is the meaning). A terminal has no keys to give
 * key() and inkey() (bly_zx.h), but ask() reads its lines. ask()'s prompt is display, as on the 48K: stderr. ----- */

static int bly_keys_terminal(void) {
    static int t = -1;
    if (t < 0) t = isatty(0);
    return t;
}

static void bly_zx_asked(void);

static bly_str bly_ask(bly_str prompt, int l) {
    bly_flush();                                           /* what was printed first shows first */
    fwrite(prompt.p, 1, prompt.n, stderr);
    fflush(stderr);
    size_t n = 0, cap = 256;
    u8 *buf = (u8 *)malloc(cap);
    int c;
    if (!buf) bly_fail("no memory for a line typed", l);
    while ((c = getchar()) != EOF && c != '\n') {
        if (n == cap) {
            u8 *b = (u8 *)realloc(buf, cap *= 2);
            if (!b) bly_fail("no memory for a line typed", l);
            buf = b;
        }
        buf[n++] = (u8)c;
    }
    bly_zx_asked();
    if (c == EOF && n == 0) bly_fail("STOP in ask", l);
    if (n > 65535) bly_fail("the line typed is longer than 65535, too long for one str", l);
    u8 *p = (u8 *)bly_alloc(n, l);
    memcpy(p, buf, n);
    free(buf);
    return bly_s(p, (u16)n);
}

/* -- intern: names become small numbers ---------------------------------------------------------------------- */

#define BLY_NAMES 65536
static bly_str *bly_names;
static i32 *bly_name_slots;                                  /* open addressing, 2 x BLY_NAMES slots, -1 empty */
static u32 bly_nnames;

static u64 bly_hash_str(bly_str s) {
    u64 h = 1469598103934665603ull;
    for (u16 i = 0; i < s.n; i++) h = (h ^ s.p[i]) * 1099511628211ull;
    return h;
}
static u16 bly_intern(bly_str s, int l) {
    if (!bly_names) {
        bly_names = (bly_str *)malloc(BLY_NAMES * sizeof *bly_names);
        bly_name_slots = (i32 *)malloc(2 * BLY_NAMES * sizeof *bly_name_slots);
        for (u32 i = 0; i < 2 * BLY_NAMES; i++) bly_name_slots[i] = -1;
    }
    u32 m = 2 * BLY_NAMES - 1, h = (u32)bly_hash_str(s) & m;
    while (bly_name_slots[h] >= 0) {
        if (bly_eq_str(bly_names[bly_name_slots[h]], s)) return (u16)bly_name_slots[h];
        h = (h + 1) & m;
    }
    if (bly_nnames == BLY_NAMES) bly_fail("too many names: intern holds 65536", l);
    u8 *copy = (u8 *)bly_alloc(s.n ? s.n : 1, l);
    if (s.n) memcpy(copy, s.p, s.n);
    bly_names[bly_nnames] = bly_s(copy, s.n);
    bly_name_slots[h] = (i32)bly_nnames;
    return (u16)bly_nnames++;
}
static bly_str bly_name(u16 id, int l) {
    if (id >= bly_nnames) { bly_pr_cstr("no name has the number "); bly_pr_int(id); bly_fail_end(l); }
    return bly_names[id];
}

/* -- iteration that checks its container doesn't change under it --------------------------------------------- */

_Noreturn static void bly_changed(const char *kind, int l) {
    bly_pr_cstr("the ");
    bly_pr_cstr(kind);
    bly_fail(" changed while for was walking it", l);
}

/* -- start and finish ---------------------------------------------------------------------------------------- */

static void bly_start(int argc, char **argv) { bly_zx_init(); bly_load(argc > 1 ? argv[1] : 0); }
static int bly_finish(void) { bly_flush(); bly_zx_save(); return 0; }

#include "bly_zx.h"

#endif
