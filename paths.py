"""Where Barley finds what it doesn't include. Each can be set in the environment, or in a file `paths.local` beside
this one (NAME=value lines, not tracked by git); otherwise it's looked for on PATH, or next to this checkout.

    SJASMPLUS       the Z80 assembler (https://github.com/z00m128/sjasmplus)
    TNYLPO          the CP/M emulator the Z80 tests run .COM files under (https://gitlab.com/gbrein/tnylpo)
    OMSE_AI         a checkout of omse-ai (https://github.com/imneme/omse-ai), for the 48K Spectrum; default ../omse-ai
    OMSE_AI_ROMS    the Spectrum ROMs (48.rom); default OMSE_AI/roms. Bring your own: see omse-ai's roms/README.md
    OMSE_AI_PYTHON  a Python that can import omse-ai (it needs Pillow); default OMSE_AI/.venv/bin/python3 if present
    CC              the C compiler for the C backend's tests; default clang
    MDWRAP          mdwrap, which keeps the Markdown wrapped at 72 columns (./check's wrap stage)
    BARLEY_BUILD    where builds go; default build/ in this checkout
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
_local = {}
if os.path.exists(os.path.join(ROOT, 'paths.local')):
    for line in open(os.path.join(ROOT, 'paths.local')):
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            _local[k.strip()] = os.path.expanduser(v.strip())


def setting(name, default=None):
    return os.environ.get(name) or _local.get(name) or default


SJASMPLUS = setting('SJASMPLUS', shutil.which('sjasmplus') or 'sjasmplus')
TNYLPO = setting('TNYLPO', shutil.which('tnylpo') or 'tnylpo')
OMSE_AI = setting('OMSE_AI', os.path.join(os.path.dirname(ROOT), 'omse-ai'))
OMSE_AI_ROMS = setting('OMSE_AI_ROMS', os.path.join(OMSE_AI, 'roms'))
_venv = os.path.join(OMSE_AI, '.venv', 'bin', 'python3')
OMSE_AI_PYTHON = setting('OMSE_AI_PYTHON', _venv if os.path.exists(_venv) else sys.executable)
CC = setting('CC', 'clang')
MDWRAP = setting('MDWRAP', shutil.which('mdwrap') or 'mdwrap')
BUILD = setting('BARLEY_BUILD', os.path.join(ROOT, 'build'))
os.environ.setdefault('OMSE_AI_ROMS', OMSE_AI_ROMS)     # omse-ai reads this too


def need(path, what, how):
    """a missing tool says so in one line, rather than as a traceback"""
    if not (os.path.exists(path) or shutil.which(path)):
        sys.exit(f'{what} not found ({path}): {how}')
    return path


def omse_ai():
    """make omse-ai importable (from speccy import Speccy)"""
    if not os.path.isdir(OMSE_AI):
        sys.exit(f'omse-ai not found at {OMSE_AI}: clone https://github.com/imneme/omse-ai there, or set OMSE_AI')
    if OMSE_AI not in sys.path:
        sys.path.insert(0, OMSE_AI)


def build_dir(*parts):
    d = os.path.join(BUILD, *parts)
    os.makedirs(d, exist_ok=True)
    return d
