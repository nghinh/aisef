"""What the developer and the reviewer are told — built from the bundle's public facts and the run's journal only.

* `task`: the story's requirement clauses (INTRODUCE / PRESERVE / VERIFY), the product subjects they are verified on,
  the plan stories it depends on, where its tests go. Never a probe, stimulus, observable or expectation: the proof is
  independent of the developer.
* `retry_feedback` (H-RETRY-001): on a retry, each failure the kernel journaled for the story with the evidence that
  decided it — criterion, role, requirement and clause, contract, spec, probe, subject, candidate, probe status and
  verdict against the expectation, the verifier's agreement, the typed failure and owner, the journal seqs. A pure
  function of the journal: prompt text, never journaled, never read by the kernel.
"""

from __future__ import annotations

import re

from aisef2.app.bundle import Project

REFUTED = ("The candidate remains {verdict} for this approved contract and the independent verifier agrees. Inspect the "
           "implementation against that requirement clause. The proof's stimulus is not part of this message.")


def _line(project: Project, o) -> str:
    f = project.facts[o.criterion_id]
    where = f" {f['section']}" if f["section"] else ""
    return (f"- [{o.role.value}] {f['requirement']} ({project.requirements_path}{where}), clause {f['clause']}: "
            f"{f['clause_text']}")


def clauses(project: Project, story: str) -> str:
    return "\n".join(dict.fromkeys(_line(project, o) for o in project.plan.obligations if o.story_id == story))


def task(project: Project, story: str) -> str:
    obligations = [o for o in project.plan.obligations if o.story_id == story]
    lines = clauses(project, story)
    after = [s for s in project.stories[story]["depends_on"] if s in project.stories]
    subjects = sorted({project.facts[o.criterion_id]["subject"] for o in obligations})
    tests = project.stories[story]["tests"]
    verify = any(o.role.value == "VERIFY" for o in obligations)
    return (f"You are the developer of story {story} of {project.name}. {project.description} "
            f"{project.requirements_path} in this repository is the authoritative specification. Implement this story in "
            f"this repository (the project's own source: {', '.join(project.product_roots)}), working only inside this "
            "directory.\n\n"
            f"What this story must deliver is defined by the requirement clauses listed below and by "
            f"{project.requirements_path}, and by nothing else.\n\n"
            + (f"The stories of this plan it depends on: {', '.join(after)}.\n\n" if after else "")
            + "When you finish, each of the following requirement clauses is verified independently against the "
              "requirements (INTRODUCE: this story makes it true; PRESERVE: it must stay true"
            + ("; VERIFY: it must be true when this story is done" if verify else "") + "):\n" + lines
            + f"\n\nThe product subjects those clauses are verified on: {', '.join(subjects)}."
            + (f"\n\nWrite this story's unit tests in {', '.join(tests)} (unittest; `python -m unittest` must pass from "
               "the repository root) and keep every earlier test passing." if tests else "")
            + f" Do not edit {project.requirements_path}. Do not run git commit; the harness commits your working tree.")


def retry_feedback(events, story_id: str, project: Project) -> str:
    """The failures the kernel observed in `story_id`, from journal events `(seq, type, data)` and the public facts."""
    by_criterion = {o.criterion_id: o for o in project.plan.obligations}
    events = [(int(q), str(t), d) for q, t, d in events]
    rows = []
    for seq, kind, data in events:
        if kind != "failure/observed" or data.get("story_id") != story_id:
            continue
        code, owner, detail = data.get("code"), data.get("owner"), str(data.get("detail", ""))
        m = re.match(r"proof of (\S+): ", detail)
        o = by_criterion.get(m.group(1)) if m else None
        about = [e for e in events if o and e[2].get("story_id") == story_id and e[2].get("criterion_id") == o.criterion_id]
        proof = next((e for e in reversed(about) if e[0] < seq and e[1] == "proof/verified"), None)
        if proof is None:
            rows.append(f"- {code} (owner {owner}): {detail}")
            continue
        f, spec = project.facts[o.criterion_id], project.specs[o.product_proof_spec_id]
        expected = spec.candidate_expectation.value
        recs = [e for e in about if e[0] < proof[0] and e[1] == "probe/evaluated"][-2:]
        executed = len(recs) == 2 and all("behavior_verdict" in ((r[2].get("record") or {}).get("result") or {}) for r in recs)
        p = proof[2]
        where = f" {f['section']}" if f["section"] else ""
        line = (f"- {code} (owner {owner}) — {story_id}, criterion {o.criterion_id} [{o.role.value}]: {f['requirement']} "
                f"({project.requirements_path}{where}), clause {f['clause']}: {f['clause_text']}\n"
                f"  contract {spec.contract_id}, ProductProofSpec {spec.id}, probe {spec.probe_id}, subject {f['subject']}; "
                f"candidate {p.get('candidate')}: probe status {'EXECUTED' if executed else 'not EXECUTED'}"
                + (f", verdict {p.get('verdict')} (expected {expected})" if executed else "")
                + f", the independent verifier {'agrees' if p.get('agreement') else 'disagrees'}. Evidence: journal seq "
                f"{', '.join(str(r[0]) for r in recs)} (the probe records), {proof[0]} (the proof), {seq} (this failure).")
        if executed and p.get("agreement") and owner == "DEVELOPER" and p.get("verdict") not in (None, expected):
            line += "\n  " + REFUTED.format(verdict=p["verdict"])
        rows.append(line)
    return "\n".join(rows)
