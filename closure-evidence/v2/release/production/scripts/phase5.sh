#!/bin/zsh
# Phase 5: the published artifacts, downloaded from PyPI, against the frozen RC2 digests.
SP=/private/tmp/claude-501/-Users-nghinh-Downloads-projects-ai-sdlc/845c9f11-719f-4f92-a0ed-4f4a07d6e27b/scratchpad
D=/tmp/aisef-2.0.0-pypi-artifacts; O=$SP/final/phase5
[[ ! -e $D && ! -e $O ]] || { echo "exists"; exit 2; }
mkdir -p $D $O && cd $D
source /tmp/aisef-2.0.0-final-verify/bin/activate
date -u +%FT%TZ > $O/started
pip download --no-cache-dir --no-deps aisef==2.0.0 > $O/pip-download.txt 2>&1; echo "exit $?" >> $O/pip-download.txt
curl -fsS https://pypi.org/pypi/aisef/2.0.0/json -o $O/pypi-2.0.0.json; echo "json exit $?" > $O/curl.txt
SDIST_URL=$(python -c "import json;print([u['url'] for u in json.load(open('$O/pypi-2.0.0.json'))['urls'] if u['packagetype']=='sdist'][0])")
curl -fsS -O "$SDIST_URL"; echo "sdist exit $? $SDIST_URL" >> $O/curl.txt
ls -la $D > $O/ls.txt
shasum -a 256 $D/* > $O/sha256.txt
python - > $O/compare.json <<PY
import json, hashlib, pathlib
FROZEN = {"wheel": "5e840f7b960cb20e0ad63b95e28c09fcafee696bf83e9771cccd03476f0eb40b",
          "sdist": "a7a1a5fb9bc6d211cc2329dab12f962ed27dd826754da8511b35c3ea1bbbef1d"}
d = pathlib.Path("$D"); j = json.load(open("$O/pypi-2.0.0.json"))
out = {"files": {}, "pypi_json": {}}
for f in sorted(d.iterdir()):
    kind = "wheel" if f.suffix == ".whl" else "sdist" if f.name.endswith(".tar.gz") else "other"
    h = hashlib.sha256(f.read_bytes()).hexdigest()
    out["files"][f.name] = {"kind": kind, "sha256": h, "frozen": FROZEN.get(kind), "match": h == FROZEN.get(kind)}
for u in j["urls"]:
    kind = "wheel" if u["packagetype"] == "bdist_wheel" else "sdist"
    out["pypi_json"][u["filename"]] = {"kind": kind, "sha256": u["digests"]["sha256"], "match": u["digests"]["sha256"] == FROZEN[kind],
                                       "upload_time_iso_8601": u["upload_time_iso_8601"], "yanked": u["yanked"]}
out["release_files_on_pypi"] = len(j["urls"])
out["verdict"] = "PASS" if out["files"] and all(v["match"] for v in out["files"].values()) and len(out["files"]) == 2 \
    and all(v["match"] for v in out["pypi_json"].values()) and len(out["pypi_json"]) == 2 else "FAIL"
print(json.dumps(out, indent=1))
PY
date -u +%FT%TZ > $O/finished
