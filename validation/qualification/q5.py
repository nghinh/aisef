"""Q5 — real-execution reproduction (owner's "P9 / QP-9 EXECUTION AUTHORIZATION"; RFC §27; F1, F9).

    python -P validation/qualification/q5.py --record                # the corpus: every item executed for real once, its model stream recorded
    python -P validation/qualification/q5.py --calibrate             # §29: the harness rejects the seven named defects (scratch recordings, never the corpus)
    python -P validation/qualification/q5.py --freeze                # SUBJECT.json: the frozen subject, before the first reproduction
    python -P validation/qualification/q5.py --reproduce             # every corpus item reproduced: model stream replayed, everything else executed again
    python -P validation/qualification/q5.py --conformance start|end

What is replayed: the MODEL OUTPUT STREAM only — the developer capability's answer (the files it wrote and its commit
message, or its failure, or its outage) and the reviewer capability's answer (its findings, or its failure, outage or
inability), each bound to the request that produced it by a request hash over the normalized request (header class,
capability identity, story, criteria, attempt, the story's prior failures, the checkout's revision and tree or the
scope's files and contents, the criteria's semantic hashes, the plan hash, the adapter's schema, the execution profile).
A replayed answer is applied for real: the files are written into the real checkout and committed by real git; the
findings enter the real review stage. Nothing else comes from the recording: git, worktrees, scratch, the python_callable
probe (corrected digest), the developer-test runner, the scanner tool in its owned process range, the merge and the
post-merge re-proof all execute again and are compared with the recorded expectation afterwards. The recording is
expectation, never evidence: evidence is the current execution plus the comparison.

Cycle 2 (QP-2.8; CYCLE2-QUALIFICATION-PLAN §6): the same mechanism on the Cycle-2 candidate, the corpus extended with
items proved by each active Cycle-2 probe — a CLI-proved story (and its refuted-then-retried variant), a file-artifact
prohibition, a scenario-proved story and a bytes-returning python_callable — each story proved by the catalog's active
probe for its kind, re-executed at reproduction exactly like every other tool. The seven Cycle-1 items stay, proved by
the frozen Cycle-1 python_callable probe (a Cycle-1 compatibility item on the Cycle-2 kernel). A new adversarial case:
a file the probe observes changed on the trunk outside the model stream (the request unchanged) is a diff.

V2.0 release (charter S5, "Q5 fresh/reproduction"): once the RC1 freeze record exists, the subject is the RC
(common.candidate()), the records go to closure-evidence/v2/release/Q5-RC1 and the differential below is Q4-RC1's.

Determinism is normalization after observation: the run's clock is the real clock and event times are dropped; temp
roots become tokens. Nothing semantic is normalized (control outcomes, owners, retryability, revisions, semantic hashes,
probe digests, request content, tool exit status, report content, file contents, test verdicts, the workspace diff).
The fixture pins the commit metadata git puts into a commit (author, e-mail, dates) so that a real commit of the same
tree has the same SHA — the revision identity is compared literally, never normalized.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import pathlib
import platform
import shutil
import socket
import sys
import tempfile
import traceback
from dataclasses import dataclass, field

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.qualification import common as C  # noqa: E402

#: the subject and its output directory are common.candidate()'s: Cycle 2's final integration candidate (cycle2/Q5-FINAL;
#: the QP-2.8 run on the QP-2.6 candidate stays in cycle2/Q5), or in V2.0 release mode the frozen RC1 (release/Q5-RC1)
OUT_REL = C.Q5_OUT_REL
CYCLE1_OUT_REL = "closure-evidence/v2/Q5"
SEMANTIC_CANDIDATE = C.SEMANTIC_CANDIDATE
KERNEL_TREE = C.KERNEL_TREE
PROBE_DIGEST = "1961e84d913edc687bdb52f6c6cd0f034e86f2d1dadd9e89fa76757a51dc35bf"   # the Cycle-1 probe (P7-FINDING-001 correction), frozen
HISTORICAL_PROBE_DIGEST = "ac434a42"
#: the fixture's commit metadata, pinned so a real commit of the same tree has the same SHA (author and e-mail are pinned
#: by aisef2.orchestrate.workspace.commit_all); the harness's own clock is not touched
GIT_DATES = {"GIT_AUTHOR_DATE": "2026-09-28T00:00:00Z", "GIT_COMMITTER_DATE": "2026-09-28T00:00:00Z"}
HARNESS_FILES = ("validation/qualification/q5.py", "validation/qualification/q5_run.sh")
FIXTURE_FILES = ("tests/v2/test_p6_orchestration.py", "tests/v2/p4/test_run_scope.py", "tests/v2/p4/world.py")
F1_FILES = ("aisef2/arch/enums.py", "aisef2/journal/event.py", "aisef2/journal/format2.py", "aisef2/journal/format3.py")
F9_FILES = ("aisef2/runtime/capability.py", "aisef2/runtime/runspec.py", "aisef2/product/contract.py", "aisef2/probe/protocol.py")

# ------------------------------------------------------------------------------------------- the preregistered model

#: request-header classes (§7): stable fields enter the request hash; normalized fields are locators dropped before
#: hashing; permitted drift fields: none in cycle 1 — the bound is 0 normalized differences per request
HEADER_CLASSES = {
    "DEVELOPER_IMPLEMENT": {
        "capability": "developer", "adapter": "aisef2.orchestrate.adapters.Developer.implement",
        "stable": ["header_class", "capability", "story_id", "criteria", "attempt", "prior_failures", "parent", "tree",
                   "semantic_hashes", "plan_hash", "tool_schema", "execution_profile", "route_class"],
        "normalized": ["checkout path (an execution locator; never hashed)"], "drift_fields": [], "drift_bound": 0},
    "REVIEWER_REVIEW": {
        "capability": "reviewer", "adapter": "aisef2.orchestrate.adapters.Reviewer.review",
        "stable": ["header_class", "capability", "story_id", "criteria", "attempt", "prior_failures", "parent", "files",
                   "content", "semantic_hashes", "plan_hash", "tool_schema", "execution_profile", "route_class"],
        "normalized": ["scope root (an execution locator; never hashed)"], "drift_fields": [], "drift_bound": 0},
}
ROUTE_CLASS = "MODEL_STREAM"   # the provider route class: the stream, recorded or replayed, never a live route
NORMALIZATION = {
    "dropped": ["event.time (the real clock, recorded and dropped after observation)"],
    "tokens": {"<TMP>": "the item's temporary root", "<PY>": "the interpreter path", "<SCRIPT>": "the scanner script path",
               "<REPORT>": "the scanner's report path (under the story's scratch)"},
    "applied_to": ["event.data.detail (text) and tool argv"],
    "never": ["control outcomes", "owner", "retryable", "revisions", "semantic_hash", "probe digest", "request content",
              "tool exit status", "report content", "file contents", "test verdicts", "workspace diff", "capability identity",
              "runspec_hash", "plan_hash"],
}
ERROR_KINDS = ("replay_request_mismatch", "assert_consumed_failure", "tool_diff", "subprocess_diff", "workspace_diff",
               "probe_product_diff", "control_diff", "capability_mismatch", "harness_error", "invariant_violation", "exception",
               "residual_process")
#: journal event types by the typed difference they belong to (§28)
_EVENT_KIND = {"tool/invoked": "tool_diff", "tool/result": "tool_diff", "tests/adequacy": "subprocess_diff",
               "probe/evaluated": "probe_product_diff", "proof/verified": "probe_product_diff",
               "capability/resolved": "capability_mismatch", "run/spec-resolved": "capability_mismatch"}

# ------------------------------------------------------------------------------------------------------- the corpus

CALC = "def sub(a, b):\n    return a - b\n"
ADD = "\n\ndef add(a, b):\n    return a + b\n"
ADD_WRONG = "\n\ndef add(a, b):\n    return a + b + 1\n"
MUL = "def mul(a, b):\n    return a * b\n"
SUB_BROKEN = "def sub(a, b):\n    return a + b\n"
TEST_ADD = ("import unittest\nfrom app import calc\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n"
            "        self.assertEqual(calc.add(1, 2), 3)\n")
TEST_MUL = "import unittest\nfrom app import mul\n\n\nclass T(unittest.TestCase):\n    def test_mul(self):\n        self.assertEqual(mul.mul(2, 3), 6)\n"
CONTRACTS = {"C1": ("app.calc:add", [1, 2], 3), "C2": ("app.mul:mul", [2, 3], 6), "C0": ("app.calc:sub", [3, 1], 2)}
S1_FILES = {"app/calc.py": CALC + ADD, "tests/test_s1.py": TEST_ADD}


def completed(files: dict, message: str) -> dict:
    return {"kind": "COMPLETED", "files": dict(files), "message": message, "detail": f"implemented {len(files)} files"}


def reviewed(findings=(), detail="reviewed") -> dict:
    return {"kind": "COMPLETED", "findings": [list(f) for f in findings], "detail": detail}


@dataclass(frozen=True)
class Story:
    id: str
    obligations: tuple[tuple[str, str], ...]     # (criterion id, role)
    tests: tuple[str, ...] = ("tests/test_s1.py",)
    regressions: tuple[str, ...] = ("tests/test_other.py",)
    tests_block: bool = True


@dataclass(frozen=True)
class Item:
    id: str
    covers: tuple[str, ...]
    stories: tuple[Story, ...]
    developer: tuple[dict, ...]                  # the model stream, in request order
    reviewer: tuple[dict, ...]
    pre_landed: dict = field(default_factory=dict)
    scanner_findings: tuple[tuple[str, bool, tuple[str, ...]], ...] = ()
    limits: dict = field(default_factory=dict)   # owner name -> retries (default 1 each)
    expected_outcomes: dict = field(default_factory=dict)
    kind: str | None = None                       # Cycle 2: the subject kind every story of the item is proved with (KIND_CONTRACTS)


#: Cycle 2: cid -> (subject kind, locator, stimulus, observable, subject absence), each proved by the catalog's active probe
KIND_CONTRACTS = {
    "C3": ("cli_invocation", "app:__main__", {"argv": ["2", "3"]}, {"exit_code": 5}, "REQUIRES_SUBJECT"),
    "C4": ("file_artifact", "path:app", {"grep": r"\bsocket\b", "suffixes": [".py"]}, {"matches": 0}, "ABSENCE_IS_DECIDABLE"),
    "C5": ("process_effect", "app.counter:Counter", {"scenario": [{"step": "construct", "args": [], "kwargs": {}},
                                                                  {"step": "call", "method": "incr", "args": [], "kwargs": {}},
                                                                  {"step": "call", "method": "incr", "args": [], "kwargs": {}}]},
           {"returns": 2}, "REQUIRES_SUBJECT"),
    "C6": ("python_callable", "app.codec:encode", {"args": ["ab"]}, {"returns_bytes_hex": "6162"}, "REQUIRES_SUBJECT"),
}
CLI_MAIN = "import sys\n\nsys.exit(int(sys.argv[1]) + int(sys.argv[2]))\n"
CLI_MAIN_WRONG = "import sys\n\nsys.exit(int(sys.argv[1]) + int(sys.argv[2]) + 1)\n"
NET_SOCKET = "import socket\n\n\ndef ping():\n    return socket.gethostname()\n"
NET_PLAIN = "def ping():\n    return 'offline'\n"
COUNTER = "class Counter:\n    def __init__(self):\n        self.n = 0\n\n    def incr(self):\n        self.n += 1\n        return self.n\n"
CODEC = "def encode(text):\n    return text.encode('utf-8')\n"
TEST_C2 = ("import unittest\n\n\nclass T(unittest.TestCase):\n    def test_package(self):\n        import app\n"
           "        self.assertTrue(app.__name__)\n")

CORPUS: tuple[Item, ...] = (
    Item("normal-completion", ("normal story completion", "developer tool execution", "candidate proof", "independent verification",
                               "review path", "security path", "merge path", "post-merge path"),
         (Story("S1", (("C1", "INTRODUCE"),)),), (completed(S1_FILES, "S1: C1"),), (reviewed(),), expected_outcomes={"S1": ["COMMIT"]}),
    Item("retry-then-commit", ("retry path", "candidate proof refuted", "developer budget"),
         (Story("S1", (("C1", "INTRODUCE"),)),),
         (completed({"app/calc.py": CALC + ADD_WRONG, "tests/test_s1.py": TEST_ADD}, "S1: C1"), completed(S1_FILES, "S1: C1")),
         (reviewed(),), expected_outcomes={"S1": ["RETRY", "COMMIT"]}),
    Item("review-finding-rollback", ("review path", "retry path", "rollback path", "review budget"),
         (Story("S1", (("C1", "INTRODUCE"),)),), (completed(S1_FILES, "S1: C1"), completed(S1_FILES, "S1: C1")),
         (reviewed([("sql-injection", True, ["scanner:bandit", "human:owner"])], "reviewed: one corroborated finding"),) * 2,
         expected_outcomes={"S1": ["RETRY", "ROLLBACK"]}),
    Item("pre-satisfied", ("PRE_SATISFIED / no developer call", "candidate proof", "review path", "security path"),
         (Story("S1", (("C1", "INTRODUCE"),), tests_block=False),), (), (reviewed(),), pre_landed=dict(S1_FILES),
         expected_outcomes={"S1": ["COMMIT"]}),
    Item("security-finding-rollback", ("security path", "tool execution", "retry path", "rollback path", "security budget"),
         (Story("S1", (("C1", "INTRODUCE"),)),), (completed(S1_FILES, "S1: C1"),) * 2, (reviewed(),) * 2,
         scanner_findings=(("hardcoded-secret", True, ("scanner:scan",)),), expected_outcomes={"S1": ["RETRY", "ROLLBACK"]}),
    Item("developer-outage-rollback", ("provider failure", "retry path", "rollback path"),
         (Story("S1", (("C1", "INTRODUCE"),)),), ({"kind": "OUTAGE", "detail": "503 from the developer capability"},) * 2, (),
         expected_outcomes={"S1": ["RETRY", "ROLLBACK"]}),
    Item("post-merge-regression", ("merge path", "post-merge path", "PRESERVE re-proof", "rollback path", "two stories"),
         (Story("S0", (("C1", "INTRODUCE"), ("C0", "PRESERVE"))),
          Story("S2", (("C2", "INTRODUCE"),), tests=("tests/test_s2.py",), tests_block=False)),
         (completed(S1_FILES, "S0: C1"), completed({"app/mul.py": MUL, "tests/test_s2.py": TEST_MUL, "app/calc.py": SUB_BROKEN}, "S2: C2")),
         (reviewed(), reviewed()), expected_outcomes={"S0": ["COMMIT"], "S2": ["ROLLBACK"]}),
    # Cycle 2: one item per active Cycle-2 probe, and a refuted-then-retried one
    Item("cli-proved-story", ("probe.cli_invocation", "candidate proof", "independent verification", "review path", "security path",
                              "merge path", "post-merge path"),
         (Story("S1", (("C3", "INTRODUCE"),), tests_block=False),), (completed({"app/__main__.py": CLI_MAIN, "tests/test_s1.py": TEST_C2}, "S1: C3"),),
         (reviewed(),), expected_outcomes={"S1": ["COMMIT"]}, kind="cli_invocation"),
    Item("cli-refuted-then-commit", ("probe.cli_invocation", "candidate proof refuted", "retry path", "developer budget"),
         (Story("S1", (("C3", "INTRODUCE"),), tests_block=False),),
         (completed({"app/__main__.py": CLI_MAIN_WRONG, "tests/test_s1.py": TEST_C2}, "S1: C3"),
          completed({"app/__main__.py": CLI_MAIN, "tests/test_s1.py": TEST_C2}, "S1: C3")),
         (reviewed(),), expected_outcomes={"S1": ["RETRY", "COMMIT"]}, kind="cli_invocation"),
    Item("file-artifact-prohibition", ("probe.file_artifact", "prohibition (grep_count 0)", "candidate proof", "merge path", "post-merge path"),
         (Story("S1", (("C4", "INTRODUCE"),), tests_block=False),), (completed({"app/net.py": NET_PLAIN, "tests/test_s1.py": TEST_C2}, "S1: C4"),),
         (reviewed(),), pre_landed={"app/net.py": NET_SOCKET}, expected_outcomes={"S1": ["COMMIT"]}, kind="file_artifact"),
    Item("scenario-proved-story", ("probe.process_effect", "scenario (construct, call, call)", "candidate proof", "post-merge path"),
         (Story("S1", (("C5", "INTRODUCE"),), tests_block=False),), (completed({"app/counter.py": COUNTER, "tests/test_s1.py": TEST_C2}, "S1: C5"),),
         (reviewed(),), expected_outcomes={"S1": ["COMMIT"]}, kind="process_effect"),
    Item("bytes-returning-python-callable", ("probe.python_callable_v2", "returns_bytes_hex", "candidate proof", "post-merge path"),
         (Story("S1", (("C6", "INTRODUCE"),), tests_block=False),), (completed({"app/codec.py": CODEC, "tests/test_s1.py": TEST_C2}, "S1: C6"),),
         (reviewed(),), expected_outcomes={"S1": ["COMMIT"]}, kind="python_callable"),
)
#: the trunk change of the `changed_probe_fixture` variant: a file the file-artifact probe observes, landed on the trunk
#: after the developer's (replayed) answer and before the merge — the model stream never saw it, the requests are unchanged
TRUNK_FIXTURE_CHANGE = {"app/extra.py": "import socket\n"}


def kind_contract(cid: str) -> tuple:
    """A Cycle-2 corpus contract, compiled against the catalog's active probe for its kind (the approval is the fixture's)."""
    from aisef2.arch.enums import Polarity, SubjectAbsence, SubjectKind
    from aisef2.probe import catalog
    from aisef2.product.approval import ContractApproval, Requirement
    from aisef2.product.compiler import ProbeRef, compile_spec
    from aisef2.product.contract import BehaviorContract, Subject
    kind, locator, stimulus, observable, absence = KIND_CONTRACTS[cid]
    req = Requirement.create(id=f"R-{cid}", text=f"requirement {cid}", source="q5")
    c = BehaviorContract.create(id=f"BC-{cid}", requirement_ids=(req.id,), subject=Subject(SubjectKind(kind), locator), stimulus=stimulus,
                                observable={**observable, "within_s": 30}, polarity=Polarity.MUST_HOLD,
                                subject_absence=SubjectAbsence[absence], rationale=f"rationale {cid}")
    approval = ContractApproval(req.id, req.requirement_hash, c.id, c.contract_hash, "human:owner", 1.0, ())
    refs = {k: ProbeRef(e.probe_id, e.probe_digest) for k, e in catalog.active().items()}
    return c, compile_spec(c, requirements={req.id: req}, approvals=[approval], probes=refs)


class _LandsAfter:
    """The `changed_probe_fixture` variant: the developer answers from the stream as always; after its answer is applied,
    a file the probe observes is landed on the trunk by somebody else (never in any request)."""

    def __init__(self, dev, repo: str, files: dict) -> None:
        self.dev, self.repo, self.files, self.landed = dev, repo, files, 0

    def implement(self, story_id: str, criteria: tuple[str, ...], checkout: str):
        from tests.v2 import test_p6_orchestration as T
        out = self.dev.implement(story_id, criteria, checkout)
        if not self.landed:
            T.land(self.repo, self.files, "a change on the trunk the model stream never saw")
            self.landed += 1
        return out


# -------------------------------------------------------------------------------------------- typed replay refusals

class ReplayMismatch(Exception):
    """A live model request the recorded stream does not answer at this point: typed by `kind` — REQUEST_HASH_MISMATCH,
    MISSING_REPLAY_ITEM, EXTRA_MODEL_CALL, REORDERED_REQUEST. Never bound by call count; never answered silently."""

    def __init__(self, kind: str, detail: str, request: dict) -> None:
        super().__init__(f"{kind}: {detail}")
        self.kind, self.detail, self.request = kind, detail, request


class DuplicateConsumption(Exception):
    """A replay item consumed twice: refused (§9)."""


def _sha(text: str | bytes) -> str:
    return hashlib.sha256(text if isinstance(text, bytes) else text.encode("utf-8")).hexdigest()


def request_hash(identity: dict) -> str:
    from aisef2.product.contract import canonical
    return _sha(canonical(identity))


class ModelStream:
    """The model output stream: recorded (from a script of answers) or replayed (from a ledger). Every request is
    identified by its hash; a replay binds the NEXT unconsumed item only if its hash equals the request's — otherwise
    the mismatch is typed and raised (§5, §9)."""

    def __init__(self, mode: str, *, script: dict[str, list[dict]] | None = None, ledger: list[dict] | None = None) -> None:
        self.mode = mode
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.ledger = [dict(x) for x in (ledger or [])]
        self.cursor = 0
        self.consumed: list[int] = []
        self.requests: list[dict] = []          # every live request, in order, with its hash and what it bound
        self.mismatches: list[dict] = []

    def answer(self, header_class: str, identity: dict) -> dict:
        h = request_hash(identity)
        seq = len(self.requests) + 1
        entry = {"seq": seq, "header_class": header_class, "request_hash": h}
        if self.mode == "record":
            queue = self.script.get(header_class) or []
            if not queue:
                self.requests.append({**entry, "matched": None})
                raise ReplayMismatch("EXTRA_MODEL_CALL", f"the script has no {header_class} answer for request {seq}", identity)
            response = queue.pop(0)
            self.ledger.append({"seq": seq, "header_class": header_class, "request_hash": h, "request": identity, "response": response})
            self.requests.append({**entry, "matched": seq})
            return response
        expected = self.ledger[self.cursor] if self.cursor < len(self.ledger) else None
        if expected is None:
            self.requests.append({**entry, "matched": None})
            m = {"kind": "EXTRA_MODEL_CALL", "seq": seq, "request_hash": h, "detail": "every recorded item is consumed; the live run asked once more"}
            self.mismatches.append(m)
            raise ReplayMismatch(m["kind"], m["detail"], identity)
        if expected["request_hash"] != h or expected["header_class"] != header_class:
            later = [x["seq"] for x in self.ledger[self.cursor + 1:] if x["request_hash"] == h and x["header_class"] == header_class]
            earlier = [x["seq"] for x in self.ledger[:self.cursor] if x["request_hash"] == h and x["header_class"] == header_class]
            # typed: the live hash recorded elsewhere -> the order changed; the next item is another kind of call -> an item
            # is missing (or the run diverged structurally); the same kind of call with another hash -> the request changed
            kind = "REORDERED_REQUEST" if later or earlier else ("MISSING_REPLAY_ITEM" if expected["header_class"] != header_class else "REQUEST_HASH_MISMATCH")
            drift = self._drift(expected["request"], identity)
            self.requests.append({**entry, "matched": None, "expected_seq": expected["seq"], "expected_hash": expected["request_hash"]})
            m = {"kind": kind, "seq": seq, "request_hash": h, "expected_seq": expected["seq"], "expected_hash": expected["request_hash"],
                 "expected_header_class": expected["header_class"], "live_header_class": header_class, "differing_fields": drift,
                 "detail": f"request {seq} ({header_class}) hashes {h[:12]}; the next recorded item {expected['seq']} ({expected['header_class']}) "
                           f"hashes {expected['request_hash'][:12]}; differing fields {drift}"}
            self.mismatches.append(m)
            raise ReplayMismatch(kind, m["detail"], identity)
        self.consume(expected["seq"])
        self.cursor += 1
        self.requests.append({**entry, "matched": expected["seq"], "replay_item_digest": _item_digest(expected), "drift": 0})
        return expected["response"]

    @staticmethod
    def _drift(recorded: dict, live: dict) -> list[str]:
        return sorted(k for k in set(recorded) | set(live) if recorded.get(k) != live.get(k))

    def consume(self, seq: int) -> None:
        if seq in self.consumed:
            raise DuplicateConsumption(f"replay item {seq} was already consumed")
        self.consumed.append(seq)

    def assert_consumed(self) -> dict:
        """§9: every expected item consumed exactly once, no unexpected request, no item left unused. While recording,
        the expectation is the script: every scripted answer given, none left over, no request beyond it."""
        extra = [r["seq"] for r in self.requests if r["matched"] is None]
        if self.mode == "record":
            leftover = [f"script:{k}#{i + 1}" for k, q in self.script.items() for i in range(len(q))]
            ok = not leftover and not extra
            return {"expected": len(self.ledger) + len(leftover), "consumed": len(self.ledger), "missing_unconsumed": leftover, "extra_requests": extra,
                    "duplicate_consumptions": 0, "mismatches": 0, "ok": ok}
        expected = [x["seq"] for x in self.ledger]
        unconsumed = [s for s in expected if s not in self.consumed]
        dup = len(self.consumed) - len(set(self.consumed))
        ok = not unconsumed and not extra and dup == 0 and len(self.consumed) == len(expected) and not self.mismatches
        return {"expected": len(expected), "consumed": len(self.consumed), "missing_unconsumed": unconsumed, "extra_requests": extra,
                "duplicate_consumptions": dup, "mismatches": len(self.mismatches), "ok": ok}


def _item_digest(item: dict) -> str:
    from aisef2.product.contract import canonical
    return _sha(canonical({k: item[k] for k in ("seq", "header_class", "request_hash", "request", "response")}))


def ledger_digest(ledger: list[dict]) -> str:
    return _sha("\n".join(_item_digest(x) for x in ledger))


# ------------------------------------------------------------------------------------------- the adapters (real side)

def _story_context(run, story_id: str) -> tuple[int, list[str]]:
    from aisef2.arch.enums import ControlProjection as P
    st = run.state(P.STORY_STATE).get(story_id) or {}
    failures = [e.data["code"] for e in run.events if e.type == "failure/observed" and e.data.get("story_id") == story_id]
    return st.get("attempt", 0), failures


def _plan_hash(run) -> str | None:
    return next((e.data["plan_hash"] for e in run.events if e.type == "plan/frozen"), None)


def _tool_schema(protocol, method: str) -> str:
    import inspect
    return _sha(f"{protocol.__module__}.{protocol.__qualname__}.{method}{inspect.signature(getattr(protocol, method))}")


def _dir_content_digest(root: pathlib.Path) -> tuple[list[str], str]:
    files = sorted(str(p.relative_to(root)).replace(os.sep, "/") for p in root.rglob("*") if p.is_file() and ".git" not in p.parts)
    h = hashlib.sha256()
    for rel in files:
        h.update(rel.encode()); h.update(b"\0"); h.update(_sha((root / rel).read_bytes()).encode()); h.update(b"\n")
    return files, h.hexdigest()


class StreamDeveloper:
    """The developer capability as a model stream: the request identified and hashed, the answer taken from the
    stream (recorded or replayed) and APPLIED FOR REAL — files written into the real checkout, committed by real git."""

    def __init__(self, run, stream: ModelStream, *, capability: dict, semantic_hashes: dict, profile: dict) -> None:
        self.run, self.stream, self.capability, self.semantic_hashes, self.profile = run, stream, capability, semantic_hashes, profile

    def identity(self, story_id: str, criteria: tuple[str, ...], checkout: str) -> dict:
        from aisef2.orchestrate.adapters import Developer
        from aisef2.orchestrate.workspace import git
        attempt, prior = _story_context(self.run, story_id)
        return {"header_class": "DEVELOPER_IMPLEMENT", "capability": self.capability, "story_id": story_id, "criteria": list(criteria),
                "attempt": attempt, "prior_failures": prior, "parent": git(checkout, "rev-parse", "HEAD").stdout.strip(),
                "tree": git(checkout, "rev-parse", "HEAD^{tree}").stdout.strip(),
                "semantic_hashes": {c: self.semantic_hashes[c] for c in criteria}, "plan_hash": _plan_hash(self.run),
                "tool_schema": _tool_schema(Developer, "implement"), "execution_profile": self.profile, "route_class": ROUTE_CLASS}

    def implement(self, story_id: str, criteria: tuple[str, ...], checkout: str):
        from aisef2.journal.format2 import OperationOutcome as O
        from aisef2.orchestrate.adapters import Implemented, ProviderOutage
        from aisef2.orchestrate.workspace import commit_all
        response = self.stream.answer("DEVELOPER_IMPLEMENT", self.identity(story_id, criteria, checkout))
        if response["kind"] == "OUTAGE":
            raise ProviderOutage(response["detail"])
        if response["kind"] == "FAILED":
            return Implemented(O.FAILED, None, response["detail"])
        for rel, text in response["files"].items():
            p = pathlib.Path(checkout, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        sha = commit_all(checkout, response["message"])       # real git: the candidate's SHA is computed now, never replayed
        return Implemented(O.COMPLETED, sha, response["detail"])


class StreamReviewer:
    def __init__(self, run, stream: ModelStream, *, capability: dict, semantic_hashes: dict, profile: dict) -> None:
        self.run, self.stream, self.capability, self.semantic_hashes, self.profile = run, stream, capability, semantic_hashes, profile

    def identity(self, scope, criteria: tuple[str, ...]) -> dict:
        from aisef2.orchestrate.adapters import Reviewer
        from aisef2.orchestrate.workspace import git
        attempt, prior = _story_context(self.run, scope.story_id)
        files, content = _dir_content_digest(pathlib.Path(scope.root))
        return {"header_class": "REVIEWER_REVIEW", "capability": self.capability, "story_id": scope.story_id, "criteria": list(criteria),
                "attempt": attempt, "prior_failures": prior, "parent": git(scope.root, "rev-parse", "HEAD").stdout.strip(), "files": files,
                "content": content, "semantic_hashes": {c: self.semantic_hashes[c] for c in criteria}, "plan_hash": _plan_hash(self.run),
                "tool_schema": _tool_schema(Reviewer, "review"), "execution_profile": self.profile, "route_class": ROUTE_CLASS}

    def review(self, scope, criteria: tuple[str, ...]):
        from aisef2.journal.format2 import OperationOutcome as O
        from aisef2.orchestrate.adapters import CapabilityUnrunnable, Finding, ProviderOutage, Reviewed
        response = self.stream.answer("REVIEWER_REVIEW", self.identity(scope, criteria))
        if response["kind"] == "OUTAGE":
            raise ProviderOutage(response["detail"])
        if response["kind"] == "UNRUNNABLE":
            raise CapabilityUnrunnable(response["detail"])
        if response["kind"] == "FAILED":
            return Reviewed(O.FAILED, (), response["detail"])
        return Reviewed(O.COMPLETED, tuple(Finding(i, b, tuple(c)) for i, b, c in response["findings"]), response["detail"])


class ObservedScanner:
    """The real scanner tool (a script run by the kernel in its owned process range), observed: its argv, and after it
    ran, its exit status and the report it produced — the tool ledger's observed side. Nothing is answered from a record."""

    name = "scan"

    def __init__(self, script: str, findings, *, interpreter: str, tokens: dict) -> None:
        self.script, self.findings, self.interpreter, self.tokens = script, tuple(findings), interpreter, tokens
        self.calls: list[dict] = []

    def argv(self, scope, report: str) -> tuple[str, ...]:
        payload = json.dumps([[i, b, list(c)] for i, b, c in self.findings])
        argv = (self.interpreter, self.script, report, payload)
        files, content = _dir_content_digest(pathlib.Path(scope.root))
        self.calls.append({"tool": self.name, "story_id": scope.story_id, "argv": [tokenize(a, {**self.tokens, report: "<REPORT>"}) for a in argv],
                           "scope_files": files, "scope_content": content, "script_sha256": _sha(pathlib.Path(self.script).read_bytes()),
                           "input_digest": _sha(json.dumps([tokenize(a, {**self.tokens, report: "<REPORT>"}) for a in argv]) + content),
                           "exit_code": None, "report_sha256": None, "report_bytes": None, "executed": None})
        return argv

    def read(self, report: str, exit_code):
        from aisef2.orchestrate.adapters import Finding, Scanned
        p = pathlib.Path(report)
        data = p.read_bytes() if p.exists() else b""
        call = self.calls[-1]
        call.update(exit_code=exit_code, report_sha256=_sha(data), report_bytes=len(data), executed=bool(data.strip()))
        if not data.strip():
            return Scanned(False, ())
        rows = json.loads(data.decode("utf-8"))
        return Scanned(True, tuple(Finding(i, b, tuple(c)) for i, b, c in rows))


SCAN_SCRIPT = "import json, sys\nopen(sys.argv[1], 'w').write(sys.argv[2])\n"
#: calibration variants of the scanner (§11, §29): a changed behaviour, a changed exit status
SCAN_SCRIPT_CHANGED = "import json, sys\nopen(sys.argv[1], 'w').write(json.dumps([['injected', True, ['scanner:scan']]]))\n"   # reports a finding whatever it is asked
SCAN_SCRIPT_EXIT = "import json, sys\nopen(sys.argv[1], 'w').write(sys.argv[2])\nsys.exit(3)\n"


def tokenize(text, tokens: dict) -> str:
    if not isinstance(text, str):
        return text
    for raw, tok in sorted(tokens.items(), key=lambda kv: -len(kv[0])):
        if raw:
            text = text.replace(raw, tok)
    return text


# --------------------------------------------------------------------------------------------------- normalization

def normalize_event(e: dict, tokens: dict) -> dict:
    """The preregistered normalization: `time` dropped; path tokens in text fields. Nothing else."""
    data = json.loads(json.dumps(e["data"]))
    for key in ("detail", "reason"):
        if isinstance(data.get(key), str):
            data[key] = tokenize(data[key], tokens)
    if isinstance(data.get("record"), dict) and isinstance(data["record"].get("result"), dict):
        r = data["record"]["result"]
        for key in ("detail", "reason"):
            if isinstance(r.get(key), str):
                r[key] = tokenize(r[key], tokens)
    return {"seq": e["seq"], "type": e["type"], "data": data, "source_seqs": list(e["source_seqs"])}


def compare_journals(expected: list[dict], observed: list[dict]) -> list[dict]:
    """Every differing position, typed by the event's kind (§28); a length difference is reported at its first index."""
    out = []
    for i in range(max(len(expected), len(observed))):
        a, b = expected[i] if i < len(expected) else None, observed[i] if i < len(observed) else None
        if a != b:
            kind = _EVENT_KIND.get((a or b)["type"], "control_diff")
            out.append({"index": i, "kind": kind, "expected": a, "observed": b})
    return out


# ------------------------------------------------------------------------------------------------ workspace identity

def workspace_identity(repo: str, ws_root: pathlib.Path, branch: str = "main") -> dict:
    from aisef2.orchestrate.workspace import git
    tip = git(repo, "rev-parse", branch).stdout.strip()
    tree = git(repo, "rev-parse", f"{tip}^{{tree}}").stdout.strip()
    rows = [ln.split() for ln in git(repo, "ls-tree", "-r", tip).stdout.splitlines() if ln.strip()]
    files = {r[3] if len(r) == 4 else " ".join(r[3:]): {"mode": r[0], "blob": r[2]} for r in rows}
    status = git(repo, "status", "--porcelain").stdout.strip()
    worktrees = [ln for ln in git(repo, "worktree", "list", "--porcelain").stdout.splitlines() if ln.startswith("worktree ")]
    return {"branch": branch, "tip": tip, "tree": tree, "files": files, "status": status,
            "status_note": "git status of the fixture repository's own checkout against its index (the branch moves by update-ref; the checkout stays at the base)",
            "worktrees": len(worktrees),
            "ws_entries": sorted(p.name for p in ws_root.iterdir()) if ws_root.exists() else [],
            "digest": _sha(json.dumps({"tip": tip, "tree": tree, "files": files, "status": status}, sort_keys=True))}


def compare_workspaces(expected: dict, observed: dict) -> list[str]:
    out = []
    for key in ("tip", "tree", "status", "worktrees", "ws_entries"):
        if expected.get(key) != observed.get(key):
            out.append(f"{key}: expected {expected.get(key)!r}, observed {observed.get(key)!r}")
    for rel in sorted(set(expected["files"]) | set(observed["files"])):
        if expected["files"].get(rel) != observed["files"].get(rel):
            out.append(f"file {rel}: expected {expected['files'].get(rel)}, observed {observed['files'].get(rel)}")
    return out


# ------------------------------------------------------------------------------------------------ capability identity

def interpreter_identity() -> dict:
    return {"path_token": "<PY>", "sha256": _sha(pathlib.Path(sys.executable).read_bytes()), "version": platform.python_version(),
            "implementation": platform.python_implementation()}


def git_identity() -> dict:
    from aisef2.orchestrate.workspace import git
    exe = shutil.which("git")
    return {"sha256": _sha(pathlib.Path(exe).read_bytes()) if exe else None, "version": git(ROOT, "--version").stdout.strip()}


def kernel_digest() -> str:
    from validation.qualification import q4
    return q4._over(q4._file_digests(("aisef2",)))


def capabilities(item: Item, scan_script: str):
    """The RunSpec's capability identities (F9): every one VERIFIED by a digest computed here — the kernel's sources,
    the interpreter binary, git, the scanner script, and the two model capabilities by the digest of their answer
    stream (the recorded stream IS the capability that answers; a stream that differs is another capability)."""
    from aisef2.arch.enums import Enforcement
    from aisef2.product.contract import canonical
    from aisef2.runtime.capability import verified
    exe = shutil.which("git")
    return [verified("kernel", kernel_digest().encode(), Enforcement.FULL, tree=KERNEL_TREE),
            verified("python", pathlib.Path(sys.executable), Enforcement.PARTIAL, version=platform.python_version()),
            verified("git", pathlib.Path(exe), Enforcement.PARTIAL) if exe else verified("git", b"absent", Enforcement.PARTIAL),
            verified("scanner", pathlib.Path(scan_script), Enforcement.FULL),
            verified("developer", canonical(list(item.developer)).encode(), Enforcement.PARTIAL, route=ROUTE_CLASS),
            verified("reviewer", canonical(list(item.reviewer)).encode(), Enforcement.PARTIAL, route=ROUTE_CLASS)]


# ---------------------------------------------------------------------------------------------------- the execution

class NetworkGuard:
    """§24: no socket may be created in the reproduction process; every attempt is counted and refused."""

    def __init__(self) -> None:
        self.attempts = 0
        self._real = socket.socket

    def __enter__(self):
        guard = self

        class Refused(self._real):
            def __init__(self_, *a, **k):
                guard.attempts += 1
                raise OSError("Q5: network refused — the model stream is replayed; nothing else may leave the process")
        socket.socket = Refused
        return self

    def __exit__(self, *exc):
        socket.socket = self._real


@contextlib.contextmanager
def pinned_git_dates():
    saved = {k: os.environ.get(k) for k in GIT_DATES}
    os.environ.update(GIT_DATES)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def execute(item: Item, mode: str, *, ledger: list[dict] | None = None, variant: str | None = None, keep_dir: pathlib.Path | None = None) -> dict:
    """One real execution of an item: `record` answers the model requests from the item's script and records them;
    `replay` answers them from `ledger`. Everything else executes for real either way. Returns the observation:
    the normalized journal, the model ledger and consumption, the tool ledger, the workspace identities, the errors."""
    from aisef2.arch.enums import Enforcement, ObligationRole, Owner
    from aisef2.errors import InvariantError
    from aisef2.orchestrate import story_runner as sr
    from aisef2.orchestrate.quality import TestsPolicy
    from aisef2.orchestrate.workspace import GitMerger, GitWorkspace
    from aisef2.probe.protocol import ExecutionEnv
    from aisef2.probe.python_callable import PythonCallableProbe
    from aisef2.product.contract import plain
    from aisef2.quality import test_execution as te
    from aisef2.runtime.run_scope import RunScope
    from aisef2.runtime.runspec import resolve
    from tests.v2 import test_p6_orchestration as T
    errors = {k: 0 for k in ERROR_KINDS}
    notes: list[str] = []
    out: dict = {"item": item.id, "mode": mode, "variant": variant, "errors": errors, "started": C.now()}
    holder = tempfile.TemporaryDirectory(prefix=f"aisef2-q5-{item.id}-")
    tmp = pathlib.Path(holder.name).resolve()
    scan_source = {"changed_tool": SCAN_SCRIPT_CHANGED, "tool_exit": SCAN_SCRIPT_EXIT}.get(variant or "", SCAN_SCRIPT)
    script = tmp / "scan.py"
    script.write_text(scan_source, encoding="utf-8")
    tokens = {str(tmp): "<TMP>", sys.executable: "<PY>", str(script): "<SCRIPT>"}
    run = None
    stream = ModelStream(mode, script={"DEVELOPER_IMPLEMENT": list(item.developer), "REVIEWER_REVIEW": list(item.reviewer)} if mode == "record" else None,
                         ledger=ledger if mode == "replay" else None)
    scanner = ObservedScanner(str(script), item.scanner_findings, interpreter=sys.executable, tokens=tokens)
    results: dict[str, list[str]] = {}
    try:
        with pinned_git_dates(), NetworkGuard() as net:
            repo, base = T.make_repo(tmp)
            if item.pre_landed:
                T.land(repo, item.pre_landed, "landed earlier")
                base = T.git(repo, "rev-parse", "main").stdout.strip()
            for n in ("ws", "merge", "run"):
                (tmp / n).mkdir()
            ws, merger = GitWorkspace(repo, tmp / "ws"), GitMerger(repo, "main", tmp / "merge")
            out["initial_workspace"] = workspace_identity(repo, tmp / "ws")
            contracts = {cid: (loc, ([2, 3] if variant == "changed_request" and cid == "C1" else args), (5 if variant == "changed_request" and cid == "C1" else ret))
                         for cid, (loc, args, ret) in CONTRACTS.items()}
            built = {cid: T.contract(cid, *contracts[cid]) for cid in CONTRACTS} if item.kind is None else \
                {cid: kind_contract(cid) for cid in KIND_CONTRACTS if KIND_CONTRACTS[cid][0] == item.kind}
            specs = {spec.id: spec for _, spec in built.values()}
            semantic = {cid: spec.semantic_hash for cid, (_, spec) in built.items()}
            caps = capabilities(item, str(script))
            limits = {o: item.limits.get(o.value, 1) for o in Owner}
            spec_fn = lambda: resolve(caps, {"limits": {"value": {o.value: n for o, n in limits.items()}, "layer": "item"},   # noqa: E731
                                            "corpus_item": {"value": item.id, "layer": "corpus"}}, base)
            run = RunScope(tmp / "run", f"q5-{item.id}", spec=spec_fn)          # the real clock
            run.begin()
            cap_id = {"name": "model-stream", "grade": "VERIFIED", "developer": next(c.tuple_["digest"] for c in caps if c.name == "developer"),
                      "reviewer": next(c.tuple_["digest"] for c in caps if c.name == "reviewer")}
            if item.kind is None:
                probe_ref = (PythonCallableProbe.id, PythonCallableProbe.digest)
                probes = {PythonCallableProbe.id: lambda on_range, scratch: PythonCallableProbe(on_range=on_range, scratch=scratch)}
            else:   # Cycle 2: the catalog's active probe for the item's kind, the only probe factory of its stories
                from aisef2.arch.enums import SubjectKind
                from aisef2.probe import catalog
                entry = catalog.active()[SubjectKind(item.kind)]
                probe_ref = (entry.probe_id, entry.probe_digest)
                probes = {entry.probe_id: lambda on_range, scratch, f=entry.factory: f(on_range=on_range, scratch=scratch)}
            profile = {"enforcement": Enforcement.PARTIAL.value, "timeout_s": 60, "runner": te.UNITTEST.name, "probe_digest": probe_ref[1]}
            if item.kind is not None:
                profile["probe_id"] = probe_ref[0]
            dev = StreamDeveloper(run, stream, capability=cap_id, semantic_hashes=semantic, profile=profile)
            rev = StreamReviewer(run, stream, capability=cap_id, semantic_hashes=semantic, profile=profile)
            env = ExecutionEnv(sys.executable, 60, Enforcement.PARTIAL)
            if variant == "changed_probe_fixture":
                dev = _LandsAfter(dev, repo, TRUNK_FIXTURE_CHANGE)
            obligations = [T.obligation(cid, built[cid][1].id, st.id, ObligationRole[role]) for st in item.stories for cid, role in st.obligations]
            plan = T.plan_of(base, *obligations, pid=f"PLAN-{item.id}")
            adapters = sr.Adapters(dev, rev, scanner, merger, ws)
            for st in item.stories:
                inputs = sr.StoryInputs(specs, probes, env, te.DeveloperTests(st.id, st.tests), te.DeveloperTests(st.id, st.regressions),
                                        te.Dependencies(frozenset(), frozenset({"app", "tests"})), te.UNITTEST)
                r = sr.run_story(run, plan, st.id, inputs, adapters, sr.Policy(limits, TestsPolicy(st.tests_block), tool_timeout_s=60))
                results[st.id] = [a.outcome for a in r.attempts]
            run.shutdown()
            if variant == "workspace_changed":
                T.land(repo, {"README.md": "landed after the run\n"}, "post-run change")
            out["final_workspace"] = workspace_identity(repo, tmp / "ws")
            out["network"] = {"guarded": True, "socket_attempts": net.attempts}
    except ReplayMismatch as e:
        errors["replay_request_mismatch"] += 1
        notes.append(f"{e.kind}: {e.detail}")
        out["replay_failure"] = {"kind": e.kind, "detail": e.detail, "request": e.request}
        _close_after_abort(run, notes)
    except DuplicateConsumption as e:
        errors["assert_consumed_failure"] += 1
        notes.append(str(e))
        _close_after_abort(run, notes)
    except InvariantError as e:
        errors["invariant_violation"] += 1
        notes.append(f"InvariantError: {e}")
        _close_after_abort(run, notes)
    except Exception as e:  # noqa: BLE001 — accounted, never silent (§28)
        errors["exception"] += 1
        notes.append(f"{type(e).__name__}: {e}\n{traceback.format_exc()[-3000:]}")
        _close_after_abort(run, notes)
    finally:
        try:
            if run is not None and run.events:
                events = [{"seq": e.seq, "type": e.type, "time": e.time, "data": plain(e.data), "source_seqs": list(e.source_seqs)} for e in run.events]
                out["journal"] = [normalize_event(e, tokens) for e in events]
                out["journal_raw_digest"] = _sha(json.dumps(events, sort_keys=True, default=str))
                out["subprocesses"] = _subprocesses(events)
                out["residual_from_journal"] = sum(1 for e in events if e["type"] == "story/resource-released" and e["data"].get("status") != "RELEASED")
                errors["residual_process"] += out["residual_from_journal"]
                if run.trace:
                    out["run_trace"] = list(run.trace)
        except Exception as e:  # noqa: BLE001
            errors["harness_error"] += 1
            notes.append(f"journal read: {type(e).__name__}: {e}")
        try:
            if keep_dir is not None:
                shutil.copytree(tmp / "run", keep_dir / f"run-{item.id}", dirs_exist_ok=True)
        except Exception as e:  # noqa: BLE001
            notes.append(f"keep: {e}")
        holder.cleanup()
    out.update(outcomes=results, model_ledger=stream.ledger, model_requests=stream.requests, consumption=stream.assert_consumed(),
               model_mismatches=stream.mismatches, tool_ledger=scanner.calls, notes=notes, finished=C.now())
    if not out["consumption"]["ok"] and errors["replay_request_mismatch"] == 0 and errors["exception"] == 0:
        errors["assert_consumed_failure"] += 1
    return out


def _close_after_abort(run, notes: list[str]) -> None:
    """A story aborted by a typed refusal leaves its scope open: the run is interrupted (every resource disposed,
    `run/interrupted` … `run/end`), so nothing survives the item. The interruption is part of the observation."""
    if run is None:
        return
    try:
        if run._state == "RUNNING":
            run.interrupt()
            notes.append("run interrupted after the abort: resources disposed")
    except Exception as e:  # noqa: BLE001
        notes.append(f"interrupt after abort failed: {type(e).__name__}: {e}")


def _subprocesses(events: list[dict]) -> dict:
    kinds = {"probe": 0, "tests": 0, "tool": 0, "worktree": 0, "scratch": 0}
    for e in events:
        if e["type"] == "story/resource-acquired":
            r = e["data"]["resource"]
            key = "probe" if r.startswith("probe ") else "tests" if r.startswith("tests ") else "tool" if r.startswith("tool ") else \
                "scratch" if r.startswith("scratch") else "worktree"
            kinds[key] += 1
    return kinds


# ------------------------------------------------------------------------------------------------------ comparison

def compare(expected: dict, observed: dict) -> dict:
    """The reproduction verdict of one item: the normalized journals, the tool ledger, the subprocess outcomes, the
    workspace, the request hashes and the consumption — every difference typed (§28)."""
    errors = dict(observed["errors"])
    diffs = compare_journals(expected.get("journal") or [], observed.get("journal") or [])
    for d in diffs:
        errors[d["kind"]] = errors.get(d["kind"], 0) + 1
    tools = []
    exp_tools, obs_tools = expected.get("tool_ledger") or [], observed.get("tool_ledger") or []
    for i in range(max(len(exp_tools), len(obs_tools))):
        a, b = exp_tools[i] if i < len(exp_tools) else None, obs_tools[i] if i < len(obs_tools) else None
        fields = ("argv", "scope_content", "script_sha256", "exit_code", "report_sha256", "executed")
        differing = [f for f in fields if (a or {}).get(f) != (b or {}).get(f)]
        verdict = "MATCH" if a and b and not differing else "DIFF"
        tools.append({"index": i, "tool": (a or b or {}).get("tool"), "story_id": (a or b or {}).get("story_id"),
                      "input_digest": {"expected": (a or {}).get("input_digest"), "observed": (b or {}).get("input_digest")},
                      "expected_result": {k: (a or {}).get(k) for k in ("exit_code", "report_sha256", "executed")},
                      "observed_result": {k: (b or {}).get(k) for k in ("exit_code", "report_sha256", "executed")},
                      "differing_fields": differing, "verdict": verdict})
        if verdict == "DIFF":
            errors["tool_diff"] = errors.get("tool_diff", 0) + 1
    ws_diff = compare_workspaces(expected["final_workspace"], observed["final_workspace"]) if expected.get("final_workspace") and observed.get("final_workspace") \
        else ["final workspace not observed on one side"]
    if ws_diff:
        errors["workspace_diff"] = errors.get("workspace_diff", 0) + len(ws_diff)
    init_diff = compare_workspaces(expected["initial_workspace"], observed["initial_workspace"]) if expected.get("initial_workspace") and observed.get("initial_workspace") \
        else ["initial workspace not observed on one side"]
    hashes_expected = [x["request_hash"] for x in expected.get("model_ledger") or []]
    hashes_observed = [r["request_hash"] for r in observed.get("model_requests") or []]
    hash_mismatches = sum(1 for a, b in zip(hashes_expected, hashes_observed, strict=False) if a != b) + abs(len(hashes_expected) - len(hashes_observed))
    consumption = observed.get("consumption") or {}
    drift_total = sum((r.get("drift") or 0) for r in observed.get("model_requests") or [])
    green = (not diffs and all(t["verdict"] == "MATCH" for t in tools) and not ws_diff and not init_diff and hash_mismatches == 0
             and consumption.get("ok") and drift_total <= 0 and all(v == 0 for v in errors.values())
             and observed.get("outcomes") == expected.get("outcomes"))
    return {"item": expected.get("item"), "status": "GREEN" if green else "FAILED", "errors": errors, "journal_diffs": diffs,
            "journal_events": {"expected": len(expected.get("journal") or []), "observed": len(observed.get("journal") or [])},
            "tool_ledger": tools, "tool_executions": len(obs_tools), "tool_diffs": sum(t["verdict"] == "DIFF" for t in tools),
            "subprocesses": {"expected": expected.get("subprocesses"), "observed": observed.get("subprocesses")},
            "subprocess_diffs": errors.get("subprocess_diff", 0), "probe_product_diffs": errors.get("probe_product_diff", 0),
            "workspace": {"initial": {"expected": (expected.get("initial_workspace") or {}).get("digest"), "observed": (observed.get("initial_workspace") or {}).get("digest"), "diff": init_diff},
                          "final": {"expected": (expected.get("final_workspace") or {}).get("digest"), "observed": (observed.get("final_workspace") or {}).get("digest"),
                                    "tip_expected": (expected.get("final_workspace") or {}).get("tip"), "tip_observed": (observed.get("final_workspace") or {}).get("tip"), "diff": ws_diff}},
            "model_calls": {"expected": len(hashes_expected), "observed": len(hashes_observed), "request_hash_mismatches": hash_mismatches,
                            "consumption": consumption, "drift_total": drift_total, "drift_bound": 0},
            "outcomes": {"expected": expected.get("outcomes"), "observed": observed.get("outcomes")},
            "network": observed.get("network"), "replay_failure": observed.get("replay_failure"), "notes": observed.get("notes")}


# -------------------------------------------------------------------------------------------------- identity / freeze

def _digests(rels) -> dict[str, str]:
    from validation.qualification import q4
    return q4._file_digests(rels)


def _over(d: dict) -> str:
    from validation.qualification import q4
    return q4._over(d)


def corpus_digest(out_dir: pathlib.Path) -> dict:
    items = {}
    for p in sorted((out_dir / "corpus").glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        items[p.stem] = {"sha256": _sha(p.read_bytes()), "ledger_digest": ledger_digest(rec["model_ledger"]), "model_calls": len(rec["model_ledger"]),
                         "tool_calls": len(rec["tool_ledger"]), "final_workspace": rec["final_workspace"]["digest"], "final_tip": rec["final_workspace"]["tip"],
                         "events": len(rec["journal"]), "outcomes": rec["outcomes"]}
    return {"items": items, "corpus_digest": _over({k: v["sha256"] for k, v in items.items()}),
            "replay_digest": _over({k: v["ledger_digest"] for k, v in items.items()})}


def identity(out_dir: pathlib.Path) -> dict:
    from aisef2.probe.python_callable import PythonCallableProbe
    import freeze_manifest as fm
    eff, links, broken = fm.lineage(ROOT)
    harness, fixtures, f1, f9 = (_digests(x) for x in (HARNESS_FILES, FIXTURE_FILES, F1_FILES, F9_FILES))
    from aisef2.product.contract import canonical
    dirty = [ln for ln in C.git("status", "--porcelain", "--", "aisef2", "tests/v2", "validation").splitlines() if ln.strip()]
    corpus = corpus_digest(out_dir) if (out_dir / "corpus").exists() else {"items": {}, "corpus_digest": None, "replay_digest": None}
    return {
        "semantic_candidate": SEMANTIC_CANDIDATE, "kernel_tree": KERNEL_TREE, "execution_commit": C.git("rev-parse", "HEAD"),
        "head_kernel_tree": C.git("rev-parse", "HEAD:aisef2"), "kernel_tree_is_the_candidates": C.git("rev-parse", "HEAD:aisef2") == KERNEL_TREE,
        "working_tree_clean": not dirty, "dirty": dirty, "kernel_digest": kernel_digest(),
        "rfc": {"effective_normative_digest": eff.get("rfc_normative_digest"), "effective_freeze_table_digest": eff.get("freeze_table_digest"),
                "lineage_end": pathlib.Path(links[-1]["record"]).name if links else None, "broken_links": broken},
        "f1_identity": _over(f1), "f9_identity": _over(f9), "harness_digest": _over(harness), "fixture_digest": _over(fixtures),
        "files": {"harness": harness, "fixtures": fixtures, "f1": f1, "f9": f9},
        "corpus": corpus, "request_class_catalog_digest": _sha(canonical(HEADER_CLASSES)), "normalization_digest": _sha(canonical(NORMALIZATION)),
        "header_classes": HEADER_CLASSES, "normalization": NORMALIZATION, "route_class": ROUTE_CLASS, "drift_bound": 0,
        "probe": {"id": PythonCallableProbe.id, "digest": PythonCallableProbe.digest, "corrected": PythonCallableProbe.digest == PROBE_DIGEST,
                  "historical_absent": not PythonCallableProbe.digest.startswith(HISTORICAL_PROBE_DIGEST)},
        "active_catalog": _active_catalog(), "kind_contracts": {cid: list(v) for cid, v in KIND_CONTRACTS.items()},
        "probe_ids_by_item": {i.id: (_active_catalog()[i.kind]["probe_id"] if i.kind else PythonCallableProbe.id) for i in CORPUS},
        "tool_adapters": {"python": interpreter_identity(), "git": git_identity(), "scanner_script_sha256": _sha(SCAN_SCRIPT), "runner": "unittest (-E -s -B)",
                          "developer": "model stream (VERIFIED by the digest of its answer stream)", "reviewer": "model stream (VERIFIED by the digest of its answer stream)"},
        "git_commit_metadata_pinned": GIT_DATES, "platform": {"system": platform.system().lower(), "release": platform.release(), "machine": platform.machine(),
                                                              "python": platform.python_version()},
    }


def _active_catalog() -> dict:
    from aisef2.probe import catalog
    return {k.value: {"probe_id": e.probe_id, "digest": e.probe_digest} for k, e in sorted(catalog.active().items(), key=lambda kv: kv[0].value)}


def one_identity(ident: dict) -> str:
    return _over({k: str(ident[k]) for k in ("semantic_candidate", "kernel_tree", "head_kernel_tree", "kernel_digest", "f1_identity", "f9_identity",
                                              "harness_digest", "fixture_digest", "request_class_catalog_digest", "normalization_digest")}
                 | {"corpus": str(ident["corpus"]["corpus_digest"]), "replay": str(ident["corpus"]["replay_digest"]),
                    "python": ident["tool_adapters"]["python"]["sha256"], "git": str(ident["tool_adapters"]["git"]["sha256"])})


def subject_problems(ident: dict) -> list[str]:
    out = []
    if not ident["kernel_tree_is_the_candidates"]:
        out.append(f"HEAD's aisef2 tree {ident['head_kernel_tree']} is not the candidate's {KERNEL_TREE}")
    if not ident["working_tree_clean"]:
        out.append(f"the working tree is dirty under aisef2, tests/v2 or validation: {ident['dirty'][:5]}")
    if ident["rfc"]["broken_links"] or ident["rfc"]["lineage_end"] != "AISEF-V2-RFC-AMENDMENT-V2-006.json":
        out.append("the effective RFC lineage does not end at V2-006 unbroken")
    if not ident["probe"]["corrected"]:
        out.append(f"the probe digest is not the corrected {PROBE_DIGEST[:12]}")
    if not ident["corpus"]["items"]:
        out.append("no corpus recorded")
    return out


# ----------------------------------------------------------------------------------------------------------- modes

def record(out_dir: pathlib.Path) -> int:
    corpus_dir = out_dir / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(p.name for p in corpus_dir.glob("*.json"))
    if existing:
        print(f"REFUSED: the corpus is recorded once; {existing} exist")
        return 2
    ok = True
    for item in CORPUS:
        obs = execute(item, "record")
        rec = {"record": "AISEF V2 — Q5 corpus item (a real execution, its model stream recorded)", "item": item.id, "covers": list(item.covers),
               "definition": {"stories": [{"id": s.id, "obligations": list(map(list, s.obligations)), "tests": list(s.tests), "regressions": list(s.regressions),
                                           "tests_block": s.tests_block} for s in item.stories], "developer": list(item.developer), "reviewer": list(item.reviewer),
                              "pre_landed": item.pre_landed, "scanner_findings": [list(f) for f in item.scanner_findings], "limits": item.limits,
                              "expected_outcomes": item.expected_outcomes},
               "platform": platform.system().lower(), "python": platform.python_version(), "execution_commit": C.git("rev-parse", "HEAD"), **obs}
        rec["ledger_digest"] = ledger_digest(rec["model_ledger"])
        good = rec["outcomes"] == item.expected_outcomes and all(v == 0 for v in rec["errors"].values()) and rec["consumption"]["ok"]
        ok &= good
        (corpus_dir / f"{item.id}.json").write_text(C.render(rec), encoding="utf-8")
        print(f"recorded {item.id}: outcomes {rec['outcomes']} (expected {item.expected_outcomes}) model calls {len(rec['model_ledger'])} tool calls "
              f"{len(rec['tool_ledger'])} events {len(rec.get('journal') or [])} errors {sum(rec['errors'].values())} sockets {rec.get('network')}"
              + ("" if good else f" NOT AS EXPECTED: {rec['notes']}"))
    index = {"record": "AISEF V2 — Q5 CORPUS (frozen before any reproduction)", "recorded": C.now(), "execution_commit": C.git("rev-parse", "HEAD"),
             **corpus_digest(out_dir), "coverage": {item.id: list(item.covers) for item in CORPUS}}
    (out_dir / "CORPUS.json").write_text(C.render(index), encoding="utf-8")
    print(f"corpus {index['corpus_digest'][:12]} replay {index['replay_digest'][:12]}: {len(index['items'])} items")
    return 0 if ok else 1


def load_corpus(out_dir: pathlib.Path) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((out_dir / "corpus").glob("*.json"))}


def reproduce(out_dir: pathlib.Path) -> int:
    subject = json.loads((out_dir / "SUBJECT.json").read_text(encoding="utf-8"))
    corpus = load_corpus(out_dir)
    ident = identity(out_dir)
    problems = subject_problems(ident)
    if one_identity(ident) != subject["one_identity"]:
        problems.append("the identity at reproduction is not the frozen subject's")
    rep_dir = out_dir / "reproduction"
    rep_dir.mkdir(parents=True, exist_ok=True)
    if any(rep_dir.glob("*.json")):
        print("REFUSED: reproduction records exist — a rerun is a new attempt directory")
        return 2
    by_id = {i.id: i for i in CORPUS}
    verdicts = {}
    for item_id, expected in corpus.items():
        item = by_id[item_id]
        if problems:
            verdicts[item_id] = {"item": item_id, "status": "UNRUNNABLE", "problems": problems}
            continue
        observed = execute(item, "replay", ledger=expected["model_ledger"])
        v = compare(expected, observed)
        v["model_requests"] = observed["model_requests"]
        v["expected_ledger_digest"] = expected["ledger_digest"]
        v["kernel_tree_after"] = C.git("rev-parse", "HEAD:aisef2")
        (rep_dir / f"{item_id}.json").write_text(C.render(v), encoding="utf-8")
        verdicts[item_id] = v
        print(f"reproduced {item_id}: {v['status']} — journal {v['journal_events']} diffs {len(v['journal_diffs'])}; tools {v['tool_executions']} diffs {v['tool_diffs']}; "
              f"workspace {'MATCH' if not v['workspace']['final']['diff'] else 'DIFF'}; model {v['model_calls']['observed']}/{v['model_calls']['expected']} "
              f"mismatches {v['model_calls']['request_hash_mismatches']} consumed ok {v['model_calls']['consumption'].get('ok')}; sockets {v['network']}")
    rec = aggregate(out_dir, subject, ident, verdicts, problems)
    (out_dir / "REPRODUCTION.json").write_text(C.render(rec), encoding="utf-8")
    print(f"Q5 {rec['status']}: {rec['totals']}")
    for p in rec["problems"]:
        print(f"  problem: {p}")
    return 0 if rec["status"] == "GREEN" else 1


def aggregate(out_dir: pathlib.Path, subject: dict, ident: dict, verdicts: dict, problems: list[str]) -> dict:
    from validation.qualification import q4_aggregate as A
    totals = {k: sum((v.get("errors") or {}).get(k, 0) for v in verdicts.values()) for k in ERROR_KINDS}
    totals.update(items=len(verdicts), green=sum(v.get("status") == "GREEN" for v in verdicts.values()),
                  expected_model_calls=sum((v.get("model_calls") or {}).get("expected", 0) for v in verdicts.values()),
                  consumed_model_calls=sum(((v.get("model_calls") or {}).get("consumption") or {}).get("consumed", 0) for v in verdicts.values()),
                  missing_replay_calls=sum(len(((v.get("model_calls") or {}).get("consumption") or {}).get("missing_unconsumed", [])) for v in verdicts.values()),
                  extra_model_calls=sum(len(((v.get("model_calls") or {}).get("consumption") or {}).get("extra_requests", [])) for v in verdicts.values()),
                  request_hash_mismatches=sum((v.get("model_calls") or {}).get("request_hash_mismatches", 0) for v in verdicts.values()),
                  drift_total=sum((v.get("model_calls") or {}).get("drift_total", 0) for v in verdicts.values()),
                  tool_executions=sum(v.get("tool_executions", 0) for v in verdicts.values()), tool_result_replays=0,
                  tool_diffs=sum(v.get("tool_diffs", 0) for v in verdicts.values()),
                  subprocess_executions=sum(sum((v.get("subprocesses") or {}).get("observed", {}).values()) for v in verdicts.values() if isinstance((v.get("subprocesses") or {}).get("observed"), dict)),
                  workspace_diffs=sum(len(((v.get("workspace") or {}).get("final") or {}).get("diff") or []) for v in verdicts.values()),
                  socket_attempts=sum(((v.get("network") or {}).get("socket_attempts") or 0) for v in verdicts.values()))
    assert_consumed = all(((v.get("model_calls") or {}).get("consumption") or {}).get("ok") for v in verdicts.values()) and bool(verdicts)
    start = out_dir / "CONFORMANCE-start.json"
    start_rec = json.loads(start.read_text(encoding="utf-8")) if start.exists() else None
    end_rec = A.conformance()
    end_rec["f9"] = end_rec["freeze_conformance"]["statuses"].get("F9")
    for when, rec in (("start", start_rec), ("end", end_rec)):
        if rec is None:
            problems.append(f"no conformance snapshot at {when}")
        elif not (rec["freeze_conformance"]["pass"] and rec["v1_evidence_guard"]["pass"] and rec["w0"]["unchanged"]):
            problems.append(f"conformance at {when} not PASS")
    calib = out_dir / "CALIBRATION.json"
    calib_rec = json.loads(calib.read_text(encoding="utf-8")) if calib.exists() else None
    if not (calib_rec and calib_rec.get("all_rejected")):
        problems.append("no calibration with every defect rejected")
    if totals["green"] != totals["items"] or totals["items"] != len(CORPUS):
        problems.append(f"{totals['green']} of {totals['items']} items GREEN (corpus {len(CORPUS)})")
    if not assert_consumed:
        problems.append("assertConsumed not GREEN on every item")
    for k in ERROR_KINDS:
        if totals[k]:
            problems.append(f"{k} = {totals[k]}")
    if totals["socket_attempts"]:
        problems.append(f"socket attempts {totals['socket_attempts']}")
    dirty_outside = [ln for ln in ident["dirty"] if not ln[3:].startswith(OUT_REL)]
    if dirty_outside:
        problems.append(f"the working tree is dirty outside {OUT_REL}: {dirty_outside[:5]}")
    p8 = f"{C.Q4_OUT_REL}/DIFFERENTIAL.json"   # the same subject's differential below this rung (release mode: Q4-RC1's)
    return {
        "record": "AISEF V2 — Q5 REPRODUCTION (real execution; the model stream alone replayed)", "rung": "Q5",
        "authority": "owner's P9 / QP-9 EXECUTION AUTHORIZATION (2026-09-28)", "aggregated": C.now(),
        "semantic_candidate": SEMANTIC_CANDIDATE, "kernel_tree": KERNEL_TREE, "execution_commit": subject["identity"]["execution_commit"],
        "reproduction_head": ident["execution_commit"], "aisef2_tree_at_reproduction": ident["head_kernel_tree"],
        "harness_digest": ident["harness_digest"], "fixture_digest": ident["fixture_digest"], "corpus_digest": ident["corpus"]["corpus_digest"],
        "replay_digest": ident["corpus"]["replay_digest"], "request_class_catalog_digest": ident["request_class_catalog_digest"],
        "normalization_digest": ident["normalization_digest"], "tool_adapters": ident["tool_adapters"], "probe": ident["probe"],
        "f1_identity": ident["f1_identity"], "f9_identity": ident["f9_identity"], "one_identity": one_identity(ident),
        "subject": {"path": f"{OUT_REL}/SUBJECT.json", "sha256": _sha((out_dir / "SUBJECT.json").read_bytes()), "one_identity": subject["one_identity"]},
        "corpus": ident["corpus"]["items"], "coverage": {i.id: list(i.covers) for i in CORPUS},
        "items": {k: {kk: vv for kk, vv in v.items() if kk not in ("journal_diffs", "model_requests", "tool_ledger", "notes")} for k, v in verdicts.items()},
        "workspaces": {k: {"initial": ((v.get("workspace") or {}).get("initial") or {}).get("observed"), "final": ((v.get("workspace") or {}).get("final") or {}).get("observed"),
                           "final_tip": ((v.get("workspace") or {}).get("final") or {}).get("tip_observed")} for k, v in verdicts.items()},
        "totals": totals, "assert_consumed": assert_consumed, "only_model_stream_replayed": True,
        "replay_mechanism": "validation/qualification/q5.py ModelStream (developer and reviewer answers only; git, probes, tests, scanner, merge execute again)",
        "network": {"guard": "in-process socket refusal during every item", "socket_attempts": totals["socket_attempts"]},
        "residual_processes": {"from_journal": totals["residual_process"], "owned_range": "see the owned-run record beside this file"},
        "conformance": {"start": start_rec, "end": end_rec}, "calibration": {"path": f"{OUT_REL}/CALIBRATION.json", "all_rejected": bool(calib_rec and calib_rec.get("all_rejected"))},
        "p8_evidence": {p8: _sha((ROOT / p8).read_bytes()), f"{C.Q4_OUT_REL}/SUBJECT.json": _sha((ROOT / C.Q4_OUT_REL / "SUBJECT.json").read_bytes())},
        "p7_evidence": {rel: _sha((ROOT / rel).read_bytes()) for rel in A.P7_EVIDENCE}, "seals": {rel: _sha((ROOT / rel).read_bytes()) for rel in A.SEALS},
        "v1_evidence": {"baseline": _sha((ROOT / "closure-evidence/v2/V1-EVIDENCE-BASELINE.json").read_bytes()), "w0": _sha((ROOT / A.W0_REL).read_bytes()),
                        "product_tree": C.git("rev-parse", "HEAD:aisef")},
        "platform": ident["platform"], "problems": problems, "status": "GREEN" if not problems else "FAILED",
    }


def freeze(out_dir: pathlib.Path) -> dict:
    ident = identity(out_dir)
    return {"record": "AISEF V2 — Q5 SUBJECT (frozen before the first reproduction)", "authority": "owner's P9 / QP-9 EXECUTION AUTHORIZATION §2",
            "frozen_at": C.now(), "identity": ident, "one_identity": one_identity(ident), "subject_problems": subject_problems(ident),
            "rule": "any kernel/control/probe semantic change after this point invalidates Q5; the corpus, the replay ledger, the header classes, "
                    "the normalization rules and the harness are bound here and compared at reproduction"}


# ------------------------------------------------------------------------------------------------------ calibration

def calibrate(out_dir: pathlib.Path) -> dict:
    """§6, §9, §11, §16, §29: a fresh scratch recording of the normal item, then each named defect, each expected to
    be rejected with its typed cause. None of it touches the corpus."""
    from aisef2.orchestrate.workspace import git
    item = next(i for i in CORPUS if i.id == "normal-completion")
    base = execute(item, "record")
    ledger = base["model_ledger"]
    three = next(i for i in CORPUS if i.id == "retry-then-commit")     # three model calls: developer, developer, reviewer
    base3 = execute(three, "record")
    fa = next(i for i in CORPUS if i.id == "file-artifact-prohibition")   # Cycle 2: proved by probe.file_artifact
    base_fa = execute(fa, "record")
    cases: dict[str, dict] = {}

    def full(name, *, variant=None, ledger_=None, expect: dict, item_=item, base_=None):
        base_ = base_ or base
        obs = execute(item_, "replay", ledger=ledger_ if ledger_ is not None else base_["model_ledger"], variant=variant)
        v = compare(base_, obs)
        got = {"status": v["status"], "replay_request_mismatch": v["errors"].get("replay_request_mismatch", 0), "tool_diffs": v["tool_diffs"],
               "workspace_diffs": len(v["workspace"]["final"]["diff"]), "consumption_ok": v["model_calls"]["consumption"].get("ok"),
               "extra": len(v["model_calls"]["consumption"].get("extra_requests", [])), "unconsumed": len(v["model_calls"]["consumption"].get("missing_unconsumed", [])),
               "model_calls": v["model_calls"]["observed"], "kind": (v.get("replay_failure") or {}).get("kind"),
               "probe_product_diff": v["errors"].get("probe_product_diff", 0),
               "tool_exit_expected_observed": [(t["expected_result"]["exit_code"], t["observed_result"]["exit_code"]) for t in v["tool_ledger"]]}
        rejected = v["status"] != "GREEN" and all(got.get(k) == val or (callable(val) and val(got.get(k))) for k, val in expect.items())
        cases[name] = {"expected": {k: (val if not callable(val) else "predicate") for k, val in expect.items()}, "observed": got, "rejected": rejected,
                       "first_journal_diff": (v["journal_diffs"][0] if v["journal_diffs"] else None)}

    control = compare(base, execute(item, "replay", ledger=ledger))
    cases["control_round_trip"] = {"observed": {"status": control["status"], "model_calls": control["model_calls"], "tool_diffs": control["tool_diffs"],
                                                "workspace_diff": control["workspace"]["final"]["diff"]}, "rejected": None, "green": control["status"] == "GREEN"}
    full("1_same_call_count_changed_request", variant="changed_request", expect={"replay_request_mismatch": lambda n: n >= 1, "kind": "REQUEST_HASH_MISMATCH"})
    full("2_changed_tool_behaviour", variant="changed_tool", expect={"tool_diffs": lambda n: n >= 1})
    l3 = base3["model_ledger"]
    full("3_missing_replay_item", item_=three, base_=base3, ledger_=[l3[0]] + l3[2:], expect={"kind": "MISSING_REPLAY_ITEM", "replay_request_mismatch": lambda n: n >= 1})
    full("4_extra_model_call", ledger_=ledger[:1], expect={"kind": "EXTRA_MODEL_CALL", "extra": lambda n: n >= 1})
    full("5_changed_final_workspace_file", variant="workspace_changed", expect={"workspace_diffs": lambda n: n >= 1})
    full("6_changed_tool_exit_status", variant="tool_exit", expect={"tool_diffs": lambda n: n >= 1, "tool_exit_expected_observed": lambda x: any(a != b for a, b in x)})
    synthetic = {**ledger[-1], "seq": len(ledger) + 1, "request_hash": "f" * 64, "request": {**ledger[-1]["request"], "story_id": "S9"}}
    full("7_unconsumed_replay_item", ledger_=ledger + [synthetic], expect={"consumption_ok": False, "unconsumed": 1})
    # Cycle 2: a file the (re-executed) file_artifact probe observes changed on the trunk outside the model stream — the
    # requests unchanged and every recorded answer consumed, the difference surfaces as a probe/product diff
    full("10_changed_probe_fixture", item_=fa, base_=base_fa, variant="changed_probe_fixture",
         expect={"replay_request_mismatch": 0, "consumption_ok": True, "probe_product_diff": lambda n: n >= 1})
    # §9 at the ledger, without a run: reordered, duplicate consumption
    if len(ledger) >= 2:
        s = ModelStream("replay", ledger=[ledger[1], ledger[0]])
        try:
            s.answer(ledger[0]["header_class"], ledger[0]["request"])
            reordered = {"rejected": False}
        except ReplayMismatch as e:
            reordered = {"rejected": e.kind == "REORDERED_REQUEST", "kind": e.kind}
        cases["9_reordered_request"] = reordered
    s = ModelStream("replay", ledger=ledger)
    s.consume(ledger[0]["seq"])
    try:
        s.consume(ledger[0]["seq"])
        cases["9_duplicate_consumption"] = {"rejected": False}
    except DuplicateConsumption:
        cases["9_duplicate_consumption"] = {"rejected": True}
    # §16 normalization cannot hide a regression
    ev = base["journal"]
    tokens = {"/tmp/one": "<TMP>"}
    e_time_a = {"seq": 1, "type": "gate/check", "time": 1.0, "data": {"detail": "x", "passed": True}, "source_seqs": []}
    e_time_b = {**e_time_a, "time": 2.0}
    e_path_a = {"seq": 1, "type": "story/resource-released", "time": 1.0, "data": {"detail": "left /tmp/one/wt", "status": "RESIDUAL"}, "source_seqs": []}
    e_path_b = {**e_path_a, "data": {"detail": "left /tmp/two/wt", "status": "RESIDUAL"}}
    n = {"timestamp_only_change_equal": normalize_event(e_time_a, tokens) == normalize_event(e_time_b, tokens),
         "temp_path_only_change_equal": normalize_event(e_path_a, {"/tmp/one": "<TMP>"}) == normalize_event(e_path_b, {"/tmp/two": "<TMP>"}),
         "meaningful_stdout_change_diff": normalize_event({**e_time_a, "data": {"detail": "1 test failed", "passed": True}}, tokens)
         != normalize_event({**e_time_a, "data": {"detail": "0 tests failed", "passed": True}}, tokens),
         "exit_code_change_diff": normalize_event({**e_time_a, "type": "tool/result", "data": {"outcome": "COMPLETED", "detail": ""}}, tokens)
         != normalize_event({**e_time_a, "type": "tool/result", "data": {"outcome": "FAILED", "detail": "exit status 3"}}, tokens),
         "file_content_change_diff": bool(compare_workspaces({"tip": "a", "tree": "t", "status": "", "worktrees": 1, "ws_entries": [], "files": {"app/calc.py": {"mode": "100644", "blob": "b1"}}},
                                                             {"tip": "a", "tree": "t", "status": "", "worktrees": 1, "ws_entries": [], "files": {"app/calc.py": {"mode": "100644", "blob": "b2"}}})),
         "owner_retryability_change_diff": normalize_event({**e_time_a, "type": "failure/observed", "data": {"code": "X", "owner": "DEVELOPER", "retryable": True, "detail": ""}}, tokens)
         != normalize_event({**e_time_a, "type": "failure/observed", "data": {"code": "X", "owner": "PLAN", "retryable": False, "detail": ""}}, tokens),
         "revision_change_diff": normalize_event({**e_time_a, "type": "story/commit", "data": {"story_id": "S1", "revision": "a" * 40}}, tokens)
         != normalize_event({**e_time_a, "type": "story/commit", "data": {"story_id": "S1", "revision": "b" * 40}}, tokens),
         "real_journal_is_time_free": all("time" not in e for e in ev)}
    cases["16_normalization"] = {"cases": n, "rejected": all(n.values())}
    all_rejected = cases["control_round_trip"]["green"] and all(c.get("rejected") for k, c in cases.items() if k != "control_round_trip")
    return {"record": "AISEF V2 — Q5 CALIBRATION (§6, §9, §11, §16, §29): the harness rejects each named defect", "when": C.now(),
            "scratch_recordings": {item.id: ledger_digest(ledger), three.id: ledger_digest(l3), fa.id: ledger_digest(base_fa["model_ledger"]),
                                   "note": "recordings made for calibration; not the corpus"},
            "cases": cases, "all_rejected": all_rejected, "harness_digest": identity(out_dir)["harness_digest"],
            "git": git(ROOT, "--version").stdout.strip()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--reproduce", action="store_true")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--conformance", choices=("start", "end"))
    ap.add_argument("--out", default=OUT_REL)
    a = ap.parse_args(argv)
    out_dir = (ROOT / a.out) if not os.path.isabs(a.out) else pathlib.Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    import tests.v2  # noqa: F401 — invariants I–IX armed at tier ROOT for every mode
    if a.record:
        return record(out_dir)
    if a.calibrate:
        rec = calibrate(out_dir)
        (out_dir / "CALIBRATION.json").write_text(C.render(rec), encoding="utf-8")
        print(f"calibration: { {k: c.get('rejected', c.get('green')) for k, c in rec['cases'].items()} } all {rec['all_rejected']}")
        return 0 if rec["all_rejected"] else 1
    if a.freeze:
        rec = freeze(out_dir)
        (out_dir / "SUBJECT.json").write_text(C.render(rec), encoding="utf-8")
        print(f"subject {rec['one_identity'][:12]} frozen; problems {rec['subject_problems']}")
        return 1 if rec["subject_problems"] else 0
    if a.conformance:
        from validation.qualification import q4_aggregate as A
        rec = A.conformance()
        rec["f9"] = rec["freeze_conformance"]["statuses"].get("F9")
        (out_dir / f"CONFORMANCE-{a.conformance}.json").write_text(C.render(rec), encoding="utf-8")
        ok = rec["freeze_conformance"]["pass"] and rec["v1_evidence_guard"]["pass"] and rec["w0"]["unchanged"]
        print(f"conformance {a.conformance}: F1 {rec['freeze_conformance']['statuses'].get('F1')} F9 {rec['f9']} all {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    if a.reproduce:
        return reproduce(out_dir)
    ap.error("one of --record, --calibrate, --freeze, --conformance, --reproduce")
    return 2


if __name__ == "__main__":
    sys.exit(main())
