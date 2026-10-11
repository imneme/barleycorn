# Examples

Programs that work something out and make it sing. Each prints the same
text in the interpreter, as C, under CP/M and on a 48K Spectrum, and its
last picture is the same in the interpreter and on the Spectrum:
`./bly all` checks both. On CP/M they print their answers without the
picture or the sound.

The ones in the first three sections were written by three other
instances of me, working at the same time from a short brief, as
Barleycorn's first users. Their lists of what they reached for and
didn't find made the language better (HISTORY.md).

For one construct at a time, in programs of 10 to 25 lines, see
[small/](small/README.md).

## Grids that come alive

- `life.bly`: Conway's Game of Life on the Spectrum's colour squares,
  one cell to a square. A random soup in the middle of the screen boils,
  spreads and dies back until it settles into a cycle. Newborn cells are
  bright yellow and settle to green, and everywhere life has ever been
  stays blue, so the picture keeps a map of where it went. The bottom
  row is a bar as long as the population, and the beeper plays the
  population too, a note a generation on a pentatonic scale: low as it
  dies down, higher as it spreads. Every generation's fingerprint goes
  into a map, so the first one seen twice gives the cycle: it plays the
  cycle twice, slowly, and prints the generation it began at, its period
  and the population. This soup ends with two blocks, a blinker and a
  period-3 oscillator, which makes period 6. Change `SEED` for another.
  About two minutes on a 48K.

      ./bly zx examples/life.bly
      ./bly run --screen life.png examples/life.bly

  ![Life settled after 300 generations: green survivors on the blue map
  of everywhere life has been](../docs/life.png)

- `maze.bly`: a maze with a room in every square of the screen, carved
  by a randomised depth-first search on a `list` used as a stack. Watch
  the yellow snake: it pushes on into the dark, draws back when it's
  boxed in, and leaves finished rooms white behind it, and its note
  rises as it grows. Then a breadth-first search floods out from the top
  left, changing colour every ten steps, round the colour wheel. Then
  the shortest way to the bottom right is traced back from the goal and
  painted in white from the start, a note a step, rising three octaves.
  It prints the length of the way through. About 25 seconds on a 48K.

      ./bly zx examples/maze.bly
      ./bly run --screen maze.png examples/maze.bly

  ![A 32 by 21 maze flooded in bands of colour, with the way through in
  white](../docs/maze.png)

- `ant.bly`: Langton's ant. On a white square it turns right, on a black
  one left, and either way it flips the square and steps on. From an
  empty screen it scribbles for about ten thousand steps with no order
  in it at all, then starts to build a highway, 104 steps that repeat
  forever, and walks off along it. The ink changes every thousand steps,
  with a note from the beeper, so the colours show when the ant was last
  in each part of the picture. It keeps its last 104 turns in a ring of
  bits, and when two whole loops of them have repeated it plays a chord
  and prints the step the highway began at: 9,977, the famous number. A
  tick for every loop along the highway, and a low note as the ant walks
  off the edge. About 40 seconds on a 48K.

      ./bly zx examples/ant.bly
      ./bly run --screen ant.png examples/ant.bly

  ![Langton's ant's scribble in bands of colour, and the highway leading
  off it to the top left](../docs/ant.png)

All three run on CP/M too (`./bly cpm examples/life.bly`), and print the
same answers there, without the picture or the sound. The maze and the
ant keep their boards in `grid`s indexed by `pos`, as the language
invites. Life touches every cell every generation, so it keeps its board
in plain arrays instead, with a dead border round it so that no cell is
a special case, and walks along them with a running index: fixed arrays
are as fast as memory gets.

## Numbers made visible

- `fern.bly`: a Barnsley fern, from 8,000 points, carried in whole
  hundredths so there's no float anywhere: the arithmetic is the same on
  every machine, and on CP/M, with no screen, it still counts the 151
  character cells the fern reaches. Written by Fern, an instance reading
  Barleycorn's source from outside (on DeepSeek's weights), who could
  not run it; first run by the Fern who built the language, on all four
  backends, the same everywhere. About 52 seconds on a 48K.

      ./bly zx examples/fern.bly

  ![A green Barnsley fern on black, drawn point by
  point](../docs/fern.png)

- `ulam.bly`: the Ulam spiral. It sieves the numbers up to 25,600 (a
  `bit` for each), then counts up from 1 in a square spiral out from the
  middle of the screen, putting a dot on every prime, and the diagonals
  Ulam noticed in 1963 appear as it grows. The beeper clicks for each
  pair of twin primes, a little higher with each turn of the spiral. It
  prints how many primes there are and how many twin pairs. About 22
  seconds on a 48K.

      ./bly zx examples/ulam.bly
      ./bly run --screen ulam.png examples/ulam.bly

  ![The Ulam spiral of the primes up to 25,600, in cyan, with the counts
  beneath](../docs/ulam.png)

- `collatz.bly`: the Collatz problem (halve an even number, triple an
  odd one and add 1, until you reach 1). It works out how many steps
  every number below 10,240 takes, remembering each one so the next can
  stop as soon as it drops below where it started, and plots them as it
  goes, n across and steps up, coloured in bands. A click marks each new
  record. Then it plays the winner's whole journey, a note a step on a
  pentatonic scale, pitched by how big the number is, while a ring hops
  around the picture to wherever that number sits; the cells it visits
  stay white, so the journey leaves footprints. It prints the winner,
  its steps, and the highest it climbs. About a minute on a 48K, the
  tune included.

      ./bly zx examples/collatz.bly
      ./bly run --screen collatz.png examples/collatz.bly

  ![The steps each number below 10,240 takes to reach 1, in bands of
  colour, with the record holder circled](../docs/collatz.png)

- `mandel.bly`: the Mandelbrot set in fixed-point integers, with no
  multiplying in the loop: a table of squares does the work, since 2xy
  is (x + y)² - x² - y². It draws the set in white with three contour
  lines round it, a row and its mirror at once, so the picture closes in
  from the top and the bottom together, and each row sings a note as
  high as the set is wide there. Then it prints the set's area, by
  counting pixels. On CP/M, with no screen, it draws the set in letters
  instead. About two minutes on a 48K, which is quick for a Mandelbrot
  on a Spectrum.

      ./bly zx examples/mandel.bly
      ./bly run --screen mandel.png examples/mandel.bly
      ./bly cpm examples/mandel.bly

  ![The Mandelbrot set in white with cyan, green and yellow contours,
  and its area](../docs/mandel.png)

- `ford.bly`: Ford circles. Every fraction p/q between 0 and 1 gets a
  circle 1/q² across, standing on a line at p/q, and no two of them ever
  overlap: neighbours in the Farey sequence just touch. It walks the
  Farey sequence of denominators up to 40 with its integer recurrence,
  drawing each circle as it comes and giving it a note, so the tiny
  circles twitter high and quick and the big ones sound low and long;
  the tune is a palindrome, because the sequence is. It checks that
  every pair of neighbours touches (bc - ad = 1), counts the fractions a
  second way with `gcd`, and prints the count. About ten seconds on a
  48K.

      ./bly zx examples/ford.bly
      ./bly run --screen ford.png examples/ford.bly

  ![Ford circles for the fractions up to 40ths: two great arcs, and
  circles nested between them down to dust](../docs/ford.png)

All four run on CP/M too, and print the same answers there, without the
picture or the sound; the Mandelbrot draws its picture in letters
instead.

## Puzzles that solve themselves

- `towers.bly`: the Towers of Hanoi, seven discs, one for each colour
  the Spectrum has besides black, moved by the recursion everyone
  learns. Each move plays a note: the small discs high, the big ones
  low, on a pentatonic scale. The row of lights above the pegs counts
  the moves in binary, and it shows a fact worth watching for: the disc
  that moves on move m is always the one whose light is m's lowest 1. So
  the smallest disc moves every other time, the next every fourth time,
  and so on. The program checks that on every move, and also that no
  disc ever lands on a smaller one. At the end every light is on (127 is
  1111111), and the scale runs back up. About 12 seconds on a 48K. On
  CP/M it just counts the moves.

      ./bly zx examples/towers.bly
      ./bly run --screen towers.png examples/towers.bly

  ![Seven discs stacked on the right-hand peg, all seven lights on, and
  "7 discs in 127 moves"](../docs/towers.png)

- `sudoku.bly`: a sudoku solved by plain backtracking. It fills the
  empty squares in reading order, tries 1 to 9 in each, and backs up
  when a square has nothing left that fits. Each digit is drawn as it
  goes down, with a click, and rubbed out when it's taken back, so you
  can watch the search surge forward and fall back. It gets most of the
  way down the board more than once, then falls back to the third row
  when a guess up there turns out wrong. The digits are drawn
  seven-segment style, with `line`, because printing them would send all
  2,302 attempts to the output. When the board is full, the answer turns
  green a row at a time while a major scale climbs. Then it prints the
  answer, and how many digits it put down and took back. The puzzle,
  `sudoku.txt`, comes from `make_sudoku.py`, which also works out the
  answer in Python, for checking. About a minute on a 48K.

      ./bly zx examples/sudoku.bly examples/sudoku.txt
      ./bly run --screen sudoku.png examples/sudoku.bly examples/sudoku.txt

  ![The solved sudoku in seven-segment digits, clues in white and the
  answer in green, with the answer as text beside
  it](../docs/sudoku.png)

- `queens92.bly`: all 92 ways to place eight queens on a chessboard so
  that none attacks another, found by backtracking a row at a time.
  Crowns go down and come off the board as the search runs, with a click
  for each queen that's higher the deeper the search is, and a chord for
  each answer. Turn an answer round or reflect it and you get another
  answer, so the answers come in families. A `map` from each family's
  smallest member (eight columns read as an octal number) to its line on
  the screen sorts them. Each family gets a line when its first member
  turns up, and a yellow stripe for every member. Eleven families have
  eight members. Watch for the one that stops at four: it looks the same
  turned halfway round. It prints the twelve families and "92 solutions,
  12 up to symmetry". About 40 seconds on a 48K.

      ./bly zx examples/queens92.bly
      ./bly run --screen queens92.png examples/queens92.bly

  ![A chessboard with the first answer's eight crowns, and the twelve
  families listed with a stripe per member](../docs/queens92.png)

All three run on CP/M too, and print the same answers there, without the
picture or the sound.

## The hill

- `sing_d12.bly`: a hill climb (Advent of Code 2022, day 12) that draws
  the search across the screen as it runs and climbs a semitone every
  dozen steps from the summit, then prints both answers. The hill,
  `hill.txt`, is made by `make_hill.py`: a landscape of ridges with
  gates in them, so the search has somewhere to go. It uses the screen
  outside `if ZX`, so it's for the Spectrum (and the interpreter and C)
  only.

      ./bly zx examples/sing_d12.bly examples/hill.txt
      ./bly run --screen hill.png examples/sing_d12.bly examples/hill.txt

  ![The hill climb on a 48K, with both
  answers](../docs/hill-on-a-48k.png)

## Melissa's Advent of Code

Four programs Melissa wrote in ZX Spectrum BASIC for Advent of Code,
ported to Barley as literally as Barley allows: the CRT and the sand by
a Fern working through Melissa's archive of them, the cube and the
towels by the Fern who wrote Barleycorn. A puzzle's own input isn't ours
to share, so each comes with one of our own, made by a small Python
script that also works out the answer, for checking. All but
`crt_d10.bly` use the screen outside `if ZX`, so like the hill they're
for the Spectrum (and the interpreter and C) only; `crt_d10.bly` prints
its answer on CP/M too.

- `crt_d10.bly`: Advent of Code 2022, day 10 (Cathode-Ray Tube). A
  little CPU runs `addx` and `noop` while a CRT draws one pixel a cycle,
  lit if the three-pixel sprite centred on the X register covers it. Her
  screen shows the instruction, the cycle and X, and the CRT as a black
  panel of dotted half-cells, with the sprite riding along each row as a
  dithered bar, so you watch the letters come up out of the dots. Part
  1's answer is the sum of the signal strengths at six cycles; part 2's
  is the word. The program, `crt_d10.txt`, comes from `make_crt.py`,
  which searches out instructions whose CRT spells SPECTRUM (or a word
  of your own, up to eight letters from its font) and works the sum out
  too: 13040. Her `PAUSE 5` a cycle is kept, so it takes 28 seconds on a
  48K, 24 of them pausing; on her own program, her interpreted BASIC
  took 86. On CP/M it prints the sum.

      ./bly zx examples/crt_d10.bly examples/crt_d10.txt
      ./bly run --screen crt.png examples/crt_d10.bly examples/crt_d10.txt

  ![SPECTRUM in cyan pixels on a black CRT of dotted half-cells, with
  the cycle, the X register and the signal strengths'
  sum](../docs/crt-d10.png)

- `sand_d14.bly`: Advent of Code 2022, day 14 (Regolith Reservoir), part 1.
  Sand pours in at 500,0 over paths of rock, and her program keeps no
  map in memory: the screen is the map. Rock is drawn two pixels wide, a
  recursive fill asks `point()` whether a square is taken (straight
  down, then down-left, then down-right), and a square whose three are
  all taken holds a grain, drawn as one pixel on alternate halves row by
  row, so the sand shows dithered against the solid rock; a grain that
  would fall past the lowest rock is rubbed out again. Her BASIC read
  DATA her Perl had made from the input; this reads the input as the
  puzzle gives it and works the bounds out itself. The rocks,
  `sand_d14.txt`, come from `make_sand.py`: a Christmas tree of widening
  cups, with presents round the trunk. A grain tries down-left first, so
  the snow heaps up on the left of each branch and spills down the
  tree's left side, and the last of it caps a present: 635 grains,
  counted in Python grain by grain and with her fill. 17 seconds on a
  48K, most of them her `PAUSE 1` a step, kept so you can watch; on her
  own rocks it took 31, where her HiSoft-compiled BASIC took 34 and her
  interpreted BASIC 326. The screen is its memory, so it doesn't run on
  CP/M.

      ./bly zx examples/sand_d14.bly examples/sand_d14.txt
      ./bly run --screen sand.png examples/sand_d14.bly examples/sand_d14.txt

  ![A Christmas tree of six widening branches in black line, snow heaped
  in dithered drifts on the left of each, a trunk and presents below,
  and "635 grains"](../docs/sand-d14.png)

- `monkey_d22.bly`: Advent of Code 2022, day 22 (Monkey Map), part 2. A
  board folded into a 50 x 50 x 50 cube, drawn twice in isometric with
  every wall a dot on its face, then walked: a 200-point worm follows
  the walker over the edges from face to face, and at the end it says
  where it stopped and which way it faced. The cube's geometry (which
  face lies beyond each edge, and how it's turned) is as her Perl,
  `cubeinfo.pl`, worked it out from the puzzle's net. The board,
  `monkey_d22.txt`, comes from `make_monkey.py`, with walls and 2,001
  moves of our own, and on top of the left-hand cube the walls draw a
  cat. About a minute on a 48K. On her own board it took 87 seconds,
  where her HiSoft-compiled BASIC took 210.

      ./bly zx examples/monkey_d22.bly examples/monkey_d22.txt
      ./bly run --screen monkey.png examples/monkey_d22.bly examples/monkey_d22.txt

  ![Two yellow isometric cubes on black, their faces dotted with walls,
  a cat's face drawn in walls on top of the left one, and the walker's
  trail on the right one](../docs/monkey-d22.png)

- `towels_d19.bly`: Advent of Code 2024, day 19 (Linen Layout), part 2.
  In how many ways can a heap of striped towels, laid end to end, make
  each design? It counts them as her Perl did, and her BASIC after it:
  working in from the design's end, the ways to make its last 1, 2, 3
  and more stripes, each from the counts before it. Each design shows as
  its stripes, two to a character cell (one in ink, one in paper), with
  a magenta rule above and below that thickens from the right as the
  count eats in. Her BASIC kept the big counts as two numbers in base
  10^8, because a Spectrum float is exact only up to 2^32; Barley has
  `quad`, so they're one number each. The heap, `towels_d19.txt`, comes
  from `make_towels.py`: 120 towels and 30 designs, the most ways for
  one design 31,099,988,700, and 46,145,737,803 in all. Under two
  minutes on a 48K. On her own heap it took 66 minutes, where her
  compiled BASIC took 147.

      ./bly zx examples/towels_d19.bly examples/towels_d19.txt
      ./bly run --screen towels.png examples/towels_d19.bly examples/towels_d19.txt

  ![A design's stripes in red, blue, black, white and green between
  magenta rules, with its ways and the total,
  46145737803](../docs/towels-d19.png)

The benchmark programs in `../z80/bench/` (fib, tak, Ackermann, queens,
a sieve, two sorts, a tree, an expression evaluator, Life, a CRC, Hanoi
and some argument shuffles) are small and readable too, and the Advent
of Code programs the tests run are in `../interp/tests/`.
