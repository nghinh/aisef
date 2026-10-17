"""D4 evidence of need: on every recorded retry of a developer, what the journal knew at the retry's request that the
retry feedback did not say — and what the retrying session went looking for on its own. Read-only over committed
evidence; no provider, no kernel run.

Who built the retry text, and how it is known (each line of the table below carries the label):
  smoke-2 (2.0.0)   aisef2/app/feedback.py retry_feedback of v2.0.0; EXPERIMENT: part 1 recomputes every developer
                    prompt with that code and compares it with the prompt_sha256 the run recorded.
  cycle-2 P10       the qualification harness, validation/qualification/c2_p9.py at each attempt's
                    repository_execution_commit (its sha256 equals the one LEDGERLOCK-REGRESSION.json records); CODE, not
                    recomputed: attempt 2 (1f992ba, :230-247) and attempt 3 (06ceb23, :422-439) tell each failure's code
                    and clause only; attempt 4 (e49226b, :222-259, :480-490) the H-RETRY-001 retry_feedback — failures and
                    the proof records before them. None of the three reads a proof that held or an admitted criterion.

    python3 -P validation/v21/context_gap.py            (from the repository root; prints the report)

Three parts: (1) what the 2.0.0 smoke-2 developers were told, recomputed by the 2.0.0 code itself (`git archive v2.0.0`,
run in a subprocess) from the journal prefix before each request and compared with the prompt_sha256 the run recorded;
(2) the table below over every recorded V2 retry with a journal; (3) the context pack this tree builds at smoke-2's two
retries (aisef2/app/feedback.context_pack; the 2.0 bundle migrated in memory, V2-007).

Not told (journal facts before the retry's provider/request):
  changed_nothing   an earlier attempt's developer result "the developer changed nothing" (provider/result)
  parent_as_cand    an earlier attempt whose evaluated candidate IS its parent (story/begin.parent): the feedback calls it
                    "candidate <sha> ... REFUTED" without saying no change was made
  held              criteria proved at an earlier candidate with the verdict the plan expects for them (the 2.0.0
                    bundle, migrated: REFUTED for a MUST_NOT_HOLD contract) and the verifier agreeing — as
                    feedback.context_pack counts it (only failures are told)
  never_proved      criteria of the story (story/admitted) with no proof in the earlier attempt (proving stops at a failure)

Sought by the retrying session (tool calls whose input matches; a regex classifier, so counts are of matching calls):
  prior_work  git naming an earlier candidate's sha (never a parent: a candidate that is its parent changed nothing),
              reflog/fsck, or a read of the story's earlier developer stream
  journal     the run's journal (journals/ or JOURNAL)
  hidden      the kernel's probe scratch, the verifier's worktree, a probe request.json — proof material
  framework   AISEF's own sources or the bundle (site-packages/aisef, /aisef2/, inputs/project.json, the ai-sdlc checkout)
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
EV = ROOT / "closure-evidence/v2"
RUNS = (("2.0.0 release smoke-2", EV / "release/smoke-2/run-1/aisef-run.jsonl", EV / "release/smoke-2/run-1/sessions"),
        ("cycle-2 P10 attempt 2", EV / "cycle2/P10/attempt-2/JOURNAL.json", EV / "cycle2/P10/attempt-2/sessions"),
        ("cycle-2 P10 attempt 3", EV / "cycle2/P10/attempt-3/JOURNAL.json", EV / "cycle2/P10/attempt-3/sessions"),
        ("cycle-2 P10 attempt 4", EV / "cycle2/P10/attempt-4/JOURNAL.json", EV / "cycle2/P10/attempt-4/sessions"))
NOTHING = "the developer changed nothing"
SMOKE2 = EV / "release/smoke-2/run-1"
BUNDLE = EV / "release/LEDGERLOCK-PROJECT.json"
#: run by the 2.0.0 kernel (PYTHONPATH = its archive): each developer prompt as 2.0.0's Developer.implement built it
TOLD_200 = r"""
import hashlib, json, sys
from aisef2.app import bundle as B, feedback
project = B.load(json.load(open(sys.argv[1], encoding="utf-8")))
evs = [json.loads(x)["event"] for x in open(sys.argv[2], encoding="utf-8") if x.strip()]
dev = [s for s in json.load(open(sys.argv[3], encoding="utf-8"))["sessions"] if s.get("role") == "developer"]
reqs = [e for e in evs if e["type"] == "provider/request" and e["data"].get("budget_owner") == "DEVELOPER"]
assert len(reqs) == len(dev) and all(r["data"]["story_id"] == s["story_id"] for r, s in zip(reqs, dev))
out = []
for r, s in zip(reqs, dev):
    before = [(e["seq"], e["type"], e["data"]) for e in evs if e["seq"] < r["seq"]]
    prompt = feedback.task(project, s["story_id"])
    if any(t == "failure/observed" and d.get("story_id") == s["story_id"] for _, t, d in before):
        told = feedback.retry_feedback(before, s["story_id"], project)
        prompt += f"\n\nA previous attempt of this story was not accepted; the kernel observed:\n{told}\nFix the implementation."
    out.append([s["story_id"], s["attempt"], r["seq"], hashlib.sha256(prompt.encode()).hexdigest() == s["prompt_sha256"],
                "".join(prompt.partition("\n\nA previous attempt")[1:]).strip()])
print(json.dumps(out))
"""
HEX = re.compile(r"\b[0-9a-f]{7,40}\b")
SOUGHT = {"journal": re.compile(r"journals/|JOURNAL"),
          "hidden": re.compile(r"scratch-|verifier-wt|request\.json|/probe-"),
          "framework": re.compile(r"site-packages/aisef|/aisef2/|inputs/project\.json|/ai-sdlc\b")}


def events(path: pathlib.Path) -> list[dict]:
    if path.suffix == ".jsonl":
        return [json.loads(ln)["event"] for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return json.loads(path.read_text(encoding="utf-8"))


def attempts(evs: list[dict], story: str, before: int) -> list[dict]:
    """The story's attempts that ended before seq `before`, from the journal."""
    out, cur = [], None
    for e in evs:
        if e["seq"] >= before:
            break
        d = e["data"]
        if d.get("story_id") != story:
            continue
        if e["type"] == "story/begin":
            cur = {"parent": d["parent"], "begin": e["seq"], "criteria": [], "proofs": {}, "result": None}
        elif cur is None:
            continue
        elif e["type"] == "story/admitted":
            cur["criteria"] = sorted(d.get("dispositions") or {})
        elif e["type"] == "provider/result" and cur["result"] is None and not d.get("synthetic"):
            cur["result"] = (e["seq"], d.get("detail", ""))
        elif e["type"] == "proof/verified":
            cur.setdefault("candidate", d.get("candidate"))
            if d.get("candidate") == cur["candidate"]:
                cur["proofs"][d["criterion_id"]] = (e["seq"], d.get("verdict"), d.get("agreement"))
        elif e["type"] == "story/end":
            out.append(cur)
            cur = None
    return out


def calls(stream: pathlib.Path):
    for ln in stream.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(ln)
        except ValueError:
            continue
        if e.get("type") == "tool_use":
            yield json.dumps(((e.get("part") or {}).get("state") or {}).get("input") or {}, ensure_ascii=False)


def migrated_project():
    """The 2.0.0 bundle migrated in memory (V2-007), loaded: the plan, specs and facts the two parts below read. The
    candidate migration writes lacks the approvals of the contracts whose evaluation changed (owner decision
    2026-10-15), so it is loaded with them approved by a stand-in — in memory, written nowhere, and used only for the
    plan and the specs, which an approval does not enter."""
    sys.path.insert(0, str(ROOT))
    from aisef2.app import bundle, bundle_cli
    candidate, report = bundle_cli.migrate(json.loads(BUNDLE.read_text(encoding="utf-8")))
    for row in (report["needs_owner_reapproval"] or {}).get("contracts", ()):
        candidate = bundle_cli.approve(candidate, row["contract"], "human:stand-in-for-a-read-only-analysis", 0.0)
    return bundle.load(candidate)


def expectations() -> dict[str, str]:
    """criterion -> the candidate expectation of its spec in the 2.0.0 bundle (migrated, V2-007; the same plan's criteria
    as P10's journals)."""
    project = migrated_project()
    return {o.criterion_id: project.specs[o.product_proof_spec_id].candidate_expectation.value for o in project.plan.obligations}


def retries(name: str, journal: pathlib.Path, sessions: pathlib.Path, expect: dict[str, str]) -> list[dict]:
    evs = events(journal)
    rows, seen = [], {}
    for e in evs:
        d = e["data"]
        if e["type"] != "provider/request" or d.get("budget_owner") != "DEVELOPER":
            continue
        story = d["story_id"]
        seen[story] = seen.get(story, 0) + 1
        if not any(x["type"] == "failure/observed" and x["data"].get("story_id") == story and x["seq"] < e["seq"] for x in evs):
            continue
        prior = attempts(evs, story, e["seq"])
        result = next((x["data"].get("detail") for x in evs if x["type"] == "provider/result" and x["seq"] > e["seq"]
                       and x["data"].get("story_id") == story), None)
        parents = {x["data"]["parent"] for x in evs if x["type"] == "story/begin" and x["seq"] < e["seq"]
                   and x["data"].get("story_id") == story}
        cands = {a.get("candidate") for a in prior} - {None} - parents
        row = {"run": name, "story": story, "developer_session": seen[story], "request_seq": e["seq"],
               "changed_nothing": [a["result"][0] for a in prior if a["result"] and a["result"][1].startswith(NOTHING)],
               "parent_as_cand": [a["begin"] for a in prior if a.get("candidate") == a["parent"]],
               "held": sum(1 for a in prior for c, v in a["proofs"].items() if c in expect and v[1] == expect[c] and v[2]),
               "never_proved": sum(len(set(a["criteria"]) - set(a["proofs"])) for a in prior),
               "outcome": result}
        stream = sessions / f"{story}.developer.{seen[story]}.jsonl"
        if stream.is_file():
            n, hit = 0, dict.fromkeys(("prior_work", *SOUGHT), 0)
            earlier = re.compile(rf"{re.escape(story)}\.developer\.[1-{seen[story] - 1}]\.jsonl")
            for c in calls(stream):
                n += 1
                gitp = re.search(r"\bgit\b", c) and (re.search(r"reflog|fsck", c) or any(
                    any(s.startswith(h) for s in cands) for h in HEX.findall(c)))
                hit["prior_work"] += bool(gitp or earlier.search(c))
                for k, rx in SOUGHT.items():
                    hit[k] += bool(rx.search(c))
            row.update(tool_calls=n, sought=hit)
        rows.append(row)
    return rows


def told_200() -> list:
    """Part 1: [story, attempt, request seq, recomputed prompt sha256 == recorded, retry text] per developer session."""
    with tempfile.TemporaryDirectory(prefix="aisef-200-") as tmp:
        arch = subprocess.run(["git", "-C", str(ROOT), "archive", "v2.0.0", "aisef2"], capture_output=True, check=True)
        tarfile.open(fileobj=io.BytesIO(arch.stdout)).extractall(tmp, filter="data")
        r = subprocess.run([sys.executable, "-P", "-c", TOLD_200, str(BUNDLE), str(SMOKE2 / "aisef-run.jsonl"),
                            str(SMOKE2 / "RUN.json")], env={**os.environ, "PYTHONPATH": tmp}, cwd=tmp,
                           capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def pack_now() -> list[tuple[int, str]]:
    """Part 3: the context pack this tree builds at smoke-2's STORY-04-02 retries."""
    sys.path.insert(0, str(ROOT))
    from aisef2.app import feedback
    project = migrated_project()
    evs = events(SMOKE2 / "aisef-run.jsonl")
    return [(q, feedback.context_pack([(e["seq"], e["type"], e["data"]) for e in evs if e["seq"] < q], "STORY-04-02", project))
            for q in (1473, 1584)]


def main() -> None:
    told = told_200()
    print("D4 context gap on recorded retries (validation/v21/context_gap.py; read-only over closure-evidence/v2)")
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout
    print(f"commit: {head} dirty: {len(dirty.splitlines())}\n")
    print("1. What the 2.0.0 release smoke-2 developers were told: each prompt recomputed by the 2.0.0 code (git archive "
          "v2.0.0) from the journal before its request, against the prompt_sha256 the run recorded")
    for story, n, seq, equal, _ in told:
        print(f"   {story} attempt {n} (request seq {seq}): {'EQUAL' if equal else 'DIFFERENT'}")
    print("   the retry text of STORY-04-02 attempt 3, as told:")
    print("\n".join("   | " + ln for ln in told[-1][4].strip().splitlines()))
    print("\n2. Every recorded V2 retry with a journal (who built the retry text: smoke-2 the v2.0.0 retry_feedback, "
          "EXPERIMENT, part 1; cycle-2 P10 validation/qualification/c2_p9.py at each attempt's execution commit, CODE, "
          "not recomputed: the module docstring)\n")
    expect = expectations()
    rows = [r for run in RUNS for r in retries(*run, expect)]
    print(f"{'run':24} {'story':12} s# {'req':>5}  nothing parent held unproved | calls prior journal hidden fw | outcome")
    for r in rows:
        s = r.get("sought") or {}
        print(f"{r['run']:24} {r['story']:12} {r['developer_session']:2} {r['request_seq']:5}  {len(r['changed_nothing']):7} "
              f"{len(r['parent_as_cand']):6} {r['held']:4} {r['never_proved']:8} | {r.get('tool_calls', '-'):>5} "
              f"{s.get('prior_work', '-'):>5} {s.get('journal', '-'):>7} {s.get('hidden', '-'):>6} {s.get('framework', '-'):>2} "
              f"| {r['outcome']}")
    told = [r for r in rows if r["changed_nothing"] or r["parent_as_cand"]]
    print(f"\nretries: {len(rows)}; with an earlier attempt that changed nothing / a parent shown as a candidate: {len(told)}; "
          f"with an earlier 'held' fact untold: {sum(1 for r in rows if r['held'])}; "
          f"with an unproved criterion untold: {sum(1 for r in rows if r['never_proved'])}")
    for k in ("prior_work", "journal", "hidden", "framework"):
        n = [r for r in rows if (r.get("sought") or {}).get(k)]
        print(f"sessions that sought {k}: {len(n)} of {sum(1 for r in rows if 'sought' in r)} "
              f"({sum(r['sought'][k] for r in n)} calls)")
    print(f"retry sessions that changed nothing: {sum(1 for r in rows if str(r['outcome']).startswith(NOTHING))}")
    print("\n3. The context pack this tree builds at smoke-2 STORY-04-02's retries (offline replay; not run evidence)")
    for q, text in pack_now():
        print(f"\n   at request seq {q} ({len(text)} characters):")
        print("\n".join("   | " + ln for ln in text.splitlines()))


if __name__ == "__main__":
    main()
