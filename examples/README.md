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

The benchmark programs in `../z80/bench/` (fib, tak, Ackermann, queens,
a sieve, two sorts, a tree, an expression evaluator, Life, a CRC, Hanoi
and some argument shuffles) are small and readable too, and the Advent
of Code programs the tests run are in `../interp/tests/`.
