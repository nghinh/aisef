# REL-GOV-01 — owner runbook: prove that a production publish waits for a human (dry run, publishes nothing)

Status: **prepared, not run.** Design: `docs/v2.3/W1-DESIGN.md` §5. The agent never changes repository settings, never
pushes a probe tag and never approves or rejects a deployment. Every step below that changes GitHub is the owner's.

## 0. What is proven, and what is not

* Proven by the probe: a job bound to environment `pypi` stops in `status: waiting` until a required reviewer acts
  (**CHECKPOINT_PAUSES**), and a tag outside the allowed pattern cannot deploy to `pypi` at all (**TAG_RESTRICTED**).
* Not proven by the probe: that `release.yml`'s own `publish` job waits. That is observed once, at W6, on the real
  `v2.3.0` tag, snapshotted **before** the owner approves (`REL-GOV-01-W6-OBSERVED.json`). If `publish` ever runs without
  `waiting`: STOP.

Why the probe cannot publish (four independent barriers):
1. The probe job has `permissions: {}`: no `id-token`, hence no OIDC token, hence no PyPI trusted publishing.
2. PyPI's trusted publisher for `aisef` is bound to workflow `release.yml` + environment `pypi`; the probe is a different
   workflow file.
3. The probe has one `echo` step: no checkout, no artifact, no `uses:`.
4. Neither probe tag matches `release.yml` (`v[0-9]+.[0-9]+.[0-9]+`, whole-name match) or `staging.yml`
   (`v*rc*`, `v*-rc*`, `v*.dev*`); and the owner **rejects** the pending deployment.

Cost: USD 0 (public repository, standard GitHub-hosted runner, one job of a few seconds per tag).

## 1. Owner configuration (persistent — this IS the control)

GitHub → repository `nghinh/aisef` → Settings → Environments → `pypi`:

| Setting | Value |
|---|---|
| Required reviewers | the owner (≥ 1 reviewer) |
| Prevent self-review | off (the owner is the only reviewer and the tagger) |
| Allow administrators to bypass | **off** |
| Deployment branches and tags | "Selected branches and tags" → one rule, **type Tag**, pattern `v[0-9]*.[0-9]*.[0-9]*` |

Read-only check after configuring (agent may run this; it calls only `GET` endpoints):

```bash
python3 -P docs/v2.3/drafts/relgov/relgov_evidence.py precheck > relgov-precheck.json
```

Exit 0 = protected (a `can_admins_bypass` note alone does not fail; the owner decides). Today it exits 1, truthfully:
no required reviewer, no tag policy. The predicate release.yml's `governance` job runs at tag time is
`validation/qualification/release_governance.py` (same GET endpoints, read-only; it needs `GITHUB_REPOSITORY` and a
token in `GITHUB_TOKEN`); its PASS is the precheck that counts.

## 2. Probe commit P (owner)

P is parented on `origin/master` and adds **only** `.github/workflows/relgov-probe.yml`
(`docs/v2.3/drafts/relgov/relgov-probe.yml`). P is never pushed to a branch; only the tags point at it.

Build P in a separate, detached worktree so the main checkout (on `release/v2.3-big`, which holds these scripts) is
untouched:

```bash
git fetch origin && git worktree add --detach ../relgov-p origin/master
git show release/v2.3-big:docs/v2.3/drafts/relgov/relgov-probe.yml > ../relgov-p/.github/workflows/relgov-probe.yml
git -C ../relgov-p add .github/workflows/relgov-probe.yml
git -C ../relgov-p commit -m "REL-GOV-01 probe (tag-only, never on a branch)"
git ls-remote --tags origin '*relgov-probe*'
```

The last command must print nothing. All later commands run from the main checkout.

## 3. Positive probe — the pause

```bash
git -C ../relgov-p push origin HEAD:refs/tags/v0.0.0-relgov-probe-1
```

1. Find the run: `gh run list -R nghinh/aisef --workflow relgov-probe.yml --limit 1`.
2. Wait (poll ≤ 600 s) until the `checkpoint` job shows **Waiting** for `pypi`.
3. Snapshot **before** acting: `python3 -P docs/v2.3/drafts/relgov/relgov_evidence.py snapshot RUN_ID pos-waiting.json`
   (records run, jobs, `pending_deployments`, approvals, UTC time; refuses to overwrite).
4. Owner **rejects** the deployment in the GitHub UI ("Review deployments" → Reject).
5. Snapshot again: `... snapshot RUN_ID pos-rejected.json`. Expected: approvals = rejected by the owner; the echo step never ran.

## 4. Negative probe — the tag restriction

```bash
git -C ../relgov-p push origin HEAD:refs/tags/relgov-probe-neg-1
```

Expected: the job fails at environment admission without ever being `waiting` (the tag does not match
`v[0-9]*.[0-9]*.[0-9]*`). Snapshot: `... snapshot RUN_ID neg.json`.

## 5. Cleanup (owner)

```bash
git push origin :refs/tags/v0.0.0-relgov-probe-1 :refs/tags/relgov-probe-neg-1
git -C ../relgov-p rev-parse HEAD
git worktree remove ../relgov-p
```

Record P's sha (the `rev-parse` output) before removing the worktree. Runs and the rejected review stay on GitHub as
evidence. Commit P is left unreferenced.

## 6. Evidence (agent, after the owner hands over the three snapshot files)

`docs/v2.3/evidence/rel-gov-01/REL-GOV-01-W1-PROBE.json` (Amendment A2 placement: never under `closure-evidence/`):
environment + policies raw JSON and their sha256, P and its parent,
positive and negative run ids with their snapshots, observed-at timestamps, cleanup, and verdict
`CHECKPOINT_PAUSES` + `TAG_RESTRICTED`, or the observed failure. A probe that does not pause is recorded as FAIL, never
retried into a PASS.
