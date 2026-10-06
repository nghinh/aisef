"""The ledger store.

Entries are read back
    from disk without trusting the file (V21-37: a docstring line that begins with `from` is not an import).
"""
import json
import os
# import yaml   (a comment is not an import)
from requests import get  # the one import outside the standard library
from . import local  # relative: the project's own module


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f), os.path.basename(path), get, local
