"""Run every test: each program on its input, against the output it must print exactly.
usage: python3 run.py   (from anywhere)"""
import os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import paths                                  # noqa: E402
RUN_ID = str(os.getpid())                     # each run builds in its own place, so two runs at once can't collide
BARLEY = os.path.join(HERE, '..', 'barley.py')
CASES = [  # program, input, expected output: our own inputs, answers from make_inputs.py's referees, not from Barley
    ('aoc2022d01.bly', 'aoc2022d01.in', 'Part 1: 31088\nPart 2: 74367\n'),
    ('aoc2022d12.bly', 'aoc2022d12.in', 'Part 1: 85\nPart 2: 80\n'),
    ('aoc2023d08.bly', 'aoc2023d08a.in', 'Part 1: 8\nPart 2: 120\n'),
    ('aoc2023d08p2.bly', 'aoc2023d08b.in', 'Part 2: 126\n'),
    ('aoc2021d15.bly', 'aoc2021d15.in', 'Part 1: 77\n'),
    ('aoc2023d06.bly', 'aoc2023d06.in', 'Part 2: 196435\n'),
]
EXTRA = os.path.join(HERE, 'semantics.txt')


BACKEND = 'c' if '--c' in sys.argv else ('z80' if '--z80' in sys.argv else ('zx' if '--zx' in sys.argv else 'interp'))
ZXBUILD = os.path.join(HERE, '..', '..', 'z80', 'zxbuild.py')
ZXRUN = os.path.join(HERE, '..', '..', 'z80', 'zxrun.py')
OMSEPY = paths.OMSE_AI_PYTHON


def run_zx(prog, args_in):
    """build a tape, load it on omse-ai's 48K, and take what the program printed"""
    os.makedirs(ZBUILD, exist_ok=True)
    tap = os.path.join(ZBUILD, 'zx.tap')
    b = subprocess.run([sys.executable, '-I', ZXBUILD, os.path.join(HERE, prog)] + args_in + ['-o', tap],
                       capture_output=True, text=True, encoding='latin-1')
    if b.returncode:
        err = (b.stdout + b.stderr).strip().splitlines()
        last = err[-1] if err else ''
        if 'floats are not on the Z80' in last:
            return 'NOTHERE: floats are not in the Z80 version 1'
        if 'nothing provides' in last:
            return 'PENDING: ' + last.replace('Z80: ', '')
        if b.returncode == 1:
            return b.stdout                                   # the checker's words
        return 'BUILD: ' + last
    try:
        r = subprocess.run([OMSEPY, ZXRUN, tap], capture_output=True, text=True, encoding='latin-1', timeout=600)
    except subprocess.TimeoutExpired:
        return 'TIMEOUT'
    return r.stdout + (('\nSTDERR: ' + r.stderr[-500:]) if r.returncode else '')
Z80GEN = os.path.join(HERE, '..', '..', 'z80', 'z80gen.py')
SJASM = paths.SJASMPLUS
TNYLPO = paths.TNYLPO
ZBUILD = os.path.join(paths.BUILD, 'zbuild', RUN_ID)


def run_z80(prog, args_in):
    """generate, assemble, and run the .COM under tnylpo; a library part nobody has written yet is PENDING"""
    os.makedirs(ZBUILD, exist_ok=True)
    stem = 'p' + str(abs(hash(prog)) % 10**6)
    gen = subprocess.run([sys.executable, '-I', Z80GEN, os.path.join(HERE, prog)], capture_output=True, text=True, encoding='latin-1')
    if gen.returncode == 1:
        return gen.stdout                              # the checker's words, as the interpreter's
    if gen.returncode:
        err = (gen.stdout + gen.stderr).strip().splitlines()[-1]
        if 'nothing provides' in err:
            return 'PENDING: ' + err.replace('Z80: ', '')
        if 'floats are not on the Z80' in err:
            return 'NOTHERE: floats are not in the Z80 version 1'
        if 'Spectrum-only' in err:
            return 'NOTHERE: the screen and sound are Spectrum-only'
        return 'GENERATOR: ' + err
    open(os.path.join(ZBUILD, stem + '.asm'), 'w').write(gen.stdout)
    a = subprocess.run([SJASM, '--nologo', f'--raw={os.path.join(ZBUILD, stem + ".com")}', os.path.join(ZBUILD, stem + '.asm')],
                       capture_output=True, text=True, encoding='latin-1')
    if a.returncode:
        return 'ASSEMBLER: ' + '\n'.join(l for l in a.stdout.splitlines() if 'error' in l.lower())[:2000]
    conf = os.path.join(ZBUILD, 'tn.conf')
    open(conf, 'w').write(f'drive a = "{ZBUILD}"\ndefault drive = a\n')
    cpm_args = []
    if args_in:
        import shutil
        shutil.copy(args_in[0], os.path.join(ZBUILD, 'input.txt'))
        cpm_args = ['input.txt']
    try:
        r = subprocess.run([TNYLPO, '-f', conf, stem] + cpm_args, capture_output=True, text=True, encoding='latin-1',
                           stdin=subprocess.DEVNULL, timeout=120)
    except subprocess.TimeoutExpired:
        return 'TIMEOUT: ran for two minutes (a loop that never ends?)'
    return r.stdout + (('\nSTDERR: ' + r.stderr) if r.stderr.strip() else '')
CGEN = os.path.join(HERE, '..', '..', 'c', 'cgen.py')
RT = os.path.join(HERE, '..', '..', 'c', 'rt')
BUILD = os.path.join(paths.BUILD, 'cbuild', RUN_ID)
CC = [paths.CC, '-std=c11', '-g', '-O1', '-Wall', '-Wno-unused-function', '-Wno-unused-variable',
      '-fsanitize=undefined,address', '-fno-sanitize-recover=all', '-I', RT]


SCREEN = {}                                            # the last run's screen, when a test asks for one


def upper(i):
    """the 22 upper rows of a 6,912-byte screen: what a Spectrum leaves alone when BASIC reports at the end"""
    if i >= 6144:
        return (i - 6144) // 32 < 22
    return (i >> 11) < 2 or ((i >> 5) & 7) < 6


def screen_of(prog, inp, backend):
    """the .scr a backend leaves, or None"""
    os.makedirs(ZBUILD, exist_ok=True)
    scr = os.path.join(ZBUILD, f'screen-{backend}.scr')
    if os.path.exists(scr):
        os.remove(scr)
    args_in = [os.path.join(HERE, inp)] if inp else []
    if backend == 'interp':
        subprocess.run([sys.executable, '-I', BARLEY, '--screen', scr.replace('.scr', '.png'),
                        os.path.join(HERE, prog)] + args_in, capture_output=True)
    elif backend == 'c':
        base = os.path.join(BUILD, os.path.splitext(prog)[0])
        subprocess.run([base] + args_in, capture_output=True, env=dict(os.environ, BARLEY_SCREEN=scr))
    elif backend == 'zx':
        subprocess.run([OMSEPY, ZXRUN, os.path.join(ZBUILD, 'zx.tap'), '--scr', scr], capture_output=True)
    return open(scr, 'rb').read() if os.path.exists(scr) else None


def run(prog, inp):
    """the program's output: from the interpreter, or (with --c) from its C, built with the sanitizers on"""
    args_in = [os.path.join(HERE, inp)] if inp else []
    if BACKEND == 'z80':
        return run_z80(prog, args_in)
    if BACKEND == 'zx':
        return run_zx(prog, args_in)
    if BACKEND == 'interp':
        args = [sys.executable, '-I', BARLEY, os.path.join(HERE, prog)] + args_in
        return subprocess.run(args, capture_output=True, text=True, encoding='latin-1').stdout
    os.makedirs(BUILD, exist_ok=True)
    base = os.path.join(BUILD, os.path.splitext(prog)[0])
    gen = subprocess.run([sys.executable, '-I', CGEN, os.path.join(HERE, prog)], capture_output=True, text=True, encoding='latin-1')
    if gen.returncode:                         # the checker said no: the same words the interpreter prints
        return gen.stdout + gen.stderr
    open(base + '.c', 'w').write(gen.stdout)
    cc = subprocess.run(CC + [base + '.c', '-lm', '-o', base], capture_output=True, text=True, encoding='latin-1')
    if cc.returncode or cc.stderr.strip():
        return 'C COMPILER: ' + cc.stderr
    r = subprocess.run([base] + args_in, capture_output=True, text=True, encoding='latin-1')
    return r.stdout + (('\nSTDERR: ' + r.stderr) if r.stderr.strip() else '')


def semantics():
    """semantics.txt: programs separated by '=== name', each followed by '--- expect' and its exact output"""
    if not os.path.exists(EXTRA):
        return []
    out, cases = [], open(EXTRA).read().split('\n=== ')[1:]
    for c in cases:
        name, rest = c.split('\n', 1)
        prog, expect = rest.split('\n--- expect\n')
        wants_screen = '\n--- screen' in prog
        prog = prog.replace('\n--- screen', '')
        inp = None
        if '\n--- input\n' in prog:
            prog, text = prog.split('\n--- input\n')
            open(os.path.join(HERE, f'_case{RUN_ID}.in'), 'w').write(text + '\n')
            inp = f'_case{RUN_ID}.in'
        open(os.path.join(HERE, f'_case{RUN_ID}.bly'), 'w').write(prog)
        got = run(f'_case{RUN_ID}.bly', inp)
        if wants_screen and BACKEND in ('c', 'zx') and not got.startswith(('PENDING', 'NOTHERE')) and got == expect:
            want_scr = screen_of(f'_case{RUN_ID}.bly', inp, 'interp')
            got_scr = screen_of(f'_case{RUN_ID}.bly', inp, BACKEND)
            if got_scr is None:
                got += '\nSCREEN: none was written'
            else:
                keep = range(6912) if BACKEND == 'c' else [i for i in range(6912) if upper(i)]
                diff = [i for i in keep if got_scr[i] != want_scr[i]]
                if diff:
                    got += f'\nSCREEN: {len(diff)} bytes differ from the interpreter, first at {0x4000 + diff[0]:04X}h'
        out.append((name, got, expect))
    return out


NUM = re.compile(r'[-+]?(?:[0-9]+[.]?[0-9]*|[.][0-9]+)(?:[eE][-+]?[0-9]+)?')


def floats_agree(got, want, rel=1e-7):
    """The Spectrum prints a float as its ROM's PRINT-FP does (8 digits; 0.5, .0001, 1E+10), not as the
    interpreter's %.10g (DESIGN.md: floats are the one place the backends may print differently). So a number with
    a point or an exponent on either side may differ by 1e-7 of itself, and in its spelling; every other character,
    and every whole number, must be exactly the interpreter's. 1e-7 covers PRINT-FP's 8 digits (5e-8) and the
    ROM's own arithmetic (about 1e-9 an operation: z80/lib/NOTES.md, floats)."""
    if NUM.split(got) != NUM.split(want):
        return False
    for g, w in zip(NUM.findall(got), NUM.findall(want)):
        if g == w:
            continue
        if not any(c in g + w for c in '.eE'):
            return False
        a, b = float(g), float(w)
        if abs(a - b) > rel * max(abs(a), abs(b)):
            return False
    return True


def main():
    fails = 0
    results = [(p, run(p, i), want) for p, i, want in CASES] + semantics()
    pending = 0
    for name, got, want in results:
        ok = got == want
        if got.startswith('PENDING') or got.startswith('NOTHERE'):
            pending += 1
            print(f'{"wait" if got.startswith("PENDING") else "n/a "} {name}: {got[9:]}')
            continue
        near = not ok and BACKEND == 'zx' and floats_agree(got, want)
        ok = ok or near
        fails += not ok
        print(f'{"ok~ " if near else "ok  " if ok else "FAIL"} {name}' + ('   (floats as the ROM prints them)' if near else ''))
        if not ok:
            print('     got:', repr(got))
            print('    want:', repr(want))
    print(f'{len(results) - fails - pending} of {len(results)} passed ({BACKEND})' + (f', {pending} waiting for library parts or not on this target' if pending else ''))
    for leftover in (f'_case{RUN_ID}.bly', f'_case{RUN_ID}.in'):
        if os.path.exists(os.path.join(HERE, leftover)):
            os.remove(os.path.join(HERE, leftover))
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
