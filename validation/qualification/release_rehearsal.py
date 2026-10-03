"""V2.0 release, before the one paid smoke (charter §15): the OFFLINE REHEARSAL — the product's own path, `aisef run`
(aisef2.app.run.execute), on the release bundle and the LedgerLock repository, with a fake client and a fake provider.
No network, no model; the real client is never looked up.

    python -P validation/qualification/release_rehearsal.py --print    # run every scenario, print the summary
    python -P validation/qualification/release_rehearsal.py --write    # -> closure-evidence/v2/release/OFFLINE-REHEARSAL.json

The fake client is a script that answers `opencode run --format json ... --title T --dir D PROMPT` the way the client
does (text and step_finish events); as a developer it writes, by scenario:

* `reference`: the P5 reference implementation (all 59 specs satisfied) and the story's unittest file, whenever called
  — the first story over-delivers legitimately. Every story must commit and ProductProof must be 59/59: a rollback
  or block here is a framework false rollback/block, and the smoke must not be preregistered.
* `partial`: the first delivery is the reference with mutant M-7-1 (one later behaviour wrong); called again, the
  reference — the story that owns the behaviour must get developer work and commit (H-REGRESSION-001).
* `nothing`: changes nothing — no story may commit and the delivery verdict must not be PASS (no false acceptance).

What the rehearsal measures for the budget is structural: the provider requests (the preflight's and one per session)
and the sessions per story; a session's turns and tokens are the fake's, not a model's.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_REL = "closure-evidence/v2/release/OFFLINE-REHEARSAL.json"
SCENARIOS = ("reference", "partial", "nothing")
ROUTE = "rehearsal/fake-model"
#: the charter's hard ceilings (§15): the rehearsal runs under them so a structural overrun shows here first
CEILINGS = {"provider_requests": 60, "turns": 700, "input_tokens": 60_000_000, "output_tokens": 400_000}
CLIENT = r'''import json, pathlib, sys
here = pathlib.Path(__file__).resolve().parent
argv = sys.argv[1:]
if argv == ["--version"]:
    print("0.0.0-rehearsal")
    raise SystemExit(0)
title, cwd = argv[argv.index("--title") + 1], pathlib.Path(argv[argv.index("--dir") + 1])
cfg = json.loads((here / "rehearsal.json").read_text(encoding="utf-8"))
calls = here / "developer-calls"
if title.startswith("developer "):
    story = title.split(" ", 1)[1]
    n = len(calls.read_text().split()) if calls.exists() else 0
    calls.write_text((calls.read_text() if calls.exists() else "") + story + "\n")
    if cfg["scenario"] != "nothing":
        modules = dict(cfg["reference"])
        if cfg["scenario"] == "partial" and n == 0:
            modules.update(cfg["partial"])
        (cwd / "ledgerlock").mkdir(exist_ok=True)
        for name, text in modules.items():
            (cwd / "ledgerlock" / name).write_text(text, encoding="utf-8", newline="\n")
        (cwd / "tests").mkdir(exist_ok=True)
        (cwd / "tests" / "__init__.py").write_text("", encoding="utf-8")
        test = cfg["test"] + (cfg["repair_test"] if cfg["scenario"] == "partial" and n > 0 else "")
        (cwd / cfg["tests"][story]).write_text(test, encoding="utf-8", newline="\n")
text = '{"findings": []}' if title.startswith("reviewer ") else "done"
print(json.dumps({"type": "text", "part": {"text": text}}))
print(json.dumps({"type": "step_finish", "part": {"tokens": {"input": 1000, "output": 100, "reasoning": 0}}}))
'''


def settings_doc() -> dict:
    from aisef2.app import settings
    from aisef2.arch.enums import Owner
    from validation.qualification import c2_p9
    return {"format": settings.FORMAT, "client": "opencode", "route": ROUTE,
            "provider": {"name": "rehearsal", "endpoint": "https://rehearsal.invalid/v1", "api_key_env": "AISEF_REHEARSAL_NO_KEY"},
            "client_env": [], "budget": dict(CEILINGS), "max_turns_per_session": 80,
            "limits": {o.value: c2_p9.PROFILES[c2_p9.EXPERIMENT][o.value] for o in Owner},
            "timeouts_s": {"developer": 600, "reviewer": 600, "tool": 120, "probe": 60}, "preflight": {"chat_probes": 2}}


def transport(path, body=None):
    if body is None:
        return 200, {"data": [{"id": "fake-model", "owned_by": "rehearsal"}]}
    return 200, {"model": "fake-model", "system_fingerprint": "fp-rehearsal", "usage": {"prompt_tokens": 9, "completion_tokens": 1}}


def scenario(name: str, project, out: pathlib.Path, cals=None) -> dict:
    from aisef2.app import run as R
    from aisef2.app import settings
    from aisef2.app.verify import verify
    from validation.qualification import c2_k_nowork_001 as kn
    from validation.qualification import c2_p9
    from validation.qualification import p5_falsifiability as pf
    from validation.qualification import p10 as P10
    fake = out / "client"
    fake.mkdir(parents=True)
    partial = {f.name: f.read_text(encoding="utf-8") for f in sorted((ROOT / kn.MUTANTS / kn.PARTIAL).glob("*.py"))}
    (fake / "rehearsal.json").write_text(json.dumps({
        "scenario": name, "reference": pf.reference_modules(), "partial": partial, "test": kn.TEST, "repair_test": kn.TEST_REPAIR,
        "tests": {s: c2_p9.test_path(s) for s in project.stories}}), encoding="utf-8")
    exe = fake / "opencode"
    exe.write_text(f"#!{sys.executable}\n" + CLIENT, encoding="utf-8")
    exe.chmod(0o755)
    rec = R.execute(project, settings.load(settings_doc()), P10.LEDGERLOCK_REPO, out / "run", transport=transport,
                    client_exe=str(exe), cals=cals)
    calls = (fake / "developer-calls").read_text().split() if (fake / "developer-calls").exists() else []
    events = rec["productproof"] or {}
    v = verify(project, out / "run")
    sessions = rec["sessions"]
    return {"scenario": name, "delivery_verdict": rec["delivery_verdict"], "delivery_blocked_by": rec["delivery_blocked_by"],
            "story_outcomes": rec["story_outcomes"], "story_errors": rec["story_errors"],
            "productproof": {k: events.get(k) for k in ("total", "satisfied_at_last_proof", "delivered")},
            "developer_calls": calls, "sessions": len(sessions),
            "sessions_per_story": {s: sum(1 for x in sessions if x.get("story_id") == s) for s in project.order()},
            "provider_requests": rec["budget"]["spent"]["provider_requests"], "preflight_requests": rec["budget"]["preflight"]["provider_requests"],
            "budget_reached": rec["budget"]["reached"], "unaccounted": rec["budget"]["spent"]["unaccounted"],
            "journal": rec["journal"], "verification": {"verdict": v["verdict"], "problems": v["problems"]},
            "final_main": rec["final_main"]}


def problems_of(results: dict, stories: list[str]) -> list[str]:
    out = []
    ref = results.get("reference")
    if ref:
        if ref["delivery_verdict"] != "PASS" or any(v[-1:] != ["COMMIT"] for v in ref["story_outcomes"].values()):
            out.append(f"reference: a framework false rollback/block — every story must commit: {ref['story_outcomes']}")
        if ref["productproof"]["delivered"] != ref["productproof"]["total"]:
            out.append(f"reference: ProductProof {ref['productproof']['delivered']}/{ref['productproof']['total']}, not 100%")
    part = results.get("partial")
    if part and (part["delivery_verdict"] != "PASS" or part["productproof"]["delivered"] != part["productproof"]["total"]):
        out.append(f"partial: the story that owns the wrong behaviour did not repair it: {part['story_outcomes']}")
    none = results.get("nothing")
    if none and (none["delivery_verdict"] == "PASS" or any(v[-1:] == ["COMMIT"] for v in none["story_outcomes"].values())):
        out.append(f"nothing: a false acceptance — a story committed with no change: {none['story_outcomes']}")
    for name, r in results.items():
        if r["verification"]["verdict"] != "VERIFIED":
            out.append(f"{name}: the run directory does not verify from its journal: {r['verification']['problems']}")
        if r["unaccounted"]:
            out.append(f"{name}: unaccounted spend: {r['unaccounted']}")
        if r["budget_reached"]:
            out.append(f"{name}: a structural budget overrun under the charter's ceilings: {r['budget_reached']}")
    return out


def rehearse(names=SCENARIOS, cals=None) -> dict:
    from aisef2.app import bundle
    from validation.qualification import release_bundle as rb
    project = bundle.load(rb.build()["bundle"])
    results = {}
    with tempfile.TemporaryDirectory(prefix="aisef-rehearsal-") as t:
        for name in names:
            results[name] = scenario(name, project, pathlib.Path(t) / name, cals)
    return {"record": "AISEF V2.0 — OFFLINE REHEARSAL OF THE RELEASE SMOKE (fake client, fake provider; no model, no network)",
            "bundle_digest": project.digest, "plan_hash": project.plan.plan_hash, "execution_order": project.order(),
            "ceilings": CEILINGS, "results": results, "problems": problems_of(results, project.order())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print", action="store_true")
    mode.add_argument("--write", action="store_true")
    ap.add_argument("--scenario", action="append", choices=SCENARIOS)
    a = ap.parse_args(argv)
    rec = rehearse(tuple(a.scenario or SCENARIOS))
    text = json.dumps(rec, indent=1, sort_keys=True) + "\n"
    if a.write:
        (ROOT / OUT_REL).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / OUT_REL).write_text(text, encoding="utf-8")
    print(text if a.print else f"wrote {OUT_REL}: problems {rec['problems']}")
    return 0 if not rec["problems"] else 1


if __name__ == "__main__":
    sys.exit(main())
