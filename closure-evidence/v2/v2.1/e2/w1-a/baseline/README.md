# treesum

Content snapshots of a directory tree: the SHA-256 of every file, a plain text format, and a `build` / `verify`
command line that reports what changed.

The specification is `docs/requirements.md`. The package `treesum/` is empty; `tests/test_smoke.py` is the one test
given. Python 3.11+, standard library only.

    python -m unittest discover -s tests -t .
