"""tkinterdnd2 import shim.

Centralises the optional dependency so other modules don't repeat the try/except.
"""

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False
    TkinterDnD = None
    DND_FILES = None
