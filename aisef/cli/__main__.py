"""Giữ nguyên `python -m aisef.cli` — trước khi tách, `cli.py` có khối
``if __name__ == "__main__"`` làm đúng việc này."""

import sys

from . import main

if __name__ == "__main__":
    sys.exit(main())
