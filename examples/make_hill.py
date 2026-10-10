"""A 41 x 161 hill for the singing demo: rings of cliff around the summit, each with one gate placed on an arc that
lies inside the grid (the outer rings only cross it on the left), so a climber has to wind round to the top."""
import math
R, C = 41, 161
cx, cy = 120, 20
walls = [(14, 0.3), (28, 2.5), (44, 3.4), (62, 3.0)]     # (radius, the angle of its gate)
rows = []
for r in range(R):
    row = []
    for c in range(C):
        dx, dy = (c - cx) / 1.4, (r - cy) * 1.1
        d, a = math.hypot(dx, dy), math.atan2(dy, dx)
        h = 9.9 - d / 9
        for rw, gate in walls:
            off = abs((a - gate + math.pi) % (2 * math.pi) - math.pi)
            if off < 0.28:
                h += 4 * min(1, max(0, (rw - d + 4) / 8))        # a ramp, half a height a square: climbable
            elif d < rw:
                h += 4                                             # a cliff, four heights at once
        row.append(chr(ord('a') + max(0, min(25, int(h)))))
    rows.append(row)
rows[20][0] = 'S'
rows[cy][cx] = 'E'
open('hill.txt', 'w').write('\n'.join(''.join(r) for r in rows) + '\n')
