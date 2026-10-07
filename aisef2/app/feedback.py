"""What the developer and the reviewer are told — built from the bundle's public facts and the run's journal only.

* `task`: the story's requirement clauses (INTRODUCE / PRESERVE / VERIFY), the product subjects they are verified on,
  the plan stories it depends on, where its tests go. Never a probe, stimulus, observable or expectation: the proof is
  independent of the developer.
* `retry_feedback` (H-RETRY-001): on a retry, each failure the kernel journaled for the story with the evidence that
  decided it — criterion, role, requirement and clause, contract, spec, probe, subject, candidate, probe status and
  verdict against the expectation, the verifier's agreement, the typed failure and owner, the journal seqs. A pure
  function of the journal: prompt text, never journaled, never read by the kernel.
* `context_pack` (V2.1 D4, docs/v2.1/CONTEXT-PACK.md): on a retry, what the journal also records about the story's
  earlier attempts, the latest first — each one's parent, its developer result, its candidate or that the parent itself
  was proved (it changed nothing), the criteria that held there and those with no proof recorded there — each line
  citing its journal seqs. Read from the controller's own records only, bounded, the developer result on one line, the
  run's secrets replaced; context, never authority: no verdict, approval or budget reads it.
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
            if code == "REVIEW_FINDING":    # V2.1: the confirmed findings that blocked this attempt, as journaled
                since = max((q for q, k, d in events if q < seq and d.get("story_id") == story_id
                             and k in ("failure/observed", "story/begin")), default=0)
                rows += [f"  {d['detail']}" for q, k, d in events if since < q < seq and k == "gate/check"
                         and d.get("check", "").startswith(f"{story_id}:review:") and d.get("passed") is False]
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


#: the context pack's bounds: the prompt is one argv element (a Windows command line holds 32 767 characters)
PACK_MAX, PACK_LIST, PACK_ATTEMPTS = 4000, 12, 4
PACK_HEAD = ("What the run's journal records about the earlier attempts of this story (the controller's own record; "
             "context only — no verdict, approval or budget reads it):")


def context_pack(events, story_id: str, project: Project, secrets=()) -> str:
    """The earlier attempts of `story_id` from journal events `(seq, type, data)` (module docstring); "" when none ended.
    It reads only the controller's own records of an attempt — story/begin, story/admitted, the DEVELOPER
    provider/request and its provider/result, proof/verified (candidate, criterion, verdict, agreement), story/end —
    never a probe, tool, gate or test record nor a session stream: no stimulus, oracle internal or agent text.
    Held = the verdict is the plan's expectation for that criterion (any story's: a committed story's PRESERVE is proved
    here too) and the verifier agrees; a criterion the plan does not know is never held."""
    expect = {o.criterion_id: project.specs[o.product_proof_spec_id].candidate_expectation.value
              for o in project.plan.obligations}

    def redact(text: str) -> str:     # the one free text it carries: on one line, the run's secrets out, longest first
        text = " ".join(text.split())    # every whitespace run, newlines included, one space: each line is the pack's own
        for s in sorted({" ".join(str(x).split()) for x in secrets if x} - {""}, key=len, reverse=True):
            text = text.replace(s, "[REDACTED]")    # a secret matched in the same one-line form (app/client.redact)
        return text
    ended, cur = [], None
    for seq, kind, d in sorted(((int(q), str(t), d) for q, t, d in events), key=lambda e: e[0]):
        if d.get("story_id") != story_id:
            continue
        if kind == "story/begin":
            cur = {"seq": seq, "parent": str(d.get("parent")), "criteria": [], "proofs": {}}
        elif cur is None:
            continue
        elif kind == "story/admitted":
            cur["criteria"] = sorted(map(str, d.get("dispositions") or {}))
        elif kind == "provider/request" and d.get("budget_owner") == "DEVELOPER":
            cur["request"] = seq
        elif kind == "provider/result" and "request" in cur and "result" not in cur:
            cur["result"] = (seq, redact(str(d.get("detail", "")))[:300])    # redacted before it is cut
        elif kind == "proof/verified":
            cur.setdefault("candidate", (seq, str(d.get("candidate"))))
            c = str(d.get("criterion_id"))
            if d.get("candidate") == cur["candidate"][1] and c not in cur["proofs"]:
                cur["proofs"][c] = (seq, d.get("agreement") is True and c in expect and d.get("verdict") == expect[c])
        elif kind == "story/end":
            ended.append({**cur, "end": seq})
            cur = None
    if not ended:
        return ""

    def named(rows):    # (criterion, seq), sorted: the first PACK_LIST by name, with their seqs
        shown = [(c, f"{c} ({project.facts[c]['clause']})" if c in project.facts else c, s) for c, s in sorted(rows)]
        more = f" and {len(shown) - PACK_LIST} more" if len(shown) > PACK_LIST else ""
        return ", ".join(x[1] for x in shown[:PACK_LIST]) + more, ", ".join(str(x[2]) for x in shown[:PACK_LIST])

    lines = [PACK_HEAD]
    if cur is not None:
        lines.append(f"- this attempt starts again at the parent {cur['parent'][:12]} (journal seq {cur['seq']})")
    if len(ended) > PACK_ATTEMPTS:
        lines.append(f"- {len(ended) - PACK_ATTEMPTS} earlier attempt(s) not shown (journal seq {ended[0]['seq']}–"
                     f"{ended[-PACK_ATTEMPTS - 1]['end']})")
    for n, a in reversed(list(enumerate(ended, 1))[-PACK_ATTEMPTS:]):    # the latest first: the bound cuts the oldest
        r, c = a.get("result"), a.get("candidate")
        line = f"- attempt {n}: parent {a['parent'][:12]} (journal seq {a['seq']}); " + (
            f"developer result: {r[1]} (journal seq {r[0]})" if r else f"no developer result (journal seq {a['seq']}–{a['end']})")
        if c and c[1] == a["parent"]:
            line += f"; the revision proved was the parent itself — that attempt changed nothing (journal seq {c[0]})"
        elif c:
            line += f"; candidate {c[1][:12]} (journal seq {c[0]}), a commit of this repository"
        lines.append(line)
        held = [(k, v[0]) for k, v in a["proofs"].items() if v[1]]
        if held:
            what, seqs = named(held)
            lines.append(f"  held at that revision, the verifier agreeing: {what} (journal seq {seqs})")
        unproved = sorted(set(a["criteria"]) - set(a["proofs"]))
        if unproved:
            what, _ = named((k, 0) for k in unproved)
            lines.append(f"  no proof recorded for them in that attempt: {what} (journal seq {a['seq']}–{a['end']})")
    text = "\n".join(lines)
    if len(text) > PACK_MAX:
        kept, size = [], 0
        for ln in text.split("\n"):
            if size + len(ln) + 1 > PACK_MAX - 120:
                break
            kept.append(ln)
            size += len(ln) + 1
        text = "\n".join(kept) + f"\n[the context pack stops here: bounded at {PACK_MAX} characters]"
    return text
