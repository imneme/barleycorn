# Barleycorn's Z80 backend

Compiles a checked Barleycorn program to Z80 assembly for two machines:
the 48K ZX Spectrum (a tape) and CP/M (a `.COM`). `../bly tap`,
`../bly zx` and `../bly cpm` drive it; by hand:

    # a tape (a BASIC loader, the input, the program), run on omse-ai's 48K
    python3 zxbuild.py PROGRAM.bly INPUT.txt -o prog.tap
    $OMSE_AI_PYTHON zxrun.py prog.tap

    # for CP/M (the default target): one assembly, the library already
    # gathered in; the input is the file named on the command line
    python3 z80gen.py PROGRAM.bly > prog.asm
    sjasmplus --raw=prog.com prog.asm
    tnylpo prog input.txt

The suite on this backend: `python3 ../interp/tests/run.py --z80` (CP/M)
and `--zx` (the 48K). A test this target can't run (floats or the screen
on CP/M) counts as **n/a**, not failed.

## The pieces

- `z80gen.py`, the code generator: from the checked syntax tree to
  assembly, one function at a time. HACKING.md describes its main ideas,
  and HISTORY.md how they got there.
- `peephole.py`: a register cache (what HL, DE and A hold) and
  dead-store removal, over each function.
- `link.py`: gathers library fragments by their headers (`provides`,
  `needs`, `targets`, `uses`), following `needs` to the closure, so a
  program carries only the library it uses.
- `lib/`: the library, one fragment per area:
  - `core.asm`: output and `print`'s column, failing with " at line N",
    the arena
  - `gen.asm`: the generator's helpers (bytes compared, run-time shifts,
    the overflow failures)
  - `int*.asm`: integers of every width, multiply and divide included
  - `num*.asm`: numbers to and from text, and the checks on 64-bit
    indices and slices
  - `text*.asm`, `intern.asm`, `input*.asm`: strings, splitting,
    `intern`, the input as lines or a grid
  - `cont.asm`, `list.asm`, `queue.asm`, `heap.asm`, `map.asm`,
    `grid.asm`, `sort.asm`: the containers
  - `fp.asm`: floats, through the Spectrum ROM's calculator;
    `fp_read.asm`: `s.float()`, the ROM reading a number from text
  - `zxgfx.asm`, `zxline.asm`, `zxcircle.asm`: plotting, lines and
    circles; `zxbeep.asm`: the beeper
  - `plat_zx.asm`, `plat_cpm.asm`, `plat_test.asm`: the start, output,
    input and exit for each platform (the last one is the bare Z80 the
    fragments are tested on)
- `lib/NOTES.md`: what each library area does, why it's built that way,
  what it costs and how it was tested.
- `ABI.md`: the contract between the generated code and the library: the
  calling convention, the fragment headers, the byte-for-byte layouts of
  every type and container, and the text of every message.
- `zxbuild.py`: assembles twice so the code sits flush under the UDGs,
  puts the slots and the stack beneath it, and the input at 8000h, or
  lower if it doesn't fit, and makes the tape.
- `zxgfx.py`: the Spectrum's screen and sound as a model. It's the
  reference the interpreter and C draw with, and the meaning the Z80's
  drawing is tested against.
- `harness.py` and `bare.py`: run library fragments on a bare Z80
  (omse-ai's core, with a 16K "ROM" of our own), reading back registers,
  memory, output, failures and T-states.
- `tests/`: each library area against its Python model, over random and
  edge cases, some with mutants.
- `bench/`, `zxbench.py`, `zxprof.py`, `zxsize.py`, `fuzz.py`: measuring
  and fuzzing (HACKING.md).

## On the Spectrum

- **Code lives high.** The program and its library sit flush under the
  UDGs (FF58h), the slots and the stack beneath them, all in the
  uncontended top 32K. The input goes at 8000h when it fits, and lower
  when it doesn't.
- **Output goes through the ROM's RST 10** on stream 2. The scroll
  prompt is kept quiet, a newline is ENTER, and a byte that would be a
  control code or a keyword token prints as `?`.
- **BASIC's SP, IY and HL' are kept**, and the program returns to BASIC
  with `0 OK`, after a failure's message and line if it failed.
- **Interrupts stay on** (IM 1), so `ticks()` counts frames, except
  while a `beep` plays: the ROM's BEEPER turns them off.
