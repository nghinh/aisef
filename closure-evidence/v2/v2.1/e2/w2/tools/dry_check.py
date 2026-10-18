"""W2 dry check (offline, no provider, no client): the hidden evaluator leaks into nothing an arm sees, and the two bundles
say what they should about the baseline commit.

    python -P -B closure-evidence/v2/v2.1/e2/w2/tools/dry_check.py <baseline repo> <scratch dir>

1. Leaks. Every distinctive string of hidden/evaluator.json (harness.distinctive: each contract's stimulus and observable as
   JSON) and every plain string of it (tools/leaks_w2.py: file names, run ids, text lines) is searched in every public
   artefact of this lane — the arms' authoring and bundle, the baseline tree's files (from the repo's object store), the task
   text, the settings, this directory's README — and must be found in none. Controls over synthetic session streams:
   positive (one hidden stimulus whose JSON holds no backslash, nested as a session would nest it): harness.leaks reports it;
   escaped (a hidden stimulus whose JSON holds `\\n`, nested the same way): what harness.leaks reports is recorded as it is —
   a limit of its quote-only escape, measured, not hidden; plain (a session echoing one hidden sentence and one hidden file
   name): leaks_w2 reports it; negative (a public stimulus and a public sentence): neither scan reports it.
2. Baseline verdicts. Copies of both bundles approved by `human:w2-dry-check` (a TECHNICAL approval for this measurement
   only, written to <scratch dir>, never committed; the owner's approvals are APPROVE.sh) are evaluated on the baseline
   commit by harness.evaluate (AISEF's own probes). Expected: every INTRODUCE contract NOT satisfied (the change is not
   there yet), every PRESERVE contract SATISFIED (the behaviour the delta must keep already holds). Each approved copy is
   also linted (admission under this release's calibrations).

Writes dry-check/leaks.json and dry-check/baseline.json next to this directory's dry-check/, and prints a summary.
Exit 0 when every expectation holds, 1 otherwise."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
W2 = HERE.parent
ROOT = W2.parents[4]
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import leaks_w2  # noqa: E402
from aisef2.app import bundle_cli  # noqa: E402
from validation.experiments import harness as H  # noqa: E402

APPROVER = "human:w2-dry-check"       # technical: this measurement's, not the owner's acceptance


def _git(repo: pathlib.Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


def public_texts(repo: pathlib.Path) -> dict[str, str]:
    """Everything an arm may see or that is committed beside the hidden bundle: name -> text."""
    out = {}
    for p in sorted(W2.rglob("*")):
        rel = p.relative_to(W2).as_posix()
        if p.is_file() and not rel.startswith("hidden/") and not rel.startswith("dry-check/"):
            out[f"w2/{rel}"] = p.read_text(encoding="utf-8", errors="replace")
    for line in _git(repo, "ls-files", "-z").decode().split("\0"):
        if line:
            out[f"baseline/{line}"] = _git(repo, "cat-file", "blob", f"HEAD:{line}").decode("utf-8", "replace")
    return out


def _session(path: pathlib.Path, text: str) -> None:
    path.write_text(json.dumps({"type": "text", "part": {"text": "the model says: " + text}}) + "\n", encoding="utf-8")


def leak_scan(repo: pathlib.Path, scratch: pathlib.Path) -> dict:
    evaluator = json.loads((W2 / "hidden" / "evaluator.json").read_text(encoding="utf-8"))
    arms = json.loads((W2 / "arms" / "bundle.json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in evaluator["contracts"]}
    marks, candidates = H.distinctive(evaluator), leaks_w2.plain_strings(evaluator)
    public = public_texts(repo)
    # public vocabulary: a string the task text or the baseline tree already holds is not a secret of the evaluator
    vocabulary = "\n".join(t for n, t in public.items() if n.startswith("baseline/") or n == "w2/baseline/TASK.txt")
    excluded = sorted(s for s in candidates if any(f in vocabulary for f in leaks_w2._forms(s)))
    plain = [s for s in candidates if s not in excluded]
    (W2 / "dry-check" / "plain-strings.json").write_text(json.dumps(
        {"evaluator_sha256": H.sha((W2 / "hidden" / "evaluator.json").read_bytes()), "strings": plain,
         "excluded_public_vocabulary": excluded}, indent=1) + "\n", encoding="utf-8")
    json_hits, plain_hits = {}, {}
    for name, text in public.items():
        n = sum(1 for m in marks if m in text or m.replace('"', '\\"') in text)
        if n:
            json_hits[name] = n
        hits = sorted(s for s in plain if any(f in text for f in leaks_w2._forms(s)))
        if hits:
            plain_hits[name] = hits
    # controls: each its own sessions directory, so a report names exactly one stream
    def control(name: str, text: str) -> dict:
        d = scratch / "sessions" / name
        d.mkdir(parents=True, exist_ok=True)
        _session(d / f"{name}.developer.1.jsonl", text)
        return {"harness_leaks": H.leaks(d, evaluator), "leaks_w2": leaks_w2.leaks(d, plain)}
    stim = lambda cid: json.dumps(by_id[cid]["stimulus"], sort_keys=True)  # noqa: E731
    hidden_sentence = next(s for s in plain if " " in s and "/" not in s and "{" not in s)
    hidden_file = next(s for s in plain if s.endswith(".md") and "/" not in s)
    public_sentence = next(iter(arms["contracts"][0]["stimulus"]["workspace"].values()))["text"].strip()
    controls = {
        "positive": control("positive", stim("H-MISSING")),
        "escaped": control("escaped", stim("H-DIR")),
        "plain": control("plain", f"I will write {hidden_file} with the line: {hidden_sentence}"),
        "negative": control("negative", json.dumps(arms["contracts"][0]["stimulus"], sort_keys=True) + " " + public_sentence),
    }
    assert "\\" not in stim("H-MISSING") and "\\" in stim("H-DIR")
    ok = (not json_hits and not plain_hits
          and controls["positive"]["harness_leaks"] == [{"session": "positive.developer.1.jsonl", "strings": 1}]
          and controls["plain"]["leaks_w2"] and controls["plain"]["leaks_w2"][0]["strings"] >= 2
          and controls["negative"]["harness_leaks"] == [] and controls["negative"]["leaks_w2"] == [])
    return {"distinctive_json_strings": len(marks), "plain_strings": len(plain), "excluded_public_vocabulary": excluded,
            "public_artefacts_scanned": len(public), "json_hits": json_hits, "plain_hits": plain_hits, "controls": controls,
            "harness_leaks_limit": ("the escaped control is NOT reported by harness.leaks" if not controls["escaped"]["harness_leaks"]
                                    else "the escaped control IS reported by harness.leaks"),
            "ok": ok}


def approved_copy(src: pathlib.Path, dst: pathlib.Path) -> dict:
    doc = json.loads(src.read_text(encoding="utf-8"))
    for c in doc["contracts"]:
        doc = bundle_cli.approve(doc, c["id"], APPROVER, time.time())
    dst.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def baseline_verdicts(repo: pathlib.Path, scratch: pathlib.Path) -> dict:
    commit = _git(repo, "rev-parse", "HEAD").decode().strip()
    out = {"baseline": commit, "approver": APPROVER + " (technical, scratch only)", "bundles": {}}
    for name, src in (("hidden", W2 / "hidden" / "evaluator.json"), ("arms", W2 / "arms" / "bundle.json")):
        doc = approved_copy(src, scratch / f"{name}-approved.json")
        lint = bundle_cli.lint(doc)
        authoring = json.loads((src.parent / "authoring.json").read_text(encoding="utf-8"))
        roles: dict[str, set] = {}
        for s in authoring["stories"].values():
            for cr in s["criteria"]:
                roles.setdefault(cr["contract"], set()).add(cr["role"])
        spec_of = {o["product_proof_spec_id"]: o["criterion_id"] for o in doc["plan"]["obligations"]}
        crit_contract = {cr["id"]: cr["contract"] for s in authoring["stories"].values() for cr in s["criteria"]}
        ev = H.evaluate(repo, commit, doc)
        rows = []
        for r in ev["specs"]:
            cid = crit_contract.get(spec_of.get(r["spec"], ""), "?")
            expected = "SATISFIED" if roles.get(cid) == {"PRESERVE"} else "NOT_SATISFIED"
            got = "SATISFIED" if r["satisfaction"] == "SATISFIED" else "NOT_SATISFIED"
            rows.append({"spec": r["spec"], "contract": cid, "roles": sorted(roles.get(cid, [])), "status": r["status"],
                         "satisfaction": r["satisfaction"], "expected_at_baseline": expected, "as_expected": expected == got})
        out["bundles"][name] = {"sha256": H.sha(src.read_bytes()), "lint_verdict": lint["verdict"], "admission": lint.get("admission"),
                               "criteria_without_calibration": lint.get("criteria_without_calibration"),
                               "evaluation": {k: ev[k] for k in ("total", "satisfied", "not_satisfied")}, "rows": rows,
                               "ok": lint["verdict"] == "READY" and all(r["as_expected"] for r in rows)}
    out["ok"] = all(b["ok"] for b in out["bundles"].values())
    return out


def main(argv: list[str]) -> int:
    repo, scratch = pathlib.Path(argv[0]).resolve(), pathlib.Path(argv[1]).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    (W2 / "dry-check").mkdir(exist_ok=True)
    started = time.strftime("%Y-%m-%d %H:%M:%S %z")
    leaks = leak_scan(repo, scratch)
    (W2 / "dry-check" / "leaks.json").write_text(json.dumps({"at": started, **leaks}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    base = baseline_verdicts(repo, scratch)
    (W2 / "dry-check" / "baseline.json").write_text(json.dumps({"at": started, **base}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"leaks_ok": leaks["ok"], "json_hits": leaks["json_hits"], "plain_hits": leaks["plain_hits"],
                      "controls": {k: {"harness": len(v["harness_leaks"]), "w2": len(v["leaks_w2"])} for k, v in leaks["controls"].items()},
                      "harness_leaks_limit": leaks["harness_leaks_limit"],
                      "baseline": {n: {"lint": b["lint_verdict"], "evaluation": b["evaluation"], "ok": b["ok"],
                                       "unexpected": [r["contract"] for r in b["rows"] if not r["as_expected"]]}
                                   for n, b in base["bundles"].items()}}, indent=1))
    return 0 if leaks["ok"] and base["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
