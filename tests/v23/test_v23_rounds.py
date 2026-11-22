"""v2.3 ROUND-AUTH: the round-v2.3 counterparts of the 11 v2.2-round sealing-gated tests (W1-DESIGN.md §2.6).

Each v2.2 test of validation/v23/replay_v22.V22_REPLAYED binds a committed record to the tree by the v2.2 selection
rule. Its control is kept twice, never weakened:

* history — the test itself, byte-identical, replayed at v2.2.0 (`RoundV23.test_replay_v22`, replay_v22.py);
* round v2.3 — its counterpart here: the SAME assertions, verbatim, run under `version_forward.in_round("v2.3")`,
  where the node's own check selects the verified head of its chain; plus the node's round-v2.3 currency state MUST be
  MEASURED or VERIFIED_REUSE. The one assertion that is not round-aware (the legacy whole-file mutation rule) is
  rebound to the F5 state of the same targets (replay_v22.REBOUND); the coverage map test proves no assertion is lost.

The round is OPEN only when ledger seq 13 (AISEF_V2_3_QUALIFICATION_ROUND_AUTHORIZED, the owner's) is committed and
the round-v2.3 selection exists (lane L1-F5). Until then every counterpart FAILS — never skips — under
AISEF_SEALING=1, so the sealing gate (the tests.yml `sealing` job, which runs `discover -s tests`) stays closed.

The gate is AISEF_SEALING=1, exactly as the sealing tier's, but it is `round_gate`, not `sealing`: W1-DESIGN.md §7 keeps
tests/v2/sealing_gate.py GATED byte-identical (the file changes only for V22_REPLAYED and the pins that guard its skip)
and tests/v2/test_sealing_gate.py unedited. The round's own closed list is V23_GATED, and
`Coverage.test_the_round_gate_list_is_closed` refuses a `round_gate` test missing from it or a listed test missing its
gate. The wiring seq 13 would authorize (SEQ13_PATCH_REL) pins this file by sha256 (RA-GP-1): the 11 v2.2 tests — and,
since R4 (Q0-1), the v2.2 Q0 calibration, whose counterpart is tests/v23/test_v23_q0_round.py — are skipped only while
this file, the Q0 counterpart, the replay, q0_round.py, the digest tool and tests/v23/__init__.py are exactly as pinned —
a deleted or edited one un-skips all 12 — so no round-v2.3 check can be dropped silently. `Seq13Wiring` is red until that patch is applied,
exactly. The round opens only for the reviewed ruling, by digest, in the owner's own words (RA-INT-2,
`ledger_seq13_problems`), only while the draft is the one every commit that added it holds — through merges, never in
a shallow clone (Q0R-INT-1, `reviewed_draft`) — and only while every file the ruling binds by sha256 (BOUND_SHA256:
the Q0-1 amendments and the evidence) is exactly those bytes (Q0R-INT-2).
"""
from __future__ import annotations

import ast
import contextlib
import copy
import functools
import importlib.util
import inspect
import json
import pathlib
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.v2 import sealing_gate  # noqa: E402
from validation.v23 import q0_round as Q  # noqa: E402
from validation.v23 import replay_v22 as RP  # noqa: E402

LEDGER_REL = "closure-evidence/v2/cycle2/RELEASE-DECISIONS.json"
ROUND_ID = "AISEF_V2_3_QUALIFICATION_ROUND_AUTHORIZED"
#: the reviewed ruling seq 13 must be, and the wiring it names. Paths, not digests: the ruling names the patch by sha256
#: and the patch pins this file, so neither digest can be written here (it would be a hash cycle).
SEQ13_DRAFT_REL = "docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT-R6.md"
SEQ13_PATCH_REL = "docs/v2.3/drafts/SEQ13-WIRING-R6.patch"
OK = ("MEASURED", "VERIFIED_REUSE")
STALE_SOURCE = ": target changed since the mutation run — re-run it"
#: the historical phases the v2.2 test reads (m.RECORDS at v2.2.0, minus V2.1 — the runner-2 phase it treats apart)
V22_HISTORICAL = {
    "P1": "closure-evidence/v2/P1-MUTATION.json", "P2": "closure-evidence/v2/P2-MUTATION.json",
    "P3": "closure-evidence/v2/P3-MUTATION.json", "P4": "closure-evidence/v2/P4-MUTATION.json",
    "P5": "closure-evidence/v2/P5-MUTATION.json", "P6": "closure-evidence/v2/P6-MUTATION.json",
    "C2-ORCH": "closure-evidence/v2/cycle2/C2-ORCH-MUTATION.json", "C2-P10": "closure-evidence/v2/cycle2/P10-MUTATION.json",
}

#: AISEF_SEALING=1 runs these, as the sealing tier; deliberately not named `sealing` (see the module docstring)
round_gate = unittest.skipUnless(
    sealing_gate.SEALING, "round-v2.3 currency counterpart: runs with the sealing tier (AISEF_SEALING=1); red until "
                          "ledger seq 13 opens the v2.3 round")

#: every `round_gate` test, closed ("path::Class" gates the class), as sealing_gate.GATED is for `sealing`
V23_GATED = ("tests/v23/test_v23_rounds.py::RoundV23", "tests/v23/test_v23_rounds.py::Seq13Wiring",
             "tests/v23/test_v23_q0_round.py::Q0RoundV23", "tests/v23/test_v23_q0_round.py::Q0Wiring")


def _git(*args: str, root: pathlib.Path = ROOT) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True,
                          env=dict(os.environ, GIT_NO_REPLACE_OBJECTS="1")).stdout


def _lf(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def reviewed_draft(root: pathlib.Path = ROOT) -> dict:
    """The entry of SEQ13_DRAFT_REL as committed at HEAD. ValueError unless HEAD's blob is the blob of every commit
    that added the file: a reviewed draft is never rewritten in place (R1-R5 are each kept as written). Q0R-INT-1:
    every add commit is seen — `--full-history`, so a merge that resolves to a rewritten draft cannot hide the reviewed
    one, and never in a shallow clone, whose cut history could hide it."""
    from validation.v23 import ledger_digest as LD
    if _git("rev-parse", "--is-shallow-repository", root=root).strip() != b"false":
        raise ValueError(f"{SEQ13_DRAFT_REL}: a shallow clone cannot show every commit that added it")
    head = _git("rev-parse", f"HEAD:{SEQ13_DRAFT_REL}", root=root).strip()
    added = _git("log", "--full-history", "--no-renames", "--format=%H", "--diff-filter=A", "HEAD", "--",
                 SEQ13_DRAFT_REL, root=root).split()
    if not added or any(_git("rev-parse", f"{c.decode()}:{SEQ13_DRAFT_REL}", root=root).strip() != head for c in added):
        raise ValueError(f"{SEQ13_DRAFT_REL} is not the draft as first committed")
    (entry,) = LD.entries(_git("show", f"HEAD:{SEQ13_DRAFT_REL}", root=root).decode("utf-8"))
    return entry


def ledger_seq13_problems(root: pathlib.Path = ROOT) -> list[str]:
    """Why the committed ledger does not open round v2.3 ([] = it does): exactly one seq 13, the owner's, whose canonical
    ruling digest (validation/v23/ledger_digest.py) is the reviewed draft's, and whose `authority` is the owner's own
    words — not empty, not the draft's `<…>` placeholder, and quoting that digest (RA-INT-2); and every file the
    ruling binds in BOUND_SHA256 is exactly those LF bytes (Q0R-INT-2: the amendments and evidence it was approved on)."""
    from validation.v23 import ledger_digest as LD
    out = []
    try:
        committed = _git("show", f"HEAD:{LEDGER_REL}", root=root)
        entries = json.loads(committed)["entries"]
        if _lf((root / LEDGER_REL).read_bytes()) != committed:
            out.append(f"{LEDGER_REL} differs from its committed bytes")
        draft = reviewed_draft(root)
        want = LD.digest(draft)
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, TypeError) as e:
        return out + [f"the ledger or the reviewed draft is unreadable: {type(e).__name__}"]
    e13 = [e for e in entries if isinstance(e, dict) and e.get("seq") == 13]
    d = e13[0].get("decision") if len(e13) == 1 else None
    if not (len(e13) == 1 and e13[0].get("id") == ROUND_ID and e13[0].get("approver") == "human:owner"
            and isinstance(d, dict) and d.get("QUALIFICATION_ROUND") == "v2.3"):
        return out + [f"the ledger holds no single committed owner entry seq 13 {ROUND_ID} (ROUND-AUTH: draft only)"]
    try:
        got = LD.digest(e13[0])
    except KeyError as e:
        return out + [f"seq 13 is not a ruling entry: {e}"]
    if got != want:
        out.append(f"seq 13's ruling digest {got} is not the reviewed draft's {want} ({SEQ13_DRAFT_REL})")
    a = e13[0].get("authority")
    a = a.strip() if isinstance(a, str) else ""
    if not a or (a.startswith("<") and a.endswith(">")):
        out.append("seq 13 authority is empty or the draft's placeholder, not the owner's own words")
    elif got not in a:
        out.append(f"seq 13 authority does not quote its ruling digest {got}")
    bound = draft["decision"].get("BOUND_SHA256", {})
    if not isinstance(bound, dict):
        return out + ["the reviewed ruling's BOUND_SHA256 is not a map of path to sha256"]
    for rel, sha in sorted(bound.items()):
        p = root / rel
        if not (p.is_file() and hashlib.sha256(_lf(p.read_bytes())).hexdigest() == sha):
            out.append(f"{rel} is not the file the reviewed ruling binds (BOUND_SHA256 {sha})")
    return out


def round_v23_missing() -> list[str]:
    """Why round v2.3 is not open on this tree ([] = open): the owner's authority, then the round's selection."""
    out = ledger_seq13_problems()
    from validation.v2 import currency_dag, version_forward as vf
    if not hasattr(vf, "in_round"):
        out.append("validation/v2/version_forward.py has no in_round (round-v2.3 selection, W1-DESIGN §2.6, L1-F5)")
    if "round" not in inspect.signature(currency_dag.validate).parameters:
        out.append("validation/v2/currency_dag.py validate() takes no round (W1-DESIGN §2.6, L1-F5)")
    return out


def wired_sealing_gate(patch: bytes, root: pathlib.Path = ROOT) -> bytes:
    """v2.2.0's tests/v2/sealing_gate.py with `patch` applied (git apply in a repository of its own), LF."""
    with tempfile.TemporaryDirectory(prefix="aisef-seq13-wiring-") as t:
        t = pathlib.Path(t)
        (t / "tests/v2").mkdir(parents=True)
        (t / "tests/v2/sealing_gate.py").write_bytes(_git("show", f"{RP.V2_2_0}:tests/v2/sealing_gate.py", root=root))
        (t / "wiring.patch").write_bytes(_lf(patch))
        subprocess.run(["git", "init", "-q", str(t)], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(t), "apply", "wiring.patch"], capture_output=True, check=True)
        return _lf((t / "tests/v2/sealing_gate.py").read_bytes())


def p5_q0_guard_problems(A) -> list[str]:
    """Q0P-3: the P5-REVERIFICATION record round v2.3 selects (`A` = validation/qualification/p5_acceptance). Reused
    v2.2 history (A.V21_OUT_REL / A.V22_OUT_REL): its guards ran at v2.2, each exit 0, and Q0 is checked live in the same
    sealing job by Q0RoundV23 — that is the VERIFIED_REUSE justification. Re-derived in round v2.3: its recorded Q0
    guard MUST be the round-v2.3 Q0 (q0_round.CHECK_ARGV), never `validation/v2/checker_calibration.py --check`, which
    no v2.3 tree passes."""
    from validation.v2 import version_forward as vf
    try:
        path, rec = vf.resolve_upstream(ROOT, A.V21_OUT_REL, A.V22_OUT_REL)
    except LookupError as e:
        return [str(e)]
    if path in (A.V21_OUT_REL, A.V22_OUT_REL):
        return []
    want = "python -P " + " ".join(Q.CHECK_ARGV)
    got = ((rec.get("guards") or {}).get("checker_calibration") or {}).get("command")
    return [] if got == want else [f"{path}: its recorded Q0 guard is {got!r}, not the round-v2.3 Q0 {want!r}"]


@functools.lru_cache(maxsize=1)
def _dag_v23() -> dict:
    from validation.v2 import currency_dag
    return currency_dag.validate(ROOT, round="v2.3")


@functools.lru_cache(maxsize=1)
def _f5_states() -> dict:
    from validation.v23 import impact
    return {s.target: s for s in impact.classify(ROOT)}


def _p10_contracts():
    name = "aisef_v2_p10_contracts"      # the alias tests/v2/test_p5_plan_v22_proposal.py loads it under
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, ROOT / "validation/qualification/p10_contracts.py")
        sys.modules[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules[name])
    return sys.modules[name]


@round_gate
class RoundV23(unittest.TestCase):
    """One counterpart per replayed v2.2 test (replay_v22.COUNTERPART), the replay itself, and the in-tree companion."""

    @contextlib.contextmanager
    def round_v23(self, node: str | None):
        missing = round_v23_missing()
        if missing:
            self.fail("round v2.3 is not open: " + "; ".join(missing))
        from validation.v2 import version_forward as vf
        if node is not None:
            st = _dag_v23()["nodes"][node]
            self.assertIn(st.get("state"), OK, f"{node}: round-v2.3 state {st.get('state')}: {st.get('detail', '')}")
        with vf.in_round("v2.3"):
            yield

    def f5_problems(self, m, record: dict, phase: str) -> list[str]:
        """REBOUND m.problems_of: every legacy-rule problem but the whole-file source rule, which F5 replaces — each
        live entry of the record MUST be MEASURED or VERIFIED_REUSE in round v2.3."""
        out = [p for p in m.problems_of(record, ROOT, phase) if not p.endswith(STALE_SOURCE)]
        old = set(m.superseded(record, phase))
        states = _f5_states()
        for t in sorted({e["target"] for e in record["targets"] if e["target"] not in old}):
            s = states.get(t)
            if s is None or s.state not in OK:
                out.append(f"{t}: {'no F5 state' if s is None else f'{s.state} ({s.component}: {s.reason})'}")
        return out

    # ---- the history: the 11 v2.2 tests and the Q0 class themselves, byte-identical, at v2.2.0 ----------------
    def test_replay_v22(self):
        r = subprocess.run([sys.executable, "-P", str(ROOT / RP.TOOL)], capture_output=True, encoding="utf-8", cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stdout[-6000:] + r.stderr[-2000:])

    def test_v22_selection_over_the_committed_records_is_intact(self):
        from validation.v2 import currency_dag
        kernel = _git("rev-parse", f"{RP.V2_2_0}:aisef2").decode().strip()
        self.assertEqual(currency_dag.validate(ROOT, kernel_digest=kernel)["problems"], [])

    # ---- the counterparts (bodies verbatim from v2.2.0; see replay_v22.coverage) --------------------------------
    def test_PLAN(self):
        with self.round_v23("PLAN"):
            from validation.qualification import c2_plan_correction as pc
            self.b = pc.build()
            self.assertEqual(pc.check_v22(), [])
            self.assertEqual(pc.record_v22(self.b)["verdict"], "PLAN CORRECTION ADMITTED STATICALLY")
            self.assertEqual(pc.history_problems(), [])
            self.assertEqual(json.loads((ROOT / pc.OUT_REL).read_text(encoding="utf-8"))["verdict"], "PLAN CORRECTION ADMITTED STATICALLY")

    def test_K_NOWORK(self):
        with self.round_v23("K-NOWORK"):
            from validation.qualification import c2_k_nowork_001 as kn
            self.assertEqual(kn.check_v22(), [])
            self.assertIn("closure-evidence/v2/v2.1/PLAN-V2.2-CORRECTION-1.json", kn.BOUND)
            self.assertEqual(kn.history_problems(), [])

    def test_ORCH(self):
        with self.round_v23("ORCH"):
            from validation.qualification import c2_orchestration_repair as rp
            self.assertEqual(rp.release_differences_v22(), [])
            rec = json.loads((ROOT / rp.OUT_REL).read_text(encoding="utf-8"))
            eq = rec["single_probe_equivalence"]
            staged = eq["identical_but_the_adequacy_stage_of_a_fully_pre_satisfied_story"]
            self.assertEqual((eq["items"], eq["identical"], staged), (7, 6, ["pre-satisfied"]))
            self.assertTrue(all(v["outcomes_identical"] for v in eq["by_item"].values()))
            self.assertEqual(sorted(i for i, v in eq["by_item"].items() if not v["journal_identical_but_kernel_identity"]), staged)
            k = eq["by_item"]["pre-satisfied"]["k_presat_001"]
            self.assertEqual(k["removed_from_the_old_journal"], {"story/resource-acquired": 3, "tests/adequacy": 1,
                                                                 "story/resource-released": 3, "gate/check": 1})
            self.assertEqual(k["adequacy_stage_events_in_the_new_journal"], {})
            self.assertTrue(k["journal_identical_but_kernel_identity_and_the_adequacy_stage"])
            self.assertTrue(k["subprocesses_identical_but_the_tests_of_the_stage"] and k["other_observations_identical_but_subprocesses"])
            self.assertEqual((k["subprocesses"]["old"]["tests"], k["subprocesses"]["new"]["tests"]), (3, 0))
            old, new = rec["defect_reproducer"]["old"], rec["defect_reproducer"]["new"]
            self.assertEqual(old["raised"], "InvariantError: cycle 1 proves a story with exactly one probe factory")
            self.assertEqual((new["raised"], new["attempts"]), (None, ["COMMIT"]))

    def test_P10_COHORT(self):
        with self.round_v23("P10-COHORT"):
            from validation.qualification import c2_p10_cohort as B
            self.assertEqual(B.check_version_forward(), [])
            rec = json.loads((ROOT / B.OUT_REL).read_text(encoding="utf-8"))
            self.assertEqual((rec["verdict"], rec["census"]["cohort_count"], rec["census"]["cohort_records"]),
                             ("machinery qualified; cohort count = 0", 0, []))
            self.assertTrue(all(c["holds"] for c in rec["adversarial"]))
            broken = copy.deepcopy(rec)
            broken["adversarial"][0]["holds"] = False
            self.assertTrue(B.problems_of(broken))

    def test_P10_PROFILE(self):
        with self.round_v23("P10-PROFILE"):
            from validation.qualification import c2_p10_profile as B
            self.assertEqual(B.check_version_forward(), [])
            rec = json.loads((ROOT / B.OUT_REL).read_text(encoding="utf-8"))
            self.assertEqual((rec["verdict"], rec["live_provider_calls"]), ("attestation qualified", 0))
            self.assertEqual({c["id"]: c["grade"] for c in rec["classifications"] if c["id"].startswith("FIX-")}, {
                "FIX-FIXED": "ATTESTED", "FIX-COMBO": "OPAQUE", "FIX-ALIAS": "OPAQUE", "FIX-ROTATING": "OPAQUE",
                "FIX-UNLISTED": "OPAQUE", "FIX-UNMEASURED": "OPAQUE"})

    def test_P5_REVERIFICATION(self):
        with self.round_v23("P5-REVERIFICATION"):
            from validation.qualification import p5_acceptance as A
            self.assertEqual(A.history_problems(), [])
            self.assertEqual(A.reverification_v22_problems(), [])
            self.assertEqual(p5_q0_guard_problems(A), [])          # Q0P-3: round v2.3's own Q0 guard

    def test_P5_PROPOSAL_kernel_provenance(self):
        with self.round_v23("P5-PROPOSAL"):
            from validation.qualification import p5_acceptance as A
            self.assertEqual(A.check_v22_proposal(), [])
            self.assertEqual(A.proposal_history_problems(), [])

    def test_MUTATION_historical(self):
        with self.round_v23(None):
            from validation.v2 import mutation as m
            self.assertEqual({p: m.RECORDS.get(p) for p in V22_HISTORICAL}, V22_HISTORICAL)
            for phase, rel in m.RECORDS.items():
                if phase in V22_HISTORICAL and m.PHASE_TARGETS[phase]:
                    with self.subTest(phase):
                        record = json.loads((ROOT / rel).read_text(encoding="utf-8"))
                        self.assertFalse([t for t in record["targets"] if t.get("runner")])
                        self.assertEqual(self.f5_problems(m, record, phase), [])
            t = next(iter(m.V21_TARGETS))
            legacy = {"target": t, "kill_tests": m.V21_TARGETS[t], "source_sha256": "0", "mutants": 1, "killed": 1, "survivors": [],
                      "results": [{"mutant": "x", "killed": True}]}
            problems = m.problems_of({"targets": [legacy]}, ROOT, "V2.1")
            self.assertIn(f"{t}: measured by a runner that does not classify — re-measure", problems)

    def test_P5_PROPOSAL_P5_8(self):
        with self.round_v23("P5-PROPOSAL"):
            from validation.qualification import p5_acceptance as PA
            A = _p10_contracts()
            self.assertEqual(PA.proposal_history_problems(), [])
            self.assertEqual(PA.check_v22_proposal(), [])
            stale = {f"{rel} is not what the authoring aid derives from this tree" for rel in (A.OUT_REL, A.DOC_REL)}
            found = [p for p in A.check() if p not in stale]
            self.assertEqual(found, [])
            rec = json.loads((ROOT / A.OUT_REL).read_text(encoding="utf-8"))
            self.assertEqual(rec["approvals"]["given"], [])
            self.assertFalse(any(m["approved"] for m in rec["decision_3_mappings"]))

    def test_Q5(self):
        with self.round_v23("Q5"):
            from validation.qualification import v21_q5_compare
            self.M = v21_q5_compare
            self.assertEqual(self.M.check_v22(), [])

    def test_CONFORMANCE_RULING(self):
        with self.round_v23("CONFORMANCE-RULING"):
            from validation.qualification import v21_conformance_ruling as R
            self.assertEqual(R.check_version_forward(), [])
            self.assertTrue(R.tolerated(), f"{R.OUT_REL} is not committed as it is")


@round_gate
class Seq13Wiring(unittest.TestCase):
    """Red until the GATED_TEST_WIRING seq 13 would authorize (SEQ13_PATCH_REL) is applied, exactly."""

    def test_the_applied_wiring_is_exactly_the_reviewed_patch_and_its_pins_hold(self):
        patch = _lf((ROOT / SEQ13_PATCH_REL).read_bytes())
        self.assertIn(hashlib.sha256(patch).hexdigest(), reviewed_draft()["decision"]["GATED_TEST_WIRING"])
        self.assertEqual(_lf((ROOT / "tests/v2/sealing_gate.py").read_bytes()), wired_sealing_gate(patch),
                         "tests/v2/sealing_gate.py is not v2.2.0's plus the reviewed patch")
        self.assertTrue(getattr(sealing_gate, "V23_PINS_HOLD", False), "a V23_PINNED file is not as pinned")

    def test_V22_REPLAYED_is_the_replayed_set_and_each_is_gated(self):
        self.assertEqual(tuple(getattr(sealing_gate, "V22_REPLAYED", ())), RP.V22_REPLAYED)
        self.assertEqual(sorted(set(RP.V22_REPLAYED) - set(sealing_gate.GATED)), [])

    def test_each_replayed_test_is_skipped_at_head_naming_the_replay(self):
        for tid in RP.V22_REPLAYED:
            path, qual = tid.split("::")
            cls, meth = qual.split(".")
            mod = importlib.import_module(path[:-3].replace("/", "."))
            fn = getattr(getattr(mod, cls), meth)
            with self.subTest(tid):
                self.assertTrue(getattr(fn, "__unittest_skip__", False))
                self.assertIn("replayed at v2.2.0", getattr(fn, "__unittest_skip_why__", ""))


class Coverage(unittest.TestCase):
    """Always runs: the parity map is closed and loses no assertion (AST of each v2.2 test at v2.2.0)."""

    def test_every_v22_assertion_has_its_counterpart(self):
        doc = RP.coverage(ROOT)
        self.assertEqual(doc["gaps"], [])
        self.assertEqual([t["id"] for t in doc["tests"] if not t["byte_identical_at_head"]], [])
        self.assertGreater(doc["assertions"], 0)

    def test_the_counterpart_map_is_closed(self):
        self.assertEqual(set(RP.COUNTERPART), set(RP.V22_REPLAYED))
        self.assertEqual(len(RP.V22_REPLAYED), 11)
        mine = {n for n in vars(RoundV23) if n.startswith("test_")}
        self.assertEqual(mine - {c.split(".")[1] for _, c in RP.COUNTERPART.values()},
                         {"test_replay_v22", "test_v22_selection_over_the_committed_records_is_intact"})
        self.assertEqual(sorted(set(RP.V22_REPLAYED) - set(sealing_gate.GATED)), [])

    def test_a_dropped_assertion_is_a_gap(self):
        tid = RP.V22_REPLAYED[0]
        cqual = RP.COUNTERPART[tid][1]
        src = (ROOT / RP.COUNTERPARTS_REL).read_text(encoding="utf-8")
        fn = RP._method(src, cqual)
        kept = [a for _, a in RP.assertions(fn)]
        self.assertIn("self.assertEqual(pc.history_problems(), [])", kept)
        weakened = src.replace("            self.assertEqual(pc.history_problems(), [])\n", "", 1)
        self.assertNotIn("self.assertEqual(pc.history_problems(), [])", [a for _, a in RP.assertions(RP._method(weakened, cqual))])


    def test_the_round_gate_list_is_closed(self):
        found = set()
        for p in sorted((ROOT / "tests").rglob("test_*.py")):
            tree = ast.parse(p.read_text(encoding="utf-8"))
            rel = p.relative_to(ROOT).as_posix()
            for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
                for node, rid in [(cls, f"{rel}::{cls.name}")] + [(f, f"{rel}::{cls.name}.{f.name}") for f in cls.body
                                                                 if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                    names = {d.id if isinstance(d, ast.Name) else d.attr for d in node.decorator_list
                             if isinstance(d, (ast.Name, ast.Attribute))}
                    if "round_gate" in names:
                        found.add(rid)
                        self.assertNotIn("sealing", names, rid)
        self.assertEqual(sorted(found), sorted(V23_GATED))
        self.assertEqual(set(V23_GATED) & set(sealing_gate.GATED), set())


class LedgerHistory(unittest.TestCase):
    """Always runs: ledger entries 1-12 are v2.2.0's, byte for byte (CT-5); the agent never writes the ledger."""

    def test_entries_1_to_12_are_the_v2_2_0_entries(self):
        old = json.loads(_git("show", f"{RP.V2_2_0}:{LEDGER_REL}"))["entries"]
        now = json.loads((ROOT / LEDGER_REL).read_text(encoding="utf-8"))["entries"]
        self.assertEqual([e["seq"] for e in old], list(range(1, 13)))
        self.assertEqual(now[:12], old)
        self.assertTrue(all(e["seq"] > 12 for e in now[12:]))


if __name__ == "__main__":
    unittest.main()
