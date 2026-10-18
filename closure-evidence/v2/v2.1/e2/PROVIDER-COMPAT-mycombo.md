# E2 lane PF — provider compatibility and settings for the alias `mycombo` on 9router (2026-10-18)

Lane brief: the only lane allowed provider traffic, capped at one `GET /v1/models` and one preflight-only `aisef run`
(requests ≤ 4). Both were made, once each; nothing else of this lane touched the network. Worktree
`wf_830a4f0d-db8-1`, branch `lane/e2-provider`, HEAD `2ac9b80` before this commit; `aisef2/`, `tests/` and
`validation/v2/mutation.py` unchanged. Timestamps are `date` output (+07). The router key stayed in `NINEROUTER_API_KEY`:
curl expanded it inside the process (`--variable %NINEROUTER_API_KEY --expand-header`), the run received it only through
its child environment; every file committed here was scanned in-process for its value (none holds it).

## 1. What the kernel does with a route, and with a provider that reports another model (code at HEAD)

**Route.** `settings.load` (`aisef2/app/settings.py:163-168`): `route` must hold a slash; the provider is the text before
the first slash, the model everything after it (so the canary's `9router/ds/deepseek-v4-pro` has model
`ds/deepseek-v4-pro`), and `provider.name` must equal that provider:

```python
if not isinstance(route, str) or route.count("/") < 1 or not all(route.split("/", 1)):
    raise SettingsError("route is <provider>/<model>, one fixed route")
p = data["provider"]
if not isinstance(p, Mapping) or sorted(p) != list(PROVIDER_KEYS) or p["name"] != route.split("/", 1)[0]:
```

`Settings.model` (`settings.py:110-111`) is `route.split("/", 1)[1]`; `client.overlay` (`client.py:150-156`) gives the
client `{"model": route, "small_model": route, "provider": {provider: {"models": {model: {"name": model, "limit":
model_limit}}}}}` — for `9router/mycombo`: provider `9router`, model `mycombo`, declared with the settings' limits.

**Preflight** (`aisef2/app/preflight.py`). One listing and `chat_probes` one-token completions, each ledgered before and
after it is sent; what is compared:

```python
model = route.split("/", 1)[1]                                                             # :96
obs = {"route": route, "declared_model": model, "expected_served_model": served_model or model,
       "expected_listed_owner": listed_owner, "probes": []}                               # :97-98
row = next((x for x in (body.get("data") or []) if isinstance(x, dict) and x.get("id") == model), None)   # :104
obs["listing"] = {"http": code, "listed": row is not None, "id": ..., "owned_by": (row or {}).get("owned_by"), ...}  # :105
code, body = transport("/chat/completions", {"model": model, "messages": [...], "max_tokens": 16, "temperature": 0})  # :110
obs["probes"].append({"http": code, "served_model": body.get("model"),
                      "system_fingerprint": body.get("system_fingerprint") or NOT_EXPOSED, ...})          # :115-116
```

The verdict (`identity_problems`, `:128-140`): the listing must be HTTP 200 and hold the route's model; when
`listed_owner` is given it must equal the row's `owned_by`; **every** probe must be HTTP 200 and its reported `model`
must equal `served_model` (the route's model when none is given); and all probes must share one fingerprint value
(`NOT_EXPOSED` counts as a value):

```python
elif p["served_model"] != served:
    out.append(f"probe {i}: served by {p['served_model']!r}, not {served!r} (an alias or a re-route)")   # :136-137
fingerprints = {p["system_fingerprint"] for p in obs["probes"]}
if len(fingerprints) > 1:
    out.append(f"the deployment changed between probes ({len(fingerprints)} fingerprints)")              # :138-140
```

Any problem makes the verdict `OPAQUE`; `PREFLIGHT.json` is written either way (`:118-120`). Then `run.py`:

```python
pre = preflight.run(settings.route, settings.chat_probes, transport, out / "preflight", settings.served_model,
                    settings.listed_owner)                                                             # :580-581
rec["preflight"] = pre
if pre["verdict"] != "ATTESTED":
    raise preflight.IdentityStop("the route is not attested: " + "; ".join(pre["problems"]))             # :583-584
```

and `cli.py:98-100` turns the `IdentityStop` into `aisef run: refused: …`, exit **2**. **So a provider that reports a
different model name than `served_model` in any probe FAILS the run: no degradation to "provider_reported", no
session, no journal; the observation is recorded (PREFLIGHT.json, LEDGER.jsonl, and RUN.json's `preflight` and
`failure`, written by `execute`'s `finally`, `run.py:648-675`).** A backing model that varies *between* probes fails
for the same reason whatever `served_model` says (at most one value can match); one that varies *between runs* fails
the runs whose preflight saw another name. The level `provider_reported` exists only in the experiment harness's manifest
vocabulary (`validation/experiments/harness.py:45`, `IDENTITY = ("verified", "provider_reported", "unverified")`); the
kernel has one level, ATTESTED, and one alternative, refusal. Two more facts of the same code:

* the preflight reads token usage in OpenAI shape only — `usage.get("prompt_tokens") or 0` (`preflight.py:112-114`): an
  Anthropic-shaped answer (`usage.input_tokens`) would ledger **0** tokens silently, against the "unknown is never 0" rule
  (`usage.py`), while `body.get("model")` still attests it; the three answers measured here were OpenAI-shaped;
* `client_identity(exe)` (`run.py:308-315`) runs `<exe> --version` — but only after an ATTESTED preflight (`:588`), so a
  refused run never starts the client. The probe below kept the real client off the PATH anyway.

**Where the key comes from** (`run.py:574-579`): `client.configured_provider(settings.provider)` must name the attested
endpoint in the client's own configuration (XDG_CONFIG_HOME, else `~/.config/opencode/opencode.json`), and the preflight's
key is `os.environ[api_key_env]` when `api_key_env` is set, else the configuration's key.

**`--check` makes no provider request** (`cli.py:82-95`): `check_git`, `check_repository` (a local clone), `admit`,
`confine.measure` only with `confinement`, `ocr_identity` only with `review.finder: ocr`; no transport is built. Verified
by reading, not by packet capture.

## 2. How 9router lists `mycombo` (one `GET /v1/models`, 2026-10-18 12:51:01 +0700, HTTP 200, 512,468 bytes)

`listing/models-mycombo.json`: 1,182 models; `owned_by` values `or` 462, `freellm` 415, `kira-ai` 107, `nvidia-gemma` 82,
`gh` 46, `cx` 15, **`combo` 14**, `mt` 9, `gemini` 8, `max` 8, `ds` 7, `minimax` 4, `fm` 3, `gemma4-26b` 1, `tr` 1.
Exactly one row has id `mycombo`:

```json
{"id": "mycombo", "object": "model", "owned_by": "combo"}
```

It carries **no** `context_length`, `max_completion_tokens` or `capabilities` — none of the 14 `combo`-owned aliases
(`code`, `agent`, `free`, `fast`, `vision`, `local`, `tts`, `mycombo`, `openclaw`, `strix`, `open-design`, `image`,
`goe`, `bread`) does, while 1,168 of the other rows do. The backing model the probes reported, MiniMax-M3, is listed
under six other owners with `context_length` 1,048,576 and `max_completion_tokens` 512,000 (`listing/models-minimax.json`);
which of them `mycombo` routes to is not stated by the listing.

## 3. The settings (`settings/`), from canary tier-2b's `settings-t3.json`, for `mycombo`

| file | sha256 | differs from the others |
|---|---|---|
| `arm-direct.json` | `1bf16ca7…` | identical to `arm-aisef.json` (the loader demands every key; the direct arm reads `route`, `provider.model_limit`, `client_env`, `budget`, `max_turns_per_session`, `timeouts_s.developer` — `tests/v2/test_v21_experiment.py:83-88`) |
| `arm-aisef.json` | `1bf16ca7…` | no `review` key → 2.0.0's rule, `REVIEW_ABSENT` (`settings.py:51`) |
| `arm-aisef-plus.json` | `334723c5…` | `+ "review": {"policy": "fix-loop", "min_severity": "high", "finder": "model"}` |

Common content: `route 9router/mycombo`; `provider {name 9router, endpoint https://9router.vnteki.com/v1, api_key_env
NINEROUTER_API_KEY, served_model "MiniMax-M3", listed_owner "combo", model_limit {context 200000, output 32768}}`;
`client_env ["NINEROUTER_API_KEY"]`; `budget {provider_requests 58, turns 700, input_tokens 30000000, output_tokens
500000}` (EXPERIMENT-PLAN's hard ceilings); `max_turns_per_session 80`; `limits` = tier-2b's, every taxonomy owner
named; `timeouts_s {developer 1800, reviewer 900, tool 600, probe 120}` (the plan's); `preflight {chat_probes 3}` (the
canaries'); **no `prices`** (`settings.load` refuses `"prices": null` — `usage.price_problem` — so the key is absent;
`usage.cost` is then `{"value": null, "status": "unknown", "why": "the settings give no price table"}`, as the probe's
RUN.json shows).

Choices to know about: `served_model` is **the backing model the one probe observed**, not the alias — with
`"mycombo"` the kernel can never attest the route (section 4); `model_limit` is tier-2b's conservative pair, **not
verified** for `mycombo` (its row has no limits; MiniMax-M3 is listed elsewhere at 1,048,576 / 512,000 — declaring less
than the real context only makes the client compact earlier); `api_key_env` names the environment variable so the key
never lives in a committed file, and the client's own configuration must still route provider `9router` to the same
endpoint (`run.py:574-577`) with a literal key or `{env:NINEROUTER_API_KEY}` (passed through `client_env`).

Validation (all offline): `settings.load` OK ×3 (`preflight-mycombo/tools/validate_settings.py`); `aisef run --check`
on the rebuilt stock `calc-1-story` project `ready: true`, exit 0, for each of the three files and for the probe's
settings (`admission.admitted: true`, `plan_hash 0abab4fb…`).

## 4. The preflight-only probe (`preflight-mycombo/`, 12:54:38 → 12:54:48 +0700)

Pre-condition met: canary tier 1's `store-before.json` and `store-after.json` are identical (sha256 `09c621f5…` both).
Settings `probe-settings.json` = the first draft of `arm-aisef.json` (`served_model: "mycombo"`) with
`budget.provider_requests: 4` (1 listing + 3 probes; the first session request would exceed it). Environment: PATH with a
stub `opencode` (`tools/stubbin-opencode.sh`, refuses everything but `--version`) and `/opt/homebrew/bin:/usr/bin:/bin`
— the real client is at `~/.opencode/bin`, not on it; `XDG_CONFIG_HOME` → `tools/xdg-opencode.json`; `python3 -P -B`
under `nice -n 19`; `PYTHONPATH` = this worktree.

Result: **OPAQUE → refused, exit 2.** `run.stderr`: `aisef run: refused: the route is not attested: probe 0: served by
'MiniMax-M3', not 'mycombo' (an alias or a re-route); probe 1: …; probe 2: …`. Observation (`run/preflight/PREFLIGHT.json`):
listing HTTP 200, `id mycombo`, `owned_by combo` (owner check passed); probes HTTP 200 ×3, `served_model` **`MiniMax-M3`
×3**, `system_fingerprint` **`NOT_EXPOSED` ×3**. Spend: 4 requests, 6,147 input + 6 output tokens (2,049 / 2 per probe
for a 7-word prompt: the router's accounting includes what it prepends), `unaccounted: []`, cost `null`. No session
(`sessions: []`), no journal, no anchor; `store-before.json` == `store-after.json` (`89dd3be3…`). `EVIDENCE.json` names
RUN.json by `_content_sha` (canonical-content digest `2eab4933…`); the file's byte digest is `13fef552…`, identical in
scratch and here.

What this single run shows and does not: the router reports **the backing model's name** in `model`, so the alias can
be attested only by naming that backing model as `served_model`; within these 10 seconds it did not vary (3/3); it
exposes no fingerprint, so the kernel's drift detector (`preflight.deployment`, `fingerprint_fields`) is blind for this
route; nothing about the real client's behaviour with `mycombo` (dual-shape streaming) was measured — the client never
ran.

## 5. Risks for E2's validity from a varying backing model, and how the manifest should state identity

1. **Selection at the gate.** With `served_model: "MiniMax-M3"`, an `aisef`/`aisef+` run starts only when all three
   probes report MiniMax-M3; a run whose preflight sees another backing model is refused (exit 2, 4 requests spent,
   recorded). The `direct` arm has no preflight and runs whatever the router serves. Unless the harness probes before the
   direct session too (same `preflight.run`, same refusal), the arms sample different router states. Recommendation:
   the harness calls `preflight.run` with the arm's settings before `direct_arm` and refuses the arm on OPAQUE, so every
   arm of a pair starts under the same observed backing model; the refused attempts are kept as records.
2. **Within-run drift is unobserved.** The preflight measures 3 answers at start; the sessions' answers are the client's
   and the stream carries no model id (the tier-2 session streams hold no `modelID`/`providerID`/`model` field: 0
   matches). A run may begin on MiniMax-M3 and continue on another model with nothing in the evidence saying so.
3. **No fingerprint.** `system_fingerprint` NOT_EXPOSED: a deployment change is invisible even between probes.
4. **"Same model" is "same alias".** EXPERIMENT-PLAN's design keeps the model constant across arms and runs; here only the
   alias is constant. Each run's `PREFLIGHT.json` must be kept and the analysis stratified by `served_models` observed;
   a campaign in which the backing model changed between runs compares arms across models.
5. **Cost is `null` for every run** (no price table): the plan's stop rule "stop when known cost reaches the budget"
   cannot fire. The owner waived the cost concern; the campaign's stop must be restated in tokens and requests, and the
   final report gives tokens, not money, as the measure.
6. **Token accounting is the router's.** 2,049 input tokens for a 7-word probe: the router adds a prompt the operator does
   not see; token totals and ceilings (30M input) count it. Anthropic-shaped answers would ledger 0 preflight tokens
   (section 1); the sessions' tokens are what the client reports per step (`client.LIMITATION`).
7. **`model_limit` unverified**: 200,000 / 32,768 declared for a backing model listed at 1,048,576 / 512,000 elsewhere;
   conservative, shared by all arms, but a backing model smaller than 200k context would surface as provider errors.
8. **Budget asymmetry**: 58 requests include the 4 preflight requests for `aisef` arms and none for `direct` (its budget
   base is zeros, `test_v21_experiment.py:84`); the direct arm has 4 more session requests under the same ceiling.
9. **Client compatibility not measured**: the canaries ran OpenCode against 9router's DeepSeek route; `mycombo`'s dual
   answer shapes with the real client were not exercised by this lane (a 2026-09 note recorded 524s on long
   non-streaming answers for a different, custom client — not re-verified here).
10. **No kernel remedy in scope.** Accepting a set of served models, or a "provider_reported" mode, is a change to
    `aisef2/` (pinned for the measurement) and an owner decision; this lane changed no code.

**Manifest statement** (`harness.check` requires `model.identity_confidence` ∈ {verified, provider_reported,
unverified} with a `reason`; `pair_problems` requires the two arms of a pair to carry the same `model` object):

```json
"model": {"declared": "9router/mycombo", "route": "9router/mycombo", "served_model_expected": "MiniMax-M3",
          "listing": {"id": "mycombo", "owned_by": "combo", "limits": null},
          "identity_confidence": "provider_reported",
          "reason": "9router alias mycombo (owned_by combo) is served by a backing model the router names in every answer and may change per request (owner's statement); the lane's preflight-only probe on 2026-10-18 12:54 +07 saw MiniMax-M3 in 3/3 probes with no system_fingerprint; the client's sessions carry no model id, so identity within a run rests on that run's own preflight (ATTESTED only when all probes report served_model_expected), and the direct arm has none unless the harness probes before it"}
```

Use `provider_reported` only if every arm of the pair, the `direct` arm included, is gated by the same preflight and its
`PREFLIGHT.json` is kept with the result; otherwise the pair's level is `unverified` with the reason above, because the
direct arm's model is then not reported by anything in the evidence.

## Files

```
closure-evidence/v2/v2.1/e2/
  PROVIDER-COMPAT-mycombo.md               this report
  settings/arm-direct.json                 1bf16ca7…  (== arm-aisef.json)
  settings/arm-aisef.json                  1bf16ca7…
  settings/arm-aisef-plus.json             334723c5…
  listing/models-mycombo.json              the mycombo row, owner counts, row keys; listing-http.txt, listing-when.txt
  listing/models-minimax.json              the MiniMax rows with their listed limits
  preflight-mycombo/                       the one probe: README.md, record (run/), settings as run, store stats, tools/
```
