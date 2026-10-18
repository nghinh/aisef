# Evidence-discipline linter — requirements delta

This repository holds one tool, `infrastructure/ci/evidence_discipline.py`: a linter that
scans Markdown and TypeScript files for "figure-shaped" text (a number with a unit such as
`250 ms`, `12 GB`, `128 streams`) and requires each figure to be cited to a run id listed in
the run registry `infrastructure/ci/run_registry.json` (`run_id: <id>` or `(run_id <id>)` on
the same line), or marked as a target with the prefix `target:`, or keyed to the placeholder
`benchmark.pending`. Lines inside fenced code blocks, indented code, comments and blank lines
are not scanned. A line that opens with `observed:`, `measured:`, `recorded:` or `achieved:`
is an observation and never a target. Its existing tests are
`infrastructure/ci/test_evidence_discipline.py` (pytest).

Run it: `python3 infrastructure/ci/evidence_discipline.py --root <file> [--root <file> ...]
[--report <json file>]`. Exit code 1 when there are uncited figures, else 0.

The maintainers ask for the four changes below. Section numbers and clause numbers are the
reference used everywhere else (tests, reviews, acceptance).

## 1. Directory roots

1.1 A `--root` that names a directory is walked recursively, and every file under it whose
name ends in `.md`, `.ts` or `.tsx` is scanned, in sorted order of its path. (Today a
directory root is silently skipped: nothing is scanned and the exit code is 0.)

1.2 While walking, a directory whose name starts with `.` (for example `.git`, `.venv`) or
whose name is `node_modules`, `build` or `dist` is not entered, and files in it are not
scanned.

1.3 A `--root` that names a file is scanned whatever its suffix (unchanged).

1.4 A `--root` that names a path that does not exist is an error: the linter prints one
message to stderr that contains that path as given, scans nothing, and returns exit code 2.
(Today such a path is silently skipped and the exit code is 0.)

## 2. The run registry

2.1 `--registry PATH` names the run registry file to read. Without it the default
`infrastructure/ci/run_registry.json` next to the linter is read, as today.

2.2 A registry that does not exist, cannot be read, is not JSON, or is not a JSON object
whose `valid_runs` is a list of strings, is an error: `load_run_registry(path)` (`path` given
as a `str` or a `pathlib.Path`) raises `RegistryError` (a subclass of `ValueError`, defined in
the module) whose message names the path, and
`cli_main` prints one line to stderr that starts with `run registry:` and contains that
message, scans nothing, and returns exit code 2. (Today such a registry is silently treated
as empty, so every figure is reported as uncited.)

2.3 `cli_main(argv)` returns its exit code (0, 1 or 2) and never calls `sys.exit` itself;
only the `if __name__ == "__main__":` block exits the process. (Argument-parsing errors keep
argparse's own behaviour.)

## 3. JSON output

3.1 `--format json` prints to stdout exactly one JSON document and nothing else: the same
document `--report` writes (keys `findings`, `accepted_targets`, `accepted_placeholders`;
each finding has `file`, `line`, `figure`, `reason`, `text`). `--format text` is the default
and prints what the linter prints today.

3.2 `--report` keeps writing its document to the named file in both formats, byte-identical
to what it writes today for the same scan (`json.dumps(..., indent=2)` of the object above,
in that key order, no trailing newline). The exit code does not depend on `--format`: 1 when
there are findings, else 0.

## 4. What must not change

4.1 Every existing test in `infrastructure/ci/test_evidence_discipline.py` keeps passing
(`python3 -m pytest infrastructure/ci -q`).

4.2 The linter stays standard-library only: `infrastructure/ci/evidence_discipline.py`
imports nothing outside the Python standard library.

4.3 The citation, `target:`, observation-prefix, placeholder and fenced-code rules are
unchanged: a figure cited to a run id present in the registry is accepted, a `target:` line
is accepted, an uncited figure on an `observed:` line is reported, and a figure inside a
fenced code block is not scanned.

## 5. Tests for the new behaviour

Write unit tests for the new behaviour with the standard library's `unittest` (no pytest
fixtures; `python3 -m unittest <file>` must pass from the repository root), one file per
section: `infrastructure/ci/test_delta_roots.py` for section 1,
`infrastructure/ci/test_delta_registry.py` for section 2 and
`infrastructure/ci/test_delta_json.py` for section 3. Use temporary directories for the
files a test scans. Do not edit this document.
