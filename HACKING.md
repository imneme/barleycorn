# Hacking on Barleycorn

## The one rule

**The interpreter is the specification, and the three implementations
agree.** `interp/barley.py` says what every program means: its output,
and the exact words and line of every failure. The C backend and the Z80
backend (on a 48K Spectrum and under CP/M) must print exactly what it
prints. So a change in meaning starts in the interpreter, with a test,
and then goes to each backend. A backend that disagrees is wrong, unless
the interpreter is, and then the interpreter is fixed first and the test
pins it. That has happened: the fuzzer's first finds were in the
interpreter (the order an assignment evaluates its parts).

Floats are the one place they may differ: the Spectrum's are the ROM's
own (DESIGN.md, section 5). The suite compares printed floats to within
the ROM's precision, and every other character exactly.

## The layout

```
bly            the front door: run, or compile and run, a program anywhere
check          every test, in order; skips (and says so) what you lack
paths.py       where the outside tools are: the environment, paths.local,
               or PATH
interp/
  barley.py    lexer, parser, type checker and interpreter: the
               specification, in one file
  tests/       run.py: the suite, on any backend (--c, --z80 for CP/M,
               --zx for the 48K); semantics.txt: small programs and their
               exact output; six Advent of Code programs, and the inputs
               make_inputs.py makes for them
c/
  cgen.py      checked program -> plain C
  rt/          barley.h, and one template per container kind
  tests/       test_screen.py: the C screen against the reference, pixel
               for pixel
z80/
  z80gen.py    checked program -> Z80 assembly
  peephole.py  the register cache and dead stores
  link.py      gathers library fragments by their headers
  lib/         the library: one .asm fragment per area, each with a
               header; NOTES.md, its design and costs
  ABI.md       the contract between the generated code and the library:
               registers, layouts, every message
  zxbuild.py   a 48K tape: two assembly passes (code flush under the UDGs),
               a BASIC loader, the input as a block
  zxrun.py     runs a tape on omse-ai and prints what it printed
  zxgfx.py     the Spectrum's screen and sound as a model: the reference
               the interpreter and C draw with
  harness.py   runs library fragments on a bare Z80 (bare.py), for tests
  tests/       each fragment against its Python model, some with
               deliberate mutants
  bench/       the first Barley's thirteen benchmark programs, and
               baseline.json (their T-states)
  zxbench.py   exact T-states on the 48K, against the baseline
  zxprof.py    where the time goes
  zxsize.py    where the bytes go
  fuzz.py      random programs, the interpreter as oracle
examples/      programs to read and run
tools/
  check_docs.py  the docs still quote the programs as they are; the
                 Markdown is wrapped
```

## How a program goes through

All three share one front end: `interp/barley.py`'s `Parser` and
`Checker`. The checker types every expression, because integer widths
decide where arithmetic wraps (unsigned) or traps (signed).

- **The interpreter** walks the tree. Every check happens here, always.
  The screen and sound draw into a model of the Spectrum's memory
  (`z80/zxgfx.py`), which can be saved as a `.scr` and a PNG.
- **C** (`c/cgen.py`): one C function per function, every subexpression
  in its own temporary in the interpreter's order, and every operation a
  call into `rt/barley.h`, which checks it in the same words. No
  undefined behaviour from our side: the tests build with UBSan and
  ASan, and any warning fails.
- **Z80** (`z80/z80gen.py`): every variable, parameter and temporary
  lives at a fixed address in its function's frame; 8- and 16-bit
  arithmetic is inline, anything wider is a call into the library.
  `peephole.py` then cleans up each function. `link.py` gathers the
  library fragments the program uses, and sjasmplus assembles the lot
  once. `zxbuild.py` makes a tape, and for CP/M the assembly is a
  `.COM`.

## Where printing happens

Every `print` ends in one routine per machine, `bly_putc`, and on the
Spectrum that is the ROM's own `RST 10h`.

- The generated code calls the library's printers for each item:
  `bly_pr_cstr` and `bly_pr_str` for text and `bly_pr_i16` for 16-bit
  numbers (`z80/lib/core.asm`), the other widths in `num.asm`, floats in
  `fp.asm`. Each byte goes through `bly_out` (`core.asm`), which keeps
  the column that `print`'s comma needs, then to `bly_putc`.
- **On the Spectrum**, `bly_putc` is in `z80/lib/plat_zx.asm`. It keeps
  the scroll counter (SCRCT) at 255 so "scroll?" never asks, turns a
  newline into ENTER, prints a control code or a keyword token as `?`
  (so nothing is ever interpreted), and does `RST 10h`. `bly_start`
  opened stream 2, the upper screen, with the ROM's CHAN-OPEN (1601h).
  `print at` is `bly_zx_at`: AT and its row and column, straight to
  `RST 10h`.
- **Text printed at a place is the screen's alone** (DESIGN.md, "the
  answer and the display"). On the Spectrum the generated code brackets
  each piece of it (an item, a comma's padding, the newline) with
  `bly_zx_scr_on` and `bly_zx_scr_off`, which send INVERSE and OVER,
  each at the value it already has, straight to `RST 10h`: nothing
  changes on the screen, but omse-ai's transcript shows `{INVERSE n}`
  and `{OVER n}`, and `z80/transcript.py` drops what lies between (user
  code can't send them: `bly_putc` prints a control byte as `?`). An
  item is worked out before its bracket opens, so a failure's message is
  never inside one. In C it's `BLY_ATTEXT`, a second setting of the flag
  that puts print's text on the virtual screen; in the interpreter,
  `write(text, screen_only)`.
- **On CP/M**, `bly_putc` is in `z80/lib/plat_cpm.asm`: BDOS function 2,
  a newline as CR LF.

**Why the ROM.** It is the Spectrum's text exactly: the font, the block
graphics and UDGs, INVERSE and OVER, every colour rule (INK 8 and 9 come
through its PO-ATTR), wrapping, and its lazy scrolling. The reference
model, `z80/zxgfx.py`, copies it, and `z80/tests/rom_text_check.py`
holds the copy to the real ROM. It is also what BASIC programmers know:
anything the ROM's printing can do, a Barleycorn program's can.

**What it costs**, measured on the 48K: about 1,800 T-states a character
(half a millisecond), so a full screen of 704 takes 0.36 s, and about
150,000 for a scroll. Hand-written printing could be perhaps four times
faster per character, but a scroll costs about the same whichever code
moves the 5.4K, and it is the scroll that dominates a program printing
line after line. So the ROM stays, unless a program shows otherwise.
Reading the keyboard will go through the ROM too (`inkey()`, and input
of numbers and text through the ROM's editor, in the way of Melissa's
spectrum-minilib), when it comes.

## Tests

`./check` runs them all; `./check --quick` the fast ones;
`./check interp c` just those stages.

- **The suite** (`interp/tests/run.py`): `semantics.txt` and the Advent
  of Code programs, on any backend. A test in `semantics.txt` is
  ```
  === what it pins down
  func main()
    ...
  end
  --- input           (optional: the text lines() and grid() read)
  ...
  --- keys            (optional: what's typed, for ask(), inkey() and
  ...                 key(); stdin off the Spectrum, and zxrun --keys
                      types it on the 48K. The keys running out is a
                      STOP in ask)
  --- screen          (optional: the final screen must match the
                      interpreter's too, pixel for pixel)
  --- as cpm          (optional: a test of CP/M's rules, run by the
                      interpreter --as cpm and by the CP/M backend)
  --- expect
  the exact output
  --- expect cpm      (optional: CP/M's output, where it differs: its
  ...                 one console shows ask()'s prompt and echo. The
                      interpreter --as cpm is held to it too)
  ```
  A failure's message is part of the output
  (`index 9 is outside 0..8 at line 4`), so tests pin failures too. On
  the 48K, `zxrun` also fails a run that ends in any report but BASIC's
  `0 OK`: a Barley program goes back to BASIC by returning, failure or
  not, so any other report is the ROM's own error. Anything that runs
  programs gives them a stdin of its own, the keys or an empty one: a
  program that reads keys reads stdin, and one inherited from a terminal
  or a pipe can leave it waiting for ever. (The screen test did, once.)
- **The fragments** (`z80/tests/test_*.py`, with omse-ai's Python): each
  library area on a bare Z80 against a Python model of what it should
  do, usually the interpreter's own code, over random and edge cases.
  `test_int_mutants.py` and `test_fp_mutants.py` break the library on
  purpose and check the tests notice.
- **The fuzzer** (`z80/fuzz.py N`): random, well-typed programs over the
  integer core (every width, comparisons, `and`/`or`/`not`, casts,
  constants, loops whose bounds change, functions that change globals,
  self-calls that shuffle their own arguments), run in the interpreter,
  as C and as CP/M programs. Any disagreement is kept in
  `build/fuzz-failures/`.
- **One program, every backend**: `./bly all PROGRAM [INPUT]` compares
  the text each prints and the final screens. A program that compares
  screens should `cls()` first: otherwise the 48K's screen still has the
  tape loader's text on it, which the interpreter's never had.
- **The screen**: `c/tests/test_screen.py` holds C to the reference;
  `z80/tests/test_zxgfx.py` holds the Z80's drawing to it;
  `z80/tests/rom_text_check.py` holds the reference's text to the real
  ROM, and `lower_check.py` its lower screen (`print #1`) to BASIC's own
  PRINT #1. `fzx_check.py` holds `print #4` to Einar Saukas's FZX driver
  itself, if `FZX_DRIVER` (paths.py) says where its source is, and to
  our adapted one on the 48K. It uses `interp/tests/sprig.fzx`, and any
  fonts in `FZX_FONTS`, since fonts aren't ours to ship.
  `tools/make_fzx.py` draws `sprig.fzx`, and with `--stray`, a font that
  breaks the rules on purpose.
- **The docs** (`tools/check_docs.py`): a code block that starts like a
  program in `interp/tests` or `examples` quotes it, and must be all of
  it, exactly; DESIGN.md quotes five. Every command's `-h` must work and
  fit in 80 columns, and an option a command hasn't got must be refused,
  not ignored (every command line is argparse's). The `wrap` stage
  checks every Markdown file is wrapped as `mdwrap` wraps it.

**A test that has never failed hasn't shown it can.** When you add a
check, break the thing it checks (a mutant) and watch the test fail.
Several gaps in these tests were found that way, and each got a test
that fails against its mutant. Make the mutant assert that it applied: a
search string that doesn't match leaves the code unchanged, and the
"mutant" passes.

## Adding to the library

A fragment is an `.asm` file in `z80/lib/` that starts with a header:

```
;; provides: bly_zx_beep
;; needs: bly_fail bly_pr_cstr bly_pr_i16 bly_mul_i32 bly_divmod_i32
;; targets: zx48
```

`provides` are the labels others may call; `needs` are what it calls
(gathered too); `targets` are where it can be used (`zx48`, `cpm`,
`test` for the bare Z80); `uses` names symbols the builder defines. The
calling convention, the memory layouts of every type and container, and
the text of every message are in `z80/ABI.md`. The rules that matter
most: IY and the alternate registers are BASIC's on the Spectrum and are
never touched, and a failure prints exactly the interpreter's words,
then " at line N".

Split a fragment when a program would carry code it doesn't use: the
linker works at fragment granularity. `z80/zxsize.py` shows where a
program's bytes go.

## Making it faster

Measure first, and keep measuring:

- `z80/zxbench.py` runs the benchmark programs on the 48K and reports
  exact T-states and code size against `z80/bench/baseline.json`,
  flagging anything more than 0.5% slower or bigger. `--save` makes the
  current numbers the baseline. Save before you start, and save again
  only when a change is done and checked.
- `z80/zxprof.py PROGRAM.bly INPUT` samples the PC every 997 T-states
  and says how much time each library routine and each source line
  (approximately) takes.
- For every change to the generator: the suite on every backend, a few
  hundred fuzz programs, and a mutant or two of the change itself.

The generator's main ideas, and where they live in `z80gen.py`:
- **Operands** (`Op`): a value in memory (a slot, or a variable read in
  place) or an immediate. `fresh` marks a temporary nothing else holds;
  `snap()` copies an in-place read where something could change it
  before it's used.
- **Conditions** are branches (`branch`, `cmp_jump`): `and`/`or`/`not`
  become jumps, and comparisons go straight to the jump.
- **Cold code** (`cold`, `fail_jp`): failure paths go after the
  function's `ret`, so the hot path doesn't set line numbers.
- **The save rule** (`liveness`, `live_slots`): a call into the caller's
  own recursive cycle saves only what's live after it, worked out from
  the syntax tree.
- **The peephole** (`peephole.py`): what HL, DE and A hold, through
  straight-line code; anything it doesn't understand forgets everything.

HISTORY.md has the steps so far with their numbers, and the next ones.

## Conventions

- Error messages are part of the language: the same words on every
  backend, ending " at line N".
- Advent of Code inputs stay out of the repository (DESIGN.md, section
  10). Tests use inputs made by `interp/tests/make_inputs.py`, with
  answers worked out there in plain Python.
- Builds go in `build/`, which git ignores.
- Markdown is for reading in a terminal: prose wrapped at 72 columns
  (`mdwrap -i FILE` does it, and changes nothing but where lines break),
  and code blocks kept to 80 by hand. Tables may be as wide as they
  need.
