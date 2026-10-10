# Barleycorn's reference interpreter

The language's specification, in Python: `barley.py`, one file. The
design it implements is `../DESIGN.md`.

    python3 barley.py [--as zx48|cpm] PROGRAM.bly [INPUT.txt]

It parses the whole program, then types every expression, because
integer widths decide where arithmetic wraps (unsigned) or traps
(signed). Then it walks the tree. Every check the design promises for a
checked build happens here, always: indices, capacities, signed
overflow, division by zero, missing keys, numbers too big for their
type. A failure prints what happened and the line, as the Spectrum would
("queue full (2) at line 3"), and exits with 1. `--as` picks the machine
it models: `ZX` or `CPM` is true accordingly (zx48 by default).

**Tests:** `python3 tests/run.py` (or `--c`, `--z80`, `--zx` for the
other backends). It runs five Advent of Code programs, on inputs made by
`tests/make_inputs.py`, whose answers it works out separately in plain
Python:
- 2022 day 1
- 2022 day 12 (the design's taste)
- 2023 day 8, on two inputs (the second has no `AAA`, so a variant skips
  part 1)
- 2021 day 15, with records, a heap and a `bit` grid
- 2023 day 6 (floats aim, integers land)

Then the programs in `tests/semantics.txt`, each with the exact output
it must print. Three deliberate mutations, each caught by exactly the
test meant for it, showed the tests can fail:
- floor division
- maps iterating sorted
- the naive minus in `ints()`

**In:**
- types: byte, word, int, long, quad, bool, str, records, pos
- fixed arrays (and `bit` elements)
- containers: list, queue, heap, map, set, grid
- statements: `for ... in` with half-open ranges and `rev`,
  `case`/`when`, compound assignment, `assert`
- BASIC's `print` (zones and trailing separators)
- `float`, with Python's doubles standing in for the machine's ("you get
  what you get"), the ROM's functions, and `**`
- builtins: `lines()`, `grid()`, `input()`, `intern`/`name`,
  `ints()`/`int(k)`/`split`/`find`/`starts`/`trim`,
  `min max abs sign gcd lcm mod`, and the casts

**The machine:** the screen and sound (with `print at`), whose meaning
is `../z80/zxgfx.py`, and a 64K memory that `peek` and `poke` share with
it: the 48K's ROM at 0000h (`poke` there does nothing, as on the real
one), the screen's 6,912 bytes at 4000h and the UDGs at FF58h. An
address is any whole number, checked as an index is
(`address 70000 is outside 0..65536`). `--screen out.png` saves the
picture and a `.scr` beside it, `--sound` the beep log. Only a program
that uses these (or `--screen`) needs the 48K ROM, for its font and
bytes; `../paths.py` says where it's looked for.

**Not yet:**
- `mark`/`release`/`free`
- `asm` clauses: these are parsed, and the body runs as the twin

Speed hasn't mattered yet. It's a plain tree walk, fine on examples. A
real input's heavy days may want the evaluator compiled to closures.
