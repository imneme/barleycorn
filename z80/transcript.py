"""What a Barleycorn program printed, read from omse-ai's transcript of the 48K's stream 2 (its printed()), which
shows control codes as {AT r,c}, {INVERSE n}, {OVER n} and so on."""
import re

LOADED = 'Bytes: program   \n'                  # the last of LOAD's own lines


def answer(printed):
    """the program's output: the transcript after LOAD's lines, without the text it printed at a place. The runtime
    brackets each piece of that text with INVERSE and OVER at their own values (invisible on the screen), and AT is
    the place; user code never sends either (print turns control bytes into ?)"""
    out = printed[printed.index(LOADED) + len(LOADED):] if LOADED in printed else 'LOADER: ' + printed
    out = re.sub(r'\{INVERSE \d\}.*?\{OVER \d\}', '', out, flags=re.S)
    return re.sub(r'\{AT \d+,\d+\}', '', out)
