#!/usr/bin/env python3
"""Build a Barley program into a Spectrum tape: a BASIC loader, the input, the
code. Code lives high.

The loader is line 10: CLEAR 32767: LOAD "" CODE: LOAD "" CODE: CLS:
RANDOMIZE USR start. The CLS takes the loader's own words away, so a program
starts on a clear screen, as it does in the interpreter and in C. A second
line, numbered with the year the tape was made, has as many statements as
the month's number (colons, which are empty statements, or a REM in
January), so a program that ends well leaves BASIC saying 0 OK, 2026:10
(Melissa's idea); a failure stops at line 10. SOURCE_DATE_EPOCH, if it's
set, says when the tape was made, for a build that comes out the same. The first
CODE block is the input at 8000h (a length word, then the
text, so a missing input is just a zero), the second is the program, assembled
twice so it sits flush under the UDGs at FF58h, with its slots just beneath
it.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
import z80gen                                          # noqa: E402
import paths                                           # noqa: E402

SJASM = paths.SJASMPLUS
TOP = 0xFF58                                           # the UDGs start here, and stay
FRAMES_TOP = 0xFDFD                                    # with a frame: its vector's jump, then its table to FF00h
INPUT = 0x8000
STACKROOM = 1024
ARENA_MIN = 512                                        # the least arena worth running with
LOWEST = 0x6000                                        # BASIC's loader and stack live below this


def assemble(src):
    with tempfile.TemporaryDirectory() as d:
        a, b, s = (os.path.join(d, n) for n in ('p.asm', 'p.bin', 'p.sym'))
        open(a, 'w').write(src)
        p = subprocess.run([paths.need(SJASM, 'sjasmplus', 'set SJASMPLUS (paths.py)'), '--nologo', f'--raw={b}', f'--sym={s}', a], capture_output=True, text=True)
        if p.returncode:
            raise SystemExit('sjasmplus: ' + '\n'.join(l for l in (p.stdout + p.stderr).splitlines() if 'rror' in l))
        sym = {}
        for line in open(s):
            m = re.match(r'(\S+):\s+EQU\s+0x([0-9A-Fa-f]+)', line)
            if m:
                sym[m.group(1)] = int(m.group(2), 16)
        return open(b, 'rb').read(), sym


def block(flag, data):
    body = bytes([flag]) + data
    x = 0
    for c in body:
        x ^= c
    body += bytes([x])
    return len(body).to_bytes(2, 'little') + body


def header(kind, name, length, p1, p2):
    return block(0, bytes([kind]) + name.ljust(10)[:10].encode() + length.to_bytes(2, 'little') +
                 p1.to_bytes(2, 'little') + p2.to_bytes(2, 'little'))


def number(n):
    """a BASIC number: its digits, then 0Eh and the five-byte small-integer form"""
    return str(n).encode() + bytes([0x0E, 0, 0, n & 0xFF, n >> 8, 0])


def made():
    """the year and month the tape is made: SOURCE_DATE_EPOCH's (UTC) if it's set, or today's"""
    t = os.environ.get('SOURCE_DATE_EPOCH')
    d = datetime.datetime.fromtimestamp(int(t), datetime.timezone.utc) if t else datetime.datetime.now()
    return d.year, d.month


def loader(start, input_at=INPUT, when=None):
    """line 10 loads and starts the program; line YEAR's last statement is the month's, for BASIC's 0 OK report"""
    CLEAR, LOAD, CODE, CLS, RANDOMIZE, USR, REM = 0xFD, 0xEF, 0xAF, 0xFB, 0xF9, 0xC0, 0xEA
    line = (bytes([CLEAR]) + number(input_at - 1) + b':' + bytes([LOAD]) + b'""' + bytes([CODE]) + b':' +
            bytes([LOAD]) + b'""' + bytes([CODE]) + b':' + bytes([CLS]) + b':' +       # the loader's words away:
            bytes([RANDOMIZE, USR]) + number(start) + b'\r')                      # the program starts on a clear screen
    year, month = when or made()
    date = (b':' * (month - 1) if month > 1 else bytes([REM])) + b'\r'          # a line can't be empty: January's REM
    return (10).to_bytes(2, 'big') + len(line).to_bytes(2, 'little') + line + \
        year.to_bytes(2, 'big') + len(date).to_bytes(2, 'little') + date


def build(src, text=b'', markers=True):
    asm1 = z80gen.compile_program(src, 'zx48', org=0x8000, bss_at=0, markers=markers) + '\nbly_input_at equ 8000h\n'
    code1, sym1 = assemble(asm1)
    size = sym1['bly_code_end'] - 0x8000
    bss = sym1['bly_bss_end'] - sym1['bly_bss']
    org = (FRAMES_TOP if 'zxr_isr' in sym1 else TOP) - size     # frame do ... end's table and vector: zxframes.asm
    bss_at = org - bss
    # the input goes at 8000h when it fits up there; otherwise lower, into contended RAM, which a text read once in
    # order minds least (DESIGN.md section 6). The arena keeps at least ARENA_MIN between it and the stack.
    input_at = INPUT
    need = ARENA_MIN + 4 * (text.count(b'\n') + 1)       # and the line table: a str (4 bytes) for every input line
    if input_at + 2 + len(text) > bss_at - STACKROOM - need:
        input_at = bss_at - STACKROOM - need - 2 - len(text)
    if input_at < LOWEST:
        raise SystemExit(f'too big for a 48K: code {size}, slots {bss}, input {len(text)}, stack {STACKROOM}')
    code, sym = assemble(z80gen.compile_program(src, 'zx48', org=org, bss_at=bss_at, markers=markers) +
                         f'\nbly_input_at equ {input_at}\n')
    size2 = sym['bly_code_end'] - org
    if size2 != size:                                  # a fragment whose size depends on where it lands (an align, say)
        raise SystemExit(f'the code is {size} bytes at 8000h but {size2} at {org:04X}h: the two passes must agree')
    code = code[:size]
    prog = loader(org, input_at)
    tap = header(0, 'barley', len(prog), 10, len(prog)) + block(0xFF, prog)
    inp = len(text).to_bytes(2, 'little') + text
    tap += header(3, 'input', len(inp), input_at, 32768) + block(0xFF, inp)
    tap += header(3, 'program', len(code), org, 32768) + block(0xFF, code)
    return tap, {'org': org, 'code': size, 'slots': bss, 'arena': bss_at - STACKROOM - (input_at + 2 + len(text)),
                 'input_at': input_at, 'sym': sym}


def main(argv):
    ap = argparse.ArgumentParser(prog='zxbuild.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('program', metavar='PROGRAM.bly', help='the program')
    ap.add_argument('input', metavar='INPUT', nargs='?', help='its input, as a block on the tape')
    ap.add_argument('-o', dest='out', metavar='OUT.tap', help='the tape (default: PROGRAM.tap beside the program)')
    ap.add_argument('--plain', action='store_true',
                    help='without the transcript markers around text printed at a place: for a real Spectrum, '
                         'which needs no transcript (faster: about 1,900 T-states a piece)')
    a = ap.parse_args(argv)
    try:
        src = open(a.program).read()
        text = open(a.input, 'rb').read() if a.input else b''
        z80gen.B.EMBED_DIR = os.path.dirname(os.path.abspath(a.program))     # embed's files are beside it
    except OSError as err:
        sys.exit(f'zxbuild.py: {err.filename}: {err.strerror}')
    try:
        tap, info = build(src, text, markers=not a.plain)
    except z80gen.B.BarleyError as err:
        print(err)                                     # the checker's words, as the interpreter prints them
        sys.exit(1)
    except (z80gen.GenError, ValueError) as err:
        print(f'Z80: {err}')
        sys.exit(2)
    open(a.out or os.path.splitext(a.program)[0] + '.tap', 'wb').write(tap)
    print(f"code {info['code']} bytes at {info['org']:04X}h, slots {info['slots']} bytes, input at {info['input_at']:04X}h, "
          f"arena {info['arena']} bytes free")

if __name__ == '__main__':
    main(sys.argv[1:])
