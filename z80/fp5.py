"""The model for floats on CP/M: the Spectrum ROM's 5-byte form (ABI.md section 11), computed exactly.

Every operation is worked out exactly (Fractions) and then rounded once to the nearest 5 bytes, ties away from zero,
as z80gen.rom5 rounds a literal: so + - * / and sqrt are correctly rounded, and reading a number from text gives the
same bytes as the literal. Results are in the full form (e m3 m2 m1 m0); the short form (00 s lo hi 00) is read
everywhere. Too big is an error (no Inf or NaN, as the ROM); too small is 0. Printing is laid out as the ROM's
PRINT-FP lays it out (measured, FLOATS-CPM.md), with its 8 digits correctly rounded.
"""
from fractions import Fraction as F
import math

MAXE = 127                                   # the exponent byte is e + 128, 1..255: 2^-129 <= |x| < 2^127


class Overflow(Exception):
    pass


def value(b):
    """the exact value of 5 bytes, either form"""
    b = bytes(b)
    if b[0] == 0:
        v = b[2] | (b[3] << 8)
        return F(v - 65536 if b[1] == 0xFF else v)
    m = ((b[1] | 0x80) << 24) | (b[2] << 16) | (b[3] << 8) | b[4]
    v = F(m) * F(2) ** (b[0] - 128 - 32)
    return -v if b[1] & 0x80 else v


def ilog2(f):
    """the e with 2^e <= f < 2^(e+1), for a positive Fraction"""
    e = f.numerator.bit_length() - f.denominator.bit_length()
    while F(2) ** e > f:
        e -= 1
    while F(2) ** (e + 1) <= f:
        e += 1
    return e


def pack(x):
    """x (exact) to the nearest 5 bytes in the full form, ties away from zero; Overflow if it's too big"""
    x = F(x)
    if x == 0:
        return bytes(5)
    neg, f = x < 0, abs(x)
    e = ilog2(f) + 1                         # f = 0.1mmm... x 2^e: 2^(e-1) <= f < 2^e
    scaled = f * F(2) ** (32 - e)            # in [2^31, 2^32)
    mi = int(scaled)
    if scaled - mi >= F(1, 2):               # ties away from zero
        mi += 1
    if mi == 1 << 32:
        mi, e = 1 << 31, e + 1
    if e + 128 > 255:
        raise Overflow()
    if e + 128 < 1:
        return bytes(5)                      # underflow: zero, as the ROM's
    return bytes([e + 128, ((mi >> 24) & 0x7F) | (0x80 if neg else 0), (mi >> 16) & 0xFF, (mi >> 8) & 0xFF,
                  mi & 0xFF])


def add(a, b):
    return pack(value(a) + value(b))


def sub(a, b):
    return pack(value(a) - value(b))


def mul(a, b):
    return pack(value(a) * value(b))


def div(a, b):
    vb = value(b)
    if vb == 0:
        raise ZeroDivisionError()
    return pack(value(a) / vb)


def sqrt(a):
    """the correctly rounded square root (an irrational root can't tie; an exact root is exact)"""
    v = value(a)
    if v < 0:
        raise ValueError()
    if v == 0:
        return bytes(5)
    k = 40 - ilog2(v) // 2                   # scaled so the integer root has 40-odd bits, far more than 32
    scale = F(2) ** k
    big = v * scale * scale
    n = big.numerator // big.denominator
    r = math.isqrt(n)                        # r <= sqrt(big) < r + 1, so the root is in [r, r + 1) / scale
    if big.denominator == 1 and r * r == n:
        return pack(F(r) / scale)
    lo, hi = pack(F(r) / scale), pack(F(r + 1) / scale)
    if lo == hi:
        return lo
    mid = (value(lo) + value(hi)) / 2        # the two round apart: the boundary between them, ties going up
    return hi if mid * mid <= v else lo


DIGITS = 40                                  # a number read from text keeps its first 40 significant digits


def read(span):
    """s.float() on CP/M: the number barley.py's FLOAT_RE found (sign, digits, point, exponent), its first DIGITS
    significant digits rounded exactly to the nearest 5 bytes, ties away (a literal is the same: z80gen)"""
    t = span.strip()
    neg = t.startswith('-')
    t = t.lstrip('+-')
    mant, _, ex = t.lower().partition('e')
    whole, _, frac = mant.partition('.')
    d, x, n = 0, int(ex) if ex else 0, 0
    for ch in whole:                         # whole digits: leading zeros skipped, past DIGITS each moves x up
        if d == 0 and ch == '0':
            continue
        if n < DIGITS:
            d, n = d * 10 + int(ch), n + 1
        else:
            x += 1
    for ch in frac:                          # after the point: each kept digit moves x down; past DIGITS, dropped
        if d == 0 and ch == '0':
            x -= 1
            continue
        if n < DIGITS:
            d, n, x = d * 10 + int(ch), n + 1, x - 1
    v = F(d) * F(10) ** x
    return pack(-v if neg else v)


def show(b):
    """the text the ROM's PRINT-FP lays out for these bytes, with the 8 digits correctly rounded (ties away)"""
    v = value(b)
    if v == 0:
        return '0'
    sign = '-' if v < 0 else ''
    f = abs(v)
    k = 0                                    # 10^k <= f < 10^(k+1)
    while F(10) ** k > f:
        k -= 1
    while F(10) ** (k + 1) <= f:
        k += 1
    q = f / F(10) ** (k - 7)                 # in [10^7, 10^8)
    d = int(q)
    if q - d >= F(1, 2):
        d += 1
    if d == 10 ** 8:
        d, k = 10 ** 7, k + 1
    digits = str(d).rstrip('0')
    if -5 <= k <= 7:
        if k >= 0:
            whole = (digits + '0' * (k + 1))[:k + 1]
            frac = digits[k + 1:]
            return sign + whole + ('.' + frac if frac else '')
        return sign + ('0.' if k == -1 else '.' + '0' * (-k - 1)) + digits
    return sign + digits[0] + ('.' + digits[1:] if len(digits) > 1 else '') + 'E' + ('+' if k > 0 else '-') + \
        str(abs(k))


if __name__ == '__main__':
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import z80gen as G
    for x, want in [(0.5, '0.5'), (0.01, '.01'), (1e-5, '.00001'), (1.2345678e-5, '.000012345678'), (1e-6, '1E-6'),
                    (99999999.0, '99999999'), (1e8, '1E+8'), (123456789.0, '1.2345679E+8'), (999999999.0, '1E+9'),
                    (12345.678, '12345.678'), (1234.5, '1234.5'), (65536.0, '65536'), (-65536.0, '-65536'),
                    (1 / 3, '0.33333333'), (2 / 3, '0.66666667'), (3.14159265, '3.1415926'), (1e-38, '1E-38'),
                    (4294967295.0, '4.2949673E+9'), (9.9999e-05, '.000099999'), (0.0, '0'), (-1.0, '-1')]:
        got = show(G.rom5(x))
        print('ok ' if got == want else 'BAD', x, got, want)
    for x in (0.1, 1 / 3, 1e10, 2.0 ** 31 + 1, 123.456):
        assert pack(F(x)) == G.rom5(x) or G.rom5(x)[0] == 0, (x, pack(F(x)).hex(), G.rom5(x).hex())
    print('pack agrees with rom5')
