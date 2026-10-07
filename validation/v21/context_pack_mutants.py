"""D4: the hand mutations of aisef2/app/feedback.py context_pack, and of its one call in aisef2/app/adapters.py
Developer.implement, and whether tests.v2.test_v21_context_pack kills each —
run on a copy of HEAD (git archive; closure-evidence linked read only), a green baseline first, one mutant at a time.
Not the kernel's mutation campaign (validation/v2/mutation.py): the D4 lines still need that, outside the current snapshot.
    python3 -P validation/v21/context_pack_mutants.py       (from the repository root, on a clean tree)
"""

from __future__ import annotations

import io
import os
import pathlib
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLASSES = [f"tests.v2.test_v21_context_pack.{c}" for c in ("Pack", "Expectation", "Prompt", "RecordedSmoke2")]
HELD = 'c in expect and d.get("verdict") == expect[c]'
MUTANTS = {
    "held ignores the expectation (verdict == SATISFIED)": (HELD, 'd.get("verdict") == "SATISFIED"'),
    "an unknown criterion defaults to SATISFIED": (HELD, 'd.get("verdict") == expect.get(c, "SATISFIED")'),
    "expectations of this story's obligations only": ("              for o in project.plan.obligations}\n",
                                                       "              for o in project.plan.obligations if o.story_id == story_id}\n"),
    "agreement not required": ('d.get("agreement") is True and c in expect', "c in expect"),
    "developer result cut at 299": ("[:300]", "[:299]"),
    "developer result cut at 301": ("[:300]", "[:301]"),
    "developer result cut at 1000": ("[:300]", "[:1000]"),
    "redacted after the cut": ('redact(str(d.get("detail", "")))[:300]', 'redact(str(d.get("detail", ""))[:300])'),
    "attempts oldest first": ("reversed(list(enumerate(ended, 1))[-PACK_ATTEMPTS:])", "list(enumerate(ended, 1))[-PACK_ATTEMPTS:]"),
    "attempt cap 5": ("PACK_ATTEMPTS = 4000, 12, 4", "PACK_ATTEMPTS = 4000, 12, 5"),
    "no-proof list is every admitted criterion": ('sorted(set(a["criteria"]) - set(a["proofs"]))', 'sorted(set(a["criteria"]))'),
    "a later proof of a criterion replaces the first": ('and c not in cur["proofs"]', ""),
    "no room left for the stop mark (PACK_MAX - 120 -> PACK_MAX)": ("> PACK_MAX - 120:", "> PACK_MAX:"),
    "room for the stop mark one character short (PACK_MAX - 120 -> PACK_MAX - 56)": ("> PACK_MAX - 120:", "> PACK_MAX - 56:"),
    "the cut skips a line that does not fit and keeps later ones (break -> continue)": (
        "                break\n            kept.append(ln)", "                continue\n            kept.append(ln)"),
    "the header says an earlier candidate is a commit, whatever is named": (
        "(journal seq {cur['seq']})\")", "(journal seq {cur['seq']}); an earlier candidate named below is a commit of this repository\")"),
    "a named candidate is not said to be a commit of this repository": (', a commit of this repository"', '"'),
    "Developer.implement gives the pack none of the run's secrets": (
        'self.project, self.kw.get("secrets", ()))', "self.project, ())", "aisef2/app/adapters.py"),
}


def main() -> None:
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout
    print(f"commit: {head} dirty: {len(dirty.splitlines())}; tests: {' '.join(CLASSES)}")
    with tempfile.TemporaryDirectory(prefix="aisef-d4-mut-") as tmp:
        arch = subprocess.run(["git", "-C", str(ROOT), "archive", "HEAD", "--", ".", ":!closure-evidence"],
                              capture_output=True, check=True)
        tarfile.open(fileobj=io.BytesIO(arch.stdout)).extractall(tmp, filter="data")
        os.symlink(ROOT / "closure-evidence", pathlib.Path(tmp) / "closure-evidence")

        def run() -> tuple[int, str]:
            r = subprocess.run([sys.executable, "-P", "-W", "ignore::ResourceWarning", "-m", "unittest", *CLASSES],
                               cwd=tmp, env={**os.environ, "PYTHONPATH": tmp}, capture_output=True, text=True)
            return r.returncode, r.stderr.strip().splitlines()[-1]
        rc, last = run()
        print(f"baseline: {last}")
        if rc:
            raise SystemExit("the baseline is not green: no mutant result means anything")
        killed = 0
        for name, (a, b, *where) in MUTANTS.items():
            f = pathlib.Path(tmp) / (where[0] if where else "aisef2/app/feedback.py")
            orig = f.read_text(encoding="utf-8")
            if orig.count(a) != 1:
                raise SystemExit(f"mutant {name!r}: its target occurs {orig.count(a)} times in {f.name}")
            f.write_text(orig.replace(a, b), encoding="utf-8")
            rc, last = run()
            f.write_text(orig, encoding="utf-8")
            killed += bool(rc)
            print(f"{'KILLED  ' if rc else 'SURVIVED'} {name}: {last}")
        print(f"killed {killed} of {len(MUTANTS)}; restored copy: {run()[1]}")


if __name__ == "__main__":
    main()
