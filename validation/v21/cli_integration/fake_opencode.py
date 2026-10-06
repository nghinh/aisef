"""The integration run's developer: attempt 1 sums three arguments as two, attempt 2 refuses them (exit 2); S2 (the
continuation segment) exits 3 on a non-integer argument — and the first time, once its usage is reported, SIGKILLs the
`aisef run` whose pid run.sh wrote to kill-run2.pid (no `finally` runs: the request's result is never journaled).
Never the real client: run.sh puts it on PATH as `opencode` and removes every directory holding a real one."""
import json, os, pathlib, signal, sys
argv = sys.argv[1:]
if argv == ["--version"]:
    print("0.0.0-integration-fake"); raise SystemExit(0)
here = pathlib.Path(__file__).resolve().parents[1]
title, cwd = argv[argv.index("--title") + 1], pathlib.Path(argv[argv.index("--dir") + 1])
if title == "developer S2":
    (cwd / "app" / "cli.py").write_text("def main(args):\n    if len(args) != 2:\n        return 2\n    try:\n"
                                        "        return int(args[0]) + int(args[1])\n    except ValueError:\n        return 3\n")
    (cwd / "tests" / "test_nan.py").write_text("import unittest\n\nfrom app.cli import main\n\n\nclass T(unittest.TestCase):\n"
        "    def test_nan(self):\n        self.assertEqual(main(['x', '1']), 3)\n")
elif title.startswith("developer"):
    calls = sorted(here.glob("prompt-*.txt"))
    (here / f"prompt-{len(calls):02d}.txt").write_text(argv[-1])
    cli = ("def main(args):\n    if len(args) < 2:\n        return 2\n    return int(args[0]) + int(args[1])\n" if not calls else
           "def main(args):\n    if len(args) != 2:\n        return 2\n    return int(args[0]) + int(args[1])\n")
    (cwd / "app" / "cli.py").write_text(cli)
    (cwd / "app" / "__main__.py").write_text("import sys\n\nfrom app.cli import main\n\nsys.exit(main(sys.argv[1:]))\n")
    (cwd / "tests").mkdir(exist_ok=True)
    (cwd / "tests" / "__init__.py").write_text("")
    (cwd / "tests" / "test_cli.py").write_text("import unittest\n\nfrom app.cli import main\n\n\nclass T(unittest.TestCase):\n"
        "    def test_sum(self):\n        self.assertEqual(main(['2', '3']), 5)\n\n    def test_usage(self):\n        self.assertEqual(main([]), 2)\n")
print(json.dumps({"type": "text", "part": {"text": "done"}}))
print(json.dumps({"type": "step_finish", "part": {"tokens": {"input": 120, "output": 7, "reasoning": 3, "cache": {"read": 10, "write": 0}}}}))
pid, killed = here / "kill-run2.pid", here / "kill-run2.done"
if title == "developer S2" and pid.exists() and not killed.exists():
    sys.stdout.flush()
    killed.write_text("SIGKILL after the usage of 'developer S2' was reported\n")
    os.kill(int(pid.read_text()), signal.SIGKILL)
