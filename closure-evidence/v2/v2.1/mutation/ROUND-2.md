# Survivor work, round 2 — the 42 survivors of campaign 3 that no kill and no audit covered

Campaign 3 (snapshot f860e57) left 242 SURVIVED mutants; 200 were covered by a positional audit (144 AUDITED, 56 EQUIVALENT) and **42 were not**: the mutants of the product fixes (a function that changed has new strings and tuples) and the audits the fixes made unmappable. Seven batches (R01-R07) were written by one engineer-agent each and every one was re-run and attacked by an independent reviewer (tests that pass under two plausible wrong implementations, harmless rewordings, the `ast.unparse` null mutant, portability), under round 1's rules: test the requirement, no verbatim-text test to raise a number, AUDITED is not KILLED, an undefined requirement is OPEN and is the owner's.

**Result: 21 KILLED, 8 AUDITED, 3 EQUIVALENT, 9 OPEN, 1 DEFECT** (reviewer verdicts: {'CONFIRMED': 32, 'RECLASSIFIED': 1, 'REVISED': 9}).

| batch | target | idx | mutant | review | disposition | killed by |
|---|---|---|---|---|---|---|
| R01 | verify.py::_runspec_problems | 4 | L37 returns None | CONFIRMED | **KILLED** |  |
| R01 | verify.py::_runspec_problems | 9 | L37 element 0 dropped | CONFIRMED | **KILLED** |  |
| R01 | verify.py::_runspec_problems | 10 | L37 element 1 dropped | CONFIRMED | **KILLED** |  |
| R01 | verify.py::verify | 125 | L87 string ' cannot be read (' emptied | CONFIRMED | **KILLED** |  |
| R01 | verify.py::verify | 126 | L87 string ')' emptied | CONFIRMED | **AUDITED** |  |
| R01 | verify.py::verify | 127 | L91 string ' is not an evidence manifest (a JSON object holding its fi | CONFIRMED | **KILLED** |  |
| R01 | verify.py::verify | 151 | L73 string ')' emptied | CONFIRMED | **AUDITED** |  |
| R01 | verify.py::verify | 153 | L97 string 'an evidence file cannot be read (' emptied | CONFIRMED | **KILLED** |  |
| R01 | verify.py::verify | 154 | L97 string '): ' emptied | CONFIRMED | **KILLED** |  |
| R01 | verify.py::verify | 170 | L172 string 'the record cannot be re-derived from the evidence: ' empt | CONFIRMED | **KILLED** |  |
| R01 | verify.py::verify | 171 | L172 string ': ' emptied | CONFIRMED | **KILLED** |  |
| R01 | verify.py::verify | 174 | L122 string ')' emptied | CONFIRMED | **AUDITED** |  |
| R02 | confine.py::_judge | 142 | L409 element 2 dropped | CONFIRMED | **OPEN** |  |
| R02 | confine.py::_judge | 143 | L409 element 3 dropped | CONFIRMED | **OPEN** |  |
| R02 | confine.py::_judge | 157 | L409 string 'devpts' emptied | CONFIRMED | **OPEN** |  |
| R02 | confine.py::_judge | 158 | L409 string 'mqueue' emptied | CONFIRMED | **OPEN** |  |
| R02 | confine.py::_probe | 61 | L305 element 1 dropped | CONFIRMED | **KILLED** | test_a_subprocess_error_that_is_not_a_timeout_is_a_problem_not_a_crash |
| R02 | confine.py::_probe | 166 | L304 string ' seconds' emptied | CONFIRMED | **KILLED** | test_the_refusal_names_the_limit_and_its_unit |
| R02 | confine.py::measure | 40 | L255 element 3 dropped | CONFIRMED | **OPEN** |  |
| R02 | confine.py::measure | 49 | L255 string 'LANG' emptied | CONFIRMED | **OPEN** |  |
| R03 | lineage.py::_claimed_run | 6 | L74 string 'not a claim' emptied | CONFIRMED | **AUDITED** |  |
| R03 | lineage.py::account_of | 42 | L274 string 'sessions' emptied | RECLASSIFIED | **DEFECT** |  |
| R03 | lineage.py::account_of | 54 | L271 string '): what the sessions spent is unknown' emptied | CONFIRMED | **KILLED** | UnreadableSessionStream (test_a_step_whose_part_is_a_list, test_a_stream_that_cannot_be_op |
| R03 | lineage.py::claim | 68 | L145 string ' is claimed (' emptied | REVISED | **KILLED** | UnreadableClaimRefusal (test_a_directory_where_the_claim_is, test_it_is_the_newest_generat |
| R03 | lineage.py::claim | 69 | L145 string ') and the claim cannot be read (' emptied | REVISED | **KILLED** | UnreadableClaimRefusal (test_a_directory_where_the_claim_is, test_it_is_the_newest_generat |
| R03 | lineage.py::claim | 70 | L146 string '): not superseded without evidence' emptied | REVISED | **KILLED** | UnreadableClaimRefusal (test_a_directory_where_the_claim_is, test_it_is_the_newest_generat |
| R04 | bundle_cli.py::_shell_word | 5 | L154 string 'win32' emptied | REVISED | **KILLED** | test_the_hosts_own_default_is_the_one_its_platform_gets) |
| R04 | bundle_cli.py::_shell_word | 11 | L161 string 'a' emptied | CONFIRMED | **KILLED** | test_the_same_letters_are_quoted_once_a_character_needs_it) |
| R04 | bundle_cli.py::continue_from | 157 | L462 string 'carried: ' emptied | CONFIRMED | **AUDITED** |  |
| R04 | bundle_cli.py::coverage | 11 | L330 string 'clause -> criteria. Every clause of a bundle that loads i | CONFIRMED | **EQUIVALENT** |  |
| R04 | bundle_cli.py::explain | 31 | L385 string 'story' emptied | CONFIRMED | **AUDITED** |  |
| R05 | usage.py::no_progress | 13 | L130 element 2 dropped | CONFIRMED | **OPEN** |  |
| R05 | usage.py::no_progress | 23 | L130 string 'story/commit' emptied | CONFIRMED | **OPEN** |  |
| R05 | usage.py::usage | 94 | L100 string ' were sent and never answered: their cost is unknown (not | CONFIRMED | **KILLED** | test_the_status_names_the_requests_and_that_they_were_never_answered |
| R05 | usage.py::usage | 118 | L115 string '; ' emptied | CONFIRMED | **KILLED** | test_two_causes_are_not_run_together |
| R06 | preflight.py::http_transport | 13 | L47 element 0 dropped | REVISED | **AUDITED** |  |
| R06 | preflight.py::http_transport | 14 | L47 element 1 dropped | REVISED | **AUDITED** |  |
| R06 | preflight.py::http_transport | 17 | L61 element 0 dropped | CONFIRMED | **EQUIVALENT** |  |
| R06 | review_verify.py::detail | 22 | L257 True->False | REVISED | **OPEN** |  |
| R06 | review_verify.py::reproducer_contract | 28 | L111 element 0 dropped | CONFIRMED | **EQUIVALENT** |  |
| R07 | adapters.py::Reviewer._ocr | 198 | L176 string '..' emptied | REVISED | **KILLED** | ARowOfAnotherShapeIsRefusedWithItsRangeItsCauseAndItsFields.test_the_refusal_names_the_ran |
| R07 | adapters.py::Reviewer._ocr | 199 | L176 string ' printed a row of another shape: ' emptied | REVISED | **KILLED** | ARowOfAnotherShapeIsRefusedWithItsRangeItsCauseAndItsFields.test_the_refusal_names_the_ran |

## What changed in the product

* **DEFECT, fixed** — `aisef2/app/lineage.py::account_of` (mutant 42, found by the reviewer of R03): with a request in
  flight and `sessions` behind a link into a directory that cannot be traversed, `account_of` raised PermissionError
  on CPython 3.11-3.13 and, on 3.14.7 (the measured interpreter), returned `unaccounted == []`: a 0 shown as known,
  against the module's own rule "what the sessions spent and the evidence cannot show is unknown, not 0". The same
  lookups on an unsearchable run directory behaved the same. Fixed at one shared point (`_look`, inside the two `try`
  blocks the function already had; `os.path.isdir/isfile` for the two lookups outside any handler): absent evidence is
  answered exactly as before (31 states x CPython 3.11-3.14 differ from the unmodified module only where it raised or
  showed a known 0); 11 tests (`test_v21_defects_lineage2.py`); every kill file of the module passes as before (136
  tests on 3.14.7, 102 on each of 3.11, 3.12, 3.13). Merge `f06cd66`. **Because the module changed, every `lineage.py`
  target is re-measured by campaign 4.**
* Same family, **not changed** (reported by the fixer): `claims()`, `child_state` and `events_of` and
  `client.Budget.spend` have the same interpreter-dependent lookups for an unsearchable run directory; `claim`'s
  refusal-versus-traceback is a design decision. They are the owner's call.
* Test fixture change: R01's `unlink` of a manifest became a `rename` (INV-MUTATION-AUTHORITY: no new destructive site
  in a test); its six kills re-proven.

## OPEN — nine mutants, four decisions that are the owner's (each with a verified draft test for the answer "keep")

| # | question | mutants | what each answer does |
|---|---|---|---|
| Q-JUDGE | Is a *writable* `devpts`/`mqueue` mount outside `/dev/` "writable outside the workspace"? No document defines "host-backed"; the only rw devpts row ever measured is `/dev/pts` (already exempt), no mqueue row exists. | `confine._judge` 142, 143, 157, 158 | (a) exempt by file-system type: code unchanged, the draft test kills the four; (b) exempt only under `/dev/`: the tuple becomes `(tmpfs, proc)` and the four mutants are the code |
| Q-LANG | Does the measurement mirror the session's locale or run in a fixed one? `measure` passes `LANG` and drops `LC_ALL`; every recorded measurement ran `LANG=C`. NOT VERIFIED (macOS host): a non-English `LANG` installed under the sandbox's `/usr` may make a correct user-namespace refusal fail to match `USERNS_REFUSED` and refuse a correct session — a fail-closed false refusal; the Linux guest run can settle it. | `confine.measure` 40, 49 | (A) mirror (`LANG` and `LC_ALL`, refusal check made locale-proof): the draft kills both; (B) fixed `C`: a different test, and the `LANG` pass-through goes |
| Q-JOURNAL | Which journals does `no_progress` quantify over? The mutants differ only on a journal shape the writer admits and no producer writes (a story that observed failures and then committed). | `usage.no_progress` 13, 23 | the dossier of 2026-10-08 (`no_progress-13-23.md`): equivalent only on kernel-written journals (domain A); the owner picks the domain |
| Q-DETAIL | `review_verify.detail()` cuts to 1500 characters with `sort_keys`: once the cut bites, which fields survive is decided by key order (the reproducer's expected value versus the verdict prose). No test asserts `len(detail) <= 1500` at all. | `review_verify.detail` 22 | which part of the reproducer must survive; whether the cut leaves valid JSON; whether nested key order may matter |

The drafts for the answer "keep" are in `round-2-drafts/` (not in the suite, not named `test_*`).
