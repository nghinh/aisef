"""Preserve ``python -m aisef.cli`` — before the split, ``cli.py`` had an
``if __name__ == "__main__"`` block that did exactly this."""

import sys

from . import main

if __name__ == "__main__":
    sys.exit(main())
