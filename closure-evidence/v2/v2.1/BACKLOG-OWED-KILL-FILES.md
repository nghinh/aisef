# V2.1 — owed kill files (backlog): the 85 unpinned survivors of campaign 9

Owner decision 2026-10-19 (a): the 2.1 mutation record is recorded as an honest FAIL (not a faked PASS) and the
snapshot pinned; writing a killing test for each of these 85 survivors is **backlog**, not a blocker for the pin.
Each is an observable behaviour of the fix-window code that the suite does not pin (survivor audit: the blind skeptic
declined to call it equivalent). Source: closure-evidence/v2/v2.1/MUTATION-SUMMARY.json (NOT_PASSING) and
campaign-9/SURVIVOR-AUDIT-SUMMARY.md. Snapshot 4ec961e (code 69b0ea9).

**PRIORITY (security): aisef2/app/diagnostics.py::Sink.__init__ [L144 element 0 dropped]** — dropping a member of the
redaction set lets a secret containing a JSON-escaped character (quote/backslash/non-ASCII) reach an artifact verbatim
(reproducer: campaign-9/survivor-audits/wave2/W2-diagnostics-1-*.json). Shipped code is correct; it is just unpinned.

Total owed: 85. By target (survivors owed), most first:

| target | owed |
|---|---:|
| aisef2/app/bundle_cli.py::_assess | 15 |
| aisef2/app/bundle_cli.py::continue_from | 9 |
| aisef2/app/bundle_cli.py::_authentic | 7 |
| aisef2/app/lineage.py::usage_lineage | 7 |
| aisef2/app/bundle_cli.py::_ground | 5 |
| aisef2/app/bundle_cli.py::_declared | 4 |
| aisef2/app/bundle_cli.py::seal | 4 |
| aisef2/app/bundle_cli.py::with_commands | 4 |
| aisef2/app/lineage.py::_without_a_journal | 4 |
| aisef2/app/bundle_cli.py::_group | 3 |
| aisef2/app/bundle_cli.py::_record | 2 |
| aisef2/app/adapters.py::_declared | 1 |
| aisef2/app/bundle_cli.py::_known | 1 |
| aisef2/app/client.py::Budget.spend | 1 |
| aisef2/app/diagnostics.py::NOT_INSPECTED | 1 |
| aisef2/app/diagnostics.py::PERMISSIONS | 1 |
| aisef2/app/diagnostics.py::Sink.__init__ | 1 |
| aisef2/app/diagnostics.py::Sink._keep | 1 |
| aisef2/app/diagnostics.py::artifact_problems | 1 |
| aisef2/app/lineage.py::_journal_mismatch | 1 |
| aisef2/app/lineage.py::child_evidence | 1 |
| aisef2/app/lineage.py::claim_unread | 1 |
| aisef2/app/lineage.py::not_there | 1 |
| aisef2/app/lineage.py::unread_runs | 1 |
| aisef2/app/review_ocr.py::declared | 1 |
| aisef2/app/review_verify.py::bounded | 1 |
| aisef2/app/run.py::OCR_CHECKS | 1 |
| aisef2/app/run.py::execute | 1 |
| aisef2/probe/cli_invocation.py::CliInvocationProbe._observe | 1 |
| aisef2/probe/cli_invocation.py::HARNESS/answer_to | 1 |
| aisef2/probe/cli_invocation.py::HARNESS/finish | 1 |
| aisef2/probe/file_artifact.py::_worker_facts | 1 |

(32 targets, 85 survivors.) Concentrated in the window-rewritten files:
bundle_cli (migrate/seal/assess report fields of the PM-9 approval semantics) and lineage (usage/dirlineage
accounting). These are report-field key/structure behaviours tested by value on the declared path but not pinned by
key/structure. Writing them is tracked here; the pin does not wait on them.

Written 2026-10-20.
