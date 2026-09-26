"""Build W1-LEDGERLOCK-PLAN-V2 from the frozen V1 epics.md (owner decision 2026-09-20, section 3).

Deterministic and auditable: every edit is declared here with the requirement it traces to, and the script rewrites
`epics.md` only through those declarations. The LedgerLock requirements are NOT touched (section 2).

    python3 build_plan_v2.py <reference project>/_bmad-output/epics.md --out <new epics.md>
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

#: story -> criterion index -> (proof mode, requirement). Index is the criterion's position in the V2 story.
OBLIGATIONS: dict[str, dict[int, tuple[str, str]]] = {
    "1.1": {1: ("CHANGE_REQUIRED", "FR-1"), 2: ("CHANGE_REQUIRED", "FR-1"), 3: ("CHANGE_REQUIRED", "FR-14"),
            4: ("NEGATIVE_INVARIANT", "FR-14"), 5: ("NEGATIVE_INVARIANT", "FR-14"), 6: ("CHANGE_REQUIRED", "FR-14")},
    "1.2": {i: ("CHANGE_REQUIRED", "FR-2") for i in range(1, 7)},
    "1.3": {i: ("CHANGE_REQUIRED", "FR-2") for i in range(1, 6)},
    "1.4": {i: ("CHANGE_REQUIRED", "FR-13") for i in range(1, 7)},
    "1.5": {1: ("CHANGE_REQUIRED", "FR-2"), 2: ("CHANGE_REQUIRED", "FR-2"), 3: ("CHANGE_REQUIRED", "FR-1"),
            4: ("CHANGE_REQUIRED", "FR-2"), 5: ("CHANGE_REQUIRED", "FR-13")},
    "1.6": {1: ("CHANGE_REQUIRED", "FR-3"), 2: ("CHANGE_REQUIRED", "FR-4"), 3: ("CHANGE_REQUIRED", "FR-5"),
            4: ("CHANGE_REQUIRED", "FR-5"), 5: ("CHANGE_REQUIRED", "FR-3")},
    "2.1": {1: ("CHANGE_REQUIRED", "FR-6"), 2: ("CHANGE_REQUIRED", "FR-6"), 3: ("CHANGE_REQUIRED", "FR-6"),
            4: ("CHANGE_REQUIRED", "FR-7"), 5: ("CHANGE_REQUIRED", "FR-7")},
    "2.2": {i: ("CHANGE_REQUIRED", "FR-9") for i in range(1, 6)},
    "3.1": {1: ("CHANGE_REQUIRED", "FR-8"), 2: ("CHANGE_REQUIRED", "FR-8"), 3: ("CHANGE_REQUIRED", "FR-8"),
            4: ("CHANGE_REQUIRED", "FR-8"), 5: ("CHANGE_REQUIRED", "FR-13")},
    "3.2": {i: ("CHANGE_REQUIRED", "FR-10") for i in range(1, 5)},
    "4.1": {**{i: ("CHANGE_REQUIRED", "FR-11") for i in range(1, 6)},
            6: ("CHANGE_REQUIRED", "FR-12"), 7: ("CHANGE_REQUIRED", "FR-12")},
    # argparse gives usage errors exit 2 as soon as STORY-04-01 builds the parser: this story must keep that true,
    # and contributes the I/O, conflict and corruption codes.
    "4.2": {i: ("CHANGE_REQUIRED", "FR-12") for i in range(1, 5)},
    "4.3": {1: ("PRESERVE_REQUIRED", "FR-12"), 2: ("CHANGE_REQUIRED", "FR-12"), 3: ("CHANGE_REQUIRED", "FR-12"),
            4: ("CHANGE_REQUIRED", "FR-12"), 5: ("PRESERVE_REQUIRED", "FR-12")},
    "5.1": {1: ("PRESERVE_REQUIRED", "FR-2"), 2: ("PRESERVE_REQUIRED", "FR-8"), 3: ("PRESERVE_REQUIRED", "FR-14")},
    "5.2": {1: ("CHANGE_REQUIRED", "FR-14"), 2: ("PRESERVE_REQUIRED", "FR-14"), 3: ("CHANGE_REQUIRED", "FR-14")},
    "5.3": {1: ("NEGATIVE_INVARIANT", "FR-14"), 2: ("NEGATIVE_INVARIANT", "FR-14")},
}

#: A story whose whole contract is verification of behaviour other stories deliver (owner section 8).
STORY_TYPE = {"5.1": "VERIFICATION_ONLY", "5.3": "VERIFICATION_ONLY"}

USAGE_AC = ("Given any subcommand invoked with the wrong number of positional arguments, the CLI exits with code `2` "
            "and writes nothing to stdout.")
NO_OUT_AC = "Given `snapshot` invoked without `--out`, the CLI exits `2`."
CLI_HELP_AC = ("Given the same checkout, `python -m ledgerlock --help` in a subprocess exits `0` and the stdout "
               "argparse usage line contains each of the literal strings `verify`, `snapshot`, `apply`, and "
               "`repair-tail`.")
OLD_DELETE_AC = ("Given `put(\"k\", \"v\", r1, t1)` followed by `delete(\"k\", r2, t2)`, `snapshot()` returns a dict "
                 "with no key `\"k\"`.")
NEW_CONFLICT_AC = ("Given a committed `put(\"k\", \"v\", \"r1\", t1)`, `delete(\"k\", \"r2\", t2)` raises "
                   "`ConflictError` (requirements §4.5: a different `rid` mutating the same key MUST conflict) and a "
                   "following `snapshot()` still returns `{\"k\": \"v\"}` — the refused delete changed nothing.")
NEW_TOMBSTONE_AC = ("Given `delete(\"k2\", \"r3\", t3)` on a key with no committed mutation (a tombstone, "
                    "requirements §4.4), `snapshot()` returns a dict with no key `\"k2\"`.")
DROPPED_PARITY_AC = ("Given the same test module, when it is executed under `python -m unittest discover` and again "
                     "under `pytest`, both runners discover and execute the test.")

#: Edits, each traced to the audit finding that requires it.
EDITS = [
    {"id": "PLAN-V2-01", "story": "2.2", "kind": "criterion_replaced",
     "finding": "AC-STORY-02-02-2 contradicts requirements §4.5 (a delete with a different rid MUST conflict), so no "
                "implementation can satisfy both; measured on run minimax-ro-2, where the reviewer verified the "
                "contradiction and the kernel ended the story as a plan deadlock",
     "traces_to": "requirements §4.5 and §6", "old": OLD_DELETE_AC, "new": NEW_CONFLICT_AC},
    {"id": "PLAN-V2-02", "story": "2.2", "kind": "criterion_added",
     "finding": "with the contradiction removed the story no longer covered the tombstone path of §6 at all",
     "traces_to": "requirements §4.4 and §6", "after": NEW_CONFLICT_AC, "new": NEW_TOMBSTONE_AC},
    {"id": "PLAN-V2-03", "story": "1.1", "kind": "criterion_moved", "to": "4.1",
     "finding": "the CLI surface criterion in the skeleton story invited it to build the whole CLI: measured on "
                "minimax-ro-1, STORY-01-01 wrote all of ledgerlock/cli.py (commit cfc462c), which left every "
                "STORY-04-01 criterion already satisfied at that story's entry",
     "traces_to": "FR-11 (CLI subcommands) owns the command surface", "old": CLI_HELP_AC, "new": CLI_HELP_AC},
    {"id": "PLAN-V2-07", "story": "4.2", "kind": "criterion_moved", "to": "4.1",
     "finding": "the usage-error exit code is delivered by the argparse parser itself, so the story that builds the "
                "parser is where the criterion can be red first; declaring it in a later story made it a criterion "
                "no implementation of that story could turn red (measured: deepseek-ro-1/2 and minimax-ro-1 all "
                "refused STORY-04-02 attempt 1 on exactly this criterion)",
     "traces_to": "FR-12 realized by the parser FR-11 creates", "old": USAGE_AC, "new": USAGE_AC},
    {"id": "PLAN-V2-08", "story": "4.2", "kind": "criterion_moved", "to": "4.1",
     "finding": "same as PLAN-V2-07 for the missing required option", "traces_to": "FR-12",
     "old": NO_OUT_AC, "new": NO_OUT_AC},
    {"id": "PLAN-V2-09", "story": "4.1", "kind": "covers_extended",
     "finding": "STORY-04-01 now delivers the two usage-error exit codes as well as the command surface",
     "traces_to": "PLAN-V2-07, PLAN-V2-08", "old": "- covers: FR-11", "new": "- covers: FR-11, FR-12"},
    {"id": "PLAN-V2-10", "story": "5.1", "kind": "covers_extended",
     "finding": "the property test asserts the atomic-batch guarantee and runs under both runners, which its "
                "criteria name — the story must declare those requirements to be traceable",
     "traces_to": "FR-8, FR-14", "old": "- covers: FR-2, FR-3, FR-4, FR-9", "new": "- covers: FR-2, FR-3, FR-4, FR-8, FR-9, FR-14"},
    {"id": "PLAN-V2-04", "story": "5.3", "kind": "criterion_dropped",
     "finding": "duplicate of AC-STORY-05-02-2 (runner parity), which STORY-05-02 owns",
     "traces_to": "FR-14", "old": DROPPED_PARITY_AC},
    {"id": "PLAN-V2-05", "story": "1.1", "kind": "write_scope_narrowed",
     "finding": "the skeleton no longer declares the CLI surface, so it no longer needs to write the CLI module",
     "traces_to": "PLAN-V2-03",
     "old": "ledgerlock/cli.py, ", "new": ""},
    {"id": "PLAN-V2-06", "story": "4.1", "kind": "story_note",
     "finding": "STORY-04-02 owns the error exit codes; a CLI story that maps them early makes that story's "
                "CHANGE_REQUIRED criteria already satisfied at entry (PLAN_OVERLAP)",
     "traces_to": "FR-11 vs FR-12 ownership",
     "new": "Scope note: the **error** exit codes (`3` I/O, `4` conflict, `5` corruption) are STORY-04-02's "
            "contract, and the stderr status shapes beyond `verify` are STORY-04-03's. Implement the success paths "
            "here; do not pre-empt them."},
]


def story_blocks(text: str) -> dict[str, tuple[int, int]]:
    marks = [(m.group(1), m.start()) for m in re.finditer(r"^### Story (\d+\.\d+):", text, re.M)]
    out = {}
    for i, (sid, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        out[sid] = (start, end)
    return out


def apply_edits(text: str) -> tuple[str, list[dict]]:
    log = []
    for e in EDITS:
        blocks = story_blocks(text)
        s, end = blocks[e["story"]]
        block = text[s:end]
        if e["kind"] == "criterion_replaced":
            assert e["old"] in block, e["id"]
            block = block.replace(e["old"], e["new"])
        elif e["kind"] == "criterion_added":
            assert e["after"] in block, e["id"]
            block = block.replace(e["after"], e["after"] + "\n- " + e["new"])
        elif e["kind"] == "criterion_dropped":
            assert e["old"] in block, e["id"]
            block = block.replace("- " + e["old"] + "\n", "")
        elif e["kind"] in ("write_scope_narrowed", "covers_extended"):
            assert e["old"] in block, e["id"]
            block = block.replace(e["old"], e["new"])
        elif e["kind"] == "story_note":
            # before the criteria block: anything between the criteria and the metadata is parsed as a criterion
            block = re.sub(r"(\n\*\*Acceptance criteria:\*\*)", "\n" + e["new"] + "\n\\1", block, count=1)
        elif e["kind"] == "criterion_moved":
            assert e["old"] in block, e["id"]
            block = block.replace("- " + e["old"] + "\n", "")
            text = text[:s] + block + text[end:]
            blocks = story_blocks(text)
            ds, de = blocks[e["to"]]
            target = text[ds:de]
            first = re.search(r"\*\*Acceptance criteria:\*\*\n\n", target)
            target = target[:first.end()] + "- " + e["new"] + "\n" + target[first.end():]
            text = text[:ds] + target + text[de:]
            log.append(e)
            continue
        text = text[:s] + block + text[end:]
        log.append(e)
    return text, log


def declare(text: str) -> str:
    """Add `- ac_proof:` and, where declared, `- story_type:` under each story's metadata."""
    for sid, decl in OBLIGATIONS.items():
        s, end = story_blocks(text)[sid]
        block = text[s:end]
        n = len(re.findall(r"^- Given ", block, re.M))
        assert n == len(decl), f"story {sid}: {n} criteria, {len(decl)} obligations declared"
        line = "- ac_proof: " + ", ".join(f"{i}={m}/{r}" for i, (m, r) in sorted(decl.items()))
        if sid in STORY_TYPE:
            line += f"\n- story_type: {STORY_TYPE[sid]}"
        block = re.sub(r"(\n- covers: [^\n]*\n)", r"\1" + line + "\n", block, count=1)
        text = text[:s] + block + text[end:]
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("epics")
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", default="")
    a = ap.parse_args()
    text = Path(a.epics).read_text(encoding="utf-8")
    text, log = apply_edits(text)
    text = declare(text)
    Path(a.out).write_text(text, encoding="utf-8")
    # the product's own parser is the judge of what a criterion is: every criterion must carry an obligation
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
    from aisef.control.normalize import parse_epics_file

    for st in parse_epics_file(a.out).stories():
        got = [(st.ac_proof.get(f"AC-{st.id}-{i}") or {}).get("proof_mode")
               for i in range(1, len(st.acceptance_criteria) + 1)]
        if None in got or len(got) != len(st.ac_proof):
            raise SystemExit(f"{st.id}: {len(st.acceptance_criteria)} criteria, obligations {got} — plan is invalid")
    if a.log:
        Path(a.log).write_text(json.dumps({"plan": "W1-LEDGERLOCK-PLAN-V2", "source": str(a.epics),
                                           "edits": log, "obligations": {k: {str(i): v for i, v in d.items()}
                                                                         for k, d in OBLIGATIONS.items()},
                                           "story_type": STORY_TYPE}, ensure_ascii=False, indent=1) + "\n",
                              encoding="utf-8")
    print(f"W1-LEDGERLOCK-PLAN-V2 written to {a.out}: {len(log)} edits, "
          f"{sum(len(d) for d in OBLIGATIONS.values())} criteria declared")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
