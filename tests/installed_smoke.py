"""Clean-install smoke (docs/v2/V2-STABLE-RELEASE-CHARTER.md §9 "clean-install fixture", G6, G8).

Run by the interpreter of a fresh venv into which exactly the built wheel was installed, isolated (`-I`), so the
checkout can never be what gets imported:

    <venv-python> -I tests/installed_smoke.py <expected-version> [--product]

Checks: `aisef` and `aisef2` import from the installed artifact; the `aisef` console script reports the expected
version; V1's runtime data is packaged; with `--product`, the V2 runtime entry `aisef run` dispatches to
(`aisef2.app.cli.run`) is present. Not collected by unittest (no `test` prefix).
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
from importlib.resources import files


def problems(want: str, product: bool) -> list[str]:
    import aisef
    import aisef2

    out = [f"{m.__name__} imported from {m.__file__}, not from the installed artifact under {sys.prefix}"
           for m in (aisef, aisef2) if not pathlib.Path(m.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve())]
    if aisef.__version__ != want:
        out.append(f"aisef.__version__ is {aisef.__version__}, expected {want}")
    exe = shutil.which("aisef", path=str(pathlib.Path(sys.executable).parent))
    if not exe:
        out.append("the `aisef` console script is not installed next to this interpreter")
    else:
        got = subprocess.run([exe, "--version"], capture_output=True, encoding="utf-8").stdout.split()
        if got != ["aisef", want]:
            out.append(f"`aisef --version` printed {got}, expected ['aisef', {want!r}]")
    root = files("aisef")
    for rel in ("kit/prompts", "kit/rules", "kit/skills", "harness/assets"):
        d = root.joinpath(*rel.split("/"))
        if not (d.is_dir() and any(True for _ in d.iterdir())):
            out.append(f"packaged runtime data missing or empty: aisef/{rel}")
    if not root.joinpath("kit", "catalog.json").is_file():
        out.append("aisef/kit/catalog.json is not packaged")
    if product:
        try:
            from aisef2.app.cli import run
        except ImportError as e:
            out.append(f"the V2 runtime entry of `aisef run` is missing: {e}")
        else:
            if not callable(run):
                out.append("aisef2.app.cli.run is not callable")
    return out


if __name__ == "__main__":
    found = problems(sys.argv[1], "--product" in sys.argv[2:])
    for p in found:
        print(f"FAIL  {p}")
    print("installed smoke: " + ("FAIL" if found else f"PASS (aisef {sys.argv[1]})"))
    sys.exit(1 if found else 0)
