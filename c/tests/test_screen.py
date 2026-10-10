#!/usr/bin/env python3
"""The C backend's screen and sound, against the reference: the interpreter,
which draws with z80/zxgfx.py.

Every case is a Barley program, run through the interpreter (--screen,
--sound) and through its C (BARLEY_SCREEN, BARLEY_SOUND; built with the
sanitizers on, as tests/run.py builds it). The two must agree on everything:
  - all 6,912 bytes of the screen, saved at the end, or at the failure (the
    interpreter saves in a finally);
  - the beep log;
  - the text printed, byte for byte, a failure's message included, and the
    exit status.

The interpreter's stdout is made latin-1 here, so a byte 80h-FFh prints as
one byte, as the C prints it.

Three kinds of case:
  EDGES   hand-picked: the screen's corners and edges, zero-length lines,
          radius 0 and huge radii, circles centred off the screen, OVER and
          INVERSE on and off, every attribute cell, wrapping and lazy
          scrolling, every byte's glyph, UDGs through a variable and a
          parameter, sound and time
  FAILS   every failure the screen and sound can report, each also checked
          against its exact words
  RANDOM  seeded random drawing programs, a few hundred calls each, some
          ending in a failure

--c-dir points at another copy of the C backend (cgen.py and rt/), which is
how it's broken on purpose to watch these tests catch it.
"""

import argparse
import os
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import paths                                  # noqa: E402
ROOT = os.path.join(HERE, '..', '..')
INTERP = os.path.join(ROOT, 'interp')
RUN_INTERP = ("import sys; sys.stdout.reconfigure(encoding='latin-1'); sys.path.insert(0, sys.argv[1]); "
              "import barley; barley.main(sys.argv[2:])")


ap = argparse.ArgumentParser(prog='test_screen.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--seed', type=int, default=9102026, help='the random cases\' seed (default 9102026)')
ap.add_argument('--random', type=int, default=60, metavar='N', help='how many random cases (default 60)')
ap.add_argument('--quick', action='store_true', help='only 6 random cases')
ap.add_argument('--c-dir', default=os.path.join(HERE, '..'), metavar='DIR',
                help='another copy of the C backend to test (cgen.py and rt/)')
ap.add_argument('--build', default=os.path.join(paths.BUILD, 'cbuild', 'screen'), metavar='DIR',
                help='where to build (default build/cbuild/screen)')
ARGS = ap.parse_args()                         # at the start: the paths below depend on it
C_DIR = os.path.abspath(ARGS.c_dir)
BUILD = os.path.abspath(ARGS.build)
CC = [paths.CC, '-std=c11', '-g', '-O1', '-Wall', '-Wno-unused-function', '-Wno-unused-variable',
      '-fsanitize=undefined,address', '-fno-sanitize-recover=all', '-I', os.path.join(C_DIR, 'rt')]


def read(path):
    return open(path, 'rb').read() if os.path.exists(path) else None


def run_interp(src, d):
    png, snd = os.path.join(d, 'i.png'), os.path.join(d, 'i.txt')
    r = subprocess.run([sys.executable, '-I', '-c', RUN_INTERP, INTERP, '--screen', png, '--sound', snd, src],
                       capture_output=True, timeout=600)
    return r.returncode, r.stdout, r.stderr, read(os.path.join(d, 'i.scr')), read(snd)


def run_c(src, d):
    gen = subprocess.run([sys.executable, '-I', os.path.join(C_DIR, 'cgen.py'), src], capture_output=True, text=True)
    if gen.returncode:
        return None, ('cgen.py: ' + gen.stdout + gen.stderr).encode(), b'', None, None
    c, exe = os.path.join(d, 'p.c'), os.path.join(d, 'p')
    open(c, 'w').write(gen.stdout)
    cc = subprocess.run(CC + [c, '-lm', '-o', exe], capture_output=True, text=True)
    if cc.returncode or cc.stderr.strip():
        return None, ('C compiler: ' + cc.stderr).encode(), b'', None, None
    scr, snd = os.path.join(d, 'c.scr'), os.path.join(d, 'c.txt')
    r = subprocess.run([exe], capture_output=True, timeout=600,
                       env=dict(os.environ, BARLEY_SCREEN=scr, BARLEY_SOUND=snd))
    return r.returncode, r.stdout, r.stderr, read(scr), read(snd)


def check(case):
    """one case: (name, source, expected stdout or None); returns a list of what disagreed"""
    name, src, want = case
    d = os.path.join(BUILD, name)
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        os.remove(os.path.join(d, f)) if os.path.isfile(os.path.join(d, f)) else None
    path = os.path.join(d, 'p.bly')
    open(path, 'w').write(src)
    irc, iout, ierr, iscr, isnd = run_interp(path, d)
    crc, cout, cerr, cscr, csnd = run_c(path, d)
    bad = []
    if ierr:
        bad.append('interpreter stderr: ' + ierr.decode('latin-1')[-600:])
    if crc is None:
        return bad + [cout.decode('latin-1')[-1500:]]
    if cerr:
        bad.append('C stderr: ' + cerr.decode('latin-1')[-1500:])
    if irc != crc:
        bad.append(f'exit status: interpreter {irc}, C {crc}')
    if iout != cout:
        k = next((i for i in range(min(len(iout), len(cout))) if iout[i] != cout[i]), min(len(iout), len(cout)))
        bad.append(f'text differs at byte {k}: interpreter {iout[max(0, k - 30):k + 30]!r}, '
                   f'C {cout[max(0, k - 30):k + 30]!r}')
    if want is not None and cout != want.encode('latin-1'):
        bad.append(f'text: wanted {want!r}, C printed {cout!r}')
    if iscr is None or cscr is None or len(cscr) != 6912:
        bad.append(f'screen: interpreter wrote {None if iscr is None else len(iscr)} bytes, '
                   f'C {None if cscr is None else len(cscr)}')
    elif iscr != cscr:
        diff = [i for i in range(6912) if iscr[i] != cscr[i]]
        bad.append(f'screen: {len(diff)} bytes differ, first at {0x4000 + diff[0]:04X}h '
                   f'(interpreter {iscr[diff[0]]:02X}h, C {cscr[diff[0]]:02X}h)')
    if isnd != csnd:
        bad.append(f'sound: interpreter {(isnd or b"")[:200]!r}, C {(csnd or b"")[:200]!r}')
    return bad


# -- hand-picked edges ----------------------------------------------------------------------------------------------

def prog(*lines, decls=''):
    return decls + 'func main()\n' + ''.join('  ' + ln + '\n' for ln in lines) + 'end\n'


CORNERS = [(0, 0), (255, 0), (0, 175), (255, 175), (128, 0), (0, 88), (255, 88), (128, 175), (1, 1), (254, 174),
           (7, 7), (8, 8), (127, 87), (128, 88)]

EDGES = [
    ('corners', prog(*[f'plot({x}, {y})' for x, y in CORNERS],
                     *[f'print point({x}, {y}); " "; point({x + (1 if x < 255 else -1)}, {y});' for x, y in CORNERS])),
    ('lines-octants', prog(*[f'line(128, 88, {x}, {y})' for x, y in
                             [(255, 88), (255, 130), (255, 175), (200, 175), (128, 175), (60, 175), (0, 175),
                              (0, 130), (0, 88), (0, 40), (0, 0), (60, 0), (128, 0), (200, 0), (255, 0), (255, 40),
                              (129, 175), (127, 0), (255, 89), (0, 87)]])),
    ('lines-edges', prog('line(0, 0, 255, 0)', 'line(0, 175, 255, 175)', 'line(0, 0, 0, 175)',
                         'line(255, 175, 255, 0)', 'line(0, 0, 255, 175)', 'line(255, 0, 0, 175)',
                         'line(3, 100, 250, 101)', 'line(100, 3, 101, 170)')),
    ('lines-zero', prog('line(0, 0, 0, 0)', 'line(255, 175, 255, 175)', 'line(5, 5, 5, 5)', 'over(true)',
                        'line(9, 9, 9, 9)', 'line(9, 9, 9, 9)', 'line(10, 10, 10, 10)')),
    ('circles', prog(*[f'circle(128, 88, {r})' for r in (0, 1, 2, 3, 10, 87, 88, 89, 100, 128, 200, 1000)])),
    ('circles-corners-and-off', prog('circle(0, 0, 50)', 'circle(255, 175, 50)', 'circle(255, 0, 3)',
                                     'circle(0, 175, 0)', 'circle(-50, 88, 60)', 'circle(300, 200, 100)',
                                     'circle(128, -1000, 1050)', 'circle(-32768, -32768, 32767)',
                                     'circle(32767, 32767, 32767)', 'circle(-200, 88, 10)')),
    ('circle-huge', prog('circle(128, 88, 32767)', 'circle(0, 0, 32767)', 'over(true)', 'circle(128, 88, 180)',
                         'circle(255, 175, 300)')),
    ('circles-over', prog('over(true)', *[f'circle(128, 88, {r})' for r in (0, 1, 2, 3, 4, 5, 7, 30, 87, 88)],
                          'circle(10, 10, 10)', 'circle(10, 10, 10)', 'circle(11, 10, 10)')),
]

for inv in (0, 1):
    for ovr in (0, 1):
        EDGES.append((f'inverse{inv}-over{ovr}', prog(
            'for x in 0..256 do plot(x, 50) end', 'for y in 0..176 do plot(200, y) end',
            'circle(60, 120, 30)', 'print at 2, 2; "under"',
            f'inverse({inv})', f'over({ovr})',
            'plot(10, 50)', 'plot(10, 50)', 'plot(11, 60)', 'plot(12, 60)', 'plot(12, 60)', 'plot(12, 60)',
            'line(0, 40, 255, 60)', 'line(200, 0, 200, 175)', 'circle(60, 120, 30)', 'circle(60, 120, 31)',
            'print at 2, 0; "on top of it"', 'print at 2, 0; "on top"', 'print point(10, 50); point(11, 60); point(200, 3)',
            'inverse(0)', 'over(0)', 'plot(100, 100)', 'print "and back"')))

EDGES += [
    ('every-attr', prog('for r in 0..24 do', '  for c in 0..32 do', '    attr(r, c, byte(r * 32 + c))', '  end', 'end',
                        'plot(0, 0)', 'plot(255, 175)', 'attr(23, 31, 0)', 'attr(0, 0, 255)', 'attr(12, 16, 0x47)')),
    ('colours', prog(*[ln for i in range(8) for ln in
                       (f'ink({i})', f'paper({7 - i})', f'bright({[0, 1, 8][i % 3]})', f'flash({i // 4})', f'border({i})',
                        f'print at {i}, {i}; "ink {i}"', f'plot({i * 30}, {i * 20})', f'attr(20, {i}, {i * 37 % 256})')],
                     'bright(true)', 'flash(false)', 'print "after"', 'cls()', 'plot(1, 1)', 'print "cls"')),
    ('colours-8-9', prog('for r in 0..24 do', '  for c in 0..32 do', '    attr(r, c, byte(r * 32 + c * 7))', '  end',
                         'end', 'ink(8)', 'paper(8)', 'print at 1, 0; "both kept"', 'ink(9)', 'print at 3, 0; "ink 9"',
                         'paper(9)', 'print at 5, 0; "paper 9 too"', 'ink(8)', 'plot(0, 100)', 'line(0, 90, 255, 80)',
                         'circle(128, 60, 30)', 'ink(3)', 'paper(8)', 'bright(8)', 'flash(8)',
                         'print at 12, 0; "bright and flash kept"', 'bright(1)', 'flash(0)', 'paper(9)',
                         'print at 14, 0; "contrast"', 'cls()', 'print "cls with paper 9"',
                         'print attr(0, 0); " "; attr(5, 3); " "; attr(23, 31)')),
    ('cls-colours', prog('paper(1)', 'ink(6)', 'bright(1)', 'flash(1)', 'cls()', 'print "flashing"', 'paper(2)',
                         'flash(0)', 'cls()', 'circle(100, 100, 40)')),
    ('scroll', prog('for i in 0..30 do', '  ink(byte(i % 8))', '  print "line "; i', 'end', 'print "last";',
                    'paper(2)', 'print', 'print "x"')),
    ('scroll-lots', prog('for i in 0..200 do', '  paper(byte(i % 8))', '  ink(byte((i + 3) % 8))',
                         '  print i, i * 7; " ";', '  if i % 3 == 0 then print end', 'end')),
    ('pending-newline', prog('print at 21, 0; "bottom"', 'print', 'paper(3)', 'print', 'print "after";',
                             'print at 21, 31; "z"', 'print', 'print', 'print', 'paper(5)', 'print "end"')),
    ('pending-then-at', prog('print at 21, 0; "x"', 'print at 0, 0; "top"', 'print at 21, 5; "y"', 'cls()', 'print "c"')),
    ('wrap-at-bottom', prog('print at 21, 28; "abcdefgh"', 'print at 21, 30; "ab";', 'print "cd"',
                            'print at 20, 31; "123456789012345678901234567890123456"')),
    ('wrap-32-then-newline', prog('print at 5, 0; "' + 'abcdefgh' * 4 + '"', 'print "next row"',
                                  'print "' + 'x' * 32 + '";', 'print "y"', 'print "' + 'q' * 64 + '"', 'print "r"')),
    ('every-byte', prog('for b in 0..256 do print chr(byte(b)); end', 'print', 'inverse(1)',
                        'for b in 0..256 do print chr(byte(b)); end', 'inverse(0)', 'over(1)', 'print at 0, 0;',
                        'for b in 0..256 do print chr(byte(b)); end')),
    ('text-over', prog('print at 3, 3; "hello"', 'over(1)', 'print at 3, 3; "hello"', 'print at 4, 3; "abc"',
                       'print at 4, 3; "xyz"', 'inverse(1)', 'print at 5, 0; "both"', 'over(0)', 'print at 6, 0; "inv"')),
    ('zones-and-at', prog('print "a", "b", "c"', 'print at 3, 5; "a", "b";', 'print "c"', 'print at 4, 15; 1, 2',
                          'print at 6, 31; "w", "x"', 'print 12345678901234567, "q"')),
    ('udgs', prog('var u: byte[8]', 'for n in 0..21 do', '  for i in 0..8 do u[i] = byte(n * 8 + i) end',
                  '  udg(n, u)', 'end', 'for n in 0..21 do print chr(byte(0x90 + n)); end', 'print',
                  'setudg(3, u)', 'print "\\x93\\x90\\xA4\\xA5\\x8F\\x80"', 'u[0] = 255', 'udg(20, u)', 'print "\\xA4"',
                  decls='func setudg(n: int, rows: byte[])\n  udg(n, rows)\nend\n')),
    ('udg-before-power-on', prog('print "\\x90\\x91\\xA4"', 'inverse(1)', 'print "\\x90"')),
    ('sound-and-time', prog('beep(0, -60)', 'beep(1, 69)', 'beep(19, 0)', 'beep(20, 0)', 'beep(32767, 12)',
                            'print ticks()', 'pause(0)', 'print ticks()', 'pause(32767)', 'print ticks(); " "; key()',
                            'beep(250, -1)', 'print ticks()', 'var t: long = ticks()', 'pause(5)',
                            'print ticks() - t')),
    ('ticks-wrap', prog('for i in 0..511 do pause(32767) end', 'print ticks()', 'pause(32767)', 'print ticks()',
                        'pause(500)', 'print ticks()', 'for i in 0..1100 do pause(32767) end', 'print ticks()',
                        'for i in 0..10239 do beep(32767, 0) end', 'print ticks()', 'pause(1)', 'print ticks()')),
    ('vars-as-args', prog('var b: byte = 200', 'var k: int = 100', 'plot(b, k - 30)', 'line(k, k, b, 0)',
                          'circle(k, k - 12, int(b) - 150)', 'attr(int(b) / 10, 3, b)', 'ink(k / 20)',
                          'bright(b / 200)', 'flash(k > 50)', 'print at k / 10, int(b) / 10; "here"', 'beep(k, k - 100)',
                          'pause(b)', 'print ticks()', 'over(b == 200)', 'plot(b, k - 30)')),
    ('flags-wide', prog('var k: int = 768', 'var w: word = 256', 'var q: long = 65536', 'bright(k / 96)',
                        'flash(int(w / 256))', 'print "bright and flash"', 'inverse(512)', 'print "inverse"', 'plot(9, 9)',
                        'over(k)', 'plot(9, 9)', 'print "over"', 'inverse(0)', 'over(0)', 'bright(int(q - 65528))',
                        'flash(int(q / 65536))', 'plot(20, 20)',
                        'print "word and long"', 'inverse(-32768)', 'over(65536)', 'circle(50, 50, 20)', 'print "end"')),
    ('peek-rom', prog('var s: long = 0', 'var t: long = 0', 'for a in 0..16384 do',
                      '  s = (s * 31 + long(peek(a))) % 1000003', '  t += long(peek(a))', 'end', 'print s; " "; t',
                      'print peek(0); " "; peek(1); " "; peek(0x3D00); " "; peek(0x3FFF)',
                      'poke(0, 0)', 'poke(0x3D00 + 8 * 33 + 2, 255)', 'poke(0x3FFF, 1)', 'poke(16383, 255)',
                      'print peek(0); " "; peek(0x3D00 + 8 * 33 + 2); " "; peek(0x3FFF)', 'print "A still A"')),
    ('poke-screen', prog('var a: word = 0x4000', 'while a < 0x5800 do', '  poke(a, byte(a % 251))', '  a += 7', 'end',
                         'for c in 0x5800..0x5B00 do poke(c, byte(c * 3)) end', 'poke(0x5AFF, 0x47)',
                         'poke(0x5B00, 1)', 'poke(0xFF57, 2)', 'print peek(0x5B00); " "; peek(0xFF57); " "; peek(0x5AFF)',
                         'plot(0, 175)', 'line(0, 0, 255, 175)', 'print at 3, 3; "on top"',
                         'print peek(0x4000); " "; peek(0x4000 + 3 * 32 + 3); " "; peek(0x5800 + 3 * 32 + 3)')),
    ('poke-udgs', prog('for a in 0xFF58..0x10000 do poke(a, byte(a * 7)) end',
                       'for n in 0..21 do print chr(byte(0x90 + n)); end', 'print',
                       'var u: byte[8]', 'for i in 0..8 do u[i] = byte(i * 33) end', 'udg(5, u)',
                       'for i in 0..8 do print peek(0xFF58 + 40 + i); " "; end', 'print', 'poke(65535, 0xFF)',
                       'print "\\xA4\\x95"; peek(65535)')),
    ('peek-scrolled', prog('for i in 0..21 do print "row "; i end', 'print at 21, 0; "bottom";',
                           'poke(0x5800 + 21 * 32, 0x56)', 'poke(0x50E0, 0xFF)', 'print',
                           'print "scrolled"', 'print peek(0x5800 + 20 * 32); " "; peek(0x50C0); " "; peek(0x50E0)')),
    ('address-types', prog('var b: byte = 7', 'var i: int = 0x4000', 'var w: word = 0xFF58', 'var l: long = 65535',
                           'var q: quad = 22528', 'poke(b, 1)', 'poke(i, 0xF0)', 'poke(w, 0x0F)', 'poke(l, 0x81)',
                           'poke(q, 0x46)', 'print peek(b); " "; peek(i); " "; peek(w); " "; peek(l); " "; peek(q)',
                           'print peek(quad(16384)); " "; peek(word(0x5800))', 'print "\\x90\\xA4"')),
    ('saved-at-failure', prog('ink(2)', 'circle(100, 100, 50)', 'print at 3, 3; "drawn"', 'beep(10, 5)',
                              'plot(256, 0)', 'plot(1, 1)')),
    ('message-not-drawn', prog('var a: int[3]', 'var k: int = 5', 'print at 4, 4; "abc"; a[k]')),
    ('message-not-drawn-2', prog('var z: int = 0', 'print at 21, 0; "x"', 'print', 'print 7 / z')),
    ('message-not-drawn-3', prog('print at 2, 2; "ok "; 300; " "', 'print at 30, 0; "never"')),
]

# -- every failure, word for word ------------------------------------------------------------------------------------

FAIL_CALLS = [
    ('ink(10)', 'ink 10 is not a colour 0..9'), ('ink(-1)', 'ink -1 is not a colour 0..9'),
    ('paper(10)', 'paper 10 is not a colour 0..9'), ('paper(-32768)', 'paper -32768 is not a colour 0..9'),
    ('border(8)', 'border 8 is not a colour 0..7'), ('border(-1)', 'border -1 is not a colour 0..7'),
    ('bright(2)', 'bright 2 is not 0, 1 or 8'), ('flash(9)', 'flash 9 is not 0, 1 or 8'),
    ('bright(-1)', 'bright -1 is not 0, 1 or 8'), ('flash(-32768)', 'flash -32768 is not 0, 1 or 8'),
    ('print attr(24, 0)', 'attr (24, 0) is off the screen'), ('print attr(0, -1)', 'attr (0, -1) is off the screen'),
    ('plot(256, 0)', '(256, 0) is off the screen'), ('plot(-1, 0)', '(-1, 0) is off the screen'),
    ('plot(0, 176)', '(0, 176) is off the screen'), ('plot(0, -1)', '(0, -1) is off the screen'),
    ('plot(-32768, 32767)', '(-32768, 32767) is off the screen'),
    ('print point(256, 175)', '(256, 175) is off the screen'), ('print point(0, -1)', '(0, -1) is off the screen'),
    ('line(-1, 0, 5, 5)', '(-1, 0) is off the screen'), ('line(5, 5, 5, 176)', '(5, 176) is off the screen'),
    ('line(300, 0, 400, 0)', '(300, 0) is off the screen'), ('line(0, 0, 256, 175)', '(256, 175) is off the screen'),
    ('circle(10, 10, -1)', 'a circle needs a radius of at least 0'),
    ('circle(-500, 10, -32768)', 'a circle needs a radius of at least 0'),
    ('attr(24, 0, 7)', 'attr (24, 0) is off the screen'), ('attr(0, 32, 7)', 'attr (0, 32) is off the screen'),
    ('attr(-1, 0, 7)', 'attr (-1, 0) is off the screen'), ('attr(0, -1, 7)', 'attr (0, -1) is off the screen'),
    ('udg(21, u8)', 'udg 21 is not one of 0..20 (A to U)'), ('udg(-1, u8)', 'udg -1 is not one of 0..20 (A to U)'),
    ('udg(0, u7)', 'a udg is 8 rows, not 7'), ('udg(20, u9)', 'a udg is 8 rows, not 9'),
    ('udg(21, u7)', 'udg 21 is not one of 0..20 (A to U)'),
    ('print at 22, 0; "x"', 'print at (22, 0) is off the screen'),
    ('print at 0, 32; "x"', 'print at (0, 32) is off the screen'),
    ('print at -1, 0', 'print at (-1, 0) is off the screen'), ('print at 0, -1', 'print at (0, -1) is off the screen'),
    ('print "before "; at 23, 40; "x"', 'print at (23, 40) is off the screen'),
    ('beep(10, 70)', 'beep pitch 70 is outside -60..69'), ('beep(10, -61)', 'beep pitch -61 is outside -60..69'),
    ('beep(-1, 0)', 'beep length -1 is negative'), ('beep(-1, 70)', 'beep pitch 70 is outside -60..69'),
    ('pause(-1)', 'pause -1 is negative'), ('pause(-32768)', 'pause -32768 is negative'),
    ('print peek(-1)', 'address -1 is outside 0..65536'), ('print peek(65536)', 'address 65536 is outside 0..65536'),
    ('poke(70000, 1)', 'address 70000 is outside 0..65536'), ('poke(-32768, 0)', 'address -32768 is outside 0..65536'),
    ('print peek(-9223372036854775807)', 'address -9223372036854775807 is outside 0..65536'),
]


def fails():
    out = []
    for i, (call, msg) in enumerate(FAIL_CALLS):
        lines = ['var u7: byte[7]', 'var u8: byte[8]', 'var u9: byte[9]', 'print "start"', 'plot(5, 5)', call,
                 'print "never"']
        before = 'start\nbefore ' if call.startswith('print "before') else 'start\n'
        out.append((f'fail{i:02d}', prog(*lines), f'{before}{msg} at line {lines.index(call) + 2}\n'))
    return out


# -- random drawing programs -----------------------------------------------------------------------------------------

def text(rng):
    n = rng.choice([0, 1, 2, 5, 9, 17, 31, 32, 33, 40, 64, 70])
    out = []
    for _ in range(n):
        p = rng.random()
        b = (rng.randint(0x20, 0x7E) if p < .7 else 10 if p < .8 else rng.randint(0x80, 0xA4) if p < .9
             else rng.randint(0, 255))
        out.append(chr(b) if 0x20 <= b <= 0x7E and chr(b) not in '"\\' else f'\\x{b:02X}')
    return '"' + ''.join(out) + '"'


def coord(rng, hi, off=0.0):
    if rng.random() < off:
        return rng.choice([-1, hi + 1, rng.randint(-300, -1), rng.randint(hi + 1, 600)])
    if rng.random() < .25:
        return rng.choice([0, 1, hi - 1, hi])
    return rng.randint(0, hi)


def random_program(rng, n):
    st = []
    flag = lambda: rng.choice(['true', 'false', '0', '1', '2', 'k0 > 0', 'b1'])      # noqa: E731
    slot = [0]

    def num(v, byte=False):
        """a literal, or sometimes a variable just set to it (the int and byte conversion paths); each argument of a
        call gets its own variable"""
        p = rng.random()
        slot[0] = (slot[0] + 1) % 4
        if p < .1 and 0 <= v <= 255:
            st.append(f'b{slot[0]} = {v}')
            return f'b{slot[0]}'
        if p < .2 and not byte and -32768 <= v <= 32767:
            st.append(f'k{slot[0]} = {v}')
            return f'k{slot[0]}'
        return str(v)

    for _ in range(n):
        w = rng.random() * 108
        if w < 16:
            st.append(f'plot({num(coord(rng, 255))}, {num(coord(rng, 175))})')
        elif w < 26:
            x0, y0, x1, y1 = coord(rng, 255), coord(rng, 175), coord(rng, 255), coord(rng, 175)
            if rng.random() < .1:
                x1, y1 = x0, y0
            st.append(f'line({num(x0)}, {num(y0)}, {x1}, {y1})')
        elif w < 33:
            p = rng.random()
            r = (rng.randint(0, 20) if p < .6 else rng.randint(20, 120) if p < .85 else rng.randint(120, 400)
                 if p < .95 else rng.randint(1000, 32767))
            cx = coord(rng, 255, .15)
            cy = coord(rng, 175, .15)
            st.append(f'circle({cx}, {cy}, {num(r)})')
        elif w < 40:
            st.append(f'{rng.choice(["ink", "paper"])}({num(rng.randint(0, 9))})')
        elif w < 44:
            v = rng.choice(['true', 'false', '0', '1', '8', 8, 1, 'k0 > 0'])     # 8 and 1: perhaps through a variable
            st.append(f'{rng.choice(["bright", "flash"])}({num(v) if isinstance(v, int) else v})')
        elif w < 49:
            st.append(f'{rng.choice(["inverse", "over"])}({flag()})')
        elif w < 50:
            st.append(f'border({rng.randint(0, 7)})')
        elif w < 51:
            st.append('cls()')
        elif w < 55:
            st.append(f'attr({rng.randint(0, 23)}, {rng.randint(0, 31)}, {num(rng.randint(0, 255), byte=True)})')
        elif w < 57:
            for i in range(8):
                st.append(f'u[{i}] = {rng.randint(0, 255)}')
            st.append(f'udg({rng.randint(0, 20)}, u)')
        elif w < 77:
            items = []
            if rng.random() < .6:
                items.append(f'at {num(rng.randint(0, 21))}, {rng.randint(0, 31)}')
            for _ in range(rng.choice([0, 1, 1, 2, 3])):
                items.append(rng.choice([text(rng), text(rng), text(rng), str(rng.randint(-40000, 40000)),
                                         f'point({coord(rng, 255)}, {coord(rng, 175)})', 'ticks()', 'key()', 'k2',
                                         'b3']))
            seps = [rng.choice(['; ', ', ', '; ']) for _ in items]
            body = ''.join(it + sep for it, sep in zip(items, seps))
            # a trailing ; keeps the line open; a trailing , would too, but the lexer joins the next line onto it
            if rng.random() < .6:
                body = body.rstrip('; ,')
            elif body.endswith(', '):
                body = body[:-2] + '; '
            st.append(('print ' + body).rstrip())
        elif w < 83:
            st.append(f'beep({num(rng.choice([0, 1, 19, 20, 50, 100, 400, rng.randint(0, 2000)]))}, '
                      f'{rng.randint(-60, 69)})')
        elif w < 86:
            st.append(f'pause({num(rng.randint(0, 300))})')
        elif w < 90:
            st.append(f'print ticks(); " "; key(); " "; point({coord(rng, 255)}, {coord(rng, 175)})')
        elif w < 95:
            x, y, m = rng.randint(0, 200), rng.randint(0, 150), rng.randint(1, 50)
            st.append(f'for i in 0..{m} do plot({x} + i, {y} + i / 2) end')
        elif w < 100:
            st.append(f'for i in 0..{rng.randint(1, 30)} do print "row "; i; " "; ticks() end')
        else:                                                    # the memory: ROM, screen, UDGs, the rest, the seams
            lo, hi = rng.choice([(0, 0x3FFF), (0x4000, 0x57FF), (0x5800, 0x5AFF), (0x5B00, 0xFF57), (0xFF58, 0xFFFF)])
            a = rng.choice([lo, hi, rng.randint(lo, hi), rng.randint(lo, hi)])
            if rng.random() < .55:
                st.append(f'poke({num(a)}, {num(rng.randint(0, 255), byte=True)})')
            else:
                st.append(f'print peek({num(a)})')
    if rng.random() < .2:                                                    # end in a failure, sometimes mid-print
        call, _ = rng.choice(FAIL_CALLS)
        if rng.random() < .3:
            call = f'print at {rng.randint(0, 21)}, {rng.randint(0, 31)}; "half"; 1 / z'
        st += [call, 'plot(0, 0)']
    return prog('var u: byte[8]', 'var u7: byte[7]', 'var u8: byte[8]', 'var u9: byte[9]',
                *[f'var k{i}: int = 0' for i in range(4)], *[f'var b{i}: byte = 0' for i in range(4)], 'var z: int = 0',
                *st)


def main():
    seed = ARGS.seed
    nrand = 6 if ARGS.quick else ARGS.random
    rng = random.Random(seed)
    cases = [(n, s, None) for n, s in EDGES] + fails()
    cases += [(f'random{i:03d}', random_program(rng, rng.choice([50, 150, 300])), None) for i in range(nrand)]
    os.makedirs(BUILD, exist_ok=True)
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        results = list(pool.map(check, cases))
    failed = 0
    for (name, _, _), bad in zip(cases, results):
        if bad:
            failed += 1
            print(f'FAIL {name}  ({os.path.join(BUILD, name, "p.bly")})')
            for b in bad:
                print('     ' + b)
    print(f'{len(cases) - failed} of {len(cases)} agree with the reference '
          f'({len(EDGES)} edges, {len(FAIL_CALLS)} failures, {nrand} random from seed {seed}; C from {C_DIR})')
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
