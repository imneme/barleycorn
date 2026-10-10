"""The inputs for the suite's five Advent of Code programs: our own, in each puzzle's format, made from fixed seeds,
with the answers worked out here by plain Python from the puzzles' rules, not by Barley. (The puzzles' own examples
are part of their text, which Advent of Code asks people not to redistribute.)

usage: make_inputs.py            writes the .in files beside it and prints the answers run.py expects
"""
import heapq
import math
import os
import random
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))


def write(name, text):
    open(os.path.join(HERE, name), 'w').write(text)


# 2022 day 1: groups of numbers between blank lines; the biggest group's total, and the top three's
def day1(r):
    groups = [[r.randint(1000, 9999) for _ in range(r.randint(1, 5))] for _ in range(7)]
    write('aoc2022d01.in', '\n\n'.join('\n'.join(map(str, g)) for g in groups) + '\n')
    sums = sorted((sum(g) for g in groups), reverse=True)
    return f'Part 1: {sums[0]}\nPart 2: {sum(sums[:3])}\n'


# 2022 day 12: a height map; a step may climb at most one; fewest steps from S to E, and from any a to E
def day12(r, rows=8, cols=16):
    while True:
        order = [(row, c if row % 2 == 0 else cols - 1 - c) for row in range(rows) for c in range(cols)]
        h = {}
        for i, p in enumerate(order):                 # a snake that climbs, a step at a time, with cliffs beside it
            h[p] = i * 26 // (rows * cols)
        for p in order[1:-1]:
            if r.random() < 0.25:
                h[p] = max(0, h[p] - r.randint(1, 2))
        s, e = order[0], order[-1]
        h[s], h[e] = 0, 25

        def dist_from(starts):
            seen = {p: 0 for p in starts}
            q = deque(starts)
            while q:
                p = q.popleft()
                for d in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                    n = (p[0] + d[0], p[1] + d[1])
                    if n in h and n not in seen and h[n] <= h[p] + 1:
                        seen[n] = seen[p] + 1
                        q.append(n)
            return seen.get(e)
        part1 = dist_from([s])
        part2 = dist_from([p for p in h if h[p] == 0])
        if part1 is not None:
            break
    text = ''
    for row in range(rows):
        for c in range(cols):
            p = (row, c)
            text += 'S' if p == s else 'E' if p == e else chr(ord('a') + h[p])
        text += '\n'
    write('aoc2022d12.in', text)
    return f'Part 1: {part1}\nPart 2: {part2}\n'


# 2023 day 8: follow the turns; part 2 walks every ..A node at once until all stand on ..Z nodes
def network(r, turns, chains, extra_name):
    """chains: (start, end, steps), steps a multiple of len(turns). Each chain's untaken branches lead to a sink, and
    its end's branches are its start's, so after `steps` the walk begins again exactly"""
    nodes, names = {}, iter(f'{a}{b}{c}' for a in 'PQRST' for b in '0123456789' for c in '0123456789')
    for start, end, steps in chains:
        path = [start] + [next(names) for _ in range(steps - 1)] + [end]
        for t in range(steps):
            turn = turns[t % len(turns)]
            nodes[path[t]] = (path[t + 1], extra_name) if turn == 'L' else (extra_name, path[t + 1])
        nodes[end] = nodes[start]
    nodes[extra_name] = (extra_name, extra_name)
    lines = [f'{n} = ({lt}, {rt})' for n, (lt, rt) in nodes.items()]
    r.shuffle(lines)
    return turns + '\n\n' + '\n'.join(lines) + '\n', nodes


def walk(nodes, turns, starts, done, limit=10 ** 6):
    """the walk itself, every ghost at once, until all are done (no LCM assumed)"""
    cur, n = list(starts), 0
    while not all(done(c) for c in cur):
        cur = [nodes[c][0 if turns[n % len(turns)] == 'L' else 1] for c in cur]
        n += 1
        assert n < limit
    return n


def day8(r):
    turns = 'LRLL'
    text, nodes = network(r, turns, [('AAA', 'ZZZ', 8), ('BBA', 'BBZ', 12), ('CCA', 'CCZ', 20)], 'XXX')
    write('aoc2023d08a.in', text)
    part1 = walk(nodes, turns, ['AAA'], lambda c: c == 'ZZZ')
    part2 = walk(nodes, turns, [n for n in nodes if n[2] == 'A'], lambda c: c[2] == 'Z')
    a = f'Part 1: {part1}\nPart 2: {part2}\n'
    turns = 'LRR'
    text, nodes = network(r, turns, [('GHA', 'GHZ', 6), ('JKA', 'JKZ', 9), ('MNA', 'MNZ', 21)], 'YYY')
    write('aoc2023d08b.in', text)
    part2 = walk(nodes, turns, [n for n in nodes if n[2] == 'A'], lambda c: c[2] == 'Z')
    return a, f'Part 2: {part2}\n'


# 2021 day 15: digits as risks; the least total risk from the top left to the bottom right (the start not counted)
def day15(r, n=12):
    g = [[r.randint(1, 9) for _ in range(n)] for _ in range(n)]
    write('aoc2021d15.in', ''.join(''.join(map(str, row)) + '\n' for row in g))
    best = {(0, 0): 0}
    q = [(0, 0, 0)]
    while q:
        d, y, x = heapq.heappop(q)
        if d > best.get((y, x), 1 << 30):
            continue
        for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < n and 0 <= nx < n and d + g[ny][nx] < best.get((ny, nx), 1 << 30):
                best[(ny, nx)] = d + g[ny][nx]
                heapq.heappush(q, (best[(ny, nx)], ny, nx))
    return f'Part 1: {best[(n - 1, n - 1)]}\n'


# 2023 day 6, part 2: the lines read as one number each; the holds h with h * (t - h) > d
def day6(r):
    while True:
        times = [r.randint(5, 99) for _ in range(3)]
        dists = [r.randint(t * t // 8, t * t // 4 - 1) for t in times]
        t = int(''.join(map(str, times)))
        d = int(''.join(map(str, dists)))
        if d < t * t // 4:
            break
    write('aoc2023d06.in', 'Time:    ' + ''.join(f'{x:5}' for x in times) + '\n' +
          'Distance:' + ''.join(f'{x:5}' for x in dists) + '\n')
    lo = (t - math.isqrt(t * t - 4 * d)) // 2                 # near the smaller root; then exactly, in integers
    while lo * (t - lo) <= d:
        lo += 1
    while lo > 0 and (lo - 1) * (t - lo + 1) > d:
        lo -= 1
    ways = sum(1 for h in range(lo - 2, t - lo + 3) if 0 <= h <= t and h * (t - h) > d)   # and counted, to be sure
    assert ways == t - 2 * lo + 1
    return f'Part 2: {ways}\n'


if __name__ == '__main__':
    r = random.Random(2026_10_09)
    a8, b8 = day8(r)
    for name, ans in (('aoc2022d01', day1(r)), ('aoc2022d12', day12(r)), ('aoc2023d08 (a)', a8),
                      ('aoc2023d08p2 (b)', b8), ('aoc2021d15', day15(r)), ('aoc2023d06', day6(r))):
        print(f'{name}: {ans!r}')
