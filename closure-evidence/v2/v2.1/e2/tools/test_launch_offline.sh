#!/bin/zsh
# test_launch_offline.sh [SCRATCH]: the launch kit end to end, OFFLINE — e2_setup.py (approver human:test, the dry run's
# loopback settings), then run_e2.sh with E2_OFFLINE=1, the dry run's fake client (installed as SCRATCH/fakebin/opencode)
# and --max-runs 2. No real client, no provider, no network, no lock: the only socket is the loopback fake provider in
# e2_launch.py's own process. PATH is stripped of ~/.opencode/bin and ~/.npm-global/bin before anything runs;
# NINEROUTER_API_KEY and CLIENT_EXE are unset (never read). Asserts: two RESULT.json (w1-a rep 1, direct then aisef:
# rep-major order), two summary rows, replay silent, `opencode` resolves to the fake on this PATH and on the recorded
# hermetic PATH, no key value and no NINEROUTER string anywhere under D, store_stat before == after, one status line.
set -eu
T=${0:A:h}; E2=${T:h}
SPD=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
S=${1:-$SPD/e2-launch-test/$(date +%Y%m%d-%H%M%S)}
[[ ! -e $S ]] || { echo "refused: $S exists" >&2; exit 2 }
mkdir -p "$S/fakebin" "$S/tmp"
cp "$E2/dry-run/tools/fake_opencode.py" "$S/fakebin/opencode"; chmod 755 "$S/fakebin/opencode"
cp -R "$E2/dry-run/reference" "$S/fakebin/ref"
export PATH=$S/fakebin:/opt/homebrew/bin:/usr/bin:/bin
unset NINEROUTER_API_KEY CLIENT_EXE
export TMPDIR=$S/tmp
fail() { echo "FAIL: $*" >&2; exit 1 }
echo "== $(date '+%F %T %z') offline test; scratch $S; PATH=$PATH; opencode=$(command -v opencode)"
[[ $(command -v opencode) == $S/fakebin/opencode ]] || fail "opencode on this PATH is not the fake"
nice -n 19 /opt/homebrew/bin/python3 -P -B "$T/e2_setup.py" "$S/D" --approver human:test --settings-dir "$E2/dry-run/settings-offline"
echo "== $(date '+%F %T %z') setup done"
rc=0; E2_OFFLINE=1 CLIENT_EXE=$S/fakebin/opencode zsh "$T/run_e2.sh" "$S/D" 2 || rc=$?
echo "== $(date '+%F %T %z') run_e2.sh exit $rc (3 = stopped at --max-runs 2: expected)"
[[ $rc == 3 ]] || fail "run_e2.sh exit $rc, expected 3"
D=$S/D
n=$(ls "$D"/out/*/RESULT.json | wc -l | tr -d ' '); [[ $n == 2 ]] || fail "RESULT.json count $n != 2"
[[ -f $D/out/w1-a-r1-direct/RESULT.json && -f $D/out/w1-a-r1-aisef/RESULT.json ]] || fail "the first two runs are not w1-a rep 1 direct, aisef"
rows=$(grep -c '^{' "$D/summary.txt"); [[ $rows == 2 ]] || fail "summary rows $rows != 2"
[[ ! -s $D/replay.txt ]] || fail "replay printed a difference: $(cat "$D/replay.txt")"
# a partial campaign (2 of 18 results) refuses --adopt-owner before it looks for any owner file
arc=0; adopt_out=$(nice -n 19 /opt/homebrew/bin/python3 -P -B "$T/e2_setup.py" "$D" --adopt-owner 2>&1) || arc=$?
[[ $arc == 1 && $adopt_out == *"the campaign is partial (2 of 18 results)"* ]] || fail "--adopt-owner on a partial campaign: exit $arc, output: $adopt_out"
echo "== $(date '+%F %T %z') --adopt-owner refused on the partial campaign (expected)"
/opt/homebrew/bin/python3 -P -B - "$D" "$S/fakebin/opencode" <<'EOF' || fail "launch record"
import json, pathlib, sys
d, fake = pathlib.Path(sys.argv[1]), sys.argv[2]
L = sorted((d / "launch").iterdir())[-1]
rec, end = json.loads((L / "launch.json").read_text()), json.loads((L / "end.json").read_text())
assert rec["mode"] == "offline" and rec["client"]["from"] == "CLIENT_EXE" and rec["client"]["realpath"] == fake, rec["client"]
assert rec["client"]["version"] == "0.0.0-dry-run-fake", rec["client"]["version"]
assert ".opencode/bin" not in rec["hermetic_path"] and ".npm-global" not in rec["hermetic_path"], rec["hermetic_path"]
assert "NINEROUTER_API_KEY" not in rec["env_names"] and "AISEF_DRYRUN_KEY" in rec["env_names"], rec["env_names"]
assert end["driver_exit"] == 3 and end["replay_exit"] == 0 and end["summary_exit"] == 0 and end["store_equal"] is True, end
assert end["secret_scan"]["files_holding_key_value"] == [], end["secret_scan"]
res = json.loads((d / "out" / "w1-a-r1-aisef" / "RESULT.json").read_text())
assert res["evaluation"]["satisfied"] == 12 and res["identity"] == "ATTESTED" and res["valid"], res["evaluation"]
print("launch record:", json.dumps({k: rec[k] for k in ("mode", "hermetic_path", "env_names")}), "end:", json.dumps({k: end[k] for k in ("driver_exit", "store_equal", "secret_scan")}))
EOF
! grep -rqF 'dry-run-loopback-key-not-a-secret' "$D" || fail "the fake key's value is under D: $(grep -rlF 'dry-run-loopback-key-not-a-secret' "$D")"
! grep -rqF 'NINEROUTER' "$D" || fail "NINEROUTER appears under D: $(grep -rlF NINEROUTER "$D")"
line=$(zsh "$T/e2_status.sh" "$D"); echo "status: $line"
[[ $(print -r -- "$line" | wc -l | tr -d ' ') == 1 && $line == *"done 2/18"* ]] || fail "status line: $line"
echo "== summary rows:"; cat "$D/summary.txt"
echo "== run.log tail:"; tail -n 8 "$D/run.log"
echo "== $(date '+%F %T %z') PASS (scratch kept at $S)"
