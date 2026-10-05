"""Run under the hermetic env: what an OpenCode client or the attempt-4 check could reach here."""
import json, os, pathlib, shutil, sys
sys.path.insert(0, os.getcwd())
env = dict(os.environ)
home, data = pathlib.Path(env["HOME"]), pathlib.Path(env["XDG_DATA_HOME"])
store = pathlib.Path(env.get("XDG_DATA_HOME") or home / ".local/share") / "opencode" / "opencode.db"   # external_problems' formula
roots = {k: env[k] for k in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME")}
print(json.dumps({
    "env_names": sorted(env),
    "secret_like_names": sorted(n for n in env if any(w in n.upper() for w in ("KEY", "TOKEN", "SECRET", "OPENCODE", "AISEF", "API"))),
    "which_opencode": shutil.which("opencode"),
    "hermetic_roots_entries": {k: sorted(str(p.relative_to(v)) for p in pathlib.Path(v).rglob("*")) for k, v in roots.items()},
    "store_the_attempt4_check_reads": str(store), "store_exists": store.exists(),
    "opencode_state_paths_existing": [str(p) for p in (home / ".local/share/opencode", home / ".config/opencode", home / ".opencode",
                                                       data / "opencode", pathlib.Path(env["XDG_CONFIG_HOME"]) / "opencode",
                                                       pathlib.Path(env["XDG_STATE_HOME"]) / "opencode", pathlib.Path(env["XDG_CACHE_HOME"]) / "opencode") if p.exists()],
}, indent=1))
