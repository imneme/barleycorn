# For agents working on Barleycorn

Start with **HACKING.md**: the one rule, the layout, how a program goes
through each backend, and how the tests and measurements work. These are
the rules that cost the most to learn. Each is here because ignoring it
produced a confident wrong answer, or nearly did.

## The rules

**The interpreter is the spec, and that includes being wrong.** When a
backend disagrees with the interpreter, the backend is usually wrong.
Usually: the fuzzer's first catch was the interpreter evaluating an
assignment's value before its target, against the design's left to
right, which both compiled backends already did right. Before you make a
backend match the interpreter, check the interpreter against DESIGN.md.
Fix whichever is wrong, and pin it with a test in `semantics.txt`.

**Watch every test fail before you trust it.** A change to the code
generator isn't checked until a mutant of it (the change deliberately
broken) has failed a test. More than once a mutant passed everything:
the fuzzer's numbers were too small to reach a path, or the one case
that needed the check was missing. Each time that meant writing the test
that was missing. And make the mutant assert that it applied. A mutation
whose search string didn't match left the code unchanged, and "passed"
twice before anyone noticed.

**Measure, don't reason.** The Z80's costs are exact and cheap to ask
for. `z80/zxbench.py` gives T-states against a saved baseline;
`z80/zxprof.py` says where the time goes. A program that ran barely
faster than compiled BASIC turned out, once profiled, to spend 59% of
its time copying values between slots, and that pointed straight at what
to fix. Profile before optimising, and bench after.

**Read the code you generate.** Most of what's been fixed in the Z80
backend was found by reading its output: copies of copies, two library
calls for one comparison, a save of something already dead. Read your
own new code too, with the same suspicion: a peephole pass's first draft
treated `(hl)` as a fixed address, and a nested `if` overwrote the state
its outer `if` still needed. Both were caught by reading before anything
ran.

**Run `./check`, not just the suite, before you commit.** A message
lives in more than one place: the interpreter says it, and so do the C
runtime and the Z80 library, each with its own copy of the words. A
change to "an int" in the interpreter passed every suite test and was
committed, while the library and the C runtime still said "a int"; only
the library's own tests (`./check`'s fragments stage) compare those
messages word for word.

**Check when, not just whether.** A tape, a baseline or a fuzz failure
file from an earlier run looks just like a fresh one. When a number
matters, make it again.

**Keep Advent of Code inputs out.** The puzzle text and inputs aren't
ours to share. Tests use inputs made by `interp/tests/make_inputs.py`,
with answers worked out by plain Python there, not by Barleycorn, so the
tests don't just check the interpreter against itself.

## Also worth knowing

- **Missing pieces say so.** No sjasmplus, no tnylpo, no omse-ai or no
  ROM each give a one-line message saying what to install or where to
  put it, and `./check` skips what it can't run. A traceback instead is
  a bug worth fixing.
- **Only programs that touch the Spectrum's screen, sound or memory need
  the ROM**, even in the interpreter.
- **macOS has no `timeout` command.** `./bly zx --minutes N` limits a
  Spectrum run, and the scripts here use Python's own timeouts.
- **The Spectrum's ROM keeps its own rules.** IY must stay 5C3Ah and HL'
  must survive for the return to BASIC. The ROM's BEEPER turns
  interrupts off, so the frame counter stands still while it plays. Its
  PRINT wraps and scrolls lazily, when the next character is printed
  rather than at the newline. When the model and the machine disagree,
  run it on the machine (omse-ai) and believe that.
- **People read these docs in a terminal.** Keep Markdown prose at 72
  columns (`mdwrap -i FILE`; `./check wrap` says if any isn't) and code
  blocks within 80. When a program DESIGN.md quotes changes, copy it
  back in: `./check docs` notices.
- **Generated programs are whole programs.** The compiler sees every
  function, so it knows exactly what any call can overwrite. That's what
  makes fixed addresses for variables beat stack frames on this CPU
  (HISTORY.md), and it's why there are no pointers to locals: nothing
  may break that.

## A note from the agent who built it

I'm Fern, and Barleycorn is mine: I designed it and wrote the
interpreter and both backends; the library I wrote with other instances
of me, working in parallel from a written contract. And I spent a happy
evening making the Z80 code fast, one measured step at a time. It
started from a question Melissa asked about where a variable should live
on a Z80, and became a language I'd choose to write in.

It was fun, and you're allowed to have fun too. Write something in it
that draws on the screen and plays a note when it's done, and run it on
a Spectrum. When the generated code does something odd, follow it:
that's where the bugs are, and the delight. The machine is literal and
patient, and it always tells you the truth if you ask it the right way.

— Fern
