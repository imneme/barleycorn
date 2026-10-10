# Barleycorn's C backend

`cgen.py` lowers a checked Barley program to deliberately dumb C. `rt/`
is its runtime: `barley.h`, plus one template per container kind.

    python3 cgen.py PROGRAM.bly > prog.c
    clang -std=c11 -O2 -I rt prog.c -lm -o prog && ./prog INPUT.txt

The front end is the reference interpreter's own parser and checker
(`../interp/barley.py`), so the two can't disagree about what a program
means. Every test runs on both backends:
`python3 ../interp/tests/run.py` for the interpreter, and
`... run.py --c` for C. The C is built with **UBSan and ASan on**
(`-fno-sanitize-recover=all`), and any compiler warning counts as a
failure.

**How the C is shaped:** the easiest code to generate, as strange as it
likes, so long as it follows all of C's rules, with no undefined
behaviour from our side:

- **Every subexpression gets its own temporary, in the interpreter's
  left-to-right order.** C leaves the order of function arguments
  unspecified, and that would let two honest backends disagree, even
  about which of two errors comes first. Assignment evaluates the
  target's parts first, then the value, then stores, with the check at
  the store. Compound assignment reads the target once and writes it
  once.
- **Control flow stays structured.** Barley's `if`, `while` and `for`
  become C's, so `break` and `continue` mean the same. A `while` is
  `for (;;) { cond; if (!c) break; body }`, so its condition's
  temporaries are recomputed. `case` is an `if` chain, so a `break`
  inside one leaves the loop, as it should. `and` and `or` short-circuit
  with real `if`s.
- **No undefined behaviour from our side.**
  - Unsigned arithmetic is done in an explicitly wider unsigned type:
    never `u16 * u16`, which C would do in signed `int`.
  - Signed arithmetic is done wider and range-checked; `quad` uses
    `__int128`.
  - Values are wrapped into signed types by arithmetic, not by
    implementation-defined conversion.
  - Shift counts are bounded, and arithmetic right shift is spelled out.
  - A zero `str` has a NULL pointer, so sub-slices never do pointer
    arithmetic on an empty string (even `NULL + 0` is undefined).
  - A float is converted to an integer only after a range check.
- **The checks are always on**, with the interpreter's words: overflow,
  bounds, capacities, missing keys, a container changed while `for`
  walks it, numbers that don't fit.
- **Generics are the preprocessor's.** `bly_list.h`, `bly_queue.h`,
  `bly_heap.h`, `bly_map.h` (which also does sets), `bly_grid.h` and
  `bly_sort.h` are each included once per element type, after
  `#define G_NAME`, `G_T` and `G_X`. Element kinds share one naming
  scheme (`bly_cmp_X`, `bly_eq_X`, `bly_hash_X`, `bly_pr_X`), so a
  record's generated functions slot in beside the built-in ones.
- **The data structures are the Z80 library's design, written in C
  first:**
  - an arena that's never freed
  - a map that keeps entries in insertion order in a dense array, beside
    an open-addressed index of entry numbers (which is why maps walk in
    insertion order, cheaply)
  - a ring-buffer queue
  - version counters, so a walk can tell its container changed

**The screen and sound** are `rt/bly_zx.h`, which follows the reference,
`../z80/zxgfx.py`, line for line: the same 6,912 bytes (the Spectrum's
layout at 4000h), the same algorithms, the same checks in the same order
with the same words.
- Every byte `print` writes also lands on the virtual screen, and only
  those: the generated code sets `bly_showing` around each item, zone
  and newline (`BLY_SHOW`), so a failure's message never draws, as in
  the interpreter.
- The font is the ROM's, read by `cgen.py` at compile time, so building
  a program that uses the screen needs `48.rom`, as running it in the
  interpreter does (`../paths.py` says where it's looked for).
- `peek` and `poke` see a 64K memory, as the interpreter's: the ROM at
  0000h (read-only), the screen at 4000h, the UDGs at FF58h. The ROM's
  16K go into a program only if it peeks, since nothing else can see
  them.
- At exit, and at a failure too, `BARLEY_SCREEN=path.scr` gets the 6,912
  bytes and a PNG beside it, and `BARLEY_SOUND=path.txt` the beep log,
  one `ms semitone` a line, as the interpreter's `--screen` and
  `--sound`.
- `tests/test_screen.py` runs hand-picked edges, every failure message
  (checked word for word), and seeded random drawing programs through
  both the interpreter and the C, and compares the screen, the sound and
  the text.

**Not yet:**
- `mark`/`release`
- a constant array used as a plain value (`dirs4` works when indexed or
  walked)
