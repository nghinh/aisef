# v2.3 W0 — Release-governance finding: the `pypi` environment is NOT protected

**Severity:** release-governance blocker (P1 for any production publish).
**Status:** OPEN — owner/admin remediation required (zero-paid, human-enforced).
**Found:** 2026-11-21, W0 verification (CLAUDE-CODE-OWNER-DIRECTIVE-v2.3 §A, §D "Release governance").

## Evidence (primary source, not memory)

GitHub REST API, `GET /repos/nghinh/aisef/environments/pypi`:

```
name: pypi
protection_rules: []
```

The `pypi` deployment environment that `.github/workflows/release.yml`'s `publish` job targets has
**no protection rules** — in particular **no required reviewer**. There is therefore **no interactive
owner approval gate** before a production PyPI upload.

## Consequence

- The 2.2.0 publish job "did not visibly pause" (owner observation, directive §A) because **there was
  nothing to approve** — not because an approval was granted. The earlier claim that "the owner clicks the
  `pypi` approval" was incorrect: that gate does not exist.
- Any tag matching `v[0-9]+.[0-9]+.[0-9]+` that passes `tests` + `staging` + `v2-gate` will **auto-publish**
  to production PyPI with no human pause. This currently includes the **in-flight 2.2.1 release**
  (run 44845176361): when its test matrix passes it will publish with no click.
- `RELEASE-DECISIONS.json` owner entries (seq 12, seq 13) are a *decision ledger*, not an *interactive,
  per-run GitHub approval*. The directive (§A, §D) explicitly forbids treating a ledger entry as the
  interactive gate. The `v2-gate` job reads the ledger, but nothing enforces a human stop at publish time.
- [W0-freeze 2026-11-21: 2.2.1 was abandoned and nothing was published; its seq 13 was withdrawn with the master force-restore to 399b775f. The ledger holds seq 1–12. Any v2.3 seq 13 exists only as the unapproved draft docs/v2.3/drafts/LEDGER-SEQ-13-DRAFT.md.]

## Remediation (owner/admin action — privileged, not performed by the agent)

Zero-paid, human-enforced. On GitHub (repo **Settings → Environments → `pypi`**):

1. Enable **Required reviewers** and add the **owner** (and/or a release-admin) as the reviewer.
2. Optionally add a **wait timer** and restrict deployment branches/tags to `v*.*.*`.

Result: `release.yml`'s `publish` job will pause in `status: waiting` until the owner clicks
**Review deployments → Approve** — the interactive gate the release charter (§19) intends.

This is a repo-settings change requiring admin rights; per directive §D it is an **owner/admin-controlled
operation**, so it is proposed here and **held** rather than applied by the agent.

## Gate for v2.3

Per directive §A/§C/§D: **no v2.3 production tag or PyPI publish** until this protection is configured and
verified (a dry-run that observes the `publish` job entering `waiting`). Recorded in `RISK-REGISTER.md` and
`MASTER-CHECKLIST.md` as `REL-GOV-01`.
