# Hacking on Barleycorn

## The one rule

**The interpreter is the specification, and the three implementations agree.** `interp/barley.py` says what every
program means: its output, and the exact words and line of every failure. The C backend and the Z80 backend (on a 48K
Spectrum and under CP/M) must print exactly what it prints. So a change in meaning starts in the interpreter, with a
test, and then goes to each backend. A backend that disagrees is wrong, unless the interpreter is, and then the
interpreter is fixed first and the test pins it. That has happened: the fuzzer's first finds were in the
interpreter (the order an assignment evaluates its parts).

Floats are the one place they may differ: the Spectrum's are the ROM's own (DESIGN.md, section 5). The suite compares
printed floats to within the ROM's precision, and every other character exactly.

## The layout

```
bly            the front door: run, or compile and run, a program on any target
check          every test, in order; skips (and says so) what your machine lacks
paths.py       where the outside tools are: the environment, paths.local, or PATH
interp/
  barley.py    lexer, parser, type checker and interpreter: the specification, in one file
  tests/       run.py (the suite, on any backend: --c, --z80 for CP/M, --zx for the 48K),
               semantics.txt (small programs and their exact output), six Advent of Code programs and the inputs
               make_inputs.py makes for them
c/
  cgen.py      checked program -> plain C          rt/   barley.h and one template per container kind
  tests/       test_screen.py: the C screen against the reference, pixel for pixel
z80/
  z80gen.py    checked program -> Z80 assembly      peephole.py   the register cache and dead stores
  link.py      gathers library fragments by their headers
  lib/         the library: one .asm fragment per area, each with a header; NOTES.md, its design and costs
  ABI.md       the contract between the generated code and the library: registers, layouts, every message
  zxbuild.py   a 48K tape: two assembly passes (code flush under the UDGs), a BASIC loader, the input as a block
  zxrun.py     runs a tape on omse-ai and prints what it printed
  zxgfx.py     the Spectrum's screen and sound as a model: the reference the interpreter and C draw with
  harness.py   runs library fragments on a bare Z80 (bare.py), for their tests
  tests/       each fragment against its Python model, some with deliberate mutants
  bench/       the first Barley's thirteen benchmark programs, and baseline.json (their T-states)
  zxbench.py   exact T-states on the 48K, against the baseline   zxprof.py   where the time goes
  zxsize.py    where the bytes go                                  fuzz.py     random programs, the interpreter as oracle
examples/      programs to read and run
```

## How a program goes through

All three share one front end: `interp/barley.py`'s `Parser` and `Checker`. The checker types every expression,
because integer widths decide where arithmetic wraps (unsigned) or traps (signed).

- **The interpreter** walks the tree. Every check happens here, always. The screen and sound draw into a model of
  the Spectrum's memory (`z80/zxgfx.py`), which can be saved as a `.scr` and a PNG.
- **C** (`c/cgen.py`): one C function per function, every subexpression in its own temporary in the interpreter's
  order, and every operation a call into `rt/barley.h`, which checks it in the same words. No undefined behaviour
  from our side: the tests build with UBSan and ASan, and any warning fails.
- **Z80** (`z80/z80gen.py`): every variable, parameter and temporary lives at a fixed address in its function's
  frame; 8- and 16-bit arithmetic is inline, anything wider is a call into the library. `peephole.py` then cleans up
  each function. `link.py` gathers the library fragments the program uses, and sjasmplus assembles the lot once.
  `zxbuild.py` makes a tape, and for CP/M the assembly is a `.COM`.

## Tests

`./check` runs them all; `./check --quick` the fast ones; `./check interp c` just those stages.

- **The suite** (`interp/tests/run.py`): `semantics.txt` and the Advent of Code programs, on any backend. A test in
  `semantics.txt` is
  ```
  === what it pins down
  func main()
    ...
  end
  --- input           (optional: the text lines() and grid() read)
  ...
  --- screen          (optional: the final screen must match the interpreter's too, pixel for pixel)
  --- as cpm          (optional: a test of CP/M's rules, run by the interpreter --as cpm and the CP/M backend)
  --- expect
  the exact output
  ```
  A failure's message is part of the output (`index 9 is outside 0..8 at line 4`), so tests pin failures too.
- **The fragments** (`z80/tests/test_*.py`, with omse-ai's Python): each library area on a bare Z80 against a Python
  model of what it should do, usually the interpreter's own code, over random and edge cases. `test_int_mutants.py`
  and `test_fp_mutants.py` break the library on purpose and check the tests notice.
- **The fuzzer** (`z80/fuzz.py N`): random, well-typed programs over the integer core (every width, comparisons,
  `and`/`or`/`not`, casts, constants, loops whose bounds change, functions that change globals, self-calls that shuffle
  their own arguments), run in the interpreter, as C and as CP/M programs. Any disagreement is kept in
  `build/fuzz-failures/`.
- **One program, every backend**: `./bly all PROGRAM [INPUT]` compares the text each prints and the final screens.
  A program that compares screens should `cls()` first: otherwise the 48K's screen still has the tape loader's text
  on it, which the interpreter's never had.
- **The screen**: `c/tests/test_screen.py` holds C to the reference; `z80/tests/test_zxgfx.py` holds the Z80's
  drawing to it; `z80/tests/rom_text_check.py` holds the reference's text to the real ROM.

**A test that has never failed hasn't shown it can.** When you add a check, break the thing it checks (a mutant) and
watch the test fail. Several gaps in these tests were found that way, and each got a test that fails against its
mutant. Make the mutant assert that it applied: a search string that doesn't match leaves the code unchanged, and the
"mutant" passes.

## Adding to the library

A fragment is an `.asm` file in `z80/lib/` that starts with a header:

```
;; provides: bly_zx_beep
;; needs: bly_fail bly_pr_cstr bly_pr_i16 bly_mul_i32 bly_divmod_i32
;; targets: zx48
```

`provides` are the labels others may call; `needs` are what it calls (gathered too); `targets` are where it can be
used (`zx48`, `cpm`, `test` for the bare Z80); `uses` names symbols the builder defines. The calling convention, the
memory layouts of every type and container, and the text of every message are in `z80/ABI.md`. The rules that matter
most: IY and the alternate registers are BASIC's on the Spectrum and are never touched, and a failure prints exactly
the interpreter's words, then " at line N".

Split a fragment when a program would carry code it doesn't use: the linker works at fragment granularity.
`z80/zxsize.py` shows where a program's bytes go.

## Making it faster

Measure first, and keep measuring:

- `z80/zxbench.py` runs the benchmark programs on the 48K and reports exact T-states and code size against
  `z80/bench/baseline.json`, flagging anything more than 0.5% slower or bigger. `--save` makes the current numbers
  the baseline. Save before you start, and save again only when a change is done and checked.
- `z80/zxprof.py PROGRAM.bly INPUT` samples the PC every 997 T-states and says how much time each library routine
  and each source line (approximately) takes.
- For every change to the generator: the suite on every backend, a few hundred fuzz programs, and a mutant or two of
  the change itself.

The generator's main ideas, and where they live in `z80gen.py`:
- **Operands** (`Op`): a value in memory (a slot, or a variable read in place) or an immediate. `fresh` marks a
  temporary nothing else holds; `snap()` copies an in-place read where something could change it before it's used.
- **Conditions** are branches (`branch`, `cmp_jump`): `and`/`or`/`not` become jumps, and comparisons go straight to
  the jump.
- **Cold code** (`cold`, `fail_jp`): failure paths go after the function's `ret`, so the hot path doesn't set line
  numbers.
- **The save rule** (`liveness`, `live_slots`): a call into the caller's own recursive cycle saves only what's live
  after it, worked out from the syntax tree.
- **The peephole** (`peephole.py`): what HL, DE and A hold, through straight-line code; anything it doesn't
  understand forgets everything.

HISTORY.md has the steps so far with their numbers, and the next ones.

## Conventions

- Error messages are part of the language: the same words on every backend, ending " at line N".
- Advent of Code inputs stay out of the repository (DESIGN.md, section 10). Tests use inputs made by
  `interp/tests/make_inputs.py`, with answers worked out there in plain Python.
- Builds go in `build/`, which git ignores.
