# treesum — content snapshots of a directory tree

`treesum` is a small command-line tool and Python package that records the SHA-256 digest of every file under a
directory and later reports what changed. Python 3.11 or newer, **standard library only**: no third-party dependency
exists and none may be added. Tests use `unittest` and run with `python -m unittest discover -s tests -t .` from the
repository root.

The package is `treesum/` (already present, empty). `python -m treesum` is the command-line entry point
(`treesum/__main__.py`).

## 1. File digests (`treesum/digest.py`)

1.1 `treesum.digest.file_sha256(path)` returns the SHA-256 of the file's bytes as 64 lowercase hexadecimal characters
(a `str`). Example: a file holding the six bytes `hello\n` gives
`5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03`.

1.2 `path` may be a `str` or a `pathlib.Path`. A path that does not exist raises `FileNotFoundError`.

## 2. Snapshots (`treesum/snapshot.py`)

2.1 `treesum.snapshot.build(root)` returns a `dict` mapping every file under the directory `root` — recursively, at any
depth — to its `file_sha256`. A key is the file's path relative to `root`, with `/` as the separator on every platform
(for example `sub/dir/file.txt`). Directories themselves are not entries.

2.2 An empty directory gives `{}`.

2.3 A `root` that does not exist, or that exists and is not a directory, raises `NotADirectoryError`.

## 3. The snapshot text format

3.1 `treesum.snapshot.dumps(snapshot)` returns the snapshot as text: one line per entry, `<sha256>  <path>` (the
digest, two spaces, the path), every line ended by `\n`, entries in ascending order of path (plain string order,
whatever order the `dict` holds them in). The empty snapshot is the empty string. Example, for a snapshot of `b.txt`
(digest `f2c8…`) and `a.txt` (digest `b6a9…`):

```
b6a98d9ce9a2d9149288fa3df42d377c3e42737afdcdaf714e33c0a100b51060  a.txt
f2c82decdd7181cf98945929a62598db7e6b477e11f6e0eb0ae97020eff151ad  b.txt
```

3.2 `treesum.snapshot.loads(text)` parses that format back into a `dict`. Empty lines and lines holding only
whitespace are ignored; a final line without `\n` is read like any other. A line that is not `<64 lowercase hex
characters>`, two spaces, `<a non-empty path>` raises `ValueError`.

3.3 `loads(dumps(s)) == s` for every snapshot `s`.

## 4. Comparing snapshots

4.1 `treesum.snapshot.compare(old, new)` returns a `dict` with exactly the keys `added`, `removed` and `changed`,
each a `list` of paths in ascending order: `added` holds the paths in `new` and not in `old`, `removed` those in `old`
and not in `new`, `changed` those in both whose digests differ. A key whose list is empty is still present.

## 5. Command line (`treesum/__main__.py`)

5.1 `treesum.__main__.main(argv)` takes the argument list (without the program name) and returns the process exit
status as an `int`; `python -m treesum ...` exits with that status.

5.2 `python -m treesum build DIR` writes `dumps(build(DIR))` to standard output and exits 0.

5.3 `python -m treesum build DIR -o FILE` writes the same text to FILE instead — creating it, or replacing its
previous content — with nothing on standard output, and exits 0. When FILE lies inside DIR, FILE is not an entry of
the snapshot.

5.4 `python -m treesum verify DIR FILE` reads the snapshot in FILE (the old one), builds the current snapshot of DIR
and prints one line per difference, in ascending order of path: `added <path>`, `removed <path>` or
`changed <path>` (the word, one space, the path). It exits 0 when there is no difference (printing nothing) and 1
when there is at least one. When FILE lies inside DIR it is ignored, as in 5.3.

5.5 Any other use exits 2 with a message on standard error and nothing on standard output: an unknown or missing
subcommand, missing or extra arguments, a DIR that is not a directory, a FILE that cannot be read or that does not
parse (3.2).

## 6. Tests

6.1 `tests/test_smoke.py` is given and must keep passing. Add `unittest` tests of each part: `tests/test_digest.py`
(§1), `tests/test_build.py` (§2), `tests/test_format.py` (§3 and §4) and `tests/test_cli.py` (§5). Tests import
nothing outside the standard library and `treesum`.
