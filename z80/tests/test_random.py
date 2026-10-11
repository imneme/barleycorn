"""random.asm against its meaning, barley.py's rng_ functions (Melissa's generator; DESIGN.md, "Random numbers").

Each call starts the generator from a state of the test's choosing (its BCDE and HL, poked in), and is compared on
what it gives back and on the state it leaves, which says it drew exactly the words the meaning draws:
  - bly_rand16, 64 steps at a time from states anywhere in the 2^32;
  - bly_random_u16 and _i16 for n at every edge of the mask (1, 2, powers of two and one either side, 65535) and
    at random, and their failures, word for word;
  - bly_random_q for n at the edges of one, two and four words a try (2^16, 2^32, 2^63 - 1, one either side),
    and at random, and its failures;
  - bly_randomize_q for seeds anywhere in the 64 bits, negative ones too.
--mutants breaks random.asm on purpose (a copy of the library) and checks these tests notice.

Run it with omse-ai's Python ($OMSE_AI_PYTHON).
"""
import argparse
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'interp'))
sys.path.insert(0, os.path.join(HERE, '..', '..'))
import paths                                  # noqa: E402
import harness                                # noqa: E402
import link                                   # noqa: E402
from harness import Runner                     # noqa: E402
import barley as B                             # noqa: E402

ap = argparse.ArgumentParser(prog='test_random.py', description=__doc__,
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--seed', type=int, default=1, help='the random cases\' seed (default 1)')
ap.add_argument('--quick', action='store_true', help='fewer random cases')
ap.add_argument('--lib', metavar='DIR', help='a mutated copy of the library to test instead')
ap.add_argument('--mutants', action='store_true', help='break random.asm on purpose, and check these tests notice')
ARGS = ap.parse_args()
if ARGS.lib:
    _lib = ARGS.lib
    harness.gather = lambda symbols, target: link.gather(symbols, target, lib=_lib)

OUT, N = 0xE000, 0xE100
EXTRA = r'''
tst_rands:                      ; HL = how many, DE = where: bly_rand16 that many times, the words in a row
        push hl
        push de
        call bly_rand16
        pop de
        ex de,hl
        ld (hl),e
        inc hl
        ld (hl),d
        inc hl
        ex de,hl
        pop hl
        dec hl
        ld a,h
        or l
        jr nz,tst_rands
        ret
'''
R = Runner(['bly_rand16', 'bly_random_u16', 'bly_random_i16', 'bly_random_q', 'bly_randomize_q'], EXTRA)
bad = checks = 0


def wrong(what):
    global bad
    bad += 1
    if bad <= 20:
        print('WRONG', what)


def state_of(res):
    s = res.sym
    w = lambda name, k=0: int.from_bytes(res.mem[s[name] + k:s[name] + k + 2], 'little')
    return [w('bly_rand16.s') | w('bly_rand16.s', 2) << 16, w('bly_rand16.h')]


def run(routine, st, **kw):
    sets = {'bly_rand16.s': st[0] & 0xFFFF, 'bly_rand16.s+2': st[0] >> 16, 'bly_rand16.h': st[1]}
    code, sym = R.build(routine)
    sym.setdefault('bly_rand16.s+2', sym['bly_rand16.s'] + 2)
    return R.call(routine, set16=sets, **kw)


def failure(n):
    """the interpreter's words for random(n) when n is 0 or less (the harness has no line, so no " at line")"""
    return f'random({n}) has nothing to choose from\n'.encode()


def check(what, res, st, want, got_value):
    global checks
    checks += 1
    after = state_of(res)
    if res.failed or got_value != want or after != st:
        wrong(f'{what}: gave {got_value}, state {after[0]:08X} {after[1]:04X}; wanted {want}, state '
              f'{st[0]:08X} {st[1]:04X}' + (f' (failed: {res.out!r})' if res.failed else ''))


def test_rand16(rng, reps):
    for _ in range(reps):
        st = [rng.randrange(1 << 32), rng.randrange(1 << 16)]
        res = run('tst_rands', st, regs={'hl': 64, 'de': OUT})
        model = list(st)
        want = [B.rng_word(model) for _ in range(64)]
        got = [int.from_bytes(res.mem[OUT + 2 * i:OUT + 2 * i + 2], 'little') for i in range(64)]
        check(f'64 steps from {st[0]:08X} {st[1]:04X}', res, model, want, got)


def test_u16(rng, reps):
    ns = sorted({1, 2, 3, 65535, 65534, 32767, 32768, 32769} | {p + d for p in (1 << k for k in range(1, 16))
                                                                for d in (-1, 0, 1)})
    ns += [rng.randrange(1, 65536) for _ in range(reps)]
    for n in ns:
        for routine in ('bly_random_u16',) + (('bly_random_i16',) if n < 32768 else ()):
            st = [rng.randrange(1 << 32), rng.randrange(1 << 16)]
            res = run(routine, st, regs={'hl': n})
            model = list(st)
            want = B.rng_below(model, n)
            check(f'{routine}({n})', res, model, want, res.regs['hl'])
    for routine, n in (('bly_random_u16', 0), ('bly_random_i16', 0), ('bly_random_i16', -1), ('bly_random_i16', -32768),
                       ('bly_random_i16', -300)):
        res = R.call(routine, regs={'hl': n & 0xFFFF})
        global checks
        checks += 1
        if not res.failed or res.out != failure(n):
            wrong(f'{routine}({n}): {res.out!r}, wanted {failure(n)!r}')


def test_q(rng, reps):
    edges = [1, 2, 3, 255, 256, 257] + [p + d for p in (1 << 16, 1 << 32, 1 << 48) for d in (-1, 0, 1)] + \
        [(1 << 63) - 1, (1 << 63) - 2, 1 << 62, (1 << 62) + 1]
    ns = edges + [rng.randrange(1, 1 << rng.choice((8, 16, 24, 32, 40, 48, 56, 63))) for _ in range(reps)]
    for n in ns:
        st = [rng.randrange(1 << 32), rng.randrange(1 << 16)]
        res = run('bly_random_q', st, regs={'hl': N, 'bc': N + 8}, mem={N: (n & (1 << 64) - 1).to_bytes(8, 'little')})
        model = list(st)
        want = B.rng_below(model, n)
        check(f'bly_random_q({n})', res, model, want, int.from_bytes(res.mem[N + 8:N + 16], 'little'))
    for n in (0, -1, -(1 << 63), -12345678901):
        res = R.call('bly_random_q', regs={'hl': N, 'bc': N + 8}, mem={N: (n & (1 << 64) - 1).to_bytes(8, 'little')})
        global checks
        checks += 1
        if not res.failed or res.out != failure(n):
            wrong(f'bly_random_q({n}): {res.out!r}, wanted {failure(n)!r}')


def test_randomize(rng, reps):
    seeds = [0, 1, -1, (1 << 36) - 1, 1 << 36, (1 << 63) - 1, -(1 << 63), 0xABCDEF012] + \
        [rng.randrange(-(1 << 63), 1 << 63) for _ in range(reps)]
    for n in seeds:
        res = run('bly_randomize_q', [rng.randrange(1 << 32), rng.randrange(1 << 16)], regs={'hl': N},
                  mem={N: (n & (1 << 64) - 1).to_bytes(8, 'little')})
        check(f'randomize({n})', res, B.rng_seed(n), None, None)


MUTANTS = [
    ('random.asm', '        rrca                        ; B = rrca(E) - B\n        sub b',
     '        rlca                        ; B = rrca(E) - B\n        sub b', 'the last swizzle turns left'),
    ('random.asm', '        sub b\n        ld b,a', '        add a,b\n        ld b,a', 'the last swizzle adds'),
    ('random.asm', '        ld a,l\n        xor h\n        ld l,a', '        ld a,h\n        xor l\n        ld h,a',
     'H gets the xor, not L'),
    ('random.asm', '.more:  scf', '.more:  or a', 'the mask never grows'),
    ('random.asm', '        sbc hl,de                   ; m - it', '        add hl,de                   ; m - it',
     'a draw past m is kept'),
    ('random.asm', '        ld c,2\n        cp 5', '        ld c,2\n        cp 7', 'two words up to six bytes'),
    ('random.asm', '        ld c,1                      ; how many', '        ld c,2                      ; how many',
     'two words for a small n'),
    ('random.asm', '        dec a\n        add a,a', '        nop\n        add a,a', 'the first word at the bottom'),
    ('random.asm', '        jr c,.try', '        nop\n        nop', 'a quad past m is kept'),
    ('random.asm', '        or 30h', '        or 20h', 'the seed outside the run'),
    ('random.asm', '        ld (bly_rand16.h),de', '        ld (bly_rand16.s),de', 'the seed\'s low 16 in the wrong place'),
    ('random.asm', '        bit 7,h\n        jr z,bly_random_u16', '        bit 6,h\n        jr z,bly_random_u16',
     'a negative int let through'),
    ('random.asm', '.zero:  db "random(0) has', '.zero:  db "random(O) has', 'the message misspelt'),
    ('random.asm', "; Melissa's chaotic generator", "; Melissa's own chaotic generator", 'CONTROL: a comment'),
]


def mutants():
    import shutil, subprocess, tempfile
    lib = os.path.join(HERE, '..', 'lib')
    missed = 0
    for f, old, new_, why in MUTANTS:
        with tempfile.TemporaryDirectory(dir=paths.build_dir('random-tests')) as d:
            for name in os.listdir(lib):
                if name.endswith('.asm'):
                    shutil.copy(os.path.join(lib, name), d)
            text = open(os.path.join(d, f)).read()
            assert text.count(old) == 1, (f, old, text.count(old))
            open(os.path.join(d, f), 'w').write(text.replace(old, new_))
            p = subprocess.run([sys.executable, __file__, '--quick', '--lib', d], capture_output=True, text=True)
            if 'sjasmplus' in p.stderr:
                print('BAD MUTANT (it does not assemble):', why)
                missed += 1
                continue
            caught = p.returncode != 0
            control = why.startswith('CONTROL')
            ok = caught != control
            missed += not ok
            first = next((l for l in p.stdout.splitlines() if l.startswith(('WRONG', 'random'))), p.stderr[-200:])
            print(f'{"ok  " if ok else "MISS"} {why:38} {first[:100]}')
    print('mutants:', 'every one caught' if not missed else f'{missed} not caught')
    return missed


def main():
    if ARGS.mutants:
        return mutants()
    rng = random.Random(ARGS.seed)
    reps = 20 if ARGS.quick else 200
    test_rand16(rng, reps // 4)
    test_u16(rng, reps)
    test_q(rng, reps)
    test_randomize(rng, reps)
    print('random:', 'all right' if not bad else f'{bad} wrong', f'({checks} checks, seed {ARGS.seed})')
    return bad


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
