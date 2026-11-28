# Where Barleycorn came from

## The first Barley (29 September 2026): where should a variable live on a Z80?

Barleycorn grew out of a smaller language, Barley, named for a cat (and
for the cheap grain that turns into something good once it's toasted).
Barley existed to answer one question with numbers: **where should a
variable live on a Z80, and what should a call cost?** The questions
were Melissa O'Neill's, from years of thinking about parameter passing.
Could variables live at fixed addresses, as Turbo Pascal 3 and HiSoft
BASIC put them, and still allow recursion? Could the immediate operand
of an instruction be a variable's home? How much of a program's memory
traffic becomes pure forward patching once values are in SSA form? Are a
few memory temporaries worth having?

I designed Barley and built its compiler in an evening: about 4,600
lines of Python, a reference interpreter, a T-state-exact harness on the
omse-ai emulator's Z80 core, and thirteen benchmark programs (fib, tak,
Ackermann, queens, a sieve, two sorts, a tree, an expression evaluator,
Life, a CRC, Hanoi and some argument shuffles), each with a C twin,
frozen before any code generator existed. Every build was checked
against the interpreter, and a fuzzer ran thousands of random programs
through every build. What it measured:

- **Fixed addresses beat IX frames on all thirteen programs**, by 26% on
  the geometric mean, once everything else was the same. They also used
  far less stack.
- **The one rule that makes fixed addresses work with recursion:** the
  compiler sees the whole program, so at every call it knows what the
  callee could overwrite. *Save what is still needed after the call and
  could be overwritten by it.* A function outside a recursive cycle
  saves nothing, and one inside saves exactly the live values. Fixed
  locals without that rule, as in pasta80 (a Turbo Pascal 3 clone), get
  `Fib(N-2) + A` wrong.
- **The best build was 15% faster than SDCC 4.6**: fixed slots, the save
  rule, operand homes (2 to 8%, never negative), hoisting loop
  invariants into temporaries with several operand homes each (the
  memory temporaries' real use: Life got 13% faster), packed saves, and
  register variables in BC chosen by running each option on the machine
  (a heuristic was right on only 8 of 13).
- **The runtime can hide behind a benchmark:** one program's whole gap
  to SDCC was the division routine.

Barley's own code isn't part of this repository. Its thirteen programs
live on as Barleycorn's benchmark suite (`z80/bench/`), and its answers
live on in the Z80 backend, which took them back one at a time (below).

## Barleycorn (8 and 9 October 2026): a whole language

Barley could compute, but it wasn't a language anyone would choose to
write in. Melissa suggested making it into one: shaped for the Spectrum,
able to drive CP/M too, small enough to know whole and big enough to
live in, with every piece what you'd reach for. The test case was Advent
of Code, which she has solved on a Spectrum in BASIC, with the answer
drawn and played as it's found. So the language had to read text, search
grids and graphs, carry 64-bit answers, and draw and play sounds as well
as calculate.

I wrote the design first (DESIGN.md), and we argued about it. Floats
came in: the ROM's, because "you use them, you get what you get". So did
screen and sound, a plain C backend beside the Z80 one, and linking
before assembly. Then I built it in the order the design said, each step
ending with something that ran:

1. **The interpreter**, which is the specification: parser, type checker
   and tree walker in one Python file.
2. **The C backend**, deliberately plain, built under the sanitizers,
   agreeing with the interpreter on every test.
3. **The Z80 backend for CP/M.** While I wrote the code generator, four
   other instances of me wrote the library in parallel, each from a
   written contract (`z80/ABI.md`): integers of every width, numbers to
   and from text, text and input, and the containers. Each fragment was
   tested on a bare Z80 against the interpreter's own code, with
   deliberate mutants to show the tests could fail. Integration found
   one real bug, in my code generator.
4. **The 48K Spectrum**: code high in memory, the input as a tape block,
   output through the ROM, tapes run on omse-ai.
5. **Screen and sound**, with a reference model (`z80/zxgfx.py`) whose
   text output matches the real ROM's on random programs, and **floats**
   through the ROM's calculator.

By the end of the second day every test passed on all four targets (CP/M
excepted where it has no floats or screen), and a hill climb drew itself
on a 48K and printed both answers (`examples/sing_d12.bly`).

## Getting fast (9 October 2026)

The Z80 backend's first version was deliberately simple: every value in
a fixed slot, every subexpression copied into a fresh one, every
comparison two library calls, and a recursive call copying its caller's
whole frame to the stack and back. Correct, and slow. On one Advent of
Code program it ran only 1.1 times as fast as the same algorithm in
Spectrum BASIC compiled with HiSoft BASIC.

So the backend took back the first Barley's measured answers, one at a
time. Each step was timed on the 48K against a saved baseline
(`z80/zxbench.py`), checked by the whole suite on every backend and by a
new fuzzer with the interpreter as its oracle (`z80/fuzz.py`), and
broken on purpose (mutants) to make sure the tests could tell:

1. **Variables read in place** rather than copied, except where
   something later in the statement could change them, and snapshots
   where a value is held across a loop or a self-call writes over its
   own arguments.
2. **Comparisons fused into branches**, with the first compiler's inline
   8- and 16-bit compares.
3. **Failure paths out of line** (index checks and overflow traps set
   their line number only when they fail), 16-bit slices checked inline,
   and small values moved without block copies.
4. **A register cache**: a pass that knows what HL, DE and A hold,
   deletes loads of what's already there, and drops stores nobody reads.
5. **The save rule** in place of copying the frame, with liveness worked
   out from the syntax tree.
6. **Arithmetic by constants inline**, and calls' argument temporaries
   counted as dead once the call is made.
7. **A new variable takes over the temporary its value arrived in.**

On the thirteen programs, in T-states on a 48K (with the ROM's interrupt
handler running, which costs about 3%), and against the first Barley's
best build on a bare Z80:

| program | first version | now | now / first | code size now / first | first Barley's best | now / best |
|---|---|---|---|---|---|---|
| ack | 94,028,248 | 16,404,309 | 0.17 | 0.72 | 4,092,695 | 4.0 |
| bubble | 31,607,710 | 16,906,114 | 0.53 | 0.60 | 8,347,565 | 2.0 |
| crc | 9,695,061 | 4,704,907 | 0.49 | 0.72 | 1,766,206 | 2.7 |
| expr | 7,937,622 | 2,623,783 | 0.33 | 0.76 | 1,305,209 | 2.0 |
| fib | 32,770,292 | 6,286,232 | 0.19 | 0.72 | 2,112,570 | 3.0 |
| hanoi | 21,968,316 | 4,545,612 | 0.21 | 0.57 | 2,481,918 | 1.8 |
| life | 46,889,587 | 12,845,809 | 0.27 | 0.76 | 5,421,536 | 2.4 |
| perm | 4,823,309 | 2,048,591 | 0.42 | 0.88 | 1,946,313 | 1.05 |
| qsort | 8,717,476 | 3,614,601 | 0.41 | 0.89 | 1,727,711 | 2.1 |
| queens | 23,761,953 | 6,133,108 | 0.26 | 0.65 | 2,743,219 | 2.2 |
| sieve | 20,180,547 | 7,036,050 | 0.35 | 0.68 | 3,836,270 | 1.8 |
| tak | 166,572,505 | 33,012,630 | 0.20 | 0.77 | 13,119,401 | 2.5 |
| tree | 12,362,495 | 3,087,577 | 0.25 | 0.59 | 1,276,500 | 2.4 |

The Advent of Code program that ran 1.1 times as fast as compiled BASIC
now runs 2.2 times as fast.

The fuzzer's first finds were in the specification, not the compiler:
the interpreter evaluated `a[i] = e`'s value before its target, against
the design's left to right, and evaluated `i` twice in `a[i] += e`. The
C backend read `g` after the call in `g += f()`. All three are fixed,
and tests pin them.

**Next**, roughly in the order the measurements suggest:
- hoisting loop invariants (in Barleycorn an `int` expression can trap
  on overflow, so a hoisted one has to fail at its original place, not
  early)
- operand homes
- register variables chosen by measuring them on the machine
- results computed straight into their destinations
- `int` arithmetic by constants inline
- a register cache that survives loop heads
- a cheaper string equality

## The first users (9 October 2026, evening)

Before Barleycorn met anyone else, three other instances of me wrote its
first programs, from a short brief and without touching the compiler:
Life, a maze and Langton's ant; the Ulam spiral, Collatz, the Mandelbrot
set and Ford circles; Hanoi, a sudoku and the 92 queens (`examples/`).
Each prints the same on every backend, and draws the same last screen in
the interpreter and on a 48K. Each also kept a list of what she reached
for and didn't find, and those lists were worth as much as the programs:

- **All three** found the interpreter running Spectrum-only calls under
  `--as cpm` while the CP/M compiler refused them, and `if ZX and ...`
  not counting as a guard. Now one rule in the checker says it for
  everyone, at the line.
- `1 << d` became an `int` before it knew it was going into a `word`; a
  literal shifted now takes its type from where it's used. Messages said
  "a int". String constants weren't allowed, so there was no constant
  table of bytes.
- On the Z80, `bit` arrays took a byte each, against the card's promise;
  `abs` went through 64 bits; `long` `% 2` called the full divide;
  constant shifts called the shifters. All are inline now, or packed.
- `./bly` runs collided in a shared folder, and `./bly zx` gave up
  silently. Each run has its own folder now, `./bly all` compares
  everything, and a program still running at the limit is reported.
- Building the bit arrays found a hole in the specification: an array of
  65536 had a length no `word` could hold.

**Still open from their lists**, and written down in DESIGN.md: array
literals for constant tables of other types; `print at` text also going
to the output; a transparent ink, as BASIC's INK 8; reading an attribute
back; an unsigned 32-bit type; and, on the Z80, grids (each access
multiplies: about 17% of the maze's time, and 55% of a grid-based
Life's; a table of row addresses would take the multiply out), `gcd`
through 64 bits, and the string comparison.

## The name

The language was Barley until it was about to meet the world, where the
name was taken. Barleycorn keeps the cat inside it. A barleycorn is also
an old unit of length, a third of an inch: a little measure for a little
language. And in the folk song, John Barleycorn is cut down and ground,
and comes back as something stronger, which is roughly what a compiler
does to a program.

## Against SDCC (18 November 2026)

Melissa asked whether Barleycorn beats the obvious C you'd write, and
then C with `static` everywhere. Fronds ported the elves (Advent of Code
2022, day 23) to C and compiled it with SDCC 4.6. It didn't: on the
elves' rounds, less the pauses, the obvious C took 429.9 Spectrum
seconds against Barleycorn's 524.2 unchecked and 615.7 checked. Her
profile put a fifth of the time in one line, `taken(cy, cx)`, which
returns `full[rowbase[cy] + cx]`. Most of that was the call itself: the
arguments copied into slots, every global in them copied first (a call
was somewhere in the statement), then the call, the return, and the
result fetched back from its slot. SDCC kept it all in registers.

So four changes:

1. **A function that is one `return`, of scalars and with no call in it,
   is worked out where it's called.** Its parameters read the arguments
   where they are, and its value is kept as a call's would be. That
   costs code, so a tape that wouldn't fit on a 48K that way is built
   again with those functions called (the checked elves on a wider grove
   than the fiddlehead is one).
2. **A global in an argument is copied first only when a call can run
   before the arguments are passed**, in that argument or a later one,
   rather than whenever the statement has a call anywhere.
3. **Three spill rewrites in the peephole pass.** The commonest is the
   left side of `a - 1` kept in a slot while the 1 loads, then fetched
   back into HL: now `ld de,1` with the left side still in HL. The cache
   pass runs first, because a reload it can delete is cheaper deleted
   than rewritten.
4. **Indexing, unchecked:** an 8- or 16-bit index goes straight into HL,
   with no length loaded for a check that isn't made. Checked or not, an
   element of 2, 4 or 8 bytes is addressed without a push and pop.

On the elves (the fiddlehead input, 270 rounds, every picture the same
as before), less the pauses, Barleycorn unchecked is now a little faster
than either C:

| build | before | after | SDCC, obvious C | SDCC, `static` |
|---|---|---|---|---|
| unchecked | 524.2 s | 401.3 s | 429.9 s | 406.2 s |
| checked | 615.7 s | 516.9 s | | |

On the thirteen programs and the examples nothing got slower. `expr`
takes 19% fewer T-states, `bubble` 12%, `tree` 9%, `qsort` 8%,
`ex-mandel` 7%, and the recursive ones are unchanged.

**The morning after: routine by routine.** Melissa looked at the memory
traces and saw much of the library never ran, and asked whether a
program links only what it needs. It did, but a whole fragment at a
time: one routine wanted brought in every routine in its file. Now each
routine is marked off in its fragment, the linker keeps one only if
something kept names it, and `z80/libblocks.py` checks the rules the
assembler can't see, such as that nothing runs on into a routine that
might be gone (ABI.md, section 3). Nothing got slower, and every
benchmark got smaller: `fib` by 43%, `perm` by 39%, the thirteen and the
examples by 18% in all, the elves by 0.9K. The checked elves on the
wider grove fit with `taken` inlined now.

**`--terse`.** Then she asked for a build that keeps code trim "when you
need that or are showing off": every check kept, but a failure just
stops, as BASIC's `C Nonsense in BASIC`. Error reporting was about a
tenth of the elves' code. Now a routine that only fails is marked
`(fails)`, a terse build drops each one and makes whatever named it jump
to the platform's wordless `bly_terse`, and the generator stops keeping
a line for a failure to name. The elves come out 10% smaller (7,234
bytes unchecked) and, with no line kept, a little faster: 393.2 seconds
less the pauses. `z80/tests/terse_check.py` builds every semantics
program both ways: one that doesn't fail prints the same, and one that
does prints what came before its failure, then stops.


## Operand homes, at last (27 November 2026)

The first Barley asked whether a variable could live in the immediate
operand of an instruction, and measured it at 2 to 8%. Barleycorn's
generator had never taken that answer back. When Melissa read the new
README, she'd assumed it had, and suggested the smallest way in:
statically pick the likely hottest place a variable is used, store the
variable in that instruction's immediate, and have every other use read
and write that location instead of its slot. First, she said, try it
both ways on a benchmark.

So a prototype rewrote the finished assembly, and the benchmarks ran
both ways, every output checked against the interpreter. Then it went
into the generator as its last pass (`z80/homes.py`). A slot of one or
two bytes gets a home if every use of it is a plain load or store of
exactly it. The home is its read at the deepest loop nesting, which
becomes the immediate form: `ld de,(x)` at 20 T-states becomes
`ld de,nn` at 10, and `ld hl,(x)` or `ld a,(x)` save 6. No use gets
slower, and `ld de,nn` is a byte shorter than `ld de,(nn)`.

| program | homes off | homes on | on / off | code bytes |
|---|---|---|---|---|
| hanoi | 4,280,501 | 3,948,680 | 0.922 | 678 -> 677 |
| tak | 33,012,633 | 30,628,936 | 0.928 | 773 -> 772 |
| fib | 6,287,320 | 5,843,772 | 0.929 | 547 -> 546 |
| sieve | 7,036,846 | 6,601,841 | 0.938 | 702 -> 700 |
| ack | 16,405,176 | 15,498,637 | 0.945 | 661 -> 661 |
| bubble | 14,887,541 | 14,173,677 | 0.952 | 1010 -> 1001 |
| life | 12,837,132 | 12,273,278 | 0.956 | 1848 -> 1826 |
| qsort | 3,320,333 | 3,191,097 | 0.961 | 1923 -> 1911 |
| crc | 2,952,019 | 2,856,013 | 0.967 | 827 -> 824 |
| tree | 2,802,253 | 2,711,501 | 0.968 | 1329 -> 1334 |
| perm | 2,048,824 | 1,986,178 | 0.969 | 1390 -> 1384 |
| ex-mandel | 393,081,495 | 380,895,064 | 0.969 | 7886 -> 7860 |
| expr | 1,896,917 | 1,853,133 | 0.977 | 1907 -> 1905 |
| queens | 6,134,285 | 6,062,805 | 0.988 | 877 -> 879 |
| ex-life | 388,469,825 | 383,632,609 | 0.988 | 9085 -> 9069 |
| ex-collatz | 178,830,936 | 177,432,056 | 0.992 | 7866 -> 7858 |
| sing | 98,421,637 | 97,863,404 | 0.994 | 8587 -> 8578 |
| ex-maze | 77,826,086 | 77,505,233 | 0.996 | 10162 -> 10142 |

Every program is faster, by 3.7% on the geometric mean: 5 to 8% on the
small recursive ones, less where the time is in the library. Code is
within half a percent either way. Two programs are a few bytes bigger,
because a home lives in the code, which RUN again doesn't reload. So a
global that relies on starting at zero, as the slots do, has its home
zeroed at every start (`z80/tests/homes_check.py` runs three programs
twice; without the zeroing, the second run carries on from the first's
count).

The prototype's first try got hanoi wrong. Its four byte-sized
parameters are saved across its recursive call two at a time: one
`ld hl,(n)`, one `push hl`, for `n` and `a` together. It moved `a` into
an operand and left that push saving the slot. Now any access that
touches two slots pins both, as does a taken address. The semantics
suite has hanoi's shape, and the mutant that forgets fails it.

**And against SDCC again.** The elves bake-off (above, "Against SDCC")
ran again with homes in, every build on the same emulator the same
evening, SDCC's tapes and November's Barleycorn reproducing their times
to the tenth of a second. Less the pauses, on our fiddlehead: the
obvious C 429.9 seconds, the `static` C 406.2, Barleycorn unchecked
401.3 in November and 390.5 now. On Melissa's goodbye: 89.1, 85.3, 86.1
and 83.6. So Barleycorn unchecked now beats the `static` C on both, and
the obvious C by 10% and 7%. Every round's picture agrees with the C's.

**Next:** this is a last pass, and Melissa's view is that it's good
enough for now but not the long-term answer. Doing it better needs more
knowledge than a pass over finished assembly has. The generator could
choose homes knowing what the register cache will hold, which variables
a register would serve better, and how often each loop runs. It could
also give the save rule a way to save a home without pinning its
neighbours.

Melissa's original design for this goes further. Rewrite the program
into SSA form at the source level, so that each version of a variable
has exactly one assignment. A version read in only one place then needs
no slot at all, because its assignment writes straight into that read's
immediate. A version read in several places gets a home in one of them
and is read from there by the others, as now. That's the first Barley's
question about how much memory traffic becomes forward patching. She
expects a source-level rewrite to cost no extra storage and no extra
code.
