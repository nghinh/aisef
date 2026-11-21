# DRAFT: BUILD-REPRO-01 reproducibility contract (W1, lane L1-BUILD)

This is not published text until it lands. W1-DESIGN.md §6 (lane D5) applies:

* `README.md` and `docs/v2/**` are never edited on `release/v2.3-big`. This text lands on master at W6 (L6-RELEASE,
  owner-authorized).
* README is shipped (`release_rc.py` `SHIPPED`) and is frozen into `shipped_trees` at RC-FREEZE. Its part therefore
  lands on master and is merged into the branch **before RC-FREEZE**.
* The owner decides this at the W6 freeze:
  * (i) land the README part before RC-FREEZE (the default);
  * (ii) ship 2.3.0 with the 2.2 README and land this after PUBLISH. This must be recorded as a decision.
* `docs/v2/RELEASE-PROCESS.md` is not shipped. It lands in the same master commit.
* The historical README rows (`README.md:131`, `:144`, `:161`) stay untouched.

`tests/v23/test_v23_repro_contract.py` (`ContractPinnedToCi`) pins the text to CI:

* the contract's interpreter list is staging.yml's `repro` matrix;
* the backend pin is `pyproject.toml`'s;
* every clause below has its CI step;
* no leg can be skipped or have its failure swallowed, and each leg builds in the tree it names.

`PinsBite.REFERENCE` in that module is a `build` + `repro` pair that passes every pin. `PinsBite.VARIANTS` lists 23
negative fixtures, each failing at least one pin. L1-CIGOV's job may differ from the reference; the pins decide.

A clause changes only by an explicit amendment of this text and of that test, never by a silent edit. A diverging CI
leg is a measurement: fix it, or amend the contract explicitly and narrow the matrix.

## (a) `docs/v2/RELEASE-PROCESS.md`: replaces lines 97–99 up to "(`repro_dist.py`)."

This replaces the first sentence of the paragraph under "The published bytes are the frozen RC's", which begins
"Builds are reproducible:" and ends "re-packed deterministically (`repro_dist.py`).". The rest of that paragraph,
from "So the stable tag may sit on a later commit", stays as it is.

> The wheel and sdist of a commit are reproduced byte for byte by `SOURCE_DATE_EPOCH=$(python -P
> validation/qualification/release_rc.py --epoch) python -m build` + `repro_dist.py`, with the pinned
> `setuptools==84.0.0`, on GitHub-hosted `ubuntu-latest` CPython 3.11, 3.12, 3.13 and 3.14 — each build records its
> interpreter and runtime zlib version — from a fresh checkout and from a copy at another path whose files carry
> non-git permission bits and which contains `__pycache__/`, a stale `aisef.egg-info/`, `dist/` and `build/`. The
> frozen and published digests are those of the CPython 3.12 staging build; the published 2.2.0 files are rebuilt
> from tag `v2.2.0` on the same four interpreters. **Not claimed:** equality under another deflate implementation
> (e.g. zlib-ng) or another OS; a changed execute bit or a file added inside the shipped trees is a different source.

How each clause is tested:

| clause | tested by |
|---|---|
| `release_rc.py --epoch` + `python -m build` + `repro_dist.py` | `build` and every `repro` leg run `repro_dist.py dist/*.tar.gz dist/*.whl` after `python -m build`, so both published files are normalised (pinned: `test_the_repro_job_runs_every_clause`, `test_each_rebuild_leg_builds_where_it_claims_and_checks_both_files`) |
| `setuptools==84.0.0` | `pyproject.toml` `[build-system].requires == ["setuptools==84.0.0"]` (`test_the_build_backend_is_pinned_as_the_contract_states`) |
| `ubuntu-latest` CPython 3.11, 3.12, 3.13, 3.14 | the `repro` matrix equals this list, the job runs on `ubuntu-latest` and `needs: build` (`test_the_repro_job_runs_the_contract_s_interpreters_after_build`) |
| each build records its interpreter and runtime zlib | `repro_dist.py --toolchain` in `build` and in `repro`. It prints one JSON object: `sys.version`, `zlib.ZLIB_RUNTIME_VERSION`, `zlib.ZLIB_VERSION`, the `build` frontend version, the runner image (`ImageOS` `ImageVersion`) and OS/kernel/arch, with no host name (`ToolchainRecord`) |
| from a fresh checkout | `repro` builds in the checkout (no `cd` before `python -m build`) and runs `sha256sum -c` against `build`'s `SHA256SUMS` (artifact `dist-sha256`) |
| from a perturbed copy at another path | `repro_dist.py --perturb SRC DST` (`PerturbedCopy`); the build runs there (the last `cd` before `python -m build` is `cd DST`) and is checked by `sha256sum -c` against the same digests. The copy: files `0600`, or `0700` if they have an execute bit; directories `0700`; `__pycache__/` from `compileall`; a stale `aisef.egg-info/` (`Version: 0.0.0`, a `SOURCES.txt` naming a file a later commit removed); `dist/` and `build/` debris (the stale wheel is a real zip, so `dist/*.whl` reads it); no `.git` |
| independence from permission bits | `repro_dist.normalize` writes git's mode into the sdist: `0755` for a directory or any execute bit, else `0644` (`ModeNormalisation`; red before the fix: three mode variants of one sdist gave three digests). `repro_dist.normalize_wheel` does the same for the wheel. It rewrites only each member's mode in the zip central directory, and leaves `RECORD` on the wheel writer's constant. A wheel already on git's modes keeps every byte (`WheelModeNormalisation`; red before: the CLI could not read a wheel) |
| no leg skipped or swallowed | no `if:` and no `continue-on-error` in `build` or `repro`; no matrix `exclude:`; no `\|\|`, pipe, background `&`, `set +…` or `exit 0` in a `repro` run. Every rebuild leg starts with `set -eu` and runs build, then normalise, then check (`test_no_leg_can_be_skipped_or_its_failure_swallowed`, `test_each_rebuild_leg_builds_where_it_claims_and_checks_both_files`) |
| the frozen digests are the CPython 3.12 staging build's | staging `build` runs `python-version: "3.12"` on `ubuntu-latest` (`test_the_contract_claims_the_four_interpreters_and_the_3_12_staging_build_freezes`) |
| the published 2.2.0 files rebuilt from tag `v2.2.0` | `repro` checks the tag out (`git worktree add … v2.2.0`, then `cd` into it), rebuilds it with `SOURCE_DATE_EPOCH` = `V2.2.0-RC2-FREEZE.json` `rc.source_date_epoch` and compares the result to its `artifacts.sha256` (`8c94dd6b…` / `102cda44…`). Unit half, CT-8 (`FreshCheckoutBytesUnchanged`): tag `v2.2.0` holds the RC2 shipped trees; on fresh-checkout modes the v2.3 `repro_dist` writes the v2.2.0 one's bytes, and also on perturbed modes, where the v2.2.0 one did not |
| a changed execute bit is a different source | `test_a_changed_execute_bit_is_a_different_source`, for the sdist (`ModeNormalisation`) and the wheel (`WheelModeNormalisation`) |
| (CR-17) the 2.2 kernel digest is unchanged | CT-9 (`KernelDigestOfTheReleasedKernel`): `aisef2.app.run.kernel_digest` and `release_rc.kernel_digest_at` both give `c2d356b1…` on tree `e865d65c` |

Measured locally on 2026-11-21. The raw record stays out of the tree (sha256
`e3a13036785857427e4feaa51825c9dcd52c86abf4c091d87e30d8cf9d9e2391`; its script `e76a3faf7cc9b0d4…`).
Toolchain: CPython 3.14.7, zlib 1.2.12, macOS arm64. Input: the published 2.2.0 sdist bytes (sha256 = the frozen
`102cda44…`), whose members are only `0644` files and `0755` directories. Results:

* the v2.3 `repro_dist` re-packs those bytes to `102cda44…` unchanged;
* a copy of them with perturbed member modes also re-packs to `102cda44…`;
* the v2.2.0 `repro_dist` re-packs that perturbed copy to `7a6cc804…`.

This measures only the re-pack. No local setuptools 84.0.0 rebuild was run: no network, and setuptools 84.0.0 is not
installed. The setuptools rebuilds on the four interpreters are the `repro` job's, and this draft claims nothing for
them until that job has run.

**The wheel (review finding L1B-R1, measured 2026-11-21).** The wheel also takes member modes from the build tree.
setuptools' `build_py` copies package data with `preserve_mode`, and `bdist_wheel` copies `dist-info/LICENSE` with
`shutil.copy`. A `.py` module is written afresh, so it does not keep its mode. RISK-REGISTER.md:11's "The wheel is
immune" is therefore wrong; correct it at W1 adjudication.

The measurement used two proxy toolchains: setuptools 58.0.4 with wheel 0.37.0 on CPython 3.9.6, and setuptools 65.5.0
with wheel 0.37.0 on CPython 3.11.4. Each tree went through sdist, extract, then a wheel from the extracted sdist,
under `SOURCE_DATE_EPOCH`. Before the fix:

* the fresh checkout and the `--perturb` copy gave different wheels;
* 13 of 221 members differed, by mode only (`0o100644` vs `0o100600`).

`repro_dist.normalize_wheel` on those same wheels:

* the fresh wheel keeps every byte (setuptools 58: `f722aa53…`; setuptools 65: `ab3e337f…`);
* the perturbed wheel becomes the fresh one, byte for byte, on both toolchains.

The record stays out of the tree (sha256 `9d9f47f26290b7958b1871f0f8c9d4d16c15938070e401536a1cd11afc8334c6`; its script `ed221a9ac79f388c…`).

Two things are not measured here:

* setuptools 84.0.0 itself;
* the published `8c94dd6b…` wheel. Its bytes are not available offline, so `normalize_wheel` being a no-op on it is
  measured only by the `repro` tag leg.

`RECORD` keeps its mode because the wheel writer sets it from a constant (`0o664` in the proxies). If 84.0.0 writes
another constant mode into some other member, the tag leg goes red, loudly, and the rule is amended explicitly.

To check in the first `repro` run (not measured here): setuptools' `manifest_maker` re-reads an existing
`SOURCES.txt` when no VCS file finder is installed. A stale `SOURCES.txt` that names a file which exists outside the
shipped trees could therefore add that file to the sdist. The perturbation uses the realistic stale case (an older
version, plus a file that no longer exists). If the run shows any other dependence, the contract is amended
explicitly.

## (b) README: the 2.3 sentence and the 2.3 release-table row

The sentence for the 2.3 "what changed" list:

> - **Reproducible builds under an explicit, tested contract.** The sdist no longer depends on the build tree's file
>   permission bits (`repro_dist.py` writes git's modes). CI rebuilds each release-branch commit on CPython 3.11–3.14,
>   from a fresh checkout and from a perturbed copy, and rebuilds the published 2.2.0 files from tag `v2.2.0`. Exactly
>   what is and is not claimed: [`docs/v2/RELEASE-PROCESS.md`](docs/v2/RELEASE-PROCESS.md).

The row for the 2.3 qualification table. Fill it only from the measured `repro` run of the RC commit. If a leg
diverged, the row says so, and the contract above is amended first:

> | reproducible build | wheel and sdist rebuilt byte for byte on CPython 3.11, 3.12, 3.13 and 3.14 (`ubuntu-latest`, `setuptools==84.0.0`), from a fresh checkout and from a perturbed copy (non-git permission bits, `__pycache__/`, stale `aisef.egg-info/`, `dist/`, `build/`), staging run `<run id>`; the published 2.2.0 files rebuilt from tag `v2.2.0` on the same four; not claimed for another deflate implementation or OS |
