"""B1 risk-gate bindings check (fail-closed; owner 2026-11-12 section B): every named target's source sha256 equals
the FROZEN manifest's binding, the aisef2 kernel tree is the frozen one, and the registry is unchanged — or exit 1
and nothing runs. Arguments: target names (default: every manifest target)."""
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST_REL = "closure-evidence/v2/v2.2/B1-RISK-MANIFEST.json"


def _v23_accepts(t: str, e: dict) -> bool:
    """Round v2.3 only (Q0-1 option Q-a; owner ruling 2026-11-22 §D: a live, version-aware, fail-closed B1 check):
    a target whose source moved since the manifest froze is accepted ONLY while its newest COMMITTED round-v2.3
    mutation entry measured exactly the live source (the entry's LF digest equals the live file's) and the entry is
    clean under the mutation rules (killed or audited, nothing open). No entry, an uncommitted newest entry, a digest
    mismatch or any open problem keeps the target red. The manifest itself is never re-pinned here (OD-B1B stays the
    owner's)."""
    from validation.v2 import mutation as mu
    newest, pre = mu.v23_newest(ROOT)
    entry = newest.get(t)
    if pre or entry is None or entry.get("error"):
        return False
    live = mu.source_digest((ROOT / e["source"]).read_text(encoding="utf-8"))
    return entry.get("source_sha256") == live and not mu.target_problems(entry, ROOT)


def problems(man: dict, targets: list[str] | None = None, *, kernel: str | None = None) -> list[str]:
    """Every binding problem of `man` against this tree (the decision main() prints). `kernel` compares the given
    aisef2 tree instead of HEAD's (a calibration fixture binds its round's own tree, not the moving head)."""
    bad = []
    if kernel is None:
        kernel = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD:aisef2"],
                                capture_output=True, text=True, encoding="utf-8").stdout.strip()
    if kernel != man["frozen_bindings"]["aisef2_kernel_tree"]:
        bad.append(f"kernel {kernel[:12]} is not the frozen {man['frozen_bindings']['aisef2_kernel_tree'][:12]}")
    reg = hashlib.sha256((ROOT / man["frozen_bindings"]["registry_file"]).read_bytes()).hexdigest()
    if reg != man["frozen_bindings"]["registry_sha256"]:
        bad.append("the registry moved since the manifest froze")
    from validation.v2 import version_forward as vf
    in_round_v23 = vf.ROUND.get() == vf.BRANCH_ROUND
    for t in (targets or list(man["targets"])):
        e = man["targets"].get(t)
        if not e:
            bad.append(f"{t}: not in the frozen manifest")
            continue
        if hashlib.sha256((ROOT / e["source"]).read_bytes()).hexdigest() != e["source_sha256"] \
                and not (in_round_v23 and _v23_accepts(t, e)):
            bad.append(f"{t}: {e['source']} moved since the manifest froze")
    return bad


def main(argv: list[str] | None = None) -> int:
    targets = (sys.argv[1:] if argv is None else argv)
    man = json.loads((ROOT / MANIFEST_REL).read_text(encoding="utf-8"))
    bad = problems(man, targets)
    kernel = man["frozen_bindings"]["aisef2_kernel_tree"]
    print("\n".join(f"FAIL  {x}" for x in bad) if bad else
          f"BINDINGS OK: {len(targets or man['targets'])} targets, kernel {kernel[:12]}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
