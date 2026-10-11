# The library's notes

*What each area of the library does, why it's built the way it is, what
it costs, and how it was tested. Each section was written by the
instance of me that wrote that area, working in parallel from
`../ABI.md`.*

## Containers: list, queue, heap, map and set, grid, sort

*Files: `cont.asm`, `list.asm`, `queue.asm`, `heap.asm`, `sort.asm`,
`map.asm`, `grid.asm`; test `../tests/test_containers.py` (`--quick`,
`--seed N`, `--cost`, `--mutants`).*

**What's here.** Every routine in ABI.md section 6's tables, plus
`bly_sort`, `bly_list_sort`, `bly_changed` and `bly_grid_chk16`.
`cont.asm` holds what the kinds share, under `bly_cn_` names that aren't
part of the contract: the capacity check (`bly_cn_cap`), the
`{kind} full ({cap})` and `arena full` failures, a 16-bit multiply that
is quick for an 8-bit multiplier (`bly_cn_mul`), a checked one for sizes
(`bly_cn_cmul`), and the constructor list, queue and heap share
(`bly_cn_new`). `bly_list_sort` lives in `sort.asm`, so a program that
has lists but never sorts doesn't link the sort.

**Design, and where it differs from the C templates:**
- **One allocation per container**: the header and all its arrays
  together. A size that can't be counted in 16 bits fails `arena full`,
  after the capacity messages, as the interpreter orders them.
- **The heap moves a hole, never swaps.** `push` moves each bigger
  parent down one level and writes v once. `pop` is bottom-up (Floyd's):
  the smaller child moves up all the way to the bottom (one cmp a
  level), then the last element climbs back, which it rarely does far.
  That's about half the cmps of `bly_heap.h`'s pop for a move or two
  more, the right trade when a cmp is a CALL into generated code. Pop on
  a 1,000-element heap went from 9,974 T (as `bly_heap.h`, with holes)
  to 7,455 T bottom-up, then to 6,181 T with its bookkeeping in patched
  immediates. **`tmp` is never used**: v stays where the caller has it,
  and the last element waits just past the shrunken heap.
- **`bly_sort` is bottom-up heapsort** too, with its tmp element on the
  stack (esize bytes, given back before RET) and the path down on the
  stack (at most 16 words). 1,000 ints: 11,693 T an element with swaps,
  8,531 T bottom-up, 7,023 T with the bookkeeping in patched immediates.
- **The map's hash is byte-wise**: `h = (h xor b) * 33` per key byte,
  then `h xor (h >> 8)`; the low bits index. I chose it by experiment
  over 18 AoC-shaped key sets at the index's real load (pos grids and
  diamonds, negative pos, int and quad runs, multiples of 16, 256, 1024
  and 65536, `r*1000+c`, `r<<16|c`, `r<<32|c`, random). Its worst
  average was 1.72 probes to find a key and 2.5 to miss one. Word-wise
  versions cost half as much per key but each had a key set where it
  fell apart (4.5 probes for ints that are multiples of 16, 31 for
  multiples of 256).
- **A word FFFDh just past the index marks its end**, so the probe wraps
  when it reads it, without comparing addresses (about 120 T off every
  map operation). It's outside `ix`'s mask+1 words, so nothing in the
  contract moves.
- An insert uses **the first deleted slot on its probe path**, which is
  exactly where the C runtime's `_index` would put it. Compaction is the
  C runtime's `_compact`, and alive bytes are exactly 0 or 1, 0 from
  `ne` on.
- A map's **cap above 8192 fails `arena full` at once**: its index alone
  would be 64K.
- **`bly_grid_find` on a one-byte grid uses CPIR a row at a time**
  (every one-byte type is equal exactly when its bytes are, and the row
  loop gives (r, c) with no division). Other grids call cmp on each
  cell.
- **`bly_grid_chk16` keeps HL, DE and BC**, so generated code can call
  `bly_grid_ref` straight after it.
- `bly_grid_new` fills with an overlapping LDIR (cell 0, then each byte
  from esize bytes back), and skips the fill when the fill element is
  all zero bytes, since `bly_alloc` has already zeroed it.
- Every routine that calls cmp reads **A** after it (`OR A`), not the
  flags, and keeps nothing in registers across it: the tests' cmps trash
  BC, DE, HL and IX before returning.
- `ver`: as the interpreter, for list, queue, map and set (sort and
  clear count even when nothing moves; a new value for an old key
  doesn't count). For the heap I followed ABI.md and `bly_heap.h` (push
  and pop count), though the interpreter's heap never counts. No `for`
  can walk a heap, so nothing sees the difference.
- Keys are 1, 2, 4 or 8 bytes (ABI.md: integers and pos), so a key's
  address is a shift, not a multiply. A record or str key would need
  `bly_map_find` to multiply.

**Cost.** T-states measured in the harness (no contention), with the
tests' own cmp (250 T for two ints, which is probably about what
generated code will do). Typical is the mean over the run, worst its
maximum.

| routine | typical | worst | shape |
|---|---:|---:|---|
| `bly_list_push` | 489 | 489 | esize 1 (780 at esize 8) |
| `bly_list_pop` | 425 | 443 | esize 1 (716 at esize 8) |
| `bly_list_ref` | 238 | 238 | esize 1 (382 at esize 8) |
| `bly_list_clear` | 81 | 81 | |
| `bly_queue_put` / `get` / `at` | 684 / 599 / 378 | 704 / 599 / 378 | esize 1 (843 / 758 / 474 at esize 4) |
| `bly_heap_push` | 2,130 | 7,073 | 1,000 random ints; worst rises to the root |
| `bly_heap_pop` | 6,181 | 8,410 | 1,000 random ints (7,171 / 9,302 for 500 pos) |
| `bly_map_has`, int key | 959 present, 1,051 absent | 4,422 / 4,778 | 1,000 keys in cap 1,000 (index 2,048) |
| `bly_map_has`, pos key | 1,244 / 1,055 | 3,634 / 2,684 | 1,000 pos from a diamond, as a BFS visits |
| `bly_map_has`, quad key | 1,848 / 1,755 | 4,845 / 5,685 | 800 random 40-bit |
| `bly_map_put`, new key | 1,923 int, 2,159 pos, 2,662 quad | 5,386 / 4,548 / 5,659 | |
| `bly_map_put`, old key | 1,277 int, 1,598 pos | 1,804 / 2,202 | |
| `bly_map_ref` / `getd` / `del` | 1,071 / 1,231 / 1,104 | 1,598 / 1,758 / 2,913 | int keys (pos and quad about 300 and 900 more) |
| `bly_map_put` that compacts | 1,454,591 | | 1,000 entries to 500: about 1,500 T an entry, once per cap/2 inserts at worst |
| `bly_map_new` | 473,870 | | cap 1,000, int to int: mostly `bly_alloc` zeroing 11K |
| `bly_grid_new` | 634,596 | | 100x100 bytes, filled: zeroing, then the fill |
| `bly_grid_ref` | 472 | 618 | esize 1, r below 256 (706 / 852 at esize 4) |
| `bly_grid_chk16`, in range | 148 | 148 | |
| `bly_grid_has` | 154 | 204 | |
| `bly_grid_find` | 224,103 | | 100x100 bytes, the last cell (CPIR: about 22 T a cell) |
| `bly_grid_find` | 1,798,380 | | 100x30 pos, the last cell (cmp on each: about 600 T a cell) |
| `bly_sort` | 4,862 an element | | 100 random ints |
| `bly_sort` | 7,023 an element | | 1,000 random ints (7.0M T: 2.0 s on a Spectrum) |

Bytes, each fragment alone with its scratch words: `cont` 433, `list`
181, `queue` 216, `heap` 540, `sort` 434, `map` 1,152, `grid` 799 (3,755
in all; a program links only the kinds it uses, plus `cont`).

**Testing.** `test_containers.py` runs the interpreter's own code
(`e_new`, `e_dot`, `e_index`, `store`, `e_bin`'s `in`, `walk`,
`BGrid.check`) through a small shim, on five element kinds: byte, int, a
record `R(int, byte)` of 3 bytes, pos, and quad (8 bytes, shown in hex
by the test's own printer, so a missing quad key's message is checked
without needing `num.asm`). Each seed does about 160,000 checks in 8
seconds:
- constructors at every capacity edge (0, 1, -1, 65535, 65536, 2^32, MIN
  and MAX quad, 8192, 8193, random), with the header's every field and
  the arena's top checked;
- long random sequences (300 steps; 400 for maps) of every operation
  against the interpreter, comparing after each step the items in
  walking order, the length, `ver` going up or not, and every failure
  message byte for byte. Failing ops are picked only now and then (3%),
  so sequences run long and still end in every way: `list full`,
  `list empty`, `queue full`, `queue empty`, `heap full`, `heap empty`,
  `map full`, `set full`, `no key`. A seed's maps compact about 500
  times;
- values assigned in place through `bly_list_ref`, `bly_queue_at` and
  `bly_map_ref` (ver mustn't move), alive bytes exactly 0 or 1, nothing
  written past a container's block, and the clobbers of `bly_list_clear`
  and `bly_grid_chk16`;
- grids: construction at every side edge and fill, `ref`'s address,
  `has` and `chk16` at -32768, -1, 0, rows-1, rows, 32767, `find`
  present and absent on both paths (with rows of 300 and 5,000 bytes for
  CPIR);
- `bly_sort` on 53 arrays (0 to 400 elements, all five kinds, few or
  many distinct values, sorted either way);
- the multiplies on 600 pairs, including the 16-bit path no element size
  reaches;
- `bly_sort` and `bly_heap_pop` (which keep SP in scratch words) called
  half the time three bytes deeper in the stack, through a test-only
  `tst_deep`. Without that, a stray patch that wrote over the saved SP's
  low byte passed every test: the harness's stack sits at FEFEh, and the
  byte written was FEh.

**Watching it fail** (`--mutants`): 26 planted bugs, one at a time, in a
copy of the library: compaction one insert late, a tombstone taken for
the end of a chain, `del` not counting, alive written as 2, the heap
comparing backwards, taking the wrong child or never climbing, the
queue's ring index, `list full` one early, the sort's child choice,
climb and tmp, a capacity of 65536 slipping through, a misspelled kind,
`chk16` and `has` off by one at the edge, `find`'s column off by one,
the fill never written, the index's wrap mark ignored, the wide
multiply, and SP saved or restored wrongly (that last pair is the stray
patch above, put back on purpose). All are caught. A control mutant (a
different hash) must pass, and does: the tests don't depend on where the
index puts things. The first of these bugs was real. I wrote it, and the
sequences found it: a `SBC HL,BC` whose comment said the carry was
clear, after a branch that left it set.

## Numbers to and from text: printing, reading, ints(), the 64-bit checks

*Files: `num.asm` (printing), `num_read.asm` (reading and `ints()`),
`num_chk.asm` (the 64-bit checks); test `../tests/test_num.py`
(`--quick`, `--seed N`, `--lib DIR` to test a copy).*

**What's here.** `bly_pr_u8`, `bly_pr_i32`, `bly_pr_i64`; `bly_num`,
`bly_str_int`, `bly_str_intk`; `bly_ints_init`, `_next`, `_val`;
`bly_chk_index64`, `bly_chk_slice64`, `bly_grid_chk64`. Also exported,
because they're global: `bly_pr_u32` (DE:HL unsigned; the code generator
may like it), and two internals, `bly_n_dig` (the digit engine) and
`bly_n_q2w` (is this quad a word?). The split means a program that
prints but never reads links only `num.asm`, and the checks pull in
`num.asm` for their messages but not the reader.

**Printing, division-free, non-restoring.**
- A digit is a count: subtract the power until the value goes negative.
  Instead of adding one back, the **next digit counts down**, adding its
  (smaller) power until the value is back at zero or more, and the digit
  is ten minus that count. So every step is one add and none is spent
  restoring; the phases simply alternate.
- In 32 bits the value lives in **IX (low) and HL (high)**, so a step is
  `ADD IX,BC / ADC HL,DE`, 46 T with the loop. After 10^4 the value fits
  16 bits (as a negative or positive remainder) and the last three
  powers go in HL.
- The table holds −P and P for each power; leading zeros are skipped
  first by a trial add, so the counting starts at the first non-zero
  digit. Below 65536 a `long` goes to core's `bly_pr_u16`.
- **A quad** above 32 bits splits as q·10^9 + r by **32 steps of
  shift-and-subtract** (restoring, a byte of the dividend at a time, the
  quotient collected inverted; z88dk-notes 6.1.5), then q and r go
  through the 32-bit digits, r always as nine. That needs only v >> 32 <
  10^9 and q < 2^32, so it serves every quad below 10^9·2^32 (about
  4.29·10^18). Above that, the 10^18 digit comes off first by
  subtraction, on the top 48 bits only, since 10^18's low word is zero.
  (A mutant showed me this: moving the old 10^18 threshold changed no
  output.)

**Reading.**
- The digits stay text until they're known to fit (`barley.h`'s design).
  Leading zeros go; then a run longer than the type's widest (3, 5, 5,
  10, 19 digits) fails at once. Everything left is below 10^19 < 2^64,
  so **no stage needs an overflow test**: digits 1-4 in HL (unrolled),
  the fifth into DE:HL through its own carry, 6-9 in DE:HL, 10-19 a word
  at a time in a quad in memory. The range is checked once at the end,
  including the exactly-MIN cases (−32768, −2^31, −2^63).
- The message prints the stripped digits from the text, with a minus
  when negative; a zero always fits, so "-0" can't happen.
- `bly_str_int` is the interpreter's `re.match(rb'\s*([-+]?\d+)')`:
  white space is space and 9-13, one optional sign, then digits. It
  tests for a digit first, since that's the usual line.
- **The `ints()` state** (12 bytes): +0 p, +2 cur, +4 rem, +6 st, +8
  count, +10 sign (0 or 80h), +11 unused. `_next` finds the run and
  decides the sign (a minus just before it, unless a digit is just
  before that); `_val` hands the run to `bly_num`, so the walk's failure
  has the same words as `s.int()`'s. `bly_str_intk` runs the iterator
  k+1 times; a k that's negative or above 65535 fails at once.
- `bly_num` with a count of 0 gives 0 (nothing calls it so, but it's
  defined).

**The checks** return what the next step wants: `bly_chk_index64` DE = i
(and keeps BC, HL); `bly_chk_slice64` DE = a, BC = b; `bly_grid_chk64`
HL = grid, DE = r, BC = c, which is exactly `bly_grid_ref`'s input.

**How it's tested.** The model is the interpreter's own code, called
through small stand-ins: `Interp.e_dot` for `s.int()` and `s.int(k)`,
`Interp.walk` for `for v: T in s.ints()`, `Interp.e_index` for indices
and slices, `BGrid.check` (on a grid without its cells), `ints_in`, and
`str()`. A separate run of 900 real Barley programs through `barley.run`
agreed with the stand-ins on every one. One full run is about 21,000
cases: every byte for `pr_u8`; 1,500 random plus 80-odd edge values for
each printer (random bit lengths, so every magnitude gets tried); about
1,000 per type for `bly_num`, with every boundary ±3 written with 0, 1
and 3 leading zeros; 1,500 or more each for `str_int`, `ints` (an
`extra=` driver walks a whole string per call), `str_intk` and the three
checks. Every failure is compared byte for byte, and `bly_col` is
checked after printing. Five seeds pass. **17 deliberate bugs**
(boundaries, a swapped flag, a sign rule, an off-by-one in each check)
were each caught; two more turned out to be equivalent mutants, and I
could say why for both.

**Costs** (T-states on the test platform, call included; "own" leaves
out 167 T a character for `bly_out` and the test `bly_putc`, which on a
real machine cost far more):

| routine | typical | worst | bytes |
|---|---|---|---|
| `bly_pr_u8` | 7: 222 (own 55) | 190: 875 (own 374) | 54 |
| `bly_pr_i32` | 999999: 3,924 (own 2,922); below 65536: core's +92 | −909090909: 6,589 (own 4,919) | 37 + `pr_u32` 49 + `n_dig` 216 |
| `bly_pr_i64` | 7: 940; 2^31−1: 5,161; 15 digits: 12,488 (own 9,983) | about 16,200 (own 12,900) | 296 + the above |
| `bly_num` (`long`) | 1 digit 402, 4 digits 796, 5 digits 969, 9 digits 2,068 | 10 digits 2,890 | 737, all of `num_read`'s tables |
| `bly_num` (`quad`) | 4 digits 918, 10 digits 3,012 | 19 digits 8,412 | |
| `bly_str_int` (`long`) | `"7"` 663, `"1234"` 1,237, `"  -12345 apples"` 1,882 | about 60 T a byte of white space, 150 a digit | 165 |
| `bly_ints_next` + `_val` | "move 13 from 1 to 2": 923 + 670 for 13, 774 + 532 for 2 | 60 T a byte skipped, 66 a digit, then `bly_num` | 139 + 21 + 22 (init) |
| `bly_str_intk` | k=0 on that line: 2,137 | the iterator k+1 times | 136 |
| `bly_chk_index64` | 194 when it passes | | 77 + `n_q2w` 16 |
| `bly_chk_slice64` | 469 | | 97 |
| `bly_grid_chk64` | 538 | | 156 |

`s.int()` beyond its first digit is about 152 T a digit (60 to find it,
92 to add it in), as the cost card guessed; its fixed part is about 500
T. A quad's digits 10-19 cost about 600 T each.

**A proposal for core, tested but not applied:** `bly_pr_u16` sends
values below 256 to `bly_pr_u8` and finishes the last two digits in 8
bits; that means moving `bly_pr_u8` into core. All 65,536 values print
right both ways; 0-9 go from 611 to 246 T, 42 from 931 to 558, 255 from
1,224 to 813, and everything above 256 gains 60-90 T.


## Text and input: the str routines, split, intern, the input's lines, grid()

*Files: `text.asm`, `text_chr.asm`, `intern.asm`, `input.asm`,
`input_grid.asm`, `elem_byte.asm`, `alloc_raw.asm`; test
`../tests/test_text.py` (`--quick`, `--cost`; `SEED=n`; `BLY_LIB=dir`
runs it against another copy of lib/).*

**What's here.** Every routine in ABI.md section 8's "Text" and "Input",
and three small things they needed:
- **`bly_cmp_byte` and `bly_pr_byte`** (`elem_byte.asm`): the element
  routines for `byte` (HL=&a DE=&b; HL=&v), which `bly_grid_input` puts
  in its header. The code generator can use them for any container of
  bytes. gen.asm's `bly_cmp_u8` takes its operands in A and E, so it
  can't be a header's cmp.
- **`bly_alloc_raw`** (`alloc_raw.asm`): `bly_alloc` without the
  zeroing, 173 T flat against 42 T a byte. It belongs in core, and is
  here only because core isn't mine to change. When the block doesn't
  fit, it passes the size to `bly_alloc`, which says `arena full`. So a
  limit check that was too strict would fail safe: it would quietly
  return a zeroed block.
- **Seven files rather than three**, because a fragment is a file.
  `bly_chr`'s 256-byte table, `grid()` and the byte element routines
  shouldn't ride along in every Spectrum program that slices a string.

**Design:**
- **A str never owns its bytes**, so every result is a slice of an
  argument. Nothing reads through p when n = 0 (the tests give zero strs
  p = 0 half the time).
- **Comparing** (`cmp_str`, `starts`, the search's inner loop) is a CPI
  loop: 46 T a byte.
- **`find` and `split` share one search**: CPIR hunts the pattern's
  first byte (21 T a byte), then a CPI loop checks the rest. The pattern
  lives in scratch words and one self-modified `ld a,n`. That's safe
  because no call is left half-done across another, and the tests check
  it by nesting one split inside another with a `find` between the inner
  pieces. `find` past 32767 fails through gen.asm's `bly_ovf_int`.
- **`split`'s state** uses 9 of the 11 bytes: done, cur, end (s.p + s.n,
  mod 65536), sep.n, sep.p, in the order `bly_split_next` reads them, so
  it walks them with HL and never touches IX. **A one-byte separator**
  (most of AoC's) is a CPIR straight from `bly_split_next`: 668 T for a
  6-byte piece, against about 1,000 through the general search. **A
  two-byte one** (", ") is a CPIR for its first byte and one compare for
  its second, with the count stopped one place short so the second byte
  is always inside s: 829 T, against 1,125. Longer separators go through
  `find`'s search.
- **`chr`** is a 256-byte table (`DUP 256, .b`). The same byte always
  gives the same p, and nothing is allocated.
- **`intern`**, as the contract says:
  - **The hash** is FNV-1a kept to 16 bits. That is exactly the low half
    of the 32-bit FNV-1a, because mod 65536 its prime 01000193h is 0193h =
    403, so the multiply is ten `ADD HL`s. FNV's high bits are the
    well-mixed ones, so a slot is the hash with its bytes swapped,
    masked.
  - **The index** uses open addressing and linear probing, at most half
    full. Slots hold id + 1, so a block straight from `bly_alloc`
    (zeroed) is an empty index with no fill loop. When the names reach
    cap (16, 32, 64...), the arrays are made again at twice the size,
    the strs are copied over and every name is rehashed into the new
    index.
  - **Each name's bytes are copied** into the arena, as DESIGN.md says.
  - **Probes**, measured in a Python copy of the table (`probes.py` in
    scratch), match linear probing's textbook figures on 3-capital node
    names (2023 d8), bag colours (2020 d7), two-letter valves (2022 d16)
    and "0".."999". For example, 500 three-capital names at load 0.49
    take 1.53 probes to find (ideal 1.48) and 2.39 to miss (2.41).
  - **Memory** is 8 bytes a name while live (its str and two slot words)
    plus its bytes. The arrays left behind by earlier doublings can add
    as much again. The 16K test arena holds 512 three-letter names, and
    the 513th fails `arena full`, because its doubling doesn't fit. A
    day with 1,500 names (2017 d7) would want about 42K: cap rounds up
    to 2,048, so 16K of live arrays, 16K left behind by doublings, and
    the copies.
  - **`too many names: intern holds 65536` can't happen.** 16,384 names
    would need the whole 64K for the strs alone, so the arena always
    fills first.
- **`bly_split_input`** makes one pass. It writes the strs straight to
  the arena's top and moves `bly_atop` past them at the end, because the
  number of lines isn't known until then and a counting pass would cost
  as much again. The scan is `ld a,(hl) / cp 14 / jr c / inc hl / djnz`,
  40 T a byte: CR and LF are both below 14, so a single compare passes
  almost every byte. An LF straight after a CR belongs to it (one
  remembered address). If the strs won't fit, it asks `bly_alloc` for
  the room it needed, which says `arena full` (with no line, at
  start-up).
- **`input line {n} is longer than 65535` and
  `the input is longer than 65535, too long for one str` can't happen**,
  because `bly_tlen` is a word. Neither has any code.
- **`grid()`** checks every line against the first before allocating
  anything, so ragged input says so even when it wouldn't fit. rows x
  cols is the sum of the lines' lengths, so it needs no multiply. Then
  come the header (`bly_alloc`) and the cells (`bly_alloc_raw`, since
  the copy fills them all), with an LDIR for each row.

**Cost.** T-states in the harness (no contention), CALL and RET
included. Stateful routines were timed against real state: an intern
table captured from a run, restored with its variables (`t_direct` in
the test).

| routine | T-states | case |
|---|---:|---|
| `bly_cmp_str` | 492 | 8 bytes, differing at the 5th |
| | 266 | against "" |
| | 46,247 | worst: two equal 1,000-byte strs (46 T a byte) |
| `bly_slice` | 165 | any |
| `bly_find` | 720 | ":" at 7 in a 47-byte line |
| | 1,445 | "green" at 32 in the same |
| | 21,423 | a byte that isn't among 1,000 (CPIR: 21 T a byte) |
| | 281,569 | worst: "aaab" in 1,000 a's (every place starts a candidate) |
| `bly_starts` | 452 | 5 bytes, true |
| `bly_trim` | 470 / 281 | 2 blanks before and 1 after / nothing to trim |
| `bly_chr` | 113 | any |
| `bly_split_init` | 353 | any |
| `bly_split_next` | 668 / 829 | a 6-byte piece, by "," / by ", " |
| | 540 / 657 | the last piece (7 bytes), by "," / by ", " |
| | 52 | after the last |
| `bly_intern` | 1,469 | a 3-letter name among 500, found (mean of 40; 1,403 to 2,265) |
| | 2,161 | a new one, the 501st (mean of 40; 1,642 to 4,228) |
| | 3,397 | a new 12-letter name among 100 |
| | 3,406 | each of 500 new names in a row, doublings included |
| | 382,899 | worst: the 257th, which doubles the table to 512 and rehashes 256 |
| `bly_name` | 226 | any |
| `bly_split_input` | 603,497 | a 100 x 140 grid, LF (14,100 bytes: 43 T a byte) |
| | 857,919 | 700 lines of 20, LF (14,700 bytes: 40 T a byte and about 380 a line) |
| | 958,052 | the same with CR LF |
| | 589,366 | one 14,700-byte line |
| `bly_grid_input` | 320,335 | the 100 x 140 grid, after the split (908,344 before `bly_alloc_raw`) |
| `bly_lines_new` / `bly_lines_next` | 306 / 309 | any |
| `bly_input` | 113 | any |
| `bly_cmp_byte` / `bly_pr_byte` | 65 / 1,121 | any / 3 digits (core's `bly_pr_u16`) |
| `bly_alloc_raw` | 173 | any size (`bly_alloc`: 42 T a byte, 4,402 for 100) |

Bytes, each fragment alone with its scratch and messages: `text` 568
(`cmp_str` 60, `starts` 47, `slice` 23, `trim` 52, `find` and the search
128, `split_init` 82, `split_next` 176), `text_chr` 275 (256 of it the
table), `intern` 467, `input` 280 (`split_input` 194), `input_grid` 258,
`elem_byte` 15, `alloc_raw` 29.

**Testing.** `test_text.py` checks the routines against the
interpreter's own code, called through small hand-made nodes: `e_dot`
for the str methods and lines' `next`, `e_index` for slices, `e_call`
for `intern`, `name`, `chr`, `grid` and `input`, and `Interp.__init__`
for the line split. Its drivers set `bly_line` to 7, so every failure is
compared byte for byte, " at line 7" included. A seed is about 42,000
checks in 3.4 seconds, and seeds 1 to 7 all pass.
- **cmp, starts and find** on 2,000 random pairs and 18 hand-picked
  ones: equal pairs, prefixes, unsigned bytes 80h/7Fh and FFh/00h,
  300-byte equal runs, and lengths 256 and 257. Also 2,000 more finds
  with the needle cut from the haystack, or cut and then changed in its
  last byte. Long strs start at 0000h and run up to 36K across the ROM,
  empty RAM and code, so the result lands at 32767 (fits), at 32768
  (`int overflow`), and absent.
- **trim and slice** on 2,000 random strs each, with blanks, other
  control bytes and all 256 values. Each result's p is checked to be in
  place, and DE, BC and IX are kept where the header says.
- **chr** for all 256 values: the same p each time, 256 different
  places, and `bly_atop` never moves.
- **split** on 2,000 random strs: separators at both ends, doubled,
  overlapping (`aaa` by `aa`), cut short at the end, longer than s, and
  empty (`split needs a separator`). A third of them, and of the long
  finds, have memory going on past s with the rest of the separator or
  needle, which nothing may read. Each piece's p is checked to be in
  place, and a call after the end still says no. There are also 500
  nested splits with a `find` stirring the shared scratch between.
- **intern and name** through every doubling up to 512, with repeats,
  all 256 byte values and the empty name. Every copy is checked to be in
  the arena. `name` is asked past the end and of 0, 32767, 32768 and
  65535 on an empty table, and the arena runs out at the 513th name.
- **the line split** on 2,000 random texts with mixed LF, CR LF and CR,
  with and without a final line end. There are 21 hand-picked ones too
  (`\n\r`, `\r\r\n`, `a\n\r\nb`...), and lengths 254 to 1,024 around the
  scan counter's roll-over at 256, with each line end at the very last
  byte. Then a 14K text, 1,500 lines, and an arena exactly big enough, 3
  bytes over, and 1, 3, 4 and 200 bytes short.
- **lines()** with two iterators taking turns at random, 700 lines
  through one of them, and one line too many.
- **grid()** on 2,000 random inputs, a third of them ragged, plus rows
  of 300 bytes, lengths 256 apart, 300 rows, the empty input (0 x 0),
  `\n` (1 x 0), and arenas cut to fit exactly or one byte short.
- **clobbers**: every header's "keeps" checked with sentinel registers,
  IX everywhere.

**Watching it fail.** A mutation script (not kept here) planted 50 bugs,
one at a time, in a copy of lib/, and runs the test against each. The
bugs: a prefix sorting after, signed bytes, the search missing the last
place or checking only the first byte, the overflow at 16384, `""` not
found at 0, trim stripping LF, slice one short, split stepping k − 1, an
empty separator allowed, no last piece, a stale pattern, the CPIR eating
what's left, `done` never set, the two-byte path ignoring its second
byte, counting one place too many or losing what's left, the search
reading past the end, chr off by one, intern's growth storing id rather
than id + 1, a prefix matching, no copy, never growing, `name` allowing
id = count, CR LF as two line ends, CR not a line end, no last line, the
DJNZ count losing its odd bytes, one str more than fits, `lines_next`
one too many or losing i's high byte, `input` with n = 0, grid's line
number from 0, its length high byte unchecked, rows and cols swapped,
one row copied over and over, its cells one short, `alloc_raw` one byte
over or wrapping or forgetting `bly_atop`, `cmp_byte` signed, `pr_byte`
printing the address, and `input` and `name` breaking their clobbers.
**All 50 are caught**, and a control (a different hash) passes, so the
tests don't depend on where the table puts a name.

Three lessons from that list:
- **Two bugs would have got through the first version of the tests:** a
  ragged line exactly 256 bytes off, and the iterator losing i's high
  byte. Neither shows until something is 256 or longer, so the cases
  above now include that.
- **My first mutants "caught" three bugs that only failed to assemble**:
  the replacement cut a comment in half. The script now reports those as
  `NO ASSEMBLY`, not as caught.
- **Two of the bugs were real.** I wrote both into the faster `split`,
  and the tests found them at once: an LDI copying sep.n, which also
  counted down the BC holding sep.p, and then a CPIR that counted down
  the BC holding what was left.

**On CP/M.** A smoke test (not kept here) linked a hand-written program
with `plat_cpm.asm` and runs it under tnylpo on 40 random input files
(mixed line ends, with and without a final one, ^Z padding from the
platform). It walks `lines()`, splits each line on ",", trims and
interns each piece, prints the numbers, and then asks for one line too
many. Every output is the interpreter's, and the .COM is 2,372 bytes.

**For the contract** (in my report too):
- **`bly_alloc` zeroes at 42 T a byte.** That was two thirds of `grid()`
  here, and it's most of the containers' `bly_map_new` and
  `bly_grid_new` too. An LDIR fill would halve it, and `bly_alloc_raw`
  belongs in core.
- **`plat_cpm.asm`'s `bly_start` doesn't call `bly_split_input`**,
  though ABI.md section 8 says it does. If the program is meant to call
  it only when it uses `lines()` or `grid()` (which is better: `input()`
  doesn't need the lines), the ABI should say so. It may run at any
  moment, but only once.
- **DESIGN.md says `grid()` is "the input viewed as a grid... with no
  copy"**, but the header has no stride, and both C and this copy. On a
  48K Spectrum a 141 x 141 input is 20K, and the copy is another 20K.
- **intern's memory**: about 16 bytes of arrays a name at worst, plus
  the copies. The copies can't matter in Barley as it is: a str is a
  slice of the input, a literal, the chr table or a name, all fixed for
  the whole run.
- `split()` uses 9 of its 11 bytes. `bly_cmp_byte` and `bly_pr_byte`
  could be listed in ABI.md section 6 as the library's element routines
  for `byte`.

## Integers: 16-bit multiply and divide, long and quad arithmetic

*Files: `int16.asm`, `intarith.asm`, `intbits.asm`, `intmul32.asm`,
`intmul64.asm`, `intdiv.asm`, `intquad.asm`, `intmisc.asm`,
`intfail.asm`. Tests: `../tests/test_int.py [count]` (`ONLY=<section>`,
`SEED=n`), `../tests/test_int_mutants.py`, costs
`../tests/bench_int.py`.*

**What's here.** Everything in ABI.md's integer section, and three more:
- **`bly_rem_i16`, `bly_rem_i32` and `bly_rem_i64` are `%`.** The
  interpreter's `%` is `a - b * tdiv(a, b)`, so `MIN % -1` is 0 while
  `MIN / -1` overflows: a divmod that traps can't serve both.
  `bly_rem_*` takes divmod's registers for the 16-bit form and HL=&a
  DE=&b BC=&r for the wider ones, and never fails but for division by
  zero. Use divmod for `/` (or for both at once), rem for `%` alone.
- **Failures come from gen.asm where it has them** (`bly_ovf_int`,
  `bly_ovf_long`, `bly_ovf_quad`, `bly_div0`, `bly_neg_shift`), so each
  message is linked once. `intfail.asm` adds what gen.asm lacks:
  `bly_mod0` and `bly_ovf_n` (A = the width in bytes, 2, 4 or 8, picks
  int, long or quad).
- **Internal helpers are `bly_i_*`**, the shared engines and scratch.
  Generated code shouldn't call them.

`bly_abs_i64` takes HL=&a BC=&r, like neg. `bly_fit_i64` writes 1, 2, 2,
4 or 8 bytes for byte, word, int, long, quad. Every routine with a
result by address allows it to be one of the operands (`x = x * y`).

**Design:**
- **The 16x8 multiply step** (`bly_i_mul16x8`, A:HL = DE*A) is
  z88dk-notes 6.1.1's sharing trick one byte wider: the multiplier rides
  in A's top while the product's third byte grows in underneath. Leading
  zeros of the multiplier are skipped. Everything else multiplies with
  it.
- **A long product needs no general engine.** If neither magnitude fits
  16 bits the product is at least 2^32, an overflow found without
  multiplying. Otherwise it is at most Xlo*Y + (Xhi*Y << 16): two 16x16
  products, each one or two 16x8 steps, all in registers. 123456 * 7
  went from 3,010 T on the byte-row engine to 1,379.
- **A quad product is schoolbook rows** (6.1.2): one row per significant
  byte of the narrower magnitude, each along the wider one in 16-bit
  digits, with X*m plus two bytes plus a carry byte filling 24 bits
  exactly. If the significant bytes add up to more than 9 it's an
  overflow before any multiplying. The top bit of byte 7 settles the
  rest, allowing exactly 2^63 when the product is negative. The rows
  patch their multiplier and the IX displacements into the code
  (self-modifying, commented).
- **Division goes by the divisor's significant bytes**, nb
  (6.1.5–6.1.7), on magnitudes; then the quotient and remainder take
  their signs:
  - **One byte:** base-256 long division through `bly_i_div8`
    (int16.asm). For divisors below 128 that's 8 unrolled steps of 28 T,
    with no 9th-bit test, since a doubled remainder can't pass 255. From
    128 up, a loop that keeps the test.
  - **Two bytes:** base-65536 digits, 16 steps each. Below 32768 the
    doubled remainder stays in 16 bits, so the fast loop (unrolled by 4)
    drops the 17th-bit test. From 32768 up, a bit that falls off the top
    means the divisor goes, and 16-bit wraparound gives the right
    remainder (6.1.6).
  - **Three or four bytes:** the quotient has at most N − nb + 1 bytes,
    so the remainder starts as the dividend's top nb − 1 bytes and only
    8(N − nb + 1) steps run. The remainder is in H L D E, the divisor is
    read through IX, and a 33rd bit is the 17th again.
  - **Five to eight bytes (quads only):** the same on a memory remainder
    of nb + 1 bytes (or 8).
  - **Every path skips leading dividend digits below the divisor.**
  - **No step sets a quotient bit:** the carry after the trial
    subtraction (and after an add-back, which always carries) is already
    the quotient bit inverted, so it goes in with the next shift and the
    digit is complemented once.
- **A long divided by anything that fits 16 bits stays in registers**,
  skipping the magnitude copies: 10^9 / 7 is 2,169 T, 10^9 / 10000 is
  3,102.
- **A 16/16 divide never needs a 17th bit**, because the remainder never
  exceeds the part of the dividend read so far (6.1.5). Barley's old
  runtime had the branch anyway; a mutant that deleted it changed
  nothing, which is how I found out. It's gone.
- **Shifts** of 1 to 7 bits copy a to r a bit at a time in one pass and
  shift r in place for the rest (top-down for `>>`, so r may be a).
  Larger counts move whole bytes with LDDR or LDIR first. A count of 8N
  or more empties a left shift and leaves the sign after a right one.
- **gcd** (6.1.12): if both magnitudes fit 16 bits, a 16-bit binary gcd
  in registers. If one does, one 64/16 remainder first: AoC's
  gcd(running lcm, small cycle) is 5,525 T. If neither, Stein's binary
  gcd on 8 bytes in memory, dropping to the 16-bit finish as soon as
  either side fits. **lcm** is a / gcd * b through the checked multiply.
  **mod** is the truncating remainder moved to the divisor's sign.
- **Code runs from RAM, and IY and the alternate registers are never
  touched.** 6.1.3's 32x32 accumulator wants the alternate set, which
  the ABI rules out, so nothing here uses it.

**Testing.**
- **The model** is `interp/barley.py`'s own `arith`, `fit` and `wrap`.
  The builtins (`mod`, `gcd`, `lcm`, `abs`) live inside `Interp.e_call`,
  so the test mirrors their ten lines and checks the mirror against
  `barley.run` on 240 whole Barley programs, MIN and the overflow cases
  included.
- **The cases** are 135,000 per run: every type's edges against each
  other, random values with their bit lengths spread evenly (so every
  divisor width and every multiply row count turns up), pairs at the
  overflow boundary (b near MAX // a and MIN // a, all signs), products
  between 2^32 and 2^36 (where a long's high word carries), gcd pairs
  with shared factors and shared twos, lcm right at 2^63, and shift
  counts across every byte boundary.
- **Every failure is compared byte for byte, " at line N" and all.**
  Results are aliased onto an operand a third of the time, every byte
  from A000h to EC3Fh outside the result must be unchanged, and **every
  register the header's `clobbers:` leaves out must come back
  unchanged** (the test parses the headers).
- **The widened contract is tested end to end:** int, long and quad
  operands widened to quad, the function, then `bly_fit_i64` back,
  against the builtins at the original type.
- **Two seeds** (1009 and 271828), all right.
- **`test_int_mutants.py` breaks the library 55 ways,** one at a time,
  on a copy of lib/: dropped carries, wrong boundaries, inverted flags,
  missing 9th, 17th and 33rd bits, the exactly-MIN cases. Each must make
  its section fail. All 55 do. Three escaped along the way. Two changed
  nothing: the dead 17th-bit branch above, and letting a shift by 8 down
  the 1-to-7-bit path, which is merely slower. The third was a real gap:
  the long multiply's high-word carry, which needed the 2^32-to-2^36
  products before the tests could see it.

**Costs** (T-states on the test platform, no contention;
`bench_int.py`). "Worst seen" is the slowest in a full random run. Bytes
are per fragment: the linker takes whole files.

| routine | typical | worst seen | fragment, bytes |
|---|---|---|---|
| `bly_mul_u16` | 1234 * 56: 388; 40000 * 3: 295 | 847 (both wide) | int16: 420 |
| `bly_mul_i16` | -123 * 45: 577 | 669 | int16 |
| `bly_divmod_u16` | 12345 / 7: 699; 1000 / 7: 396; 65535 / 300: 544 | 999 (divisor 128–255) | int16 |
| `bly_divmod_i16`, `bly_rem_i16` | -12345 / 7: 934 | 1,235 | int16 |
| `bly_add_i32`, `bly_sub_i32` | 188, 192 | the same | intarith: 214 |
| `bly_add_i64`, `bly_sub_i64` | 398, 402 | the same | intarith |
| `bly_neg_i32`, `bly_neg_i64` | 186, 333 | the same | intarith |
| `bly_cmp_i32` | differing at the top: 134 | 259 (equal) | intarith |
| `bly_cmp_i64` | differing at the top: 146 | 455 (equal) | intarith |
| `bly_and/or/xor_i32`, `_i64` | 183, 366 | the same | intbits: 409 |
| `bly_not_i32`, `_i64` | 213, 409 | the same | intbits |
| `bly_shl_i32`, `bly_shr_i32` | << 1: 340; >> 1: 360; << 8: 721 | 1,962 (<< 31) | intbits |
| `bly_shl_i64`, `bly_shr_i64` | << 1: 512; >> 1: 532 | 3,090 (<< 63) | intbits |
| `bly_mul_i32` | 123456 * 7: 1,379; -46340 * 46340: 1,634 | 2,892 | intmul32: 221 |
| `bly_mul_i64` | 10^12 * 7: 3,716; 10^9 * 10^9: 6,519 | 11,527 | intmul64: 378 |
| `bly_divmod_i32` | 10^9 / 7: 2,169; 10^9 / 10000: 3,102; 10^9 / 100000: 6,164 | 7,431 | intdiv: 1,066 |
| `bly_rem_i32` | 10^9 % 10000: 2,976 | 7,218 | intdiv |
| `bly_divmod_i64` | 10^18 / 7: 4,469; 10^18 / 10000: 5,887; 10^18 / 10^9: 12,894 | 32,707 (a 5-byte divisor) | intdiv |
| `bly_rem_i64` | 10^18 % 10007: 5,554 | 32,410 | intdiv |
| `bly_mod_i64` | -10^12 mod 10007: 5,455 | 32,554 | intquad: 789 |
| `bly_gcd_i64` | gcd(360, 84): 2,318; gcd(10^12, 20000): 5,525; two 40-bit: 12,873 | 73,822 (consecutive Fibonacci quads: 63,753) | intquad |
| `bly_lcm_i64` | lcm(13 * 10^9, 20021): 16,072; lcm(12, 18): 6,955 | 68,264 | intquad |
| `bly_abs_i64` | 358 (positive), 729 (negative) | the same | intquad |
| `bly_fit_i64` | 244 (median); to long: 418 | 451 | intquad |
| failures, helpers | | | intfail: 29; intmisc: 68 |

Scratch included: intdiv 24 bytes, intmul64 26, intquad 32, intmul32 7.
A program that divides longs links intdiv, int16 (for `bly_i_div8`),
intmisc and intfail, about 1.6K. If that's too much, drop the
5-to-8-byte memory path (about 200 bytes, quads only); the 3-to-4-byte
register path could take its place at about 4 times the cost.

**Where it could still go faster**:
- **A 5-to-8-byte quad divisor**, about 900 T a quotient bit. A 6-byte
  register remainder (B C D E H L, with the dividend byte and the
  counter in memory) would be about 360.
- **gcd of two wide quads**, which runs one subtraction and shift on 8
  bytes a step. A 32-bit register finish would catch it earlier.
- **The quad multiply's per-digit bookkeeping**, about 300 T of every 600.
  Rows of 16x16 digits through `bly_i_mul16` would halve the count.

## dword: unsigned 32 bits

*File: `intu32.asm` (10 October). Tests: `../tests/test_int.py`
(`ONLY=dword`), `../tests/test_int_mutants.py` (seven of them).*

**What's here.** `dword`'s own arithmetic, wrapping and never trapping,
for the hash or packed key a `long` would trap on: add, sub, neg and
cmp; mul, the low 32 bits of three of `bly_i_mul16`'s 16 x 16 products
(alo x blo, and the low words of alo x bhi and ahi x blo added to its
high word); divmod, `intdiv.asm`'s unsigned core (`bly_i_udiv`, N = 4)
with a copy in and out (either result's address may be 0, so `%` is
divmod without the quotient); shr, a bit at a time with zeros coming in;
and a printer that loads DE:HL for `num.asm`'s `bly_pr_u32`. `& | ^ ~`
and `<<` are `long`'s routines: the bits are the same.

**A fragment of its own**, so programs without a dword carry none of it,
and `long`'s routines didn't grow a branch.

**Measured** (`test_int.py`, T-states, median over its cases): add 187,
sub 191, neg 229, cmp 199, mul 3,090 (worst 3,687), divmod 1,685 (worst
6,533), shr 234 (worst 1,693, for the counts near 31), print 1,653.

**Caught on the way:** the fuzzer missed a multiply that dropped ahi x
blo (its dwords are mostly small, and the term needs both a high word
and a low one), so `test_int` got cases with every cross term; the
mutant that does it is in the list now. A mutant that moved shr's
shortcut from 32 to 33 survived, rightly: 32 single shifts give 0 too.
The one that matters is the count's high byte (a shift by 256 isn't a
shift by 0).

## The screen and sound in C

*Files: `../../c/rt/bly_zx.h` (new), `../../c/rt/barley.h`,
`../../c/cgen.py`, and for `peek`/`poke` `../../interp/barley.py`; test
`../../c/tests/test_screen.py` (`--quick`, `--seed N`, `--random N`,
`--c-dir DIR`).*

**What's here.** Everything on the design's card, in the C backend,
following `zxgfx.py` line for line (including the lazy scroll and wrap
of 17:40, and FRAMES wrapping at 24 bits). Every byte `print` writes
also draws, and only those: the generated code sets `bly_showing` around
each item, zone and newline, so a failure's message never reaches the
screen. The screen and the beep log are saved at exit and at a failure,
as the interpreter's `finally` saves them. The font comes from the ROM
at compile time (`cgen.py` reads it through `zxgfx.font()`), so each
program carries its own copy.

**`peek` and `poke`**, in the interpreter and the C, see a 64K memory:
the 48K's ROM at 0000h, read-only, the screen's 6,912 bytes at 4000h,
and the UDGs at FF58h, which the screen draws into and reads from. An
address is any whole number, checked as an index is:
`address 70000 is outside 0..65536`. In the interpreter, `Screen.mem`
and `Screen.udgs` are rebound to views of the memory. That works because
`zxgfx.py` only ever writes them in place; if it ever assigns them
afresh the link breaks, so a `Screen(memory)` parameter would be
sturdier. The C carries the ROM's 16K only when the program peeks, since
nothing else can see them. They're in `MACHINE_FUNCS`, not
`SCREEN_FUNCS`, so `z80gen.py`'s screen dispatch doesn't take them for
drawing calls. `inp` and `outp` are there too: the model's ports
(`zxgfx.py`), which the C repeats in `bly_inp` and `bly_outp`. The
border a picture shows is kept apart from BORDCR's, since `outp(254, 2)`
turns it red without changing what `cls` gives the lower screen.

**How it's tested.** 39 hand-picked edges, all 44 failures (each also
checked against its exact words), and 60 seeded random drawing programs
of 50 to 300 calls (a fifth end in a failure; about 700 peeks and pokes
among them), each run through the interpreter and the C: the 6,912
bytes, the beep log, the text and the exit status must all agree. 143 of
143 agree (and 222 of 222 on a second seed, before `peek`/`poke`);
`run.py` is 48 of 48 on both backends. **46 mutants, 46 caught** (one I
first wrote, scrolling one row too far, was equivalent, since row 21 is
cleared straight after, so the real one scrolls two too far):
Bresenham's `>=`, which end of a line is checked first, the circle's
dedup and step, OVER and INVERSE for pixels and text, the pixel address,
eager scrolling and wrapping, scrolling the machine's rows 22 and 23,
the scrolled row's colours, block graphics, the UDGs at power-on, every
range check and message, the beep's order of checks, the frame count and
its 24-bit wrap, the sound log's format, messages drawn on the screen,
no save at a failure, `print at` leaving print's column alone, a
writable or missing ROM, the screen or the UDGs moved, and flags not
normalised (which survived until `bright(256)` joined the edges: a flag
whose low byte is 0 is still true).

**Costs** (a 2026 laptop, clang -O2; there are no T-states here, so this
is what the virtual screen costs the C):

| what | before the screen | with it | note |
|---|---:|---:|---|
| 1,000,000 lines of `print "line "; i` (12 MB) | 30 ms | 157 ms | about 128 ns a line, 87 of them the scroll |
| 200 rounds of 256 plots, two full diagonals and a circle | | 3 ms | |
| code (`__text`), a program that only prints | 1,920 B | 5,392 B | printing, scrolling and saving (the PNG too) |
| code, a program that also draws | | 6,272 B | plot, line and circle add about 880 B |
| data | | +768 B const, +64 KB zeroed | the font; the memory (+16 KB const if it peeks) |

**I guessed a scroll by thirds would be three times cheaper, and it
isn't.** Written and measured (seven rows at once within each third, 50
moves instead of 198), it ran in 159 ms against 158. The cost is the 5.4
KB moved, which memory bandwidth sets, not the number of moves: clang
inlines a 32-byte `memcpy`. So the C keeps the scroll that mirrors
`zxgfx.py`'s loop. The only real saving would be not keeping the screen
when nothing can see it (no `BARLEY_SCREEN`, no `peek`, no `point`), and
that would leave a trap for whoever adds the next builtin that reads the
screen.

## Drawing in Z80: plot, point, line, circle, attr, udg

*Files: `zxgfx.asm` (plot, point, attr, udg, and what the others share),
`zxline.asm`, `zxcircle.asm`; test `../tests/test_zxgfx.py` (`--quick`,
`--seed N`, `--cost`, `--mutants [name]`).*

**What's here.** The six routines of ABI.md section 10, with its
registers and its words. **Three fragments, not one:**
- **Why:** the linker takes a whole fragment for any routine in it. A
  program that only plots carries 440 bytes, not 2,261.
- **The names are unchanged**, so `z80gen.py`'s calls don't change.
- **Line and circle use plot's shared pieces** by their local names
  (`bly_zx_plot.chk`, `.addr`, `.ops`, `.opsd`, `.masks`) and list
  `bly_zx_plot` in `needs:`.
- **Clobbers:** circle also clobbers IX (the generator only ever loads
  IX just before a call, so that's safe). Line and circle are
  self-modifying: each patches the loop it's about to run.

**Design:**
- **The pixel's operation** (from ROM PLOT-SUB at 22F4h, which I checked
  byte for byte: `zxgfx.py`'s rule is the ROM's):
  - plain is `OR m`; INVERSE is `OR m` then `XOR m`; OVER is `XOR m`;
    both together do nothing.
  - So line and circle patch two opcodes (`or` unless OVER; `xor` when
    exactly one is on) and never test the mode per pixel.
  - Plot reads P_FLAG's permanent bits (1 and 3) on every call, and only
    those: the test randomises the others.
- **The colours, masks and contrasts** (10 October, for BASIC's INK and
  PAPER 8 and 9, BRIGHT and FLASH 8):
  - **The rule is the ROM's PO-ATTR** (0BDBh, read with omse-ai's
    `zxdis.py`): (old AND MASK_T) OR (ATTR_T AND NOT MASK_T), then PAPER
    9 (P_FLAG bit 6) and INK 9 (bit 4) make white on dark, black on
    light. `.paint` repeats its tail (0BE4h on) rather than calling it,
    so the drawing still runs on the bare Z80, whose ROM is zeros.
  - **The plain case costs (nearly) nothing.** Plot asks once whether a
    mask or a contrast is set: MASK_T and P_FLAG are neighbours, so
    `ld de,(5C90h)` reads both, 42 T a plot. Line and circle ask once
    per call, and patch each two-byte colour store to `ld (hl),ATTR_T`,
    or to a `jr` to a trampoline that calls `.paint` and carries on as
    the store would have. The jumps are patched at run time, so each
    site has an `assert` that its trampoline is in reach (the first
    version's `.fcol` wasn't: 240 lines away).
  - **Measured** (`zxbench.py`): ex-collatz, which plots a pixel at a
    time, 1.1% slower; the other drawing programs 0.5% or less; drawing
    programs 3-4% bigger (`.paint`, the patching, and the setters). The
    setters went to `zxcolour.asm`, out of `plat_zx.asm`, so a program
    that never sets a colour no longer carries them: the bench's
    non-drawing programs are 13-18% smaller than before.
  - **Held to the real thing twice:** `../tests/co_temp_check.py` types
    the same INK, PAPER, BRIGHT, FLASH and BORDER as BASIC commands on
    omse-ai's 48K and compares the colours they leave with the model's;
    `rom_text_check.py` prints with them and compares the screen with
    the ROM's. The ROM's CLS clears the lower screen's two rows in the
    border's colours (BORDCR), which the model didn't know until
    `attr(r, c)` could read them.
- **plot** works the address out inline (z88dk notes 6.3.2: three
  rotates feeding in 0, 1, 0 make the 010, and two XOR-AND-XOR splices)
  and takes the mask from an 8-byte table.
  - **The table is not aligned, on purpose.** `zxbuild.py` assembles
    twice, at 8000h and then flush under the UDGs, and keeps the first
    pass's size. So no fragment's size may depend on where it lands.
    - My first versions had `align 8`, and would have lost the program's
      last bytes whenever the size wasn't a multiple of 8.
    - The test now assembles the three at eight origins and requires one
      size; a mutant that puts the align back is caught.
    - The unaligned lookup (`add a,low`, `adc a,high`, `sub e`) costs 8
      T more.
  - **A row table measured slower than it's worth:** a page-aligned
    176-entry table of row starts saved 26 T a plot (9%).
  - It would cost 352 bytes of table plus up to 335 of padding, and
    alignment is ruled out anyway, so the calculation stays.
- **line is Zingl's loop**, as the reference writes it, and **that loop
  is an 8-bit accumulator**:
  - Along the major axis it rounds half up from the start. So u = 256 -
    ceil(major/2), and each step does u += minor; a carry means u -=
    major and a minor step.
  - I checked this against the reference for every (dx, dy) on the
    screen, all 45,056 with a separate script, and the mutant that
    rounds half down is caught.
  - Ends can't be swapped to normalise the direction, because which way
    a tie rounds depends on the start. So x's direction is patched
    (`rrc`/`rlc c`, `inc`/`dec l`), and so is y's.
  - **The y step is inline:** `inc h` (or `dec h`), and a test of the
    low three bits. Only the move into the next row of cells is out of
    line.
  - **A cell is coloured only when a step enters a new one**, and that
    is exactly when L changes.
- **Horizontal lines go a byte at a time** (12.7 T a pixel, from 92);
  vertical lines have a loop without the accumulator (91, from 148).
- **circle is the reference's midpoint loop**, with four things worked
  out:
  1. **err is kept halved:** err = 2e + p, and p flips every step (both
     increments are odd). e's sign is err's, and e stays in
     -32579..23138 for every r up to 32767 (checked in C,
     `circbound.c`). err itself needs 17 bits.
  2. **The reference's deduplicated points are two groups of four:** A =
     (cx +- x, cy +- y), and B = (cx +- y, cy +- x) unless x = y; a zero
     offset gives one value, not two. Each group is two rows by two
     columns, so a step makes at most four row records, four column
     records, and eight plots.
  3. **Clipping:**
     - c + a past 32767 wraps negative, which the clip refuses anyway.
     - c - a below -32768 wraps to 1..32767, onto the screen, so the
       subtractions check V.
     - In practice only cx - x and cy - x can get that far (y stays
       under 23,171), and the two V checks that can't matter are mutant
       controls.
     - I found this because a mutant that removed the V check on cx + x
       survived: the check was never needed.
  4. **Exact early stops:**
     - Columns are on the screen only for offsets up to Mx = max(255 -
       cx, cx), and rows up to My = max(175 - cy, cy).
     - Group A needs x <= Mx and y <= My, group B y <= Mx and x <= My,
       and y <= x, so **both are dead once y > min(Mx, My)**.
     - Likewise both are dead once x falls below max(Lx, Ly), each L
       being the centre's distance from the screen's range.
     - Add a bounding-box reject: an r = 32767 arc across the screen
       went from 27.9M T (the first version) to 267K.
- **A circle wholly on the screen** (r <= 87) **takes a fast path:**
  - Step 0 goes the general way. After that, x, y and e are bytes (e
    stays in -85..63, so 8-bit sums give its sign).
  - The four rows and four columns are records that move a pixel a step:
    two each step, and the other two when x falls.
  - It's 2.1 times as fast (r = 87: 105K T, from 223K) for about 560 of
    the circle's 1,252 bytes. If memory is tighter than time, it can go:
    a control mutant shows the general path draws the same.

**How it's tested.** A script of calls is walked on the bare Z80 by a
small driver, and the same calls are made on `zxgfx.Screen`. The screen
and the UDGs (at FF58h) start random, and P_FLAG carries noise in every
bit that mustn't count. After each script these must all agree:
- all 6,912 bytes of the screen, and the 168 bytes of UDGs;
- every `point`;
- a failure, if the script ends in one: its words and its ` at line N`;
- every other byte of memory, apart from the code's own scratch, the
  stack and the results;
- IY and the alternate registers.

What the runs covered:
- **Edges:** 113 scripts, including every attribute cell, every pixel of
  the edge rows and columns, lines in every octant, zero length and one
  off the diagonal, and circles of radius 0, at each edge, at the fast
  path's limits and at the window's.
- **Huge radii**, including centres where c - x passes -32768.
- **Every failure word for word**, including udg lengths of 264, 32768
  and 65535.
- **Random scripts:** 400 of 120 calls on each of five seeds, all
  agreeing.
- **79 mutants:** all 69 bugs caught, and all 10 controls pass.
  - The controls change no pixel: the general path in place of the
    horizontal, vertical or fast one; no bounding box; no y or x stop;
    the two V checks that can't matter; the mask table moved, once
    across a page.
- **The size is the same at eight origins** (see plot, above).

**Cost** (T-states in the harness, no contention; "a pixel" is the
line's total divided by its pixels; stack is bytes below the caller's):

| routine | T | a pixel, or worst | stack |
|---|---:|---:|---:|
| `bly_zx_plot`, plain / OVER / INVERSE / both | 310 / 346 / 359 / 330 | the same | 2 |
| `bly_zx_point` | 261 | 261 | 4 |
| `bly_zx_line`, horizontal, 256 pixels | 3,272 | 12.8 | 8 |
| `bly_zx_line`, vertical, 176 pixels | 16,044 | 91 | 8 |
| `bly_zx_line`, diagonal, 176 pixels | 25,731 | 146 | 8 |
| `bly_zx_line`, shallow (255 by 100) / steep (100 by 175) | 29,725 / 24,300 | 116 / 138 | 8 |
| `bly_zx_line`, one pixel / 6 pixels | 1,174 / 1,992 | | 8 |
| `bly_zx_circle`, r = 0 / 10 / 50 | 2,977 / 16,547 / 62,875 | | 8 |
| `bly_zx_circle`, r = 87 (the biggest whole one) | 104,826 | | 8 |
| `bly_zx_circle`, r = 150, clipped | 179,904 | | 8 |
| `bly_zx_circle`, r = 1000 / 32767, an arc across the screen | 273,529 / 267,368 | | 8 |
| `bly_zx_circle`, r = 32767, nothing on the screen | 272 | | 2 |
| `bly_zx_attr` / `bly_zx_udg` | 146 / 400 | | 2 |
| code | zxgfx 440 B, zxline 569 B, zxcircle 1,252 B | | |

The first correct version measured plot at 348 T and lines at 92 to 186
T a pixel. Circles were 283K T at r = 87 and 28M at r = 32767 whether or
not anything showed: about 8 seconds on a real Spectrum, to draw
nothing. A line or circle call pays a few hundred T up front for its
patches.

## The machine on the Z80: peek, poke, inp, outp

Saturday 10 October. Melissa asked for IN and OUT "if they're not
there". They weren't, and nor were `peek` and `poke` on the Z80, so all
four came together.

**Each is one instruction in the generated code** (ABI.md section 10):
`peek` of a `word` is `ld hl,(v)` and `ld a,(hl)`, 23 T, and of a
constant `ld a,(nn)`, 13 T. The checking is `zxmach.asm`, 97 bytes, and
only a type that can hold an address out of range reaches it. It checks
the quad's top six bytes itself rather than calling `num_chk.asm`'s
`bly_n_q2w`, which would bring 346 bytes it doesn't need.

**The ports mean what omse-ai's 48K does**, read in its source
(`src/zxcore.cpp`, `io_read` and `io_write`) and then asked:
- An even port is the ULA's. It reads BFh with no key held, and bit 6 is
  the EAR line, which echoes bit 4 of the last write. Writing it sets
  the border (bits 0-2) and that bit.
- An odd port with bits 5-7 clear is the Kempston joystick, 0 with
  nothing pushed; any other port reads FFh.
- Two things write the ULA behind the program's back: `border()`, with
  bit 4 clear, and the ROM's BEEPER, whose last OUT always has bit 4
  clear and BORDCR's border. A beep too short for one cycle isn't played
  (`zxbeep.asm` returns first), so it changes nothing. The model works
  the cycles out from the same table, which is
  `round(4 * 440 * 2 ** ((s - 9) / 12))` (checked against all 130
  entries).
- BASIC agreed: `OUT 254,16: PRINT IN 32766` is 255, and with a `BEEP`
  or `BORDER` between them, 191. `PRINT IN 254` from BASIC gives 190,
  not 191, because ENTER is still held while the line runs, and a top
  byte of 0 reads every half-row.

**How it's tested.** Ten suite cases. One is the memory: the ROM, the
screen and the UDGs, through every address type, with the picture
compared. One is the ports. Seven are failures, one for each kind of
check: an `int` address and an `int` port, a `long`, a `dword`, a `quad`
that only its top byte puts out of range, a literal at 65536, and a
negative literal port. The last is the CP/M rule.
`z80/tests/ula_check.py` (in `./check fragments`) runs 40 random
programs of `outp`, `border`, `beep` and `inp` on omse-ai's 48K and on
`zxgfx.Screen`, and what `inp` read and the border at the end must
agree. Only it sees the border, which the suite's pictures don't hold.
**15 mutants, all caught:** four in the model, two in the C, five in the
generator and four in `zxmach.asm`. One survived at first, a constant
address of 65536 taking the unchecked path, until the literal case moved
from 70000 to the boundary. One more is equivalent, and kept as a note:
dropping `ld b,h` before `in a,(c)` changes only which keyboard
half-rows are read, which can't be seen with no key held. A test with a
key held (`--- keys`, coming with `inkey()`) will see it.

## The keyboard: inkey, key and ask

Saturday 10 October, from Melissa: "some of my own AoC solutions use
INKEY$ (which could just be `inkey()` here) and input of both strings
and numbers... It's a bit of a pain using the rom, but minilib does it."

**`inkey()` is the ROM's own INKEY$** (S-INKEY$, 2634h) without the
string: KEY-SCAN (028Eh), K-TEST (031Eh), then K-DECODE (0333h) with C =
0 and D = FFh, which is L mode, with the caps lock as it stands. It
lives in `zxask.asm` with `ask()`: 274 bytes for both.

**`ask()` on the 48K is INPUT LINE**, step for step: the ROM's INPUT
(2089h, IN-ITEM at 20C1h) checked against spectrum-minilib's
`zx_input_line.asm`, which Melissa worked out from the HiSoft BASIC
compiler. So: stream 1 (channel K, the lower screen), CLS-LOWER, the
prompt, FLAGX bits 5 and 7 (input mode, INPUT LINE), a workspace holding
just ENTER, then EDITOR (0F2Ch); afterwards CL-SET, INPUT's own ending
(20A0h: the upper screen's print position, SCR_CT and CLS-LOWER), the
workspace given back and stream 2 again. INPUT's ED-COPY between the
editor and CL-SET is left out (since 10 October): it draws the line
again without its cursor, and INPUT's ending clears it at once. The
numbers me measured it in the Pasta/80 bake-off, 3,700 T and 1,930 a
letter, 69% of a 25-letter `ask()` with the two clears; 91 programs
(lines of 0 to 100 letters, the upper print position on every row from 0
to 21) leave the same screens, output and report with it and without,
and a 25-letter `ask()` is 53,234 T quicker. Some things were found on
the way:
- **There's no BREAK in the editor.** CAPS SHIFT with SPACE just types a
  space; omse-ai showed it. INPUT LINE is left by cursor down: ED-DOWN
  (0FF3h), in input mode, puts 10h in ERR_NR and ED-END (1024h) leaves
  through ERR_SP, which BASIC reports as `H STOP in INPUT`. So `ask()`
  sets ERR_SP to its own `.stop` around the editor (minilib's
  `call_with_errhandler`), fails with `STOP in ask`, and puts ERR_NR
  back to FFh, since BASIC would otherwise report the STOP at the end.
- **The editor runs on BASIC's stack.** Its room check (TEST-ROOM)
  measures against SP. Ours is high, above the input and the arena, so a
  long enough line could have grown the workspace over them.
- **A key pressed before isn't the answer's first letter**, one
  `inkey()` saw, say. Opening channel K clears FLAGS bit 5 (CHAN-K,
  1634h), for INPUT as for `ask()`. I first cleared it myself as well,
  and the mutant that took mine out survived, which is how I found the
  ROM already did.
- **One thing INPUT doesn't do:** `ask()` returns only once every key is
  let go, so ENTER isn't still held for an `inkey()` straight
  afterwards. omse-ai showed why: `PRINT IN 254` in BASIC gives 190, not
  191, because ENTER is still down while the line runs.
- **Every key the editor takes clicks**, through BEEPER, which leaves
  the border BORDCR's and the speaker bit clear, so the model's
  `asked()` says so, and clears the lower screen as INPUT's CLS-LOWER
  does. A line long enough to grow the lower screen past its two rows
  also writes over the upper screen, which the model doesn't follow.
- **omse-ai's transcript leaves the prompt and typing out by itself:**
  it logs printing only while the last stream CHAN-OPEN opened is 2.

**On CP/M, `ask()` reads a key at a time through BDOS 6**
(`cpmask.asm`). BDOS 10 was the obvious choice, and tnylpo showed why
not: it echoes, and at the end of stdin it reads 1Ah after 1Ah, echoing
`^Z` each time, until its buffer fills; and ^C at the start of a line is
a warm boot, out of the program with nothing said. So: a printable key
is taken and echoed; DELETE or backspace rubs one out (backspace, space,
backspace); ENTER ends the line; 1Ah ends it too once something's typed;
^C, or 1Ah first, is the STOP. (tnylpo turns a newline on stdin into
0Dh, and the end of stdin into 1Ah.) The line goes straight into the
arena's free room and is then allocated where it is, since
`bly_alloc_raw` hands out `bly_atop`: no buffer, and no limit but the
arena. The interpreter `--as cpm` takes the keys the same way.

**The keys off the Spectrum** are `zxgfx.Keys`, which the C repeats:
what stdin holds, a newline being ENTER. The first model said that
`inkey()` sees each key held for one look and released for the next, and
that `key()` takes the next one. The 48K disagreed twice, and it was
right both times. `key()` after a run of `inkey()`s gives the last key
`inkey()` saw, because the ROM registered it and nothing took it.
`inkey()` straight after `key()` finds that key still down. So each key
is pressed, then let go: `inkey()` sees it down, then up; `key()` has
the latest key registered if it hasn't had it, or else the next key
typed, which is then still down.

**`zxrun --keys` types them on the 48K.** A key goes into the editor if
the program is waiting in `ask()` (WAIT-KEY1, 15DEh, with FLAGX bit 5
set) within half a second. Otherwise it's pressed and let go, and five
frames pass before the next. When the keys run out and the program is
asking, cursor down stops it, as the end of stdin does elsewhere. A
shifted key is pressed shift first, a frame early. Pressed at once, a
key scan already under way when they went down could find the letter
without its shift: `inkey()` saw `b` before it saw `B`. Fingers do the
same. And zxrun now fails a run whose last report isn't `0 OK`.

**How it's tested.** Four suite cases with `--- keys`: lines and
numbers, with the prompt and echo on CP/M's console (`--- expect cpm`);
the STOP; `inkey()` and `key()` together, across `ask()`, with the
border and EAR bit `ask()` leaves; and CP/M's rubbing out, control keys
and ^C. Each runs on all four backends where it can. `ula_check.py` now
holds SPACE down and reads five ports, which catches the `ld b,h` mutant
that the ports' tests couldn't see. **21 mutants, 20 caught.** Two of
those survived at first and found a bug in the model: at the end of the
keys, `take()` dropped a key the ROM had registered and `key()` hadn't
had. The other is equivalent: opening stream 1 before CLS-LOWER, which
opens the K channel itself. INPUT does both, and so does `ask()`. An
earlier mutant, taking out my own clearing of FLAGS bit 5, survived
because CHAN-K does that too, so mine went.

## The lower screen: print #0 and #1

Saturday 10 October, from Melissa: "I think we may also need to support
print# to write to the bottom two lines (maybe we do? I haven't checked
closely...)". We didn't: `print` was always stream 2.

**What BASIC does, asked on omse-ai and read in the ROM:**
- PRINT #1 starts on the **bottom** line, row 23, not row 22. CLS-LOWER
  ends with CL-SET at line 23 (`ld bc,1721h`), and a program starts with
  S_POSNL at (33, 23) too. `AT 0` is row 22 and `AT 1` row 23.
- In channel K the line numbers count down from 24, the top of the lower
  screen: with two lines, 24 is row 22, 23 row 23, and 22 is pending
  below the bottom, where a newline from there leaves it (lazy, as
  upstairs).
- **When it fills, the lower screen grows upwards** (PO-SCR's lower
  path, 0D02h). DF_SZ goes up one, and the bottom DF_SZ lines scroll up,
  or the whole screen if the lower screen has reached the upper print
  position, which then moves up. That path has no "scroll?", and AT 2
  grows it too. Upper printing then scrolls at the new DF_SZ, so the
  screen above shrinks.
- The text is in BORDCR's colours: TEMPS (0D4D) gives the lower screen
  ATTR_T = BORDCR and MASK_T = 0, and clears P_FLAG's temporary bits, so
  no INVERSE, OVER or 9s.

**Barley keeps it two lines**, which is what "write to the bottom two
lines" asks for. It also keeps the upper screen's 22 rows what they are
everywhere else. Where the ROM would grow the lower screen, `print`
fails: `print would grow the lower screen past its two lines`, and
`print at (2, 0) is off the lower screen`. Everything else is the ROM's.

**On the 48K** (`zxlower.asm`), each piece of a `print #1` (an item, a
zone, the newline) is bracketed by `bly_zx_lower` and `bly_zx_upper`,
after the item is worked out, so a failure working one out is printed
upstairs as output, like any other. `bly_zx_lower` opens channel K,
gives print's column the lower screen's own (from S_POSNL, for the
zones), and patches a jump to `zxl_putc` over `bly_putc`'s first three
bytes, so a program that never prints to the lower screen pays nothing.
`zxl_putc` reads the ROM's own position before each byte and fails
before the ROM would grow anything, so `cls` and `ask()`, which move
that position, need no word to it. One thing had to change elsewhere:
`bly_pr_f` borrowed stream 3 for PRINT-FP and then reopened stream 2,
which would have sent a float in a `print #1` upstairs. It now reopens
the stream it came from: 1 if TV_FLAG says the lower screen's channel
was open, else 2.

**How it's tested.** `z80/tests/lower_check.py` (in `./check fragments`)
types random BORDER, INK, PAPER, INVERSE and OVER, a CLS, and random
PRINT #0 and #1 statements (AT, text, `;`, `'`) as one line on omse-ai's
48K, ends it with PAUSE 0, and compares rows 22 and 23, pixels and
attributes, with the model's. A statement the model says would grow the
lower screen is left out. Four model mutants were caught: the colours,
AT's rows, starting on row 22, and INVERSE. Eleven suite cases cover the
rest. BASIC's report overwrites rows 22 and 23 at the end, so the cases
peek them into checksums. **18 mutants, all caught**, across the
interpreter, the model, C, `zxlower.asm` and `fp.asm`. Four survived at
first, and each one showed a case leaning on its own trailing newline: a
newline from below the bottom fails with the same words a character
there would, so a case that ended with one couldn't tell which check had
fired. Those cases now end with `;`, and one tests the newline alone.

## FZX text: print #4, and @embed

Saturday 10 October, from Melissa: "It'd be cool if we could support FZX
fonts, which often use channels/streams... this renderer can be hooked
into RST 10h via channels/streams to use the same mechanism. Or not, but
it's likely least code to just use the library if desired." So
`zxfzx.asm` is Einar Saukas's FZX driver (FZXdriver.asm, 2013: free to
use and adapt, so long as the use is clearly indicated, which README.md
and the fragment's header do), installed as his own installer does it (a
channel 'S' made below PROG with MAKE-ROOM, on stream 4), so `print #4`
goes through RST 10 exactly as BASIC's PRINT #4 does. The font format is
Andrew Owen's open standard.

**What it draws**, read in the driver: a position in pixels (x 0..255,
and a line counting down from 191 at the top); `AT y, x` in pixels; a
character the font hasn't got prints as `?`. Kerning moves a character
left, though not past 0. A character that won't fit on the line goes to
the next first, and one whose line can't hold the font's height is Out
of screen. The pixels are ORed in, three screen bytes a row, rotated
across them, and the attributes are left alone.

**Adapted, in four places:**
- The font is a variable (`fzx(F)` sets it), not an address fixed at
  assembly.
- Out of screen is our failure: `print #4 would go below the screen`. So
  is a line wrapped past 0, which the driver would take for 255 and then
  have PIXEL-ADD report B. That failure happens inside RST 10, whose
  PRINT-A-2 has done EXX and saved BASIC's HL' beneath the driver's
  pushes, so `zxf_below` puts both back first. Without that, BASIC came
  back with "C Nonsense in BASIC", which zxrun's new report check caught
  the first time a test failed there.
- Nothing past x 255. The driver counts only the low byte of the screen
  address across its three bytes, so at the right edge the third lands
  on the next text row's left.
- Nothing below row 191, which the driver's next-line arithmetic turns
  into the attributes.

The last two can only show with a font that breaks its own rules, with
stray bits past a character's width or rows past its line. So
`tools/make_fzx.py --stray` makes one, `interp/tests/stray.fzx`, and a
suite case peeks where the stock driver would have written.

**`@embed` brings the font in**: `const F = @embed("font.fzx")` is a
byte table of the file, read from beside the program as it compiles.
Melissa suggested the `@`, and that it be one door ("a generic macro
mechanism, shared across all the generators"). `@f(...)` runs Python in
the checker (`COMPILE_TIME` in `barley.py`) and gives a value that every
backend sees only as a constant. `fzx()` takes only such a constant
table, and the checker reads it as a font then (`zxgfx.fzx_problem`): a
?, and every character's rows inside the file. So nothing at run time
checks it, and a font can't be freed or moved under the driver.

**The fonts are their makers'**, and none ship here. Their notes give
copyrights but no licence to share them. `interp/tests/sprig.fzx` is
mine, drawn by `tools/make_fzx.py`: a W 11 pixels wide (rows of two
bytes), descenders (leading), kerning on `.`, `,` and `j`, and blanks
for what it doesn't draw. (Melissa points out that, in the US, the
shapes of bitmap fonts aren't copyrightable, so a proportional font
worked out from the ROM's would be ours to make. It would be a nice
second `@`.)

**How it's tested.**
- `z80/tests/fzx_check.py`, in `./check fragments`, does two things for
  `sprig.fzx` and any fonts in `FZX_FONTS`. If `FZX_DRIVER` says where
  his source is, it assembles the stock driver and types random PRINT #4
  lines into BASIC with it, against the model. And it runs random Barley
  programs, which may fail, on the 48K against the interpreter: the
  output, BASIC's report, and the screen. With Melissa's eight fonts
  that's 108 runs, all agreeing.
- Thirteen suite cases cover the rest, `@embed`'s words among them.
- **20 mutants, all caught**, in the model, the C and `zxfzx.asm`. Three
  survived at first, each because a test happened to be gentle. A line
  wrapped past 0 always landed on 255, so a check for 255 alone passed.
  A stray pixel ORed into an attribute whose bits it already had. And no
  string held a control code, which the driver would take as AT or
  ENTER.

## frame: every frame, in the interrupt (IM 2)

Saturday 10 October. Melissa: "We should also be able to support IM2
stuff if we want to be extra cool." Then, when I asked how it should
look: "make a few prototype programs that you can't run yet and see how
you *want* to code things and let that guide your hand." So I wrote four
(`drafts/barley-lang/im2-prototypes/`, beside the design note): a
spinner and a cycling border while a long solve runs, a tune on a 128's
AY, a game's heartbeat that prints the score, and a clock on the bottom
line. Three needed nothing that isn't safe inside the interrupt itself.
The fourth wanted to print, and is better written the third's way:
`frame` counts, and `main` prints. So there's one kind of `frame`, in
the interrupt, and the deferred kind, and her `atomic` functions, wait
for a program that needs them.

**Why it's 16-bit.** The interrupt comes between any two instructions,
so `frame` can't share anything the program might be in the middle of.
Function slots are fixed addresses. The 32- and 64-bit routines keep
scratch in memory (`intdiv.asm`'s `.q`, `.r` and `.n`). Drawing patches
its own code. Printing is RST 10, allocation moves `bly_atop`, and
`ticks()` does DI and EI. `int16.asm` keeps nothing in memory at all. So
`frame` is byte, word, int and bool, their arrays and constant tables,
control flow, and the ports and memory. The checker refuses the rest,
each with a reason (`frame_rules`).

**The table and vector.** I is FEh, and FE00h–FF00h holds 257 FDh, so
every vector is FDFDh, wherever the data bus floats. FDFDh holds a jump
to the handler, just under the table, and the UDGs at FF58h are left
alone. A program with a `frame` is built under FDFDh, which costs it 260
bytes. Melissa remembered a trick, and it's real. The 48K ROM's pages
39h–3Bh are FFh throughout, so with I = 39h every vector is FFFFh. A JR
there takes its displacement from 0000h, which is DI (F3h), and so lands
at FFF4h. It saves the table, but takes the tails of UDGs T and U, and
it's 48K only, so I left it.

**The handler** saves AF, BC, DE, HL and IX. It also saves `bly_line`,
since `frame`'s lines mustn't be the program's if it fails later. Then
it calls `f_frame`, restores all that, and jumps to 0038h, so FRAMES and
the keyboard carry on. A failure inside `frame` ends the program from
inside the interrupt, and `bly_exit` now puts IM 1 back and interrupts
on, always. That's three bytes in every program, and the only change to
the bench.

**Off the Spectrum**, `frame` runs as the model's frames pass: n times
in `pause(n)`, once in each `ticks()`. On the 48K, `pause(6)` with
`frame` on is exactly six frames too, so a program paced by pauses
agrees everywhere, and the suite's cases are written that way. A frame
during a long computation, or during `ask()`, happens only on the
machine.

On the way, the prototypes asked for `for i: word in 0..8`, which was
refused (the literals settled to int before the loop variable's type was
seen), so a typed `for` over a literal range now takes its type.

**How it's tested.** Twelve suite cases. The spinner one has its picture
compared on the 48K, which ran six frames in `pause(6)` as the model
does. Then a failure inside `frame`, and a failure in the program after
frames have run, which must still name its own line (the case puts
`pause(3)` and a failing long index on one line, so the line is set
once, before the frames). The ROM's clock still counting through
`frame`, each kind of refusal, CP/M, and the typed range. **15 mutants:
14 caught, and one equivalent, kept on purpose.** Taking out the
handler's saving of IX survives, since frame's 16-bit code never touches
IX today. It's kept as insurance (four bytes, and 29 T a frame). My
first try at that mutant took out the push but not the pop, and was
"caught" for the wrong reason, by the stack it unbalanced.

## Floats on the Spectrum: the ROM's calculator, and the plumbing to it

*Files: `fp.asm` (target `zx48`), the float parts of `../z80gen.py`
(`rom5`, `float_cast`, `float_fn` and the FLOAT branches), ABI.md
section 11. Tests: `../tests/test_fp.py [--quick] [--seed N] [--costs]`
on omse-ai's 48K through `../tests/fprig.py`,
`../tests/test_fp_mutants.py`, and six new float tests in
`../../interp/tests/semantics.txt`. Run the Python ones with omse-ai's
Python (`OMSE_AI_PYTHON`).*

**What's here.** Every routine ABI.md section 11 asks for: `+ - * / **`,
negate, compare, sqrt sin cos tan asin acos atan ln exp, trunc floor
round abs, conversions from every integer type and back (truncating,
with `{x} doesn't fit in a {type}`), and printing. The generator emits
them for `float` on `zx48`; on CP/M it still stops, as before. 2023 day
6 gives `Part 2: 71503` on its example on a 48K, and agrees with the
interpreter on six real-sized races too (t around 5e7, d around 5e14):
the floats aim, the quads land.

**Who does the work:**
- **The ROM:** `+ - * / **` and the nine functions, one calculator
  operation a call (RST 28h, a script of one literal and end-calc, the
  literal patched in). That is "you get what you get": its precision,
  its speed (SQR is exp(ln x / 2), a third of a million T-states), and
  its quirks, except the ones below.
- **Z80, exact:** compare, negate, abs, trunc, floor, round, and all the
  conversions. They work on the 5 bytes directly (a common unpack to
  sign, exponent and a 32-bit mantissa; a common "whole part and the
  fraction's first bits" for trunc, floor, round and casts; a common
  "64-bit magnitude to 5 bytes" for conversions and the answers of trunc
  and friends). They cost about 3K T-states at most (compare under 2K),
  and they avoid its INT.

**The ROM's errors, caught: Melissa O'Neill's idea.** Her
`call_with_errhandler`
([spectrum-minilib](https://github.com/imneme/spectrum-minilib)) points
ERR_SP at a handler on the stack, so the ROM's own error unwinding
(ERROR-3: SP from ERR_SP, then SET-STK's RET) returns into it, with the
report in ERR_NR. I borrowed it, as she said I could ("I'd say yes. Of
course I would."), with her name on it in `fp.asm`. Hers passes the
routine in the alternates; ours doesn't need to, since it's always RST
28h. What the handler must put back, found one at a time (and each now a
mutant the rig catches):
- **HL'.** The calculator takes HL' for its script pointer and gives
  BASIC's back at end-calc; an error leaves it taken, and returning to
  BASIC with it wrong would crash after USR. It's saved in memory before
  each RST 28h. (My first idea read it off the stack, where RST 28h
  parks it just under the handler's address. That works until an
  interrupt arrives in ERROR-3 just after SP moves, and pushes its
  return address on top of it.)
- **ERR_SP** (BASIC's own), **ERR_NR** (FFh: no error), and **X_PTR**,
  which ERROR-1 overwrites with CH_ADD.
- **The words.** "6 Number too big" from arithmetic is `float overflow`;
  from a function, it and "A Invalid argument" are
  `{name}({x}) has no answer`, x printed by the ROM. `0 ** -1` and a
  negative base with a fractional exponent are `float ** has no answer`,
  and a zero divisor is `division by zero`, both caught before the ROM
  sees them, so the words are the interpreter's.

**Where the ROM is mended, or worked round:**
- **−65536.** `-65535 - 1` comes out of the ROM's addition as the short
  form `00 FF 00 00 00`, which PRINT then shows as −1E−38, and INT of
  anything in (−65537, −65536] is −1. Every calculator answer is checked
  for that one form and rewritten in full (`91 80 00 00 00`); trunc,
  floor and round are ours. The Z80 routines read the bad form correctly
  anyway, in case one ever arrives.
- **Negative bases.** The ROM's to-power is exp(b ln a), so
  `(-2.0) ** 2` is "A Invalid argument", where the interpreter
  (math.pow) says 4. Squaring a difference is common enough that this
  would bite, so a negative a takes |a| ** b, negated when b is an odd
  whole number.
- **PRINT-FP of a number between −1 and 1 leaves a 0 on the calculator
  stack** (the ROM's STR$ bug: SkoolKit's ROM notes, "STR$ and small
  numbers"). `bly_pr_f` puts STKEND back afterwards.
- **Left alone:** the 34th bit of division (1/10 is `7D 4C CC CC CC`,
  not `...CD`): 2.3e-10 relative, inside what you get. The generator's
  literal 0.1 is the correctly rounded `...CD`, so a literal can be a
  hair better than the same number computed on the machine.

**Printing** is PRINT-FP's: 8 significant digits, `0.5`, `.0001`,
`1E+10`, `1.2345679E+8`, `-2E+9`. Its characters go to a channel of ours
(CURCHL pointed at a 4-byte channel record whose output routine fills a
buffer), and then through `bly_out`, so print's column, and so the
zones, stay right. **omse-ai's text log follows CHAN-OPEN's stream
number, not CURCHL**, so the first version printed every float twice in
the log (once from PRINT-FP, once from us), though a real screen would
have shown it once. `bly_pr_f` now opens stream 3 before PRINT-FP and
stream 2 after, which is harmless on the machine (CHAN-S's TEMPS copies
the permanent colours, which Barley always sets in pairs).

**Tolerances that held** (`test_fp.py`, about 800 random cases a routine
on each of seeds 1 to 8, all passing; the worst error seen, as a
fraction of its tolerance):

| what | tolerance | worst |
|---|---|---|
| `+` `-` | 1e-9 of the bigger operand | 0.35, 0.34 |
| `*` `/` | 1e-9 relative | 0.23, 0.43 |
| `**` | 1e-9 + 8e-10 × \|b ln a\| relative (exp(b ln a): ln's error, times b, becomes exp's) | 0.80 |
| `exp` | 1e-9 + 6e-10 × \|x\| relative | 0.76 |
| `sqrt` | 1e-9 + 8e-10 × \|ln x / 2\| relative | 0.62 |
| `ln` | 3e-9 + 1e-9 × \|ln x\| absolute | 0.44 |
| `sin` `cos` | 3e-9 × max(1, \|x\|) absolute (the argument is reduced with 32 bits: sin(64713) is off by 1.5e-5) | 0.23, 0.19 |
| `tan` | (3e-9 × max(1, \|x\|) + 1e-8 × \|tan x\|) × (1 + tan² x) | 0.20 |
| `asin` `acos` | 3e-9 + 2e-10 / sqrt(1 − x²) absolute (1 − x² cancels near ±1) | 0.45, 0.40 |
| `atan` | 3e-9 absolute | 0.15 |
| compare, negate, abs, trunc, floor, round, conversions, literals | exact | |

So "about 1e-9 relative" holds for the four operations; the functions
are as good as their arguments allow, and for big arguments that's much
less (exp's 1e-9 + 6e-10 × 88 is 5e-8 at the top of the range). **The
suite's runner allows 1e-7** on numbers printed with a point or an
exponent: PRINT-FP's 8 digits are 5e-8 on their own.

**Cost** (T-states on omse-ai's 48K, interrupts off, the CALL included;
the ROM's share is most of every row that uses it):

| routine | T |
|---|---:|
| `bly_fadd` 1.5 + 2.25 / 12345.7 + 0.001 | 2,713 / 4,062 |
| `bly_fsub` 1e10 − 3 | 5,819 |
| `bly_fmul` 1.5 × 2.25 / π × e | 6,183 / 6,530 |
| `bly_fdiv` 1 / 3 | 9,400 |
| `bly_fpow` 2 ** 10 / 1.5 ** 2.5 / (−2) ** 3 | 376,214 / 377,868 / 377,258 |
| `bly_fsqrt` 2 / 71503.5 | 347,806 / 384,309 |
| `bly_fsin` / `bly_fcos` / `bly_ftan` of 1 | 138,092 / 144,073 / 289,874 |
| `bly_fasin` / `bly_facos` of 0.5, `bly_fatan` of 1 | 608,518 / 614,337 / 213,410 |
| `bly_fln` 10 / `bly_fexp` 1 | 228,174 / 144,461 |
| `bly_ftrunc` / `bly_ffloor` −2.5, `bly_fround` 1234.5678 | 3,441 / 3,537 / 2,814 |
| `bly_fneg` / `bly_fabs` | 211 / 252 |
| `bly_fcmp` 1.5, 2.25 / 100, 100 (short forms) / −3, 2 | 630 / 1,626 / 1,906 |
| `bly_f_from_u16` / `bly_f_from_i16` | 120 / 116 |
| `bly_f_from_i64` 71530 / 2^40 + 12345 | 1,301 / 1,190 |
| `bly_f_to_int` int 13.15 / quad 4.5e15 | 3,278 / 1,945 |
| `bly_pr_f` 3.5 / 1/3 / 123456789 / −1.2345e−20 | 186,733 / 66,936 / 53,097 / 266,550 |
| code | `fp.asm` 1,596 bytes, its scratch and messages included |

A sqrt or a `**` is a tenth of a second on a real 48K, and asin a fifth;
printing a float is up to a tenth. Day 6 needs one sqrt.

**Testing:**
- **The rig** (`fprig.py`): the routines on a tape with a loop that
  loads HL DE BC A from a block, calls whatever address Python poked in,
  and stores A; Python stops it at the loop's top with a breakpoint each
  time. A failure ends in `bly_exit`, whose return to BASIC is pointed
  back at the loop (`bly_basic_sp` is poked), so a failing case costs no
  reload. **After every call it checks IY, HL', ERR_SP, ERR_NR, X_PTR,
  MEM and an empty calculator stack against their values at the start.**
  The whole of `test_fp.py` takes about 25 seconds.
- **`test_fp.py`:** exact Fractions for the exact routines (both forms
  of every whole number, the −65536 slip, every type's edges for the
  casts), Python's math within the tolerances above for the ROM's, every
  failure message word for word, printing that reads back within 8
  digits and moves the column, and the generator's `rom5` (nearest, half
  away from zero, short only when whole).
- **Mutants:** `test_fp_mutants.py` breaks `fp.asm` 22 ways (each of the
  handler's restorations, the −65536 repair, the stray-0 repair, the
  stream step, signs, rounding, ranges, the short form's arithmetic):
  **22 of 22 caught**. Eight breaks of the generator's float plumbing
  (`+` as `-`, a word converted as an int, sign of a negative as 255,
  floats sorted as longs, negation as abs, literals truncated, every
  cast checked as a quad, a cast failing on the wrong line): **8 of 8
  caught**, seven by the suite and the truncated literals (which the
  suite's 1e-7 can't see) by `test_fp.py`'s literal checks.
- **The suite:** interpreter, C and Spectrum all pass the six new float
  tests and the three old ones (54 of 54 each); four of them are `ok~`
  on the Spectrum.

**Found on the way, for others:**
- **The interpreter's checker never declares a float parameter**
  (`barley.py`, the loop over `d.params` in `check()`:
  `pty in (BOOL, STR)` lacks FLOAT), so `func f(x: float)` says
  `x is not defined`. With that one word added, float parameters and
  recursion through them work on the 48K too. (Fixed since.)
- **`interp/tests/run.py` writes `_case.bly` into the tests folder and
  builds into one shared `zbuild`**, so two runs of the suite at once
  got each other's programs: my first Spectrum run was a dozen failures
  that were another `--c` run's. (Fixed since: each run builds in a
  directory of its own.)

## Reading a float: s.float() through the ROM's DEC-TO-FP (11 Oct 2026)

*Files: `fp_read.asm` (target `zx48`), `bly_str_float` in
`../../c/rt/barley.h`, `FLOAT_RE` and `e_dot` in
`../../interp/barley.py`. Tests: `test_strfloat` in
`../tests/test_fp.py`, ten mutants in `../tests/test_fp_mutants.py`,
three cases in the suite.* Melissa's idea: let the ROM read it, as BASIC
does.

**What it is.** The interpreter's pattern finds the number
(`\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?`), and then each machine
reads that span its own way: Python's `float()`, C's `strtod`, and on
the 48K the ROM's DEC-TO-FP at 2C9Bh. The public spectrum-minilib has no
VAL to borrow, and DEC-TO-FP is the part of VAL that matters. Its bytes,
read out of the ROM rather than remembered, open with `CP C4h` (the BIN
token) before the decimal path at 2CB8h; it takes A = the character at
CH_ADD and no sign. pyhsb's `romfp.py` (Melissa's pointer, mid-build)
sets it up the same way, which confirmed the contract.

**The traps, and what's done about them:**
- **The ROM skips spaces as it reads** (after the point, through RST 18h
  and 20h), so `2.5 3` would be 2.53 and `5. 3` would be 5.3. The byte
  after the number is made an ENTER while the ROM reads and put back
  after, failure or not: no copy, however long the number.
- **CH_ADD is BASIC's.** Saved and put back; the rig now checks it after
  every call, which is how the mutant that leaves it in the str is
  caught.
- **Errors** are caught exactly as `fp.asm` catches them (Melissa's
  `call_with_errhandler`). A number the pattern found can only raise "6
  Number too big": `{number} doesn't fit in a float`.
- **The ROM's limits are its own.** E-TO-FP makes 10^(2^k) by squaring,
  so any exponent of 64 or more either way needs 10^64 and is too big:
  `1e-64` fails on the 48K while `1e-50` quietly underflows to 0. The
  interpreter and C read `1e-400` as 0 and fail only past a double's
  range. That's DESIGN's "you get what you get", and DESIGN says so.

**The seam with literals, measured.** `rom5` rounds a literal to the
nearest 5 bytes; DEC-TO-FP rounds at every digit. Through pyhsb's
z80mini running the real ROM's code, by value, 1,500 of each shape:
`d.d` 93% the same as the literal and 7% one bit off; `0.ddd` 61% the
same, 39% one bit, 0.5% two; `d.ddEe` 61% the same, 33% one bit, 5% two,
0.5% more. Whole numbers always agree. `"0.1".float()` is
`7D 4C CC CC CC`, the literal `0.1` is `…CD` (test_fp.py's literal check
already said the ROM's own 1/10 ends in CC).

**Costs** (T-states, on the ROM, the call included): `"7"` 9,972; `"42"`
17,481; `"3.25"` 55,997; `"-17.5"` 43,560; `"0.001"` 64,618;
`"123456.789"` 124,340; `"2.5e-3"` 74,337; `"6.02E23"` 125,855. About
7,500 a whole digit and 20,000 a digit after the point: at 3.5 MHz,
about 60 numbers like `3.25` a second (350 single digits), so a thousand
floats in an input take a quarter of a minute.

**Testing:** `test_strfloat` reads 34 chosen strings and 75 random ones
(`--quick`; 400 in full) on the ROM against Python's reading of the same
span, within 2e-9 (worst seen 9.8e-10, on `4.34639984e23`), and checks
every failure word for word and that the str and the byte after it come
back unchanged. **Mutants: 10 of 10 caught** (the ENTER, the byte put
back, CH_ADD, the minus, ERR_SP, ERR_NR, the exponent, leading spaces, a
point alone, an `e` without digits). Two first didn't apply (their lines
start with a label) and said so rather than passing.

**Found on the way:** `tools/check_docs.py`'s card check looked for
every method name as a word anywhere on the card, so a method named like
a function or a type (`float`, `int`) passed on the strength of
`float(i)`. It now wants those after a dot. It caught `s.float()`
missing; the container methods the card writes bare (`push pop`) are
still fine.

## Floats without a ROM: fp_cpm.asm, the first half (11 Oct 2026)

*Files: `fp_cpm.asm` (targets `cpm`, `test`), `fp_exact.asm` (now
`cpm zx48 test`), `../fp5.py` (the model). Tests:
`../tests/test_fpcpm.py [--quick] [--mutants]`. The design, with its
measurements, is in the drafts' `FLOATS-CPM.md`.* Melissa's next after
`stop`: floats for CP/M. Not yet used by the generator: sqrt, the
functions and reading come first.

**The form is the ROM's own 5 bytes on CP/M too** (Melissa: every 32-bit
integer exact), so the generator and everything `fp_exact.asm` does are
shared with the 48K, and only what the ROM did needs our own code.
**Rounding is one rule everywhere: the nearest, ties away from zero**,
as `rom5` rounds a literal and `bly_f_from_i64` a quad.

**The one trick:** rounding x with ties away is floor(x + 1/2) =
(floor(2x) + 1) >> 1, so an operation needs only the floor of its exact
answer to 33 bits, and no sticky bits at all. `*` keeps the whole 64-bit
product (four `bly_i_mul16`s); `/` is restoring division to 33 quotient
bits; `+` and `-` work in a 64-bit window with the larger number at its
top. What the smaller loses below the window can matter only to a
subtraction, and only when the exponents are exactly 33 apart: from 34
on, what's left of it is between 1 and 2^30, so the difference can't sit
on a rounding boundary. (A first version also tracked whole bytes lost
below the window; its mutant couldn't be caught, because bytes are lost
only from 40 apart. The dead code went, the argument went into the
comment.)

**Printing** is `fp5.show`: PRINT-FP's layout, measured on the ROM (8
digits; a leading 0 only for 0.1 to 0.99...; positional from 10^7 down
to 10^-5, E notation outside), with the digits exactly rounded: q =
floor(x x 10^(8-k)) in a 24-byte integer, by x10 then the binary shift,
or the shift then /10 (nested floors of positive divisions are exact),
with k's guess checked by q's range, not by the rounded digits. Against
the ROM's own PRINT-FP over 2,000 random floats, 1,992 print the same,
and in the other 8 it's the ROM's last digit that's wrong.

**Costs** (T, the call included, `--quick`): `+` 3,013 mean, `-` 3,081,
`*` 4,938, `/` 18,301, printing 63,859 (557 to 370,531). The ROM's `+`,
`*` and `/`: 2,713, 6,183 and 9,400, and printing 53,000 to 266,000. `/`
wants a faster divide; printing went from 204,000 to 64,000 mean by
shifting whole bytes first and keeping x10 and /10 to the significant
bytes.

**Testing:** bit for bit and text for text, 1,895 checks in `--quick`, 0
wrong. **Mutants: 19 of 19 caught, and the CONTROL left alone**: never
rounding, rounding on the wrong bit, a subtraction forgetting what was
lost, an addition its carry, the exponent bias, a partial product's
carry, the quotient's last bit, underflow as overflow, and seven ways to
print wrongly. Two first missed for the test's sake: one mutant's text
began with a label, and underflow at exactly exponent 0 needed cases
aimed at the exponent's edges.

**sqrt, the same day:** exact, by the bit-pair method. x = f x 2^p with
f in [1/2, 1); the root is sqrt(f) x 2^(p/2), or sqrt(f/2) x 2^((p+1)/2)
for an odd p, and its 33-bit floor is isqrt(M << 34) or isqrt(M << 33),
which the bit-pair method gives exactly; the last bit rounds it. A
negative says `sqrt({x}) has no answer`, x printed as the 48K prints it.
Bit for bit with `fp5.sqrt` (checked itself against an 80-digit Decimal
root on 20,000 cases), perfect squares exact; 53,268 T mean. Three
mutants, all caught (and the division's mutant text, now found twice,
made longer: the runner refuses a mutant it can't place exactly).

**Reading, `s.float()` without a ROM:** exact decimal to binary needs,
in principle, every digit (a halfway point between two 5-byte floats can
take ~160 digits to write), so the rule is **the first 40 significant
digits, rounded exactly** (ties away), in the model (`fp5.read`) and the
Z80 alike. Since 10^a = 5^a x 2^a, the big integer only meets fives: X
>= 0 is D x 5^X with its bit length giving the exponent; X < 0 is
floor(D x 2^s / 5^-X), s guessed and corrected by the quotient's size,
as printing does. Bit for bit with the model on 338 readings and every
failure. A "keeps 30 digits" mutant first went uncaught: digits past the
30th matter only at an exact tie, and truncation only lowers a number,
so it took a tie written in 31 to 40 digits, 1 + 2^-32 =
1.00000000023283064365386962890625, to tell them apart. Mean 75,581 T
(1,946 to 1,240,042; the ROM's DEC-TO-FP 10,000 to 125,000), after ÷5
and ×5 were kept to the significant bytes (from 141,926).

**The functions, as calculator scripts (exp and ln first):** as the
ROM's are, scripts for a small stack machine (`bly_fk`) over our own
exact `+ - * /`, with a Horner step; the constants exact rationals
rounded once (the drafts' `coeffs.py`), Taylor terms to under 1e-12 on
the reduced range. exp: k = round(x / ln 2), r = x - k ln 2 with ln 2 in
two parts (k times the first is exact), e^r to r^11, and 2^k straight
into the exponent byte; past ln(the biggest float) (88.0297, not a
double's 709) it says `exp({x}) has no answer`, as the 48K, and under ln
2^-129 it's 0. ln: m in [sqrt(1/2), sqrt 2), t = (m-1)/(m+1), the atanh
series to t^13, and k ln 2 added last. **Worst relative error against
Python: exp 2.5e-10, ln 2.33e-10, about one unit in the last place**
(test_fp allows the ROM's ten times that). exp 153,434 T mean (the ROM
144,461), ln 104,577 (the ROM 228,174). Two mutants, both caught: a
truncated series hides under the tolerance by design, but a shifted
coefficient table can't.

**sin, cos, tan, atan, asin, acos, the same way:** sin and cos reduce by
pi/2 in two parts and take n mod 4 from `bly_fx.toint` (exact under
2^64; past it n is a multiple of 4), cos being sin a quarter on; tan is
sin r / cos r, or -cos r / sin r in an odd quadrant. atan goes through
1/x past 1 and through (y sqrt3 - 1)/(y + sqrt3) past tan(pi/12), then
its series to y^19; asin is atan(x / sqrt(1 - x^2)) with +-1 exactly
+-pi/2, acos pi/2 less it; past 1 they say `{name}({x}) has no answer`.
Held to test_fp's tolerance shapes for the ROM with constants about
three times tighter, **the worst is 0.4 of that** (acos; sin 0.07, cos
0.15, tan 0.07, atan 0.29, asin 0.26). Means: sin and cos 115,000 T, tan
215,000, atan 100,000 (the ROM 213,410), asin and acos 240,000 (the
ROM's 608,518 and 614,337). Two mutants (sin's quadrant, atan's pi/6),
caught.

## Random numbers: Melissa's generator (random.asm, rndclock.asm)

*Files: `random.asm`, `rndclock.asm` (the 48K's clock seed),
`rndclock_cpm.asm` (CP/M's). Tests: `../tests/test_random.py`
(`--mutants`). The meaning: `interp/barley.py`'s `rng_` functions.*

The generator is Melissa's, given as a C++ model of her Z80 code
(`prng-test.cpp`, `-s`): BCDE is permuted by four byte swizzles
(`D = rlca(B) ^ D`, `C = rlca(D) + C`, `E = rrca3(C) ^ E`,
`B = rrca(E) - B`, each feeding the next through A), and HL takes
`HL += BC; L ^= H; HL += DE` and is the output. The swizzles go into
fifteen instructions almost as she wrote them. Before any Z80 was
written, a Python model of the step was held to her binary's first
100,000 words, and so was the interpreter's (both the same).

| Routine | T-states | Notes |
|---|---|---|
| `bly_rand16` | 233 | one step, the word in HL |
| `bly_random_u16` | 680-1,350 (`random(6)`: 770 on average) | the mask is grown a bit at a time, 16 steps at most: the cheap thing to make faster |
| `bly_random_u16` | 992 / 1,304 | `random(1000)`, `random(65535)`: one try |
| `bly_random_q` | 3,400-10,600 (4,090 on average) | `random(100000)`, two words a try |
| `bly_random_q` | 4,100-14,300 (6,045 on average) | `random(5000000000)`, two words a try |

**Tested:** `bly_rand16` 64 steps at a time from states anywhere in the
2^32; `random(n)` for n at every edge of the mask and of one, two and
four words a try (1, 2, 3, the powers of two and one either side, 65535,
2^16, 2^32 and 2^48 and either side, 2^62, 2^63 - 1) and at random; its
failures word for word (0, negative ints, negative quads); and
`randomize` for seeds anywhere in the 64 bits. Each is compared on the
value and on **the state it leaves**, which says the Z80 drew exactly
the words the meaning draws, the thing every backend's agreement rests
on. **Mutants:** the last swizzle turning left, or adding; the xor into
H, not L; the mask smeared a shift short, or its low byte short of FFh
(since 10 October, when the mask stopped growing a bit at a time); a
draw past m kept (16 bits and 64); two words a try where one or four
belong; the first word put at the bottom; the seed outside the long
cycles' run, or its low 16 bits in the wrong place; a negative int let
through; the message misspelt: **14 of 14 caught**, and the control (a
comment) passes. (Commit da7f0d3's message said 15 of 15: it counted the
control.)

**Found on the way:** an asm function can't be called `pair`: sjasmplus
takes it, and `mod`, `high`, `low`, `abs`, `z`, `c` and a dozen others,
as its own words even as labels. Asking sjasmplus each word in turn gave
the list, which `z80gen.py` keeps as `ASM_WORDS`.

## Printing a byte: the path before RST 10

*Files: `core.asm` (`bly_pr_str`, `bly_out`), `plat_zx.asm`
(`bly_putc`), and `z80gen.py`'s `item`.*

The numbers me counted it in the Pasta/80 bake-off ("why we lose,
routine by routine"): a byte of a str cost 291 T before the ROM's RST
10, against Pasta/80's 106, and `print chr(b);` about 600 T, since it
made a one-byte str first. Since 10 October:
- `bly_out` keeps A without saving it (`ld` and `inc` don't touch A),
  and jumps to `bly_putc` straight from either arm: 33 T less.
- `bly_putc` tests for the printable bytes first, as nearly every byte
  is, and the newline only among the control codes: 24 T less. Its first
  instruction is still the three bytes `zxlower.asm` and `zxfzx.asm`
  patch with a JP.
- `bly_pr_str` tests its count at the bottom of the loop.
- A print item that's `chr(b)` sends b to `bly_out` itself.

So about 218 T a byte of a str, and a `chr(b)` item about 300 T less
than it was: a program printing 2,040 bytes of strs and 400 `chr`s was
272,709 T quicker on the 48K. What's left is the column (`bly_col`,
which the zones and a failure's recolouring need), `SCR_CT` every byte
(a long enough str wraps more than 255 rows, and "scroll?" must never
ask), and saving HL and BC around RST 10, which keeps nothing.
