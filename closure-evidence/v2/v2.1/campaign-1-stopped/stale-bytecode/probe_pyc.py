"""probe_pyc.py: does a mutant written in the same second, with the same size, as the previous one run the previous
one's bytecode? (mutation.py rewrites the target in one copy tree and runs each kill file without -B)"""
import pathlib, subprocess, sys, time
d = pathlib.Path(sys.argv[1])
m = d / "mod_under_test.py"
out = []
for i in range(20):
    a = "def f():\n    return 1 < 2\n"
    b = "def f():\n    return 1 > 2\n"          # same size: an operator swap
    m.write_text(a)
    r1 = subprocess.run([sys.executable, "-c", "import mod_under_test as x; print(x.f())"], cwd=d, capture_output=True, text=True).stdout.strip()
    m.write_text(b)
    r2 = subprocess.run([sys.executable, "-c", "import mod_under_test as x; print(x.f())"], cwd=d, capture_output=True, text=True).stdout.strip()
    out.append((r1, r2))
    time.sleep(1.1)   # next pair in a fresh second
stale = sum(1 for r1, r2 in out if r2 == "True")
print(f"pairs {len(out)}; second write (1 > 2, expect False) ran the FIRST write's bytecode in {stale} pairs")
