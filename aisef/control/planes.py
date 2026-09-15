"""Product plane and assurance plane — what a commit changes, and what that
changes the meaning of.

Written against D-022 (2026-09-15). `v1.7.1` was on PyPI and G1 read PASSED;
one commit later — a documentation sync touching nothing that ships — G1.0 was
FAILED because HEAD no longer equalled the release commit. Recording evidence
*about* a release invalidated the release, so the only cure was another release,
whose evidence would land in a later commit and invalidate it in turn. The
closure gate had confused two different questions:

* **Is the published artifact the product this source describes?** — a
  question about the *product plane*: runtime source, package data, build
  configuration; answered by content digests, not by which commit is HEAD.
* **Does this evidence describe the tree it claims to?** — a question about
  the *assurance plane*: tests, evidence, approvals, reports, closure records;
  answered by whether anything the evidence depends on changed since it was
  recorded.

The previous exception, `_only_bookkeeping_changed`, was a filename allowlist
of one directory and one file. It answered neither question; it named two
places the loop had bitten. This module states the model instead.

**Classification is data, not inference.** Every tracked path gets a class from
an ordered rule list in `docs/closure-gate.json#planes` — first match wins —
and a path no rule matches is `UNRESOLVED`. Unresolved is never harmless: a
probe that meets one blocks and names the path, so the rule list has to be made
complete on purpose rather than assumed complete by default. The rules live in
the criteria file rather than here so that extending them for a new directory
after a release is an assurance-plane edit, not a product change that would
force the very release it exists to avoid.

| class | meaning | changing it after release … |
|---|---|---|
| `PRODUCT_AFFECTING` | ships in the wheel/sdist, or decides how they are built | makes the release not describe HEAD — a new release is required |
| `ASSURANCE_AFFECTING` | tests, CI, validation tooling, anything a recorded run depends on | stales commit-bound evidence (suite, lint, selfcheck) — re-run and re-record |
| `EVIDENCE_ONLY` | records: closure evidence, approvals, reports, the criteria file | changes nothing about the product or about what was measured |
| `DOCUMENTATION` | prose and public pages | governed by the claim/onboarding rules (G5.6, G6.1), not by staleness |

**Identity is a digest over content, not a SHA of a commit.** The product
identity of a revision is the SHA-256 over `mode blob path` for every
PRODUCT_AFFECTING path in that revision's tree, taken from `git ls-tree` so
untracked and ignored files cannot enter it. Two revisions with the same
product digest carry the same product, whatever else differs between them —
that is the invariant that lets a closure record commit coexist with the release
it closes. Sub-digests per `part` (runtime source, package data, build config)
exist so a mismatch can say *which* part moved.

`README.md` is deliberately DOCUMENTATION although its text enters the wheel's
metadata as the long description: nothing executes it, the published artifact
does not change when it is edited, and treating it as product would reinstate
the loop for every typo. The release manifest records its blob at release time
so the metadata's provenance is still auditable.

Pure and read-only: the only subprocess is `git`, read-only, and nothing here
touches the working tree.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

from .worktree import GitError, _git

PRODUCT = "PRODUCT_AFFECTING"
ASSURANCE = "ASSURANCE_AFFECTING"
EVIDENCE = "EVIDENCE_ONLY"
DOCUMENTATION = "DOCUMENTATION"
UNRESOLVED = "UNRESOLVED"

#: Every class a rule may declare. `UNRESOLVED` is not among them on purpose —
#: it is what the absence of a rule means, never something a rule can grant.
CLASSES = (PRODUCT, ASSURANCE, EVIDENCE, DOCUMENTATION)

#: Classes whose change after a recording makes commit-bound evidence stale.
STALING = (PRODUCT, ASSURANCE)

#: Where the rules live in the criteria file.
SPEC_KEY = "planes"


@dataclass(frozen=True)
class Rule:
    cls: str
    match: str
    part: str = ""

    def hits(self, path: str) -> bool:
        """`fnmatch` over the POSIX path — `*` crosses `/`, so `docs/*` is the
        whole subtree and `aisef/kit/*` every file under it."""
        return fnmatchcase(path, self.match)


def rules_from(spec: dict) -> tuple[Rule, ...]:
    """The ordered rule list, or `()` when the criteria file declares none.

    Malformed entries raise: a rule with an unknown class would otherwise be
    skipped silently, and a skipped rule turns every path it covered into
    `UNRESOLVED` — visible, but wrongly attributed to the paths.
    """
    block = (spec or {}).get(SPEC_KEY) or {}
    out = []
    for i, raw in enumerate(block.get("rules") or []):
        cls, match = str(raw.get("class") or ""), str(raw.get("match") or "")
        if cls not in CLASSES or not match:
            raise ValueError(f"{SPEC_KEY}.rules[{i}] is not a rule: class={cls!r} match={match!r}")
        out.append(Rule(cls, match, str(raw.get("part") or "")))
    return tuple(out)


def classify(path: str, rules: tuple[Rule, ...]) -> Rule | None:
    """First rule that matches, or `None` — the caller decides what an
    unclassified path means, and it never means "fine"."""
    p = Path(path).as_posix()
    for r in rules:
        if r.hits(p):
            return r
    return None


def class_of(path: str, rules: tuple[Rule, ...]) -> str:
    r = classify(path, rules)
    return r.cls if r else UNRESOLVED


def _out(root: Path, *args: str) -> str:
    try:
        proc = _git(root, *args, check=False)
    except (OSError, GitError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def tree(root: Path, rev: str) -> list[tuple[str, str, str]]:
    """`(mode, blob, path)` for every file in `rev`'s tree, from git — the
    working tree is never consulted, so an uncommitted or ignored file cannot
    enter an identity."""
    raw = _out(root, "ls-tree", "-r", "-z", rev)
    rows = []
    for rec in raw.split("\0"):
        if not rec:
            continue
        meta, _, path = rec.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            rows.append((parts[0], parts[2], path))
    return rows


def _digest(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(lines)) + "\n").encode()).hexdigest()


@dataclass
class Identity:
    """The product identity of one revision.

    `digest` is empty when the revision cannot be read. `unresolved` lists every
    tracked path no rule classifies — non-empty means the identity is not
    trustworthy, because a product file could be hiding among them.
    """

    rev: str
    digest: str = ""
    files: int = 0
    parts: dict[str, str] = field(default_factory=dict)
    unresolved: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.digest) and not self.unresolved

    def as_dict(self) -> dict:
        return {"rev": self.rev, "digest": self.digest, "files": self.files,
                "parts": dict(self.parts), "unresolved": list(self.unresolved)}


def identity(root: Path | str, rev: str, rules: tuple[Rule, ...]) -> Identity:
    root = Path(root)
    full = _out(root, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()
    if not full:
        return Identity(rev=rev)
    lines: list[str] = []
    by_part: dict[str, list[str]] = {}
    unresolved: list[str] = []
    paths: list[str] = []
    for mode, blob, path in tree(root, full):
        rule = classify(path, rules)
        if rule is None:
            unresolved.append(path)
            continue
        if rule.cls != PRODUCT:
            continue
        line = f"{mode} {blob} {path}"
        lines.append(line)
        paths.append(path)
        by_part.setdefault(rule.part or "product", []).append(line)
    return Identity(rev=full, digest=_digest(lines), files=len(lines),
                    parts={k: _digest(v) for k, v in sorted(by_part.items())},
                    unresolved=sorted(unresolved), paths=sorted(paths))


@dataclass
class Changes:
    """What changed between two revisions, by class."""

    a: str
    b: str
    by_class: dict[str, list[str]] = field(default_factory=dict)
    readable: bool = True

    @property
    def staling(self) -> list[str]:
        return sorted(p for c in STALING for p in self.by_class.get(c, ()))

    @property
    def unresolved(self) -> list[str]:
        return sorted(self.by_class.get(UNRESOLVED, ()))

    @property
    def product(self) -> list[str]:
        return sorted(self.by_class.get(PRODUCT, ()))

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.by_class.values())


def changes(root: Path | str, a: str, b: str, rules: tuple[Rule, ...]) -> Changes:
    """Paths that differ between `a` and `b`, each under its class.

    An unreadable diff is reported as such (`readable=False`) rather than as
    "nothing changed": not knowing is not the same as knowing nothing moved.
    """
    root = Path(root)
    try:
        proc = _git(root, "diff", "--name-only", "-z", f"{a}..{b}", check=False)
    except (OSError, GitError, subprocess.TimeoutExpired):
        return Changes(a=a, b=b, readable=False)
    if proc.returncode != 0:
        return Changes(a=a, b=b, readable=False)
    out = Changes(a=a, b=b)
    for path in proc.stdout.split("\0"):
        if path:
            out.by_class.setdefault(class_of(path, rules), []).append(path)
    return out


def bundle_digest(directory: Path | str, *, exclude: tuple[str, ...] = ()) -> tuple[str, list[str]]:
    """Digest of an instructions bundle: SHA-256 over `name:sha256(bytes)` for
    every file under `directory`, sorted by POSIX path. Byte-exact on purpose —
    the value protected is that a participant and the gate read the same
    instructions, so a "harmless" edit after the run must be visible.

    Returns `(digest, names)`; `("", [])` when the directory has no files.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return "", []
    rows, names = [], []
    for p in sorted(directory.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(directory).as_posix()
        if rel in exclude:
            continue
        rows.append(f"{rel}:{hashlib.sha256(p.read_bytes()).hexdigest()}")
        names.append(rel)
    if not rows:
        return "", []
    return hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest(), names
