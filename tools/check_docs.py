#!/usr/bin/env python3
"""Checks that the docs still say what the code does.

A code block in any Markdown file here whose first line is the first line
of a program in interp/tests or examples is a quotation of that program,
and must be the whole of it, exactly. (DESIGN.md quotes several; when a
program changes, copy it back in.)

Every command's -h works and fits in 80 columns, and an option it doesn't
have is refused, with exit status 2, rather than quietly ignored.

With --wrap MDWRAP, also checks that every Markdown file is wrapped as
mdwrap would wrap it: prose at 72 columns, for readers in a terminal.
"""
import argparse
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def markdown_files():
    out = subprocess.run(['git', 'ls-files', '*.md'], cwd=ROOT, capture_output=True, text=True)
    files = out.stdout.split() if out.returncode == 0 else []
    return files or sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, '**', '*.md'),
                                                                     recursive=True) if '/build/' not in p)


def quotations():
    """failures: blocks that start like a program and don't match it"""
    programs = {}
    for p in glob.glob(os.path.join(ROOT, 'interp', 'tests', '*.bly')) + glob.glob(os.path.join(ROOT, 'examples', '*.bly')):
        text = open(p).read()
        programs.setdefault(text.split('\n')[0], []).append((os.path.relpath(p, ROOT), text.rstrip('\n')))
    bad, seen = [], 0
    for md in markdown_files():
        for m in re.finditer(r'^```[^\n]*\n(.*?)^```', open(os.path.join(ROOT, md)).read(), re.S | re.M):
            block = m.group(1).rstrip('\n')
            first = block.split('\n')[0]
            if first not in programs:
                continue
            seen += 1
            if not any(text == block for _, text in programs[first]):
                names = ', '.join(name for name, _ in programs[first])
                bad.append(f'{md} quotes {names}, and the two differ')
    return seen, bad


# every command a person types, with enough arguments that an extra option is the only thing wrong
# (argparse checks them all before a file is opened); the second group needs omse-ai's Python
COMMANDS = {'bly': ['run', 'x.bly'], 'check': [], 'interp/barley.py': ['x.bly'], 'interp/tests/run.py': [],
            'c/cgen.py': ['x.bly'], 'c/tests/test_screen.py': [], 'c/tests/test_wrap.py': [], 'z80/z80gen.py': ['x.bly'],
            'z80/zxbuild.py': ['x.bly'], 'z80/fuzz.py': [], 'examples/make_sudoku.py': [],
            'examples/make_monkey.py': [], 'examples/make_towels.py': [],
            'examples/make_crt.py': [], 'examples/make_sand.py': [],
            'tools/check_docs.py': [], 'tools/gallery.py': []}
OMSE_COMMANDS = {'z80/zxrun.py': ['x.tap'], 'z80/zxbench.py': [], 'z80/zxsize.py': ['x.bly'],
                 'z80/zxprof.py': ['x.bly'], 'z80/tests/test_containers.py': [], 'z80/tests/test_fp.py': [],
                 'z80/tests/test_num.py': [], 'z80/tests/test_text.py': [], 'z80/tests/test_zxgfx.py': [],
                 'z80/tests/test_int.py': [], 'z80/tests/test_int_mutants.py': [],
                 'z80/tests/rom_text_check.py': [], 'z80/tests/rerun_check.py': [], 'z80/tests/co_temp_check.py': [], 'z80/tests/test_fpcpm.py': []}


def commands():
    """failures: a command whose -h doesn't work or is too wide, or that takes an option it hasn't got"""
    sys.path.insert(0, ROOT)
    import paths
    omse = os.path.isdir(paths.OMSE_AI)
    bad, seen = [], 0
    env = dict(os.environ, NO_COLOR='1', COLUMNS='80')
    for cmd, fine in list(COMMANDS.items()) + (list(OMSE_COMMANDS.items()) if omse else []):
        py = paths.OMSE_AI_PYTHON if cmd in OMSE_COMMANDS else sys.executable
        seen += 1
        h = subprocess.run([py, os.path.join(ROOT, cmd), '-h'], capture_output=True, text=True, env=env, cwd=ROOT,
                           timeout=120)
        if h.returncode != 0 or not h.stdout.startswith('usage:'):
            bad.append(f'{cmd} -h: exit {h.returncode}: {(h.stdout + h.stderr).strip()[-200:]}')
        wide = [line for line in h.stdout.split('\n') if len(line) > 80]
        if wide:
            bad.append(f'{cmd} -h: {len(wide)} lines over 80 columns, such as: {wide[0]}')
        x = subprocess.run([py, os.path.join(ROOT, cmd)] + fine + ['--no-such-option'], capture_output=True,
                           text=True, env=env, cwd=ROOT, timeout=120)
        if x.returncode != 2 or 'unrecognized arguments: --no-such-option' not in x.stderr:
            bad.append(f'{cmd} {" ".join(fine)} --no-such-option: exit {x.returncode}, not refused as unknown: '
                       f'{(x.stdout + x.stderr).strip()[-160:]}')
    return seen, omse, bad


def card():
    """the card (DESIGN.md section 4) against the language: every built-in function and every method the checker
    knows is on it, since the card is the whole language on one page. (The outside reading found nothing held it.)"""
    import inspect
    sys.path.insert(0, os.path.join(ROOT, 'interp'))
    import barley as B
    design = open(os.path.join(ROOT, 'DESIGN.md')).read()
    text = design.split('## 4. The whole language, on one page', 1)[1].split('```', 2)[1]
    words = set(re.findall(r'[A-Za-z_][A-Za-z_0-9]*', text))
    dotted = set(re.findall(r'\.([A-Za-z_][A-Za-z_0-9]*)', text))
    funcs = set(B.BUILTIN_FUNCS) | set(B.SCREEN_FUNCS) | set(B.MACHINE_FUNCS) | set(B.FLOAT_FUNCS)
    methods = set(re.findall(r"'([a-z_]+)': \(", inspect.getsource(B.Checker.method_sig)))
    named = funcs | set(B.INTS) | {'float', 'bool', 'bit', 'str', 'pos'}   # a method named like these is on the card
    bad = [f'the card leaves out the function {n}' for n in sorted(funcs) if n not in words] + \
          [f'the card leaves out the method {n}' for n in sorted(methods)    # after a dot: float(i) isn't s.float()
           if n not in (dotted if n in named else words)]
    return len(funcs) + len(methods), bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--wrap', metavar='MDWRAP', help='check the wrapping too, with this mdwrap')
    a = ap.parse_args(argv)
    seen, bad = quotations()
    for b in bad:
        print('FAIL: ' + b)
    print(f'{seen} quoted programs, {len(bad)} out of date')
    if not a.wrap:
        n, omse, cbad = commands()
        for b in cbad:
            print('FAIL: ' + b)
        print(f'{n} commands\' -h' + ('' if omse else ' (not the omse-ai ones: no omse-ai here)') +
              f', {len(cbad)} wrong')
        bad += cbad
        n, kbad = card()
        for b in kbad:
            print('FAIL: ' + b)
        print(f'the card: {n} functions and methods, {len(kbad)} left out')
        bad += kbad
    if a.wrap:
        files = markdown_files()
        r = subprocess.run([a.wrap, '--check'] + files, cwd=ROOT, capture_output=True, text=True)
        for f in r.stdout.split():
            print(f'FAIL: {f} is not wrapped (run: mdwrap -i {f})')
        if r.returncode not in (0, 1):
            print('FAIL: mdwrap: ' + r.stderr.strip())
        print(f'{len(files)} Markdown files, {len(r.stdout.split())} not wrapped')
        bad += r.stdout.split() or ([] if r.returncode in (0, 1) else ['mdwrap'])
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
