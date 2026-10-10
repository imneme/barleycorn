# Barleycorn: the design

*The design the language was built from, kept up to date with what was
built. It says what each piece is for and why it's there. Section 4 is
the whole language on one page; section 13 lists what isn't built yet.
HISTORY.md tells where it came from: "Barley" below is the first,
smaller language, whose compiler Barleycorn grew out of.*

## The decisions, and the reasons for them

- **Floats are in.** You use them, you get what you get, and what you
  get on a Spectrum is the ROM's calculator.
- **It's for making things sing, not only for answers.** Screen and
  sound are on the card. They have reference twins (a virtual screen
  saved as a picture, and a log of the sound), so programs that draw
  still run everywhere.
- **Two compiled backends: Z80 assembly and deliberately plain C.** C is
  the fast route (native, through clang), and it stays plain so that
  it's easy to trust. Not LLVM IR, which goes stale in a month.
- **Linking comes before assembly.** The library is a pile of fragments
  that declare what they need. The compiler gathers only what's used,
  pastes it, and assembles once.
- **Extensible, and testable everywhere.** A hand-written routine ships
  with a reference twin in Barleycorn. The twin runs in the interpreter
  and in C; on the Z80 the routine is checked against its twin.
- **Three implementations must agree**, output by output: the
  interpreter (the spec), the C, and the Z80.
- **Division truncates and overflow wraps**, as C gives for free, so the
  C stays plain. `mod(a, m)` is there by name for the ring-wrapping
  case. Checks still trap signed overflow, on every backend.
- **One `for`:** `for x in ...`, with half-open ranges `a..b`. One loop
  statement, one range notation, everywhere.
- **Text is bytes, and the charset is decided** (section 5): the
  Spectrum's £ and ©, and no token ever printed by accident.
- **Start tiny.** An interpreter, then three puzzles end to end through
  every backend. After that the language grows a puzzle at a time, and
  each feature arrives with the puzzle that needed it.
- **Found while building the interpreter:** maps and sets walk in
  insertion order, because three implementations can only agree on a
  defined order. `print` takes the rest of its line, and `at` is a
  keyword only straight after it. `print`'s `,` pads with spaces to
  16-column zones on every target. `s.ints()` reads a minus as a sign
  only when it doesn't follow a digit, so `2-4` is two numbers.
  `s.int()` takes its type from where it's used, as a literal does
  (`long` when nothing says). An assignment evaluates its target's parts
  first, once, then the value. And the interpreter models a target
  (`--as zx48` or `--as cpm`), so `if ZX` means the same thing there as
  on the machine.

## 1. What it's for

Writing things on a 48K Spectrum, and under CP/M, that are a pleasure to
write and worth watching. **Advent of Code is the first use case and the
measuring stick.** The Spectrum solutions it was made for don't just
calculate the answer, they make it *sing*: the search spreads across the
screen, and the machine plays something when it's done. So:

- **Text comes in, and numbers, pictures and sound go out.** Parsing
  lines, pulling integers out of them, walking grids and searching
  graphs are most of what AoC asks, so each is one word, not a library
  you write first. Drawing and sound are one word each too.
- **The answers are big.** Part 2 often passes 2^32 (2023 day 8's is
  around 10^13), so 64-bit integers exist even on a machine whose
  registers are 16 bits.
- **The machine is small.** 40K is all a 48K Spectrum can spare for
  code, input and data together, and AoC inputs run 10–30K. Memory has
  to be visible: you should know where every byte went, and the language
  should help.
- **The machine is slow, honestly.** On the order of 50,000 simple
  statements a second at 3.5 MHz (Barley's Sieve is about 75 T a
  statement), so 10^6 steps take 20 seconds and 10^8 most of an hour.
  There are two faster lanes. CP/M under tnylpo runs the same Z80 code
  about **430 times faster than a real Spectrum** (measured: 1,000 Sieve
  passes, ~9.6 billion T-states, in 6.4 s). And the C backend runs
  natively.

**Small enough to be known** has a test: the whole language fits on one
page (section 4). If a feature doesn't fit, it has to push something
else off. **Every piece being what you'd reach for** has a test too, and
it's measurable: features arrive with the puzzles that need them, and
anything no puzzle has used gets cut (section 10).

## 2. A taste first

AoC 2022 day 12: climb from `S` to `E`, one step up at most. Searching
*downhill* from `E` answers both parts at once.

```
-- AoC 2022 day 12: fewest steps up the hill. Search down from E, and both
-- parts fall out.

func height(ch: byte): byte
  case ch
    when 'S' then return 'a'
    when 'E' then return 'z'
  end
  return ch
end

func main()
  var g = grid()                               -- the input: rows and columns
                                               -- of bytes
  var start = g.find('S')
  var goal = g.find('E')
  var dist = grid[word](g.rows, g.cols, 65535)      -- 65535: not reached yet
  var q = queue[pos](1000)
  dist[goal] = 0
  q.put(goal)
  var part2: word = 65535
  while q.len > 0 do
    var p = q.get()
    if height(g[p]) == 'a' then part2 = min(part2, dist[p]) end
    for d in dirs4 do
      var n = p + d
      -- backwards, a step is allowed if going forwards it climbed at most one
      if g.has(n) and dist[n] == 65535 and height(g[n]) + 1 >= height(g[p]) then
        dist[n] = dist[p] + 1
        q.put(n)
      end
    end
  end
  print "Part 1: "; dist[start]
  print "Part 2: "; part2
end
```

The shape is the first Barley's (`func`, `var`, `if`/`while` ... `end`,
`--` comments). The rest is what you'd reach for in AoC and find:
`case`, `grid()`, `pos` and `dirs4`, a `queue`, BASIC's `print`. Memory
for the real input (41 x 161): the input 6.6K in place, `dist` 13.2K,
the queue 4K. It fits on a 48K with room left. Section 8 has the same
program made to sing.

## 3. The rules it holds itself to

1. **One page.** The reference card in section 4 is the language. The
   rest of this document explains it.
2. **Three implementations agree.** The Python interpreter is the spec.
   The dumb C and the Z80 (on both machines) must print exactly what it
   prints, output by output. The one exception is floats, which section
   5 explains.
3. **Every construct has a cost you can know.** There's a cost card
   (section 12) with a T-states column, and the measuring culture that
   built Barley keeps it honest. Nothing hides an allocation or a loop
   you didn't write.
4. **Memory is visible.** There's no garbage collector. Containers say
   their capacity when you make them, live in an arena, and can be given
   back in bulk with `mark` / `release` (Turbo Pascal's names). `free()`
   tells you what's left.
5. **Checked first, fast second.** Every index, capacity, signed
   overflow and division is checked, on every backend, and a failure
   prints what happened and the line. (A `--fast` that drops the checks
   once the answer's right is planned: section 13.)
6. **Anything missing can be added, and still tested everywhere.** A
   library routine, or one of yours, can be hand-written in Z80 as long
   as it ships a reference twin in Barley (section 5, "The machine").
7. **Nothing breaks the save rule.** Scalars still can't be aliased: no
   pointers and no address-of. Containers are references, but their
   contents live in the arena, never in a variable's slot, so fixed
   slots, operand homes and *save live_after ∩ clobber(callee)* all
   carry over untouched.

## 4. The whole language, on one page

```
-- a comment       const N = 140       const NOTES = "\x00\x02\x04"
const SCALE = int[0, 2, 4, 7, 9]       a table: any element type, read-only
var total: long = 0                    (every variable has a value)
func f(a: int, xs: list[word]): long ... end
                   recursion anywhere; call before define; main() runs first
record Step  risk: word; at: pos  end
                   Step(5, p) makes one; s.risk; records compare by field

STATEMENTS  x = e   x += e   (-= *= /= %= &= |= ^= <<= >>=)   a; b on a line
            if c then ... elif c then ... else ... end
            while c do ... end         for x in xs do ... end
            for i in a..b do ... end   (half-open; rev(a..b) counts down)
            for k, v in m do ... end  case e when v1, v2 then ... else ... end
            break  continue  return [e]  assert c

NUMBERS     byte word dword: unsigned 8, 16, 32
            int long quad: signed 16, 32, 64
            bool: true false.  Overflow wraps; checked builds trap signed
            overflow.  Widen up freely; narrow with a cast: int(x)
            + - * / %  (as C: / truncates, % has the dividend's sign)
            mod(a, m) is never negative    abs min max sign gcd lcm
            & | ^ ~ << >>   and or not    literals 42 0x2A $2A %101010 'a'
            loosest first: or, and, not, == != < > <= >= in, .., | ^, &,
            << >>, + -, * / %, unary - ~, **   (as Python, not C: & binds
            tighter than ==, so x & 1 == 0 means (x & 1) == 0)
            float: the machine's own (the ROM's on a Spectrum).  1.5 2e9
            float(i) trunc floor round sqrt sin cos tan asin acos atan ln
            exp x ** y.  You use them, you get what you get.

TEXT        str: bytes, sliced   s.len  s[i]  s[a..b]  ==  <   for ch in s
            "ASCII, \n and \x90"   s.int()  s.int(k) (the k-th integer)
            s.ints() (all)  s.split(c)  s.find(t)  s.starts(t)  s.trim()
            intern(s) -> word (0, 1, 2...)   name(id) -> str   chr(b)

ARRAYS      T[N]: global, or local where not recursive.  a[i] a.len
            a.sort().  A parameter T[] is by reference.  bit as an element
            type packs 8 to a byte.  An index can be any integer type.

POSITIONS   pos(r, c)  p + d  p - q  ==  p.r  p.c    dirs4 (N E S W)  dirs8

CONTAINERS  list[T](cap)    push pop [i] len sort clear
            queue[T](cap)   put get len
            heap[T](cap)    push pop (smallest) len
            set[K](cap)     add in del len
            map[K, V](cap)  m[k] = v  m[k]  get(k, default)  in  del  len
            grid[T](rows, cols[, v])   g[p]  g[r, c]  has  rows  cols  find
            References, made in the arena, fixed capacity, checked; maps
            and sets walk in insertion order.
            mark() release(m) free()  (not yet)

IN AND OUT  lines() (for line in lines(), or .next())   grid()   input()
            ask(prompt): a line typed (ask("n? ").int() for a number)
            print a; b, c;   BASIC's: ; joins, , pads to the next
            16-column zone, a trailing ; or , keeps the line open.
            A print takes the rest of its line.

SCREEN      cls  ink(0..9)  paper(0..9)  bright(0, 1, 8)  flash(0, 1, 8)
            (8: a square keeps its own; 9: the contrast)  inverse over border
            print at r, c; ...    plot(x, y)  line(x0, y0, x1, y1)
            circle(x, y, r)  point(x, y)  attr(r, c[, a])  udg(n, bytes)
            key()  inkey()  ticks()  pause(frames)
SOUND       beep(ms, semitone)
            (on a 128, later: ay(reg, v)  tone(voice, hz, vol)  quiet())
            On the Spectrum, the real thing; in the interpreter and C, a
            virtual screen saved as a picture and a log of the sound; on
            CP/M, an error, at its line, wherever a run could reach it:
            guard it with if ZX then ... end, or if ZX and ... then

MACHINE     peek(a)  poke(a, v)  inp(port)  outp(port, v)   (call later)
            const ZX, CPM, C: the target, folded away
            func f(...) ... asm "f.asm" end    the body is f's reference
            twin (the Z80 running the fragment: later)
```

## 5. The pieces, and why each one is there

### Numbers

The first Barley's `byte`, `word` and `int` stay as they are, and two
signed types join them: **`long`** (32-bit) and **`quad`** (64-bit).
`quad` is there for answers and products; `long` because most running
totals need more than 16 bits and much less than 64, and on a Z80 a
`long` add is about a third the cost of a `quad` add.

- **Widening is free and silent going up** (byte to word or int, then
  long, then quad), so `sum += line.int()` just works. Going down takes
  a cast. Mixing `word` and `int` still needs one, as it does in Barley,
  because the answer to "is 65535 big or is it -1?" should be written
  down.
- **Overflow wraps, and division truncates**, as on the Z80 and as in C.
  Efficient and simple won, and the deciding argument is the C backend.
  With C's own semantics the C can stay dumb (`/` and `%` as written,
  arithmetic done in unsigned types so signed overflow is never
  undefined), and the three backends agree for free. Unsurprising
  *between backends* matters more than unsurprising in the abstract.
- **`mod(a, m)` is never negative**: it's the one you reach for when a
  position wraps round a ring and can go below zero (`mod(x - 1, w)`).
  Floor division lives there by name rather than being a surprise in
  `/`.
- **Checked builds trap signed overflow**: on the Z80 by testing the V
  flag, in C with `__builtin_add_overflow` and friends, in Python by
  range. Unsigned types wrap even when checked, because wrapping is what
  you want for a hash or a packed key, and it's never what you want for
  a running total. The type says which you meant.
- **`dword`** is unsigned 32 bits, for the hash or packed key a `long`
  would trap on. It widens from `byte` and `word` and to `quad`, and
  meets `int` and `long` only through a cast, as `word` and `int` do. On
  the Z80 its arithmetic is a small fragment of its own, so a program
  without one doesn't carry it.
- **`bool`** is a byte that's 0 or 1, with `true` and `false`. Barley's
  comparisons were already 0 or 1.

### Floats: you get what you get

`float` is the machine's own. **On a Spectrum that's the ROM's 5-byte
floating point**, worked by the ROM's calculator (RST 28h), with its
precision (a 32-bit mantissa, about nine and a half digits), its speed
(thousands of T-states an operation) and its functions: SQR, SIN, COS,
TAN, ASN, ACS, ATN, LN, EXP, `**`. The compiler can emit calculator
scripts directly: `a * b + c` is push a, push b, *multiply*, push c,
*addition*, *end-calc*. The calculator needs IY = 5C3Ah and its stack
between STKBOT and STKEND, which Barley's rules already keep.

Elsewhere it's what's to hand. In C it's a `double`. In the interpreter
it's Python's float (and one day, when exact agreement matters, the real
ROM borrowed through an emulator). On CP/M there's no ROM, so there are
no floats yet. So **floats are the exception to "three implementations
agree"**. Programs that print floats are compared to a tolerance, and
the card says so: you use them, you get what you get.

The way to use them in AoC is to **aim with floats and land with
integers**. In section 8, 2023 day 6 finds the roots of a quadratic in
floats, then steps to the exact answer in `quad`s. That's correct even
at the ROM's precision (checked: 2,000 real-sized races with a 32-bit
mantissa, and none wrong).

### Records

```
record Step
  risk: word
  at: pos
end
```

A record is a value, not a reference: `var s = Step(0, start)` copies,
and a record parameter arrives by value. That's what makes them free in
Barley's scheme. **A record local is just several locals**, one slot (or
register, or operand home) per field, so the save rule, webs and homes
apply field by field with no new machinery.

**Records compare field by field**, like Python's tuples. That one rule
is why `sort()` and `heap` need no comparison function: put the key you
want to order by first. For an unusual order, compute a key record once
(`Hand(kind, c1, c2, c3, c4, c5)` for 2023 day 7). On a Z80 that's also
cheaper than calling a comparator in every comparison.

### Text, and what a byte means on each machine

**`str` is a slice**: a pointer and a length, two words. Literals are
slices into the program; lines are slices into the input, which stays in
memory for the whole run, so nothing is copied and no line goes stale.
Slicing uses the same half-open range as `for`: `s[a..b]`, so
`line[7..10]` is a node name and nothing ever needs a `- 1`.

There's no string building and no concatenation. AoC almost never needs
it. Where it seems to, it wants one of two things: **printing**, which
`print` does a piece at a time, or **a key**, which `intern` does
better. `intern(s)` copies the bytes into the arena once and returns a
small dense number (0, 1, 2...), so maps and arrays are indexed by names
without hashing strings again, and `name(id)` gives the text back.
That's the Spectrum-shaped answer to string keys: names become small
numbers.

The parsing helpers are the ones AoC solutions reach for first:

- `s.ints()` iterates every integer in `s`, signs included, ignoring
  everything else. It's the famous `re.findall(r"-?\d+", line)`,
  probably the most-copied line in Python AoC, without the regex or the
  allocation, and with its classic trap fixed: a minus is a sign only
  when it doesn't follow a digit, so `2-4,6-8` is four positive numbers,
  while `x=-3` is still minus three.
- `s.int(k)` is the k-th of those, so `move 3 from 1 to 2` is
  `line.int(0)`, `line.int(1)`, `line.int(2)`.
- `s.int()` reads a leading integer; `s.split(c)` iterates the pieces
  between `c`s; `for ch in s` walks the bytes.
- **A number read from text takes its type from where it's used**, as a
  literal does: `sum += line.int()` reads a `long` if `sum` is one. With
  nothing to say, it's a `long`. A number too big for its type stops a
  checked build with the number and the line.

**A string is bytes, and the language never translates them.** What
changes between machines is only what printing a byte shows:

- **Source files are UTF-8, but string literals are ASCII**, with
  escapes for anything else (`"\x90"` is the first UDG). A literal `é`
  is an error that says so, rather than two bytes that print as
  keywords.
- **On the Spectrum**, 20h–7Fh print as the ROM's characters, which are
  ASCII except that **60h is £ and 7Fh is ©**. 80h–8Fh are the block
  graphics and 90h–A4h the UDGs. **A5h and up are BASIC's keyword
  tokens, and `print` never sends them to the ROM**, which would expand
  them into words; it prints `?` instead. A newline is ENTER (0Dh).
- **On CP/M**, bytes print as they are (ASCII), and a newline is CR LF.
- **Input** is AoC's ASCII. Line ends may be LF, CR LF or CR, and
  `lines()` treats them all alike. ^Z ends a CP/M file.

### Arrays, and the one bit type

Barley's fixed arrays stay: `var cols: byte[8]`, at a fixed address, as
fast as memory gets. They're now allowed as **locals in functions that
aren't recursive**, where a local is a fixed slot anyway. In a recursive
function a local array would have to be saved across every call, so it's
an error that suggests a `list` instead.

**`bit` is an element type only**, packed eight to a byte:
`var seen: bit[8192]` is 1K. It's the one place the language does
something clever with memory without being asked, and it's visible in
the type. A bit costs about twice a byte to read, and on 48K that trade
is usually right.

**A constant table** is an array made once, in the program itself:
`const SCALE = int[0, 2, 4, 7, 9]`, `const NAMES = str["one", "two"]`,
`const MOVES = pos[pos(-2, -1), pos(-1, -2)]`, or a record's
(`Step[Step(3, pos(0, 1)), ...]`). Its type is in its brackets, and each
element is a constant of that type, so `byte[1, 300]` says 300 doesn't
fit. It's read as any array is (`SCALE[i]`, `SCALE.len`,
`for x in SCALE`), and it can be passed to a function that takes
`int[]`, but nothing may change it. Assigning into it, or sorting it, is
an error, and so is passing it to a function that may change that
parameter, directly or by passing it on: the checker works out which
functions can, over the whole program. `dirs4` and `dirs8` are tables
too, and the same rule holds them (it didn't, until tables came). On the
Z80 a table is laid out in the code exactly as an array is in memory, so
reading one costs what reading an array costs.

### Positions and grids

Half of AoC is grids. **`pos`** is a built-in record of two `int`s, `r`
and `c`, with `+` and `-`. **`dirs4`** (north, east, south, west, so
turning right is `mod(d + 1, 4)`) and **`dirs8`** are constant arrays of
them. A `pos` can be a map key: it packs into 32 bits.

**`grid()`** is the input viewed as a grid: rows and columns over the
text in place, with no copy. **`grid[T](rows, cols, v)`** makes a new
one in the arena. Both index by `pos` or by `r, c`, check bounds in
checked builds, and say `g.has(p)` for the edge test you'd otherwise
write as four comparisons.

### Containers

Five, each a thing AoC reaches for weekly: **list** (a stack and
growable array), **queue** (breadth-first search), **heap** (Dijkstra;
the smallest comes out first, by the record rule), **map** and **set**
(open addressing; keys are numbers or `pos`; `intern` makes names into
numbers). Maps and sets walk their keys **in insertion order**, as
Python's dicts do. It's the only order three implementations can agree
on without sorting, and it's cheap on a Z80 too: the entries live in a
dense array, in order, with a small index of hashes beside it. They're
**references**: assigning or passing one shares it. They're made in the
arena with a **fixed capacity**, which is the honest shape for a 48K
machine. A checked build says `queue full (1000) at line 28` rather than
wandering into the stack, and you raise the number.

They're generic only in the way built-ins are: `list[T]` is specialised
by the compiler for `T`'s size, as C++ templates are, so `xs[i]` on a
`list[word]` is a shift and an add, not a call. **Users can't write
generic code.** That keeps the type system one page long.

`mark()` and `release(m)` give a whole phase's containers back at once:
parse into a map, solve part 1, release, solve part 2 in the same
memory.

### Loops: one `for`

There's one loop over things: **`for x in ...`**. Ranges are half-open,
`a..b` (a up to but not including b), as in Rust; `rev(a..b)` walks the
same numbers downwards. A range is just another iterable, alongside
arrays, containers, `lines()`, `s.split(c)` and `s.ints()`, so the
compiler has one `for` statement and the programmer has one range
notation, the same one slices use. Half-open won because it's less to
write: `for i in 0..n` against `for i = 0 to n - 1`, and `line[7..10]`
against `line[7..9]`.

The first Barley's `for i = a to b` and `downto` are retired. The
thirteen programs of its benchmark suite converted mechanically, and
they're the benchmark the Z80 backend is measured with (`z80/bench/`,
and HISTORY.md).

### Input and output

`lines()` is an iterator over the input's lines, without their line
ends. Use `for line in lines() do` for all of them, or `.next()` to take
the first few by hand, then `for` takes the rest. A blank line is `""`.
`grid()` and `input()` (the whole text as one `str`) are the other two
ways in. **How the input gets there** depends on the target (section 7):
bundled onto the tape, read from a CP/M file, or read from a file by the
interpreter and the C.

**The keyboard** is three words. `ask(prompt)` is BASIC's INPUT LINE:
the line typed, as a `str`, and `ask("How many? ").int()` for a number.
On the Spectrum it is the ROM's own editor in the lower screen, cursor
keys, DELETE and all; the way in is spectrum-minilib's, which was worked
out from the HiSoft BASIC compiler. `inkey()` is INKEY$, the key held
down now, as a `byte` (0 for none), so it compares with `'q'`. `key()`
is a new keypress since it last looked. **The prompt and the typing are
display, not output,** as `print at` is: on the Spectrum they're in the
lower screen, which `ask()` clears again as INPUT does, and the
interpreter and C put the prompt on stderr. CP/M has one console, so
there they're output: the prompt, the line echoed, and a newline.
**Cursor down stops an `ask()`**, as it stops INPUT LINE (BREAK, in the
ROM's editor, only types a space), and so do ^C on CP/M and running out
of keys anywhere; it fails with `STOP in ask`. In the interpreter and C,
the keys come on stdin, which is how the tests type them. A terminal
gives `ask()` its lines but has no keys for `inkey()` and `key()`, which
find none held. `inkey()` and `key()` are the Spectrum's, so they're
Spectrum-only on CP/M; `ask()` is everywhere.

**`print` is BASIC's PRINT.** `;` joins, `,` moves to the next 16-column
zone, and a trailing `;` or `,` keeps the line open. Everyone who grew
up on a Spectrum already knows it, and AoC output is "Part 1: " and a
number. Two details make it agree everywhere: the zones are padded with
spaces on every target (not a tab on CP/M), and a `print` takes the rest
of its line, so its `;` never gets mistaken for the statement separator.

### Screen and sound: making it sing

The screen library speaks **BASIC's own vocabulary and coordinates**:
`plot(x, y)` with (0, 0) at the bottom left, `line`, `circle`, `ink`,
`paper`, `bright`, `flash`, `inverse`, `over`, `border`, `print at`,
`attr`, `udg`, and `point` to read a pixel back. On the Spectrum,
drawing is done by Barleycorn's own Z80 routines, checked pixel for
pixel against the reference (`z80/zxgfx.py`), which is in turn checked
against the real ROM for text.

**The colours are BASIC's, 8 and 9 included.** `ink` and `paper` take
0..7, or 8 for transparent (a square printed or drawn on keeps its own
ink, or paper), or 9 for the contrast (white on a dark square, black on
a light one); `bright` and `flash` take 0, 1 or 8 (true and false too).
A square gets them as the ROM's PO-ATTR gives them, and `cls` clears in
the colours as they are, as BASIC's CLS does. `attr(r, c)` reads a
square's byte back, as BASIC's `ATTR` does; `attr(r, c, a)` sets it.
`z80/tests/co_temp_check.py` holds the model's colours to BASIC itself,
typed in on omse-ai's 48K, and `rom_text_check.py` its drawing to the
ROM.

**Sound** is `beep(ms, semitone)` through the ROM's BEEPER on any
Spectrum. On a 128 it would be the AY too: raw registers with
`ay(reg, v)`, and `tone(voice, hz, vol)` and `quiet()` for everyone
else.

**The answer and the display.** A program's output, what `./bly` shows
and what the backends are held to, is what its ordinary `print`s print,
and those land on the screen too. **Text printed at a place is the
screen's alone:** in a `print` with an `at`, everything from the `at` on
(its newline included) is drawn and not output. So a counter shown live
with `print at 5, 3; "count "; n` never floods the output, and the
answer is an ordinary `print`. To put the answer somewhere in
particular, place it first: `if ZX then print at 20, 4; end` and then
`print "Part 1: "; n`. On the Spectrum it lands at row 20, elsewhere on
the next line, and the output is the same everywhere. (The 48K's runtime
marks each piece of placed text with two control codes that change
nothing on the screen, so the transcript the tests read can leave it
out; HACKING.md says how.)

**Off the Spectrum, they still run.** The interpreter and the C backend
give `peek` and `poke` a 64K memory, and the screen library's twins draw
into it **at 4000h, laid out exactly as the Spectrum's screen is**.
`inp` and `outp` get the 48K's ports as omse-ai's 48K answers them with
no key held: the border, and the EAR bit, which echoes what was last
sent to the speaker (`z80/zxgfx.py` has the rule). The twin of `plot` is
just the real algorithm: work out the screen address, set the bit. At
exit the screen is saved as a `.scr` and a PNG. Sound becomes a log of
(duration, pitch) events, which can be rendered or compared. So a
program that sings can be tested anywhere, and the picture it ends with
is the one the Spectrum will show.

### The machine, and adding what isn't there

`peek` and `poke` are there because it's a Spectrum and you will want
them, and `inp` and `outp` for the same reason: the keyboard's
half-rows, the border, the speaker, a Kempston joystick (`call` later).
An address or a port is any whole number, checked as an index is. Only
the ROM, the screen and the UDGs are the same everywhere: the rest of
the 64K is the interpreter's own, so a `peek` at the system variables or
the program reads 0 off the Spectrum and the machine's bytes on it, and
a `poke` there can break a Spectrum program, as it can in BASIC. **`ZX`,
`CPM` and `C` are compile-time constants**, so
`if ZX then beep(50, 12) end` costs nothing elsewhere.

**Anything missing can be added**, by anyone, the same way the library
itself is written: a function whose body is plain Barley, with a
hand-written Z80 fragment beside it.

```
func isqrt(n: long): word
  var x: long = 0           -- the reference twin: the interpreter and C run it
  while (x + 1) * (x + 1) <= n do x += 1 end
  return word(x)
asm "isqrt.asm"               -- on the Z80, this runs instead
end
```

The fragment starts with a header the compiler reads: what it provides,
which other fragments it needs, which targets it's for, where its
arguments and result live, and what it clobbers (which the save rule
needs):

```
;; provides: isqrt   needs: (none)   targets: zx48 zx128 cpm
;; in: DEHL = n (long)   out: HL   clobbers: AF BC DE HL
```

**On the target, the build checks the fragment against its twin**, over
the program's own inputs and a fuzzer's (as the first Barley's fuzzer
found the `x + (-7)` bug). "Only testable on the target" becomes
"testable everywhere, verified on the target". A fragment could also
bring a `c "isqrt.c"` for the C backend, when there's a faster native
way. (The library's own fragments work this way already, with Python
models as their twins; `asm` clauses in programs are parsed, and their
bodies run, but the Z80 doesn't yet run the fragment in their place.)

## 6. Memory: what fits where

**48K Spectrum** (a TAP: a BASIC loader, the program, and the input as a
second CODE block). **Code lives high**, and data and the stack go down
under it, so that everything that runs, and as much as possible of what
it reads, is in the top 32K. On a 48K, 4000h–7FFFh is shared with the
ULA. Code there is slowed while the screen is drawn, which would make
timed sound wobble and the cost card's T-states read low. So code lives
high.

```
0000-3FFF  ROM
4000-5AFF  screen and attributes           <- contended RAM: 4000-7FFF
5B00-5Dxx  system variables, the calculator's stack, the BASIC loader
           the input, *only* if it doesn't fit above 8000h: it's read in
           order, a byte at a time, so it minds contention least
                                           (CLEAR goes below the lowest data)
8000-      globals                         <- the top 32K: full speed
           the input, when it fits up here (AoC inputs run 10-30K)
           the arena, growing up: containers, interned names
           ...
           the stack, growing down beneath the code
    -FF57  the program and the library: code lives high (an AoC
           solution 3-6K, plus only the library it uses)
FF58-FFFF  the UDGs, kept, so udg() works
```

That's about 40K for program, input and data together, the top 32K of it
at full speed. Most AoC days fit. Some don't, and the language should
say so early and plainly (`free()`, and a checked build's "arena full"
with the line that asked). Where a day doesn't fit, the Spectrum-shaped
move is usually a smaller representation (`bit`, packed keys, `intern`)
rather than a bigger machine. When that runs out, there's the 128K mode,
CP/M, and C.

The runtime keeps interrupts on (IM 1), so FRAMES counts (except during
a `beep`: the ROM's BEEPER turns them off, so the clock stands still
while it plays) and `ticks()` works. Compiled code never touches IY or
the alternate registers on the Spectrum: the ROM's interrupt routine and
calculator need IY = 5C3Ah, and the return to BASIC needs HL'. (That's
stricter than the machine needs, and section 13 has it as an open
question.)

**128K Spectrum** (the "big day" mode, later): the input in the banks at
C000h, so 30K inputs and a full arena both fit. One rule changes: a line
from a banked input is copied into a buffer, and is valid until the next
line is read. Programs that keep lines around call `keep(line)`.

**CP/M** (a `.COM`, run as `day12 input.txt`): the program at 0100h, the
input read whole from the file named on the command line, the arena
above it, the stack at the top of the TPA. That's 50-odd K.

## 7. Backends, and how a program is built

```
            source (.bly)
              |  parse and check (interp/barley.py: one front end for all)
              +--------------------> the interpreter: the spec; runs anywhere
              |
       +------+-------------------------+
       |                                |
   Z80 assembly (z80/z80gen.py,      plain C + rt/barley.h (c/cgen.py)
   then z80/peephole.py)             -> clang (or any C11 compiler):
                                        native and fast
   + library fragments (z80/lib),
     gathered by their headers
   -> sjasmplus, once
   -> TAP (a BASIC loader, the input, the program) or .COM
```

**The Z80 backend** works from the checked syntax tree. It began
deliberately simple (every value in a fixed slot, every subexpression
copied into its own) and has been taking back, one measured step at a
time, what the first Barley's compiler learnt about where values should
live and what a call should cost (HISTORY.md). **The C backend**
(`c/README.md`) is deliberately plain:
- one C function per Barleycorn function, with exact-width variables
  (`u8` up to `i64`);
- every subexpression in its own temporary, in the interpreter's
  left-to-right order, so C's unspecified argument order can't make two
  backends disagree;
- structured control flow, so `break` and `continue` mean the same;
- every operation a call into `rt/barley.h`, which checks it the way the
  interpreter does, in the same words, and has no undefined behaviour
  from our side;
- the preprocessor's generics: one small template per container kind,
  included once per element type.

The C runtime's data structures are the ones the Z80 library uses (an
arena, an insertion-ordered map, a ring queue, version counters), so the
C runtime is that library's design, written first where it could be
tested. The tests run it under UBSan and ASan, matching the interpreter
byte for byte. It's for speed (clang makes even plain C fast), and as a
second witness. **No LLVM IR**: it goes stale in a month, and C doesn't.

**Linking comes before assembly** (Melissa O'Neill's suggestion, and it
fits exactly). The library is a directory of fragments, each with the
header in section 5. The compiler starts from what the program
references, follows `needs:` to the closure, picks each fragment's
version for the target, pastes them after the program, and runs
sjasmplus once. There's no object format and no relocation: one
assembly, with every symbol known.

**What CP/M changes** is all in a small platform layer, about ten
routines with the same names on each machine:

- **Output** goes through BDOS, not the ROM's RST 10. `print`'s `,` pads
  with spaces, as everywhere. The screen and sound don't exist, and
  `if ZX` folds away.
- **Input** comes from the file named on the command line: open with
  BDOS 15, read 128-byte records with BDOS 20 into the arena.
- **Memory**: the TPA runs from 0100h to the BDOS address at 0006h.
  **Registers**: IY and the alternate set would be free there, which is
  worth measuring one day.
- **Exit** is `JP 0`. There's no `ticks()`, no BREAK, no screen, and no
  floats until there's a library.
- **Testing gets easy**: tnylpo captures stdout, so every program can be
  diffed against the interpreter in milliseconds. It runs Z80 code about
  430 times faster than a real Spectrum.

**How the input gets in:** `./bly tap prog.bly input.txt` puts it on the
same TAP as its own CODE block, which the loader puts in place, so you
load your puzzle input from tape like a real one. On CP/M it's the file
named on the command line. The interpreter and the C take a file name.

## 8. What writing in it looks like

*Each of these programs (and the taste in section 2) is in the test
suite, `interp/tests/`, and runs on every backend on inputs made for
this repository, with the answers worked out separately by
`make_inputs.py`.*

**AoC 2022 day 1**: numbers in groups separated by blank lines; the
biggest group, and the top three together.

```
-- AoC 2022 day 1: the elf carrying the most calories, and the top three
-- together.

func keep(top: long[], sum: long)          -- top is kept sorted, smallest first
  if sum > top[0] then
    top[0] = sum
    top.sort()
  end
end

func main()
  var top: long[3]
  var sum: long = 0
  for line in lines() do
    if line == "" then
      keep(top, sum)
      sum = 0
    else
      sum += line.int()
    end
  end
  keep(top, sum)                 -- the last elf has no blank line after it
  print "Part 1: "; top[2]
  print "Part 2: "; top[0] + top[1] + top[2]
end
```

**AoC 2023 day 8**: a first line of turns, then a network
(`AAA = (BBB, CCC)`). Part 2 starts at every node ending in `A` at once;
each walk is a cycle, so the answer is the LCM of their lengths, and it
needs a `quad`.

```
-- AoC 2023 day 8: follow the turns through the network.

var turns: str
var left = map[word, word](1024)
var right = map[word, word](1024)

func arrived(node: word, ghost: bool): bool
  if ghost then return name(node)[2] == 'Z' end
  return name(node) == "ZZZ"
end

func walk(node: word, ghost: bool): long
  var n: long = 0
  while not arrived(node, ghost) do
    if turns[n % turns.len] == 'L' then
      node = left[node]
    else
      node = right[node]
    end
    n += 1
  end
  return n
end

func main()
  var input = lines()
  turns = input.next()
  input.next()                             -- the blank line
  for line in input do                     -- AAA = (BBB, CCC)
    var node = intern(line[0..3])
    left[node] = intern(line[7..10])
    right[node] = intern(line[12..15])
  end
  print "Part 1: "; walk(intern("AAA"), false)
  var all: quad = 1
  for node in left do
    if name(node)[2] == 'A' then all = lcm(all, walk(node, true)) end
  end
  print "Part 2: "; all
end
```

**AoC 2023 day 6, part 2**: how many ways to beat a record. The winning
holds are an interval round the middle, and its edges are a quadratic's
roots: aim with floats, land with integers.

```
-- AoC 2023 day 6, part 2: aim with floats, land with quads.

func digits(s: str): quad    -- part 2: a line is one number, spaces and all
  var n: quad = 0
  for ch in s do
    if ch >= '0' and ch <= '9' then n = n * 10 + (ch - '0') end
  end
  return n
end

func ways(t: quad, d: quad): quad           -- holds h with h * (t - h) > d
  var root = (float(t) - sqrt(float(t) * float(t) - 4.0 * float(d))) / 2.0
  var lo = quad(floor(root))      -- the ROM's floats hold 9 digits: a guess,
  while lo * (t - lo) <= d do lo += 1 end        -- then up to the first win
  while lo > 0 and (lo - 1) * (t - lo + 1) > d do lo -= 1 end   -- or down
  return t - 2 * lo + 1           -- the winners are symmetric about t / 2
end

func main()
  var input = lines()
  var t = digits(input.next())
  var d = digits(input.next())
  print "Part 2: "; ways(t, d)
end
```

**AoC 2021 day 15, part 1**: the lowest-risk path across a 100 x 100
grid of digits, by Dijkstra.

```
-- AoC 2021 day 15, part 1: the safest path through the cave.

record Step
  risk: word                               -- first, so the heap orders by it
  at: pos
end

func main()
  var g = grid()
  var done = grid[bit](g.rows, g.cols)     -- 1.25K for 100 x 100
  var h = heap[Step](2048)
  var goal = pos(g.rows - 1, g.cols - 1)
  h.push(Step(0, pos(0, 0)))
  while true do
    var s = h.pop()
    if s.at == goal then
      print "Part 1: "; s.risk
      return
    end
    if done[s.at] then continue end
    done[s.at] = true
    for d in dirs4 do
      var n = s.at + d
      if g.has(n) and not done[n] then
        h.push(Step(s.risk + (g[n] - '0'), n))
      end
    end
  end
end
```

On a 48K: the input 10K in place, `done` 1.25K, the heap 12K. Part 2
tiles the cave 5 x 5 into 250,000 cells, and even as bits that's 31K.
It's a 128K or CP/M day, or a cleverer one: risks are 1-9, so a ring of
ten buckets can replace the heap. Saying so is part of what the language
is for. A checked build that runs out of heap says so:

```
heap full (2048) at line 25
0 OK, 0:1
```

**Making it sing**: 2022 day 12 again, with a handful of lines added
(the whole program is `examples/sing_d12.bly`). The search spreads
across the screen as it runs, and the speaker climbs a semitone every
dozen steps it gets from the summit. In the interpreter or in C, the
same program ends by saving the picture and the log of the notes.

```
  ...
  cls()
  var layer: word = 0
  while q.len > 0 do
    var p = q.get()
    plot(p.c, 175 - p.r)        -- one pixel a square: 161 x 41 fits the screen
    if dist[p] > layer then
      layer = dist[p]
      if layer % 12 == 0 then beep(20, int(layer / 12)) end
    end
    ...
  end
  print at 21, 0;                    -- the place: the answers below are an
  print "Part 1: "; dist[start]; "  Part 2: "; part2   -- ordinary print
```

## 9. Deliberately out

- **A garbage collector.** On 40K you want to know where the bytes went.
  Fixed capacities, an arena, and `mark` / `release` are enough for a
  program that runs once and prints two numbers.
- **Pointers and address-of.** They'd break the save rule, which is the
  thing Barley is best at. Containers and indices cover what AoC uses
  pointers for (a tree is a list of records with child indices).
- **Function values and closures.** Records-compare-field-by-field
  covers sorting and heaps. Function values are the first thing I'd add
  back, because Barley's design already has their perfect home: the
  operand of `call nn`, which makes an indirect call cost the same as a
  direct one. Closures no: they need captured variables to live
  somewhere other than a slot.
- **User generics, methods on records, operator overloading, exceptions,
  modules.** Each is a page of its own. One file per program, with
  `include "aoc.bly"` for shared helpers, is enough.
- **String building.** Covered by `print` and `intern` (section 5).
- **Unbounded integers.** `quad` covers every AoC answer I know of.
- **A second loop syntax.** Swift has both; we pick one (section 5).

## 10. Where it came from

HISTORY.md: the first Barley and what its compiler measured, how
Barleycorn was designed and built, and how the Z80 backend got fast.

**Advent of Code inputs stay out of this repository.** The puzzle text
and inputs are Eric Wastl's, and he asks that they not be redistributed.
The AoC programs here are solutions, which can be shared, and the tests
run them on inputs made for this repository
(`interp/tests/make_inputs.py`).

## 11. How we'll know it's right

- **The one-page test** (section 4), kept honest on every change.
- **Three implementations agree**, byte for byte, on every program, on
  every change.
- **Every feature has a puzzle that used it.** A feature no puzzle has
  used after a season of them gets cut.
- **The cost card is measured, not guessed** (section 12's column is
  still estimates; `z80/zxbench.py` and `z80/zxprof.py` are how they'll
  be replaced).
- **Someone writes a program in it** without reading anything but the
  card. Wherever they have to ask, the card is wrong.

## 12. The cost card (estimates, to be replaced by measurements)

| operation | about, in T-states | notes |
|---|---|---|
| read a `word` variable | 10-16 | 10 from an operand home, 16 from a fixed slot; 0 in a register |
| `word` add | 11-30 | `ADD HL,DE` plus whatever loads it needs |
| `word` multiply / divide | ~700 / ~1,200 | library routines (Barley's) |
| `long` add | ~100 | two 16-bit adds with the carry between |
| `long` multiply | ~3,000 | library |
| `quad` add / multiply | ~300 / ~12,000 | library, in memory |
| `float` anything | thousands | the ROM's calculator; you get what you get |
| `xs[i]` on a `list[word]` | ~50 | a shift, an add, two loads (plus ~30 checked) |
| `xs.push(v)` | ~70 | plus the capacity check |
| `m[k]`, a `word` key that hits | ~300-500 | hash, probe, compare |
| `h.push` / `h.pop`, 1,000 six-byte records | ~2,000 | ten levels of compare and move |
| `s.int()` | ~150 a digit | |
| `plot` | the ROM's: slow; a fast fragment later | |
| one statement, on average (Barley's Sieve) | ~75 | so about 50,000 a second at 3.5 MHz |

## 13. Decided, not yet built, and still open

**Decided:** floats in, the ROM's; screen and sound on the card, with
twins; Z80 assembly and plain C as the backends; linking before
assembly; extension through fragments with twins; three implementations
agree; truncating division and wrapping overflow, with `mod`; one `for`,
half-open; the charset; start tiny; checked by default. The aesthetic
choices are mine: `end` blocks, BASIC's `print`, `long` and `quad`,
records that compare field by field, fixed capacities. The name is
Barleycorn (HISTORY.md says why).

**Not built yet:**
- `mark`, `release` and `free`, and `--fast` (every build is checked)
- `call`, anywhere
- on the Z80, `grid[bit]` and containers of bits are a byte a bit (bit
  arrays pack), and a bit array can't be sorted
- floats on CP/M
- the 128K mode (input in the banks; the AY sound chip)
- the Z80 running an `asm` clause's fragment in place of its body
- `include`

**Still open:**
1. **Floats on CP/M**: our own routines, or none until a program asks?
2. **The alternate registers.** The rule that compiled code never
   touches them is stricter than the machine needs: the return to BASIC
   needs HL' restored, and nothing may be kept there across a ROM
   routine that uses them. Leaf routines could use EXX freely.
3. **How fast can the Z80 backend get?** HISTORY.md has the measured
   steps so far, and the next ones.
4. *Answered (10 October):* constant tables, `const SCALE = int[...]`,
   of any element type (section 5, "Arrays"). An array literal anywhere
   else (a `var`'s first value, an argument) is a later question.
5. *Answered (10 October):* text printed at a place is the screen's
   alone, and the answer is an ordinary `print` (section 5, "Screen and
   sound").
6. *Answered (10 October):* BASIC's INK and PAPER 8 and 9, BRIGHT and
   FLASH 8, and `attr(r, c)` reading a square back, all as the ROM does
   them (section 5, "Screen and sound").
7. *Answered (10 October):* `dword`, unsigned 32 bits (section 5,
   "Numbers").

And the one that matters most, every time: **what would you reach for,
and not find?**
