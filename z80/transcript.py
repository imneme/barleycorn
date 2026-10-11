"""What a Barleycorn program printed, read from omse-ai's transcript of the 48K's stream 2 (its printed()), which
shows control codes as {AT r,c}, {INVERSE n}, {OVER n} and so on."""
import re

LOADED = 'Bytes: program   \n'                  # the last of LOAD's own lines
BLOCKS = "\u2800\u259d\u2598\u2580\u2597\u2590\u259a\u259c\u2596\u259e\u258c\u259b\u2584\u259f\u2599\u2588"
BYTES = {**{ch: chr(0x80 + i) for i, ch in enumerate(BLOCKS)},              # omse-ai's Unicode for 80h-8Fh,
         **{chr(0x24B6 + i): chr(0x90 + i) for i in range(21)},              # the UDGs' (A..U, circled),
         '\u00a3': '\x60', '\u00a9': '\x7f'}                               # and the Spectrum's own 60h and 7Fh


def answer(printed):
    """the program's output: the transcript after LOAD's lines, without the text it printed at a place. The runtime
    brackets each piece of that text with INVERSE and OVER at their own values (invisible on the screen), and AT is
    the place; user code never sends either (print turns control bytes into ?). The characters omse-ai writes for
    the bytes that aren't ASCII (the block graphics, the UDGs, the pound and the copyright sign) are those bytes
    again, as latin-1 characters, so a caller writing latin-1 gets the bytes the program printed"""
    out = printed[printed.index(LOADED) + len(LOADED):] if LOADED in printed else 'LOADER: ' + printed
    out = re.sub(r'\{INVERSE \d\}.*?\{OVER \d\}', '', out, flags=re.S)
    out = re.sub(r'\{AT \d+,\d+\}', '', out)
    return ''.join(BYTES.get(ch, ch) for ch in out)        # each byte as itself, as the interpreter and C print it
