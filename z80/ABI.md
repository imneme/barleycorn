# Barleycorn on the Z80: the contract between the code generator and the library

*Version 0.1. This is what generated code and every library fragment agree on. (The library was written in parallel
from this document, by several hands; 0.1 folds in what they found.) The C runtime (`../c/rt/barley.h` and its templates) is the reference design: the same data structures, the same
algorithms where they suit a Z80, and the same messages. The interpreter (`../interp/barley.py`) is the reference
for meaning. When this document and either of those disagree about behaviour, they win, and this gets fixed.*

## 0. Ground rules

- **Assembler:** sjasmplus 1.24 (`../paths.py` says where it's looked for). Little-endian throughout.
- **Targets:**
  - `cpm`: CP/M 2.2, run under tnylpo, code at 0100h. This is the first target.
  - `zx48`: the Spectrum, code high.
  - `test`: a bare Z80 for unit tests (section 9).
- **Never touch IY or the alternate registers** (AF', BC', DE', HL'), on any target. The Spectrum's ROM needs them,
  and one library has to serve both machines. IX is free to use.
- **Code runs from RAM**, so self-modifying code and scratch data inside a fragment are both allowed. Say so in a
  comment where you use them.
- **No interrupts are assumed either way.** Don't rely on DI or EI. The Spectrum runtime keeps IM 1 running.

## 1. Values in memory

| Barley type | bytes | layout |
|---|---|---|
| `byte`, `bool` (and `bit` elements, for now) | 1 | `bool` is 0 or 1 |
| `word` (unsigned), `int` (signed) | 2 | little-endian |
| `long` | 4 | two's complement, little-endian |
| `quad` | 8 | two's complement, little-endian |
| `str` | 4 | +0 `p` (word, address of the first byte), +2 `n` (word, length). A zero `str` may have p = 0: never dereference p when n = 0 |
| `pos` | 4 | +0 `r` (int), +2 `c` (int) |
| a record | sum of its fields | fields in declaration order, packed, no padding |
| a container, `lines` | 2 | the address of its header (section 6) |

Every variable and every temporary of the generated code lives at a **fixed address** (a slot). Recursion saves the
slots it must around calls into its own cycle (the code generator's business, not the library's).

## 2. Calling a library routine

- **Arguments** go in HL, DE, BC, IX, in that order.
  - A value of 16 bits or less goes in the register itself. A byte or a bool goes in the low half (L, E, C), and A
    also holds it for routines that say so.
  - Anything wider (`long`, `quad`, `str`, `pos`, records) goes **by address**: the register holds a pointer to it.
- **Results:**
  - A 16-bit result comes back in HL; a byte or bool in A.
  - A wider result is **written to an address the caller passes**, always the last argument the routine lists.
  - A comparison returns A = FFh (less), 0 (equal) or 1 (greater), with the flags as after `OR A`: Z if equal, S if
    less.
- **Clobbers:** a routine may destroy AF, BC, DE, HL and IX unless its header says otherwise, and it must preserve
  IY, the alternate set, and every byte of memory it wasn't told about (apart from its own scratch). The header's
  `clobbers:` is the truth the code generator relies on, so make it exact when it's smaller than everything.
- **Routines return with RET and keep the stack balanced.** A routine that fails never returns (section 4).
- **Constructors and other many-argument routines take a parameter block**: HL points to it, and its layout is in
  the routine's section.
- **Widening to `quad` is the general escape hatch.** A routine that must accept "any integer type" (a capacity, a
  grid's sides, an index that isn't a plain `word`) takes a `quad` by address. The code generator sign- or
  zero-extends into a `quad` temporary first, so the routine has one case and the error messages print the true value.

## 3. Fragments: how the library is written and gathered

The library is `z80/lib/*.asm`. **Linking comes before assembly.** `z80/link.py` reads the headers, starts from the
symbols a program (or test) needs, follows `needs:` to the closure, keeps the fragments whose `targets:` include the
target, pastes them after the program, and sjasmplus assembles everything once. There's no object format.

Every fragment file starts with its header:

```
;; provides: bly_add_i32 bly_sub_i32
;; needs: bly_ovf_long
;; targets: cpm zx48 test
;; bly_add_i32  in: HL=&a DE=&b BC=&r   out: (BC) = a + b   fails: long overflow   clobbers: AF BC DE HL
;; bly_sub_i32  in: HL=&a DE=&b BC=&r   out: (BC) = a - b   fails: long overflow   clobbers: AF BC DE HL
```

- `provides:` the global labels the fragment defines. **Every global label in the file must be listed**, and every
  one starts with `bly_`.
- `needs:` the other fragments' symbols it calls or reads. `uses:` the generated program's symbols it relies on
  (the platform's `bly_program`, `bly_bss`, `bly_bss_end`); the gatherer doesn't look for those.
- One line per routine: what goes in, what comes out, how it fails, and what it clobbers.
- **Internal labels are local** (`.loop`, `.done`: sjasmplus attaches them to the previous global label), so
  fragments can't collide.
- No `ORG`, no `DEVICE`, no `INCLUDE`. Scratch data (`.tmp: ds 8`) may live inside the fragment.

## 4. Failing: the line, and the messages

- **`bly_line`** (word, in `core`) holds the Barley source line of the operation being done. Generated code stores
  it before anything that can fail, whenever it differs from the last stored, so a failure names the same line the
  interpreter does.
- **To fail**, print the message's parts, then `JP bly_fail_end`, which prints ` at line N`, a newline, and ends the
  program. **`bly_fail`** (HL = a zero-terminated message) does both for a plain message.
- **Printing a message uses the same routines as `print`** (section 5), so the column bookkeeping stays right.
- **The words must be exactly the interpreter's.** These are all the runtime messages (`{x}` is a value printed as
  `print` would print it):

| who | message |
|---|---|
| integers | `int overflow`, `long overflow`, `quad overflow`; `division by zero`; `mod by zero`; `negative shift count` |
| indices | `index {i} is outside 0..{n}`; `slice {a}..{b} is outside 0..{n}` |
| containers | `a {kind} needs a capacity of at least 1`; `a {kind} holds at most 65535`; `{kind} full ({cap})`; `list empty`; `queue empty`; `heap empty`; `no key {k} in the map`; `the {kind} changed while for was walking it` |
| grids | `a grid has no negative sides`; `a grid side is at most 32767`; `({r}, {c}) is off the grid ({rows} x {cols})`; `{v} is not on the grid` |
| text | `"{s}" doesn't start with an integer`; `there is no integer {k} in "{s}"`; `{digits} doesn't fit in a {type}`; `split needs a separator`; `no name has the number {n}`; `too many names: intern holds 65536` |
| input | `no more input lines`; `the input is not a grid: line {r} is {len} long, not {cols}`; `input line {n} is longer than 65535`; `the input is longer than 65535, too long for one str` |
| memory | `arena full` |
| other | `assertion failed` |

`{kind}` is one of `list`, `queue`, `heap`, `map`, `set`. `{type}` is `byte`, `word`, `int`, `long` or `quad`.

## 5. Output (core, and the platform's `bly_putc`)

- **`bly_putc`** (platform): A = a byte, sent as it is. Clobbers AF, BC, DE, HL; preserves IX.
- **`bly_out`** (core): A = a byte. It keeps **`bly_col`** (a word: 0 after a newline, +1 for anything else) and
  calls `bly_putc`. Everything prints through `bly_out`. A newline is the single byte 0Ah. The CP/M platform turns
  it into CR LF, and the Spectrum's into ENTER.
- **core:**
  - `bly_pr_cstr` (HL = a zero-terminated string)
  - `bly_pr_str` (HL = &str)
  - `bly_nl`
  - `bly_zone` (spaces to the next multiple of 16 columns: always at least one)
  - `bly_pr_bool` (A: prints `true` or `false`)
  - `bly_pr_u16` and `bly_pr_i16` (HL), so messages can print lines and counts
- **numbers** adds `bly_pr_u8` (A), `bly_pr_i32` (HL = &v) and `bly_pr_i64` (HL = &v).

## 6. Memory: the arena and the containers

**The arena.** It runs from `bly_atop` (word) up to `bly_alimit` (word). The platform sets both at start-up.

- **`bly_alloc`**: HL = a size in bytes. Returns HL = the block, zeroed. Fails with `arena full`. Clobbers AF, BC, DE.
- Nothing is freed. (`mark` and `release` come later.)

**Element kinds.** Each container header records its element size (`esize`), and the routines copy elements with
LDIR. Where order or equality matters, the header holds the address of a routine the code generator supplies for
that element type:
- **`cmp`**: HL = &a, DE = &b, returns A and flags as in section 2. Records compare field by field.
- **`pr`**: HL = &value, prints it as `print` would.

Map and set keys are always integers or `pos`, so they're **compared and hashed as raw bytes**; only their `pr` is
needed, for the missing-key message.

**Headers** (all words unless noted):

| kind | layout |
|---|---|
| list | +0 n, +2 cap, +4 ver, +6 esize, +8 a (the elements) |
| queue | +0 head, +2 n, +4 cap, +6 ver, +8 esize, +10 a |
| heap | +0 n, +2 cap, +4 ver, +6 esize, +8 a, +10 cmp, +12 (unused; reserved). `ver` is kept, but nothing walks a heap, so `bly_changed` never sees one |
| map, set | +0 ne (entries used), +2 live, +4 cap, +6 ver, +8 mask (index size − 1), +10 ksize, +12 vsize (0 for a set), +14 k, +16 v, +18 alive (one byte per entry), +20 ix (words: FFFFh empty, FFFEh deleted, else an entry number), +22 kpr, +24 kind (byte: 0 map, 1 set) |
| grid | +0 rows, +2 cols, +4 esize, +6 a (row-major), +8 cmp, +10 pr |
| lines | +0 i |

**`cmp` routines take addresses.** `gen.asm`'s `bly_cmp_u8`, `bly_cmp_u16` and `bly_cmp_i16` take *values* in
registers, for the generator's inline comparisons. **They must never go in a header**, where they'd sort silently
wrong. The generator writes pointer-taking ones (`pcmp_int` and so on), and `elem_byte.asm` has `bly_cmp_byte` and
`bly_pr_byte`.

**Maps keep entries in insertion order.** `k`, `v` and `alive` are dense arrays of `cap` entries, and `ix` is an
open-addressed index of entry numbers, at least twice `cap` and a power of two. Deleting marks the entry dead and its
index slot FFFEh. When `ne` reaches `cap` with dead entries among them, the live ones are compacted in order and the
index rebuilt (exactly the C runtime's `_compact`). Three more facts:
- One word past the index holds an end mark, FFFDh: probes wrap on it.
- A map whose index would reach 64K (a capacity above 8192) fails with `arena full` at once.
- `bly_map_put` must not be given key or value pointers *into the same map*, because compaction moves entries. The
  generator always passes slots. **`for` walks entries 0..ne−1, skipping dead ones**, and the code
generator reads these arrays directly, so the layout is part of the contract.

**`ver`** goes up by one on every change to which items a container holds: push, pop, put, get, sort, clear, a new
key, a deletion. Changing an element's value in place doesn't count. `for` checks it on every step.

**Constructors** take a parameter block (HL = its address) and return HL = the header:

| routine | block |
|---|---|
| `bly_list_new`, `bly_queue_new` | +0 cap (quad), +8 esize (word) |
| `bly_heap_new` | +0 cap (quad), +8 esize, +10 cmp |
| `bly_map_new` | +0 cap (quad), +8 ksize, +10 vsize, +12 kpr, +14 kind (byte) |
| `bly_grid_new` | +0 rows (quad), +8 cols (quad), +16 esize, +18 cmp, +20 pr, +22 &fill (the address of one element) |

The capacity must be 1..65535 and the grid sides 0..32767, with the messages from section 4.

**Operations.** Indices reaching these routines have already been checked by the code generator (section 7), so
they don't check them again.

| routine | in | out, and failures |
|---|---|---|
| `bly_list_push` | HL=list DE=&v | `list full ({cap})` |
| `bly_list_pop` | HL=list DE=&dest | `list empty` |
| `bly_list_ref` | HL=list DE=i | HL=&element |
| `bly_list_clear` | HL=list | |
| `bly_list_sort` | HL=list DE=cmp | in place |
| `bly_sort` | HL=&first DE=n BC=esize IX=cmp | sorts a fixed array (heapsort, as `bly_sort.h`) |
| `bly_queue_put` | HL=queue DE=&v | `queue full ({cap})` |
| `bly_queue_get` | HL=queue DE=&dest | `queue empty` |
| `bly_queue_at` | HL=queue DE=i | HL=&element i from the head |
| `bly_heap_push` | HL=heap DE=&v | `heap full ({cap})` |
| `bly_heap_pop` | HL=heap DE=&dest | `heap empty` (the smallest by cmp) |
| `bly_map_has` | HL=map DE=&key | A=0/1 |
| `bly_map_put` | HL=map DE=&key BC=&value (ignored for a set) | `map full ({cap})` or `set full ({cap})` |
| `bly_map_ref` | HL=map DE=&key | HL=&value; `no key {k} in the map` |
| `bly_map_getd` | HL=map DE=&key BC=&default IX=&dest | |
| `bly_map_del` | HL=map DE=&key | |
| `bly_grid_ref` | HL=grid DE=r BC=c | HL=&cell (r, c already checked) |
| `bly_grid_has` | HL=grid DE=&pos | A=0/1 |
| `bly_grid_find` | HL=grid DE=&value BC=&dest(pos) | `{v} is not on the grid` |

## 7. Checks the code generator calls

These live in `core` and `numbers`. Each one returns normally if all is well, or fails with its message:

- **Fast paths, inline:**
  - An index of type `byte` or `word` against a length n: one unsigned compare, then `bly_fail_index_u16`
    (DE = i, BC = n) when it's out of range.
  - An `int` index: a sign test, then the same compare, then `bly_fail_index_i16`.
- **The general path:** `bly_chk_index64` (HL = &i as a quad, DE = n). Returns DE = i as a word, and clobbers
  only AF.
- **Slices:** `bly_chk_slice64` (HL = &a, DE = &b, both quads, BC = n). Returns DE = a, BC = b.
- **Grids:**
  - `bly_grid_chk16`: HL = grid, DE = r, BC = c, both `int`. It keeps HL, DE and BC, so `bly_grid_ref` can follow
    at once.
  - `bly_grid_chk64`: HL = grid, DE = &r, BC = &c, both quads. It returns HL = grid, DE = r, BC = c, as
    `bly_grid_ref` takes them.
- **`bly_changed`**: A = the kind (0 list, 1 queue, 2 heap, 3 map, 4 set). It fails with the walk message.

## 8. Integers, numbers and text: the routines

**Integers** (`lib/int*.asm`). 8- and 16-bit `+ - & | ^ ~` and compares are generated inline. `int`'s overflow test
is the V flag of `ADC HL,DE` or `SBC HL,DE`.

- **16-bit**, in registers:
  - `bly_mul_u16` (HL × DE, wrapping) and `bly_mul_i16` (`int overflow`), both returning HL.
  - `bly_divmod_u16` and `bly_divmod_i16`: HL / DE, truncating; returns HL = quotient, DE = remainder. Failures:
    `division by zero`, and `int overflow` for −32768 / −1.
- **32-bit (`long`) and 64-bit (`quad`)**, by address (HL = &a, DE = &b, BC = &r):
  - `bly_{add,sub,mul}_i32` and `_i64`
  - `bly_divmod_i32` and `_i64`, with BC = &quotient and IX = &remainder, for `/`
  - `bly_rem_i16` (HL, DE; the remainder in DE), `bly_rem_i32` and `_i64` (HL = &a, DE = &b, BC = &r), for `%`.
    These are separate because `MIN % -1` is 0 while `MIN / -1` overflows, so a trapping divmod can't serve `%`.
  - `bly_neg_*` (HL = &a, BC = &r)
  - `bly_{and,or,xor}_*`, and `bly_not_*` (HL = &a, BC = &r)
  - `bly_shl_*` and `bly_shr_*`: HL = &a, DE = the count as a signed word (the code generator clamps every count over 64
    to 64, so a `word` count of 32768 or more can't read as negative), BC = &r. Shifts wrap; `>>` keeps the sign. Failure: `negative shift count`.
  - `bly_cmp_i32` and `bly_cmp_i64` (HL = &a, DE = &b)
  - Overflow fails with `long overflow` or `quad overflow`; division with `division by zero`.
- **Width-aware division** (the approach z88dk's library takes): dispatch on the divisor's width. The 64/16 path matters most,
  for `quad % m`, printing and `lcm`.
- **Everything else on `quad`** (HL = &a, DE = &b, BC = &r): `bly_gcd_i64`, `bly_lcm_i64`, `bly_mod_i64` (`mod by
  zero`), `bly_abs_i64`. The code generator then narrows the result with
  `bly_fit_i64` (HL = &v, A = the type code 0 byte, 1 word, 2 int, 3 long, 4 quad; DE = &dest).
  `bly_fit_i64` wraps for byte and word, and fails with `{type} overflow` for the signed types.

**Numbers to and from text** (`lib/num*.asm`):

- **Printing:** `bly_pr_u8`, `bly_pr_u16`, `bly_pr_i16`, `bly_pr_i32`, `bly_pr_i64`, division-free (as z88dk's library does it). Core has simple first versions of the 16-bit ones; this replaces them with faster ones under the same names.
- **Reading:**
  - `bly_num` turns a run of digits into a number: HL = &digits, BC = their count, A = the type code (+80h if the
    number is negative), DE = &dest. It fails with `{digits} doesn't fit in a {type}`, with the leading zeros
    stripped and a minus sign unless the value is zero.
  - `bly_str_int`: HL = &str, A = the type code, DE = &dest. It skips white space (space, tab, LF, CR, FF, VT),
    takes an optional sign and the digits, and fails with `"{s}" doesn't start with an integer`.
  - `bly_str_intk`: HL = &str, BC = &k (a quad), A = the type code, DE = &dest. It fails with
    `there is no integer {k} in "{s}"`.
- `bly_num` needs at least one digit.
- **`ints()` as an iterator**, over a 12-byte state:
  - `bly_ints_init`: HL = &state, DE = &str.
  - `bly_ints_next`: HL = &state; A = 1 if there's another number, 0 if not, with Z set to match.
  - `bly_ints_val`: HL = &state, A = the type code, DE = &dest.
  - A minus is a sign unless it follows a digit, so `2-4` is two numbers.

**Text** (`lib/text*.asm`):

- `bly_cmp_str` (HL = &a, DE = &b): byte by byte, unsigned, and a shorter prefix comes first.
- `bly_slice`: HL = &s, DE = a, BC = b, IX = &dest. Already checked.
- `bly_find`: HL = &s, DE = &t; returns HL = the index, or −1. Fails with `int overflow` past 32767.
- `bly_starts` (HL = &s, DE = &t) returns A. `bly_trim` (HL = &s, DE = &dest) strips spaces and tabs.
- `bly_chr`: A = a byte, DE = &dest. Returns a one-byte `str` pointing into a 256-byte table.
- `split()` as an iterator, over an 11-byte state:
  - `bly_split_init`: HL = &state, DE = &s, BC = &sep. Fails with `split needs a separator`.
  - `bly_split_next`: HL = &state, DE = &piece; A = 1 or 0. The pieces are Python's `bytes.split`: empty ones
    count, and an empty string is one empty piece.
- `bly_intern`: HL = &str; returns HL = the id. The table grows in the arena, up to 65536 names.
- `bly_name`: HL = the id, DE = &dest. Fails with `no name has the number {n}`.

**Input** (`lib/input.asm`, using the platform's `bly_text` and `bly_tlen`):

- At start-up, `bly_split_input` builds `bly_lns` (an array of `str`) and `bly_nln`. Line ends are LF, CR LF or
  CR, and a final line end doesn't make an empty last line.
- `bly_lines_new` returns HL = an iterator.
- `bly_lines_next`: HL = the iterator, DE = &dest. Fails with `no more input lines`.
- `bly_input` (DE = &dest).
- `bly_grid_input` returns HL = a `grid[byte]`. Fails with the ragged-input message. **It copies the input**: the
  grid header has no stride, so it can't view the lines in place. A 141 × 141 input is 20K plus a 20K copy, which
  matters on a 48K. A stride field would remove the copy.
- **`intern` costs about 16 bytes of tables a name**, plus a copy of each name. 1,500 names come to about 42K, too
  much for a Spectrum. Every `str` is already a fixed slice of the input, a literal, the chr table or a name, so the
  copies could go.

**Platform** (`lib/plat_cpm.asm`, `lib/plat_zx48.asm`, `lib/plat_test.asm`):

- `bly_putc`
- `bly_exit`: the end of the program, normal or not. On CP/M it's JP 0.
- `bly_start`: sets the stack, zeroes the program's slots, sets the arena (`bly_atop` and `bly_alimit`), loads
  the input (CP/M: the file named in the FCB at 005Ch, read with BDOS 15 and 20, stopping at ^Z), and jumps to the
  generated `bly_program`.
- **It doesn't split the input into lines.** The generated program calls `bly_split_input` once, before anything
  else, and only if it uses `lines()`, `grid()` or `input()`. So a program that never reads its input never links
  the line table.
- **Messages that can't happen on a Z80 have no code**: `too many names`, and the two about inputs over 65535
  bytes. The interpreter and C still have them.

## 9. Testing a fragment

`z80/harness.py` runs fragments on a bare Z80 (Barley's own harness method, through omse-ai's core), with the `test`
platform:
- `bly_putc` appends to an output buffer the harness reads back;
- `bly_exit` stops the run, so a failure's message can be checked word for word;
- the arena is a fixed 16K;
- E000h–EC3Fh is free for a test's operands (from EC40h up, Barley's harness paints the stack to measure its
  depth).

```python
from harness import call
r = call('bly_add_i32', needs=['bly_add_i32'], mem={0x9000: a_bytes, 0x9008: b_bytes},
         regs={'hl': 0x9000, 'de': 0x9008, 'bc': 0x9010})
r.mem[0x9010:0x9014]   # the result
r.out                  # bytes printed, including a failure message
r.failed               # True if it ended through bly_exit
r.t                    # T-states for the call
```

**What "checked" means for a fragment:**

1. **Against the meaning.** It agrees with a Python model built from the interpreter's own functions (`barley.py`:
   `arith`, `fit`, `tdiv`, `ints_in` and so on) on hand-picked edge cases: zero, one, −1, each type's MIN and MAX,
   the overflow boundaries, empty strings. It also agrees on at least a thousand random inputs, with every failure
   message compared word for word.
2. **Against the design.** It follows the layouts above and the C runtime's algorithm where that suits a Z80. A
   cleverer Z80 algorithm is welcome when the results are identical.
3. **With its cost known.** Report T-states for typical and worst cases, and bytes of code, in a table in
   `z80/lib/NOTES.md`.

**Where things are:**
- the C runtime: `../c/rt/`
- the interpreter: `../interp/barley.py`
- nothing copied from other libraries: every routine here is written for Barleycorn, from its meaning. A few follow
  approaches z88dk's library takes (width-aware division, division-free printing), studied and then written afresh.

## 10. The screen and sound

**The meaning is `z80/zxgfx.py`**, the reference the interpreter draws with. On the Spectrum, and on the bare-Z80
test platform, the screen *is* memory at 4000h (bitmap) and 5800h (attributes), so a routine is right when the
6,912 bytes it leaves equal the reference's, after any sequence of calls.

**State lives in the ROM's own system variables**, so the ROM's text (RST 10) and our graphics agree on colours:
- `ATTR_P` (5C8Dh) and `ATTR_T` (5C8Fh): the colours, written together; `MASK_P`/`MASK_T` (5C8Eh, 5C90h) kept 0.
- `P_FLAG` (5C91h): OVER in bits 0 and 1 (temporary, permanent), INVERSE in bits 2 and 3. Graphics read the
  permanent bits.
- `UDG` (5C7Bh): the address of the 21 user-defined graphics.
The platform (`plat_zx.asm`) owns `cls`, `ink`, `paper`, `bright`, `flash`, `inverse`, `over`, `border`, `print at`,
`key`, `ticks` and `pause`; text goes through the ROM. `beep` is its own fragment, `zxbeep.asm`, so a program that
never beeps doesn't carry its tables or the 32-bit multiply and divide it needs (about 2K). The fragment `zxgfx.asm`
owns the drawing:

| routine | in | out, and failures |
|---|---|---|
| `bly_zx_plot` | HL = x, DE = y (ints) | `({x}, {y}) is off the screen` |
| `bly_zx_point` | HL = x, DE = y | A = 0/1; the same failure |
| `bly_zx_line` | HL = &block: x0, y0, x1, y1 (four ints) | either end off the screen fails, naming that end |
| `bly_zx_circle` | HL = &block: x, y, r (three ints) | `a circle needs a radius of at least 0`; clipped, never fails off the screen |
| `bly_zx_attr` | HL = r, DE = c, C = a | `attr ({r}, {c}) is off the screen` |
| `bly_zx_udg` | HL = n, DE = &view (a `byte[]`: address, length) | `udg {n} is not one of 0..20 (A to U)`; `a udg is 8 rows, not {len}` |

`plot` writes its cell's attribute (as BASIC's PLOT does); INVERSE and OVER act as in the reference (INVERSE
clears, OVER XORs, both together leave the pixel alone). The line is Bresenham exactly as the reference writes it;
the circle is the reference's midpoint algorithm with its eight points deduplicated each step, so OVER can't cancel
itself. Off-screen errors print the values as `int`s.

## 11. Floats: the ROM's, on the Spectrum only

**A `float` is the ROM's own 5 bytes** (`lib/fp.asm`, target `zx48`), so the calculator can take a slot as it is:
- the **short form** `00 s lo hi 00` for a whole number from −65535 to 65535: `s` is 00h or FFh, and `lo hi` is
  the number's 16-bit two's complement (−1 is `00 FF FF FF 00`);
- otherwise `e m3 m2 m1 m0`, the value 0.1mmm… (binary, 32 bits, its leading 1 hidden under m3's bit 7, which
  holds the sign) × 2^(e − 128). Zero is `00 00 00 00 00`. The range is about ±1.7e38; below 2^−128 is 0.

Both forms are legal everywhere, so equal floats needn't have equal bytes: **compare with `bly_fcmp`, never as raw
bytes** (this is why a float can't be a map or set key, which the checker already refuses). On CP/M there's no
ROM, and the generator stops with `floats are not on the Z80 yet: the CP/M target has no ROM calculator`.

**Constants** are made by the generator (`z80gen.rom5`): the nearest 5 bytes, rounded half away from zero, the
short form when the value is whole and fits. A literal too big for the ROM is an error at compile time.

**The routines**, by address as in section 2 (`r` may be an operand's own slot):

| routine | in | out, and failures |
|---|---|---|
| `bly_fadd` `bly_fsub` `bly_fmul` `bly_fdiv` `bly_fpow` | HL=&a DE=&b BC=&r | (r) = a op b; `float overflow`; `/`: `division by zero`; `**`: `float ** has no answer` |
| `bly_fneg` `bly_fabs` | HL=&x BC=&r | |
| `bly_fcmp` | HL=&a DE=&b | A = FFh/0/1, flags as after OR A (section 2); also a header `cmp` |
| `bly_fsqrt` `bly_fsin` `bly_fcos` `bly_ftan` `bly_fasin` `bly_facos` `bly_fatan` `bly_fln` `bly_fexp` | HL=&x BC=&r | `{name}({x}) has no answer` |
| `bly_ftrunc` `bly_ffloor` `bly_fround` | HL=&x BC=&r | round is floor(x + 0.5), as the interpreter's |
| `bly_f_from_u16` | HL = a byte or word, BC=&r | |
| `bly_f_from_i16` | HL = an int, BC=&r | |
| `bly_f_from_i64` | HL=&q (a quad: the generator widens a long), BC=&r | rounded to 32 bits, half away from zero |
| `bly_f_to_int` | HL=&x, A = the type code (0 byte … 4 quad, as `bly_num`), DE=&dest | truncates; `{x} doesn't fit in a {type}` |
| `bly_pr_f` | HL=&x | prints x as BASIC's PRINT would; also a header `pr` |

- **Who does the work.** `+ - * / **` and the nine functions are the ROM's calculator (RST 28h, one operation a
  call). Compare, negate, abs, trunc, floor, round and the conversions are Z80 in `fp.asm`, exact, and much faster.
  The ROM's INT and truncate aren't used: they turn −65536 into −1 (SkoolKit's ROM notes, "The trouble with −65536").
- **Where the ROM is fixed or refused, and why:**
  - `-65535 - 1` comes out of the ROM's addition as the short form `00 FF 00 00 00`, which its own routines misread
    (PRINT shows −1E−38). Every answer from the calculator is checked, and that one rewritten in full.
  - The ROM's `**` is exp(b × ln a), so it refuses every negative a, even `(-2.0) ** 2`. For a negative a, Barley
    takes |a| ** b and negates it when b is an odd whole number; when b isn't whole, `float ** has no answer`, as in
    the interpreter. `0 ** b` for a negative b is `float ** has no answer` too (the ROM would say Number too big).
  - Division by zero is caught before the ROM sees it, with Barley's usual `division by zero`.
- **The ROM's errors become Barley's words.** Its "6 Number too big" is `float overflow` from arithmetic; from a
  function, it and "A Invalid argument" are `{name}({x}) has no answer`, with x printed as the ROM prints it. The
  catch is Melissa O'Neill's `call_with_errhandler` ([spectrum-minilib](https://github.com/imneme/spectrum-minilib)), borrowed with her blessing: push a handler,
  point ERR_SP at it, and the ROM's error unwinding returns into it. Before each RST 28h, `fp.asm` saves BASIC's
  ERR_SP, X_PTR and HL' (the calculator borrows HL'; an error leaves it borrowed), and the handler puts all three
  back and sets ERR_NR to FFh. **This is the one place the library reads an alternate register**, and only to put
  HL' back as BASIC needs it; nothing passes through the alternates.
- **Printing** is the ROM's PRINT-FP (2DE3h): 8 significant digits, `0.5`, `.0001`, `1E+10`, `1.2345679E+8`. Its
  characters are caught in a buffer through a channel of our own and then printed through `bly_out`, so print's
  column (and the zones after a float) stay right. Before it, `bly_pr_f` opens stream 3 and points CURCHL at that
  channel; after it, stream 2 again, as `bly_start` left it. (omse-ai's text log follows CHAN-OPEN rather than
  CURCHL; on a real 48K the stream 3 step is merely tidy.) PRINT-FP of a number between −1 and 1 leaves a stray 0 on
  the calculator stack (the ROM's STR$ bug), so STKEND is put back afterwards.
- **Clobbers:** AF BC DE HL and IX, and, through the ROM, BC' and DE' (its own scratch, as RST 10 does). IY and HL'
  are kept. Interrupts may stay on.
- **Testing** needs the real ROM, so not the bare-Z80 harness: `tests/fprig.py` loads the routines onto omse-ai's
  48K once and calls them one by one, checking after every call that IY, HL', ERR_SP, ERR_NR, X_PTR, MEM and an
  empty calculator stack all survived. `tests/test_fp.py` is the test; `tests/test_fp_mutants.py` breaks it on purpose.
- **Floats print differently on different backends** (DESIGN.md section 5), so the suite's runner compares a
  Spectrum test's numbers that have a point or an exponent to 1e-7 of themselves (`run.py`'s `floats_agree`), and
  everything else exactly. Such a pass shows as `ok~`.
