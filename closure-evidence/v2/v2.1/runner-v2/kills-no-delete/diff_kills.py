"""Old (deleting) vs new (fresh-repo) versions of the two rewritten kill methods: the same mutants must fail each."""
import importlib.util, json, pathlib, shutil, subprocess, sys
W = pathlib.Path(sys.argv[1]); D = pathlib.Path(sys.argv[2]); GP = sys.argv[3]
spec = importlib.util.spec_from_file_location("mutation", W / "validation/v2/mutation.py")
m = importlib.util.module_from_spec(spec); sys.modules["mutation"] = m; spec.loader.exec_module(m)
TF = "tests/v2/test_v21_kills_adapters.py"
trees = {}
for ver in ("old", "new"):
    t = D / ver
    shutil.rmtree(t, ignore_errors=True)
    trees[ver] = m._pristine(W, t)[0]   # the runner's own COPY parts
(trees["old"] / TF).write_bytes(subprocess.run(["git", "-C", str(W), "show", f"HEAD:{TF}"], capture_output=True, check=True).stdout)
src = (W / "aisef2/app/adapters.py").read_text()
plan = [("Reviewer.review", "ReviewerReview.test_a_change_to_the_checkout_names_the_stage_it_happened_in"),
        ("tree_of", "TreeOf.test_an_empty_directory_or_a_directory_turned_into_a_link_named_dir_is_a_change"),
        ("_unchanged", "TreeOf.test_an_empty_directory_or_a_directory_turned_into_a_link_named_dir_is_a_change")]
def run(t, test):
    for p in t.rglob("__pycache__"): shutil.rmtree(p, ignore_errors=True)
    home = D / "home"; shutil.rmtree(home, ignore_errors=True); home.mkdir()
    env = {"PATH": GP, "HOME": str(home), "TMPDIR": str(home), "LANG": "C.UTF-8"}
    r = subprocess.run([sys.executable, "-B", "-m", "unittest", f"tests.v2.test_v21_kills_adapters.{test}"],
                       cwd=t, env=env, capture_output=True, text=True, timeout=300)
    return "PASS" if r.returncode == 0 else "FAIL"
out = []
for func, test in plan:
    for ver, t in trees.items():   # control on the unmutated module
        (t / "aisef2/app/adapters.py").write_text(src)
        assert run(t, test) == "PASS", (ver, test)
    for desc, msrc in m.mutants(src, func, m._enum_members(src, W)):
        row = {"target": func, "mutant": desc, "test": test}
        for ver, t in trees.items():
            (t / "aisef2/app/adapters.py").write_text(msrc)
            row[ver] = run(t, test)
        out.append(row)
        print(json.dumps(row), flush=True)
for t in trees.values():
    (t / "aisef2/app/adapters.py").write_text(src)
same = all(r["old"] == r["new"] for r in out)
print(json.dumps({"mutants": len(out), "same": same, "killed_old": sum(r["old"] == "FAIL" for r in out),
                  "killed_new": sum(r["new"] == "FAIL" for r in out),
                  "differ": [r for r in out if r["old"] != r["new"]]}))
