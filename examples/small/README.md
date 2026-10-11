# Small examples

One construct each, in a program small enough to be known: 10 to 25
lines, whose first line says what it shows and whose last lines say
exactly what it prints. Melissa asked for them, and they were written by
Ferns meeting Barleycorn fresh, from the card and these docs.

Run one with `./bly run NAME.bly` (with its input file, when its shape
names one: `./bly run containers-queue.bly containers-queue.txt`), or
`./bly all` to see every machine agree. Those marked [zx] are the
Spectrum's alone; their pictures are beside them. `./check small` holds
every one to what it says it prints, on every machine.

The shape, for writing another: line 1 is `-- ` and the construct in a
sentence, ending ` [zx]` if it's the Spectrum's alone. At the end,
`-- prints:` and then each line it prints as `-- > text` (`-- >` for an
empty line, and no line ending in a space). Before that, if it needs
them, `-- keys:` with each line typed as `-- < text`, and
`-- input: NAME.txt` for an input file beside it. A [zx] one has
`NAME.png`, made with `./bly run --screen NAME.png NAME.bly`.

## Basics

- [basics-hello](basics-hello.bly): print's `;` and `,`, and a trailing
  `;`
- [basics-loops](basics-loops.bly): `a..b`, `rev()`, `continue`, `break`
  and `while`
- [basics-integers](basics-integers.bly): the six sizes of whole number
- [basics-divide](basics-divide.bly): `/` and `%` as C has them, and
  `mod()` as a clock does
- [basics-overflow](basics-overflow.bly): a signed number stops at its
  edge, an unsigned one wraps
- [basics-bits](basics-bits.bly): `& | ^ ~ << >>` and `%1010`
- [basics-quad](basics-quad.bly): 64 bits, for 20!
- [basics-case](basics-case.bly): `case`, and a `when` with several
  values
- [basics-recursion](basics-recursion.bly): a function calling itself,
  and main first
- [basics-records](basics-records.bly): records, and comparing them
  field by field
- [basics-tables](basics-tables.bly): a const table: Roman numerals
- [basics-arrays](basics-arrays.bly): `T[N]`, `.sort()`, and a `T[]`
  parameter
- [basics-sieve](basics-sieve.bly): `bit[N]`, eight to a byte

## Text and input

- [text-lines](text-lines.bly): the input a line at a time
- [text-ints](text-ints.bly): every number in a string
- [text-strings](text-strings.bly): slicing, `find`, `starts`, `split`
- [text-intern](text-intern.bly): words into small numbers, and back
- [text-ask](text-ask.bly): a line typed at the keyboard
- [text-pad](text-pad.bly): right-aligning a number by hand

## Containers

- [containers-stack](containers-stack.bly): a list as a stack: a
  reverse-Polish calculator
- [containers-queue](containers-queue.bly): a queue, for the shortest
  way out of a maze
- [containers-heap](containers-heap.bly): a heap: the smallest first
- [containers-set](containers-set.bly): a set: have I been here before?
- [containers-map](containers-map.bly): a map: word counts
- [containers-grid](containers-grid.bly): `grid()`: minesweeper's
  numbers

## The machine

- [machine-if-zx](machine-if-zx.bly): `if ZX`: one program for every
  machine
- [machine-print-at](machine-print-at.bly): `print at`: display, not
  output
- [machine-colours](machine-colours.bly) [zx]: ink, paper, bright,
  flash, inverse, 8 and 9
- [machine-attr](machine-attr.bly) [zx]: a square's colours as one byte:
  pi in bars
- [machine-draw](machine-draw.bly) [zx]: `plot`, `line`, `circle` and
  `point`
- [machine-over](machine-over.bly) [zx]: `over` and `inverse`
- [machine-udg](machine-udg.bly) [zx]: a character of your own
- [machine-beep](machine-beep.bly) [zx]: notes on the beeper
- [machine-keys](machine-keys.bly) [zx]: `inkey()` and `key()`
- [machine-timing](machine-timing.bly) [zx]: `pause()` and `ticks()`
- [machine-floats](machine-floats.bly) [zx]: the ROM's floats, and what
  they cost
- [machine-status](machine-status.bly) [zx]: `print #1`, the lower
  screen
- [machine-frame](machine-frame.bly) [zx]: `frame`, every fiftieth of a
  second
- [machine-ports](machine-ports.bly) [zx]: `inp` for BREAK, `outp` for
  the border
- [machine-peek-poke](machine-peek-poke.bly) [zx]: the screen's bytes,
  read and written
- [machine-embed](machine-embed.bly): `@embed`, a file's bytes in the
  program
- [machine-fzx](machine-fzx.bly) [zx]: `print #4`, a proportional font
  (`sprig.fzx`, beside it, is the tests' own)
