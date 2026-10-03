# AISEF 2.0 — using the V2 runtime (`aisef run`)

AISEF 2.0 provides deterministic, evidence-bound orchestration and product verification for AI-assisted software
delivery. `aisef run` executes an owner-approved plan on a git repository: for each story a developer session (the
OpenCode client, on one fixed model route) changes the code, and the V2 kernel decides — from independent probes of
the product, never from the developer's word — whether the story is delivered, retried or rolled back. Every decision
is written to a hash-chained journal that the run directory keeps, and that `aisef run --verify` re-derives.

## Install

```bash
pip install aisef==2.0.0
```

Needs Python 3.11 or newer, `git`, and — for a live run — the `opencode` client on `PATH` and an OpenAI-compatible
provider endpoint whose key is in an environment variable you name. `aisef run --check` needs neither.

## What a run takes

**A project bundle** (`aisef-v2-project/1`, one JSON file): everything the run proves the project against.

| field | what it holds |
|-------|---------------|
| `name`, `description` | how the developer is told about the project |
| `requirements_document` | `{path, sha256}` — the requirements file in the repository at the plan's baseline (UTF-8, LF), checked before anything runs |
| `product_roots` | the top-level names of the project's own source (`["pkg", "tests"]`) |
| `requirements`, `contracts`, `approvals` | the kernel's Requirement, BehaviorContract and human ContractApproval objects, each sealed by its hash |
| `plan` | the Plan: its baseline commit and its obligations (criterion, ProductProofSpec, story, role INTRODUCE / PRESERVE / VERIFY) |
| `facts` | per criterion, the public facts the developer may be told: `requirement`, `section`, `clause`, `clause_text`, `subject` |
| `stories` | per story, `depends_on` and the `tests` paths its developer writes |

Loading re-checks every seal, requires a human approval binding each contract to each requirement it cites, and
compiles every contract with this release's probes; a plan naming a spec no approved contract compiles to is
refused. Before the run starts, the plan must pass static admission (the kernel's nine checks). AISEF 2.0 runs
bundles; it does not author them.

**Run settings** (`aisef-v2-run/1`, one JSON file). Every field is required — nothing is defaulted:

```json
{
  "format": "aisef-v2-run/1",
  "client": "opencode",
  "route": "myprovider/my-model",
  "provider": {"name": "myprovider", "endpoint": "https://api.example.com/v1", "api_key_env": "MYPROVIDER_API_KEY"},
  "client_env": ["MYPROVIDER_API_KEY"],
  "budget": {"provider_requests": 60, "turns": 700, "input_tokens": 60000000, "output_tokens": 400000},
  "max_turns_per_session": 80,
  "limits": {"DEVELOPER": 2, "PLAN": 0, "ENVIRONMENT": 1, "PROVIDER": 1, "INTEGRATION": 0, "REVIEW": 1, "SECURITY": 1},
  "timeouts_s": {"developer": 2400, "reviewer": 900, "tool": 120, "probe": 60},
  "preflight": {"chat_probes": 2}
}
```

`route` is `<provider>/<model>` and is the only model the client may use (main and small model alike).
`client_env` names the operator variables the client receives; its whole environment is otherwise built (PATH, HOME,
locale, XDG and temporary directories), never inherited. `limits` are the retries each failure owner may consume.
The key is read from `api_key_env` at run time and is never written anywhere.

## Commands

```bash
aisef run --check  --project bundle.json --settings run.json --repo ./myproject   # inputs + admission; no provider request
aisef run          --project bundle.json --settings run.json --repo ./myproject --out ./runs/r1
aisef run --verify --project bundle.json --out ./runs/r1                          # re-derive a finished run from its journal
```

Exit status: **0** the delivery verdict is PASS (`--check`: ready; `--verify`: VERIFIED) · **1** FAIL or NOT_REACHED
(`--verify`: REFUTED) · **2** refused before the run began — an input that does not hold, an unadmitted plan, an
identity stop; no session was started.

A run, in order: the repository is cloned (never written) at the plan's baseline and its requirements document
checked; the plan is admitted; a private probe interpreter is created (a venv without pip or the host's site
packages); the **preflight** lists the provider's models and sends `chat_probes` one-token completions — the route is
attested only if every answer was served by the declared model under one deployment fingerprint, otherwise the run
stops (an identity stop) before any session; then the stories run in dependency order. The budget is re-derived from
the evidence (the preflight ledger, the journal, the session streams) before and during every session; a ceiling
reached — or spend that cannot be accounted for — ends the run, and a session is stopped at its turn cap.

## The run directory

`--out` must not exist; a run directory is never reused, and nothing in it is removed.

| path | what it is |
|------|------------|
| `RUN.json` | the record: delivery verdict and why, story outcomes, ProductProof account, budget, sessions, final `main`, the journal's digest — written whatever ends the run (an exception, an interruption) |
| `run/journals/aisef-run.jsonl` | the raw journal (format 3, hash-chained): the authority for every decision |
| `repo/` | the project's clone: `main` is the delivered product, every candidate and merge is kept |
| `preflight/` | the preflight's ledger and observation |
| `sessions/` | one event stream per model session |
| `probe-python/` | the run's probe interpreter |

`delivery_verdict` is **PASS** only when every story of the plan committed, the budget was not reached and no story
was refused; **NOT_REACHED** when no story reached its gate. `plan_quality_verdict` is always `NOT_CLAIMED` in 2.0.

## What 2.0 claims, and what it does not

Claimed: deterministic, evidence-bound orchestration and product verification. Candidate code (what the developer
writes) runs only in the probe's agent process; the verdict comes from a controller that never imports it, over an
authenticated channel, so the candidate cannot manufacture a probe result. Raw run evidence is preserved.

Threat model: a trusted operator; generated code may be faulty or opportunistic. Not claimed: generalization across
arbitrary workloads, superiority over V1, model quality, hostile multi-tenant isolation, full isolation against a
malicious process of the same OS user, protection against the machine's owner. Probes run with the standard library
and the candidate's own source only (no third-party dependencies of the project). A model review is informational
and never blocks; the scanner (`ruff`, when installed) is informational.

Platforms: `aisef run` is supported on Linux and macOS. On Windows the package installs and the kernel's test suite
runs, but a live `aisef run` is not part of the 2.0 claim.

## Coming from AISEF 1.x

- `aisef run` is now V2. V1's execution command is `aisef legacy run …`, with the same options as 1.x `aisef run`;
  every other V1 command is unchanged.
- V1 projects are not V2 bundles: V2 runs approved behavior contracts and a static-admitted plan, not V1 story
  files. There is no automatic conversion in 2.0.
- V2 writes nothing into the project repository; its results are the run directory and the clone's `main`.
