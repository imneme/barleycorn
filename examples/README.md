# Examples

- `sing_d12.bly`: a hill climb (Advent of Code 2022, day 12) that draws the search across the screen as it runs and
  climbs a semitone every dozen steps from the summit, then prints both answers. The hill, `hill.txt`, is made by
  `make_hill.py`: a landscape of ridges with gates in them, so the search has somewhere to go.

      ./bly zx examples/sing_d12.bly examples/hill.txt
      ./bly run --screen hill.png examples/sing_d12.bly examples/hill.txt

The benchmark programs in `../z80/bench/` (fib, tak, Ackermann, queens, a sieve, two sorts, a tree, an expression
evaluator, Life, a CRC, Hanoi and some argument shuffles) are small and readable too, and the Advent of Code programs
the tests run are in `../interp/tests/`.
