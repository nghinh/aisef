"""Step 3 — generate HTML mockups for each screen, then extract the visual contract.

Work is split according to the core principle:

* **Requires judgment -> delegate to model.** Layout, visual rhythm, button
  labels: one session per screen, loading only that screen's slice.
* **Requires correctness -> write code.** Rendering pages in a browser,
  extracting components and input constraints, verifying all screens,
  generating the index page: deterministic work, no model needed.

Screens are independent so re-runs only generate what is missing — existing
mockups are skipped to avoid paying twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..clients.base import ClientAdapter, RunSpec
from ..config import Config
from ..control.design_contract import CONTRACT_FILE, DesignContract, build
from ..control.experience import Experience, Screen, parse_experience_file
from ..control.machine_gate import GateResult, check_design_contract, is_route_like
from ..harness.guardrails import (
    ENV_PROJECT,
    ENV_STORY_ID,
    ENV_WORKDIR,
    ENV_WRITE_SCOPE,
    PLANNING_SCOPE,
)
from ..harness import browser
from ..harness.observe import EvidenceStore
from ..harness.prompts import load_catalog

MOCKUP_DIR = "mockups"
SKILL = "aisef-mockup-html"


@dataclass
class MockupResult:
    experience: Experience | None = None
    contract: DesignContract | None = None
    generated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    gate: GateResult | None = None
    index_path: Path | None = None
    cost_usd: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        if self.error or self.failed:
            return False
        return bool(self.gate and self.gate.passed)

    @property
    def needs_human(self) -> bool:
        """Mockup gate **always** warrants human review: the machine can check
        whether components exist, but not whether they are usable."""
        return True

    def machine_checks(self) -> dict[str, str]:
        checks = {"screens": str(len(self.experience.screens) if self.experience else 0)}
        if self.gate:
            checks["machine gate"] = "pass" if self.gate.passed else "fail"
            if self.gate.warnings:
                checks["warnings"] = "; ".join(self.gate.warnings)
        return checks

    def summary(self) -> str:
        if self.error:
            return f"mockup: ✗ {self.error}"
        n = len(self.experience.screens) if self.experience else 0
        lines = [
            f"mockup: {n} screen(s) — generated {len(self.generated)}, "
            f"skipped {len(self.skipped)}"
        ]
        for sid, why in self.failed.items():
            lines.append(f"  ✗ {sid}: {why}")
        if self.cost_usd:
            lines.append(f"  cost: ${self.cost_usd:.2f}")
        if self.gate:
            lines.append(self.gate.summary())
        if self.index_path:
            lines.append(f"  open: {self.index_path}")
        return "\n".join(lines)


def _spec(*, prompt: str, project: Path, cfg: Config) -> RunSpec:
    """Run spec for a mockup session, with the guard's inputs **declared**.

    Same reason as the plan phase: without an explicit env the guard reads
    the ambient one, and a stale `AISEF_STORY_ID` left in the shell turns the
    planning scope into an empty story scope that denies every write.
    """
    spec = RunSpec(
        prompt=prompt,
        workdir=project,
        max_turns=cfg["run.max_turns"],
        timeout_seconds=cfg["run.timeout_seconds"],
    )
    spec.env = {
        ENV_WRITE_SCOPE: ",".join(PLANNING_SCOPE),
        ENV_STORY_ID: "",
        ENV_PROJECT: str(project),
        ENV_WORKDIR: str(project),
    }
    return spec


def build_prompt(screen: Screen, experience: Experience, artifact_root: Path) -> str:
    """Prompt for a single screen — only its slice, not the full document."""
    rules = [
        f"- {name}: {experience.component_rules.get(name, '')}".rstrip(": ")
        for name in screen.components
    ]
    return load_catalog().get("mockup-screen").render(
        {
            "screen_id": screen.id,
            "screen_name": screen.name,
            "purpose": screen.purpose or "(not specified in document)",
            "reached_from": screen.reached_from or "(not specified in document)",
            # The UX table's column is "Route/state", which invites prose, and
            # the agent then copies the sentence verbatim into the meta tag —
            # `todo` shipped "Single initial document; no route change
            # required" as a route, the dev server answered 404, and the
            # mockup-map step blamed the app for missing every component.
            # Ask for a path when what the document holds is a description.
            "route": (
                f"`{screen.route}` — use this exact string in the aisef-route meta tag"
                if is_route_like(screen.route)
                else (
                    f"the document says \"{screen.route}\" — that is a description, not a path. "
                    f"Put the path the app really serves this screen at in the meta tag "
                    f"(`/` for a single-page app)"
                    if screen.route
                    else "(not declared in document — choose a reasonable path and declare it in the meta tag)"
                )
            ),
            "components": "\n".join(rules) or "- (not specified in document)",
            "states": ", ".join(screen.states) or "(default state only)",
            "artifact_root": artifact_root.name,
            "output": f"{artifact_root.name}/{MOCKUP_DIR}/{screen.id}.html",
        }
    )


def mockup_path(artifact_root: Path, screen_id: str) -> Path:
    return artifact_root / MOCKUP_DIR / f"{screen_id}.html"


def generate(
    project: Path | str,
    client: ClientAdapter,
    *,
    config: Config | None = None,
    force: bool = False,
    only: list[str] | None = None,
) -> MockupResult:
    """Generate missing mockups, extract the design contract, run the machine gate."""
    from ..harness.runlog import run_log
    from .plan import ARTIFACT_ROOT

    project = Path(project)
    root = project / ARTIFACT_ROOT
    cfg = config or Config.load(project)
    res = MockupResult()

    def _log(msg: str) -> None:
        run_log(root, f"mockup {msg}")

    screens_only = ",".join(only) if only else "all"
    _log(f"START screens={screens_only} force={force}")

    exp_file = root / "EXPERIENCE.md"
    if not exp_file.is_file():
        res.error = "EXPERIENCE.md not found — run `aisef plan` first"
        _log(f"ERROR {res.error}")
        return res

    res.experience = parse_experience_file(exp_file)
    if not res.experience.screens:
        res.error = "EXPERIENCE.md does not list any screens"
        _log(f"ERROR {res.error}")
        return res

    _log(f"screens_found={len(res.experience.screens)}")
    (root / MOCKUP_DIR).mkdir(parents=True, exist_ok=True)

    for screen in res.experience.screens:
        if only and screen.id not in only:
            continue
        path = mockup_path(root, screen.id)
        if path.is_file() and not force:
            res.skipped.append(screen.id)
            _log(f"screen={screen.id} SKIP exists")
            continue

        _log(f"screen={screen.id} agent START")
        run = client.run(
            _spec(
                prompt=build_prompt(screen, res.experience, root),
                project=project,
                cfg=cfg,
            )
        )
        res.cost_usd += run.cost_usd
        EvidenceStore(root).agent_run(f"mockup-{screen.id}", run, name=screen.id)
        if not run.ok:
            res.failed[screen.id] = run.error or "run failed"
            _log(f"screen={screen.id} FAIL ${run.cost_usd:.2f} err={res.failed[screen.id][:120]}")
            continue
        if not path.is_file():
            res.failed[screen.id] = f"completed but {path.name} not found"
            _log(f"screen={screen.id} FAIL ${run.cost_usd:.2f} err={res.failed[screen.id]}")
            continue
        res.generated.append(screen.id)
        _log(f"screen={screen.id} OK ${run.cost_usd:.2f}")

    res.contract, gate_extra = extract(root, res.experience)
    res.gate = gate_extra
    res.index_path = write_index(root, res)
    _log(f"DONE generated={len(res.generated)} skipped={len(res.skipped)} failed={len(res.failed)} ${res.cost_usd:.2f}")
    return res


def extract(
    artifact_root: Path,
    experience: Experience,
    stories: list | None = None,
) -> tuple[DesignContract, GateResult]:
    """Render mockups in a real browser, then extract the design contract and run the gate."""
    jobs = []
    for screen in experience.screens:
        html = mockup_path(artifact_root, screen.id)
        if html.is_file():
            jobs.append({
                "id": screen.id,
                "html": str(html),
                "png": str(html.with_suffix(".png")),
            })

    rendered = browser.render(jobs, project=artifact_root.parent)
    if rendered.unavailable:
        gate = GateResult("machine gate: mockup")
        # Do not pretend to pass. Without a browser the contract does not exist,
        # and the mockup-map step in phase 6 will have nothing to compare against.
        gate.errors.append(f"could not extract design contract: {rendered.unavailable}")
        return DesignContract(), gate

    contract = build(experience, rendered, artifact_root=artifact_root)
    contract.write(artifact_root)
    return contract, check_design_contract(contract, experience, stories)


def write_index(artifact_root: Path, res: MockupResult) -> Path | None:
    """Index page — lets the reviewer see all screens in one open.

    The mockup gate is a human gate: forcing them to open six files one by one
    means most will only open the first.
    """
    if not res.experience:
        return None
    rows = []
    for screen in res.experience.screens:
        c = res.contract.by_id(screen.id) if res.contract else None
        html = f"{screen.id}.html"
        exists = mockup_path(artifact_root, screen.id).is_file()
        status = "—"
        if c and c.error:
            status = f'<span class="bad">{_esc(c.error)}</span>'
        elif c and c.unresolved:
            status = f'<span class="warn">{len(c.unresolved)} unresolved</span>'
        elif c:
            status = f'<span class="ok">{len(c.components)} component · route {_esc(c.route or "?")}</span>'
        elif not exists:
            status = '<span class="bad">not generated</span>'

        shot = f'<img src="{screen.id}.png" alt="{_esc(screen.name)}">' if (
            artifact_root / MOCKUP_DIR / f"{screen.id}.png"
        ).is_file() else '<div class="noshot">no screenshot</div>'

        link = f'<a href="{html}">{_esc(screen.name)}</a>' if exists else _esc(screen.name)
        rows.append(
            f'<figure><figcaption><h2>{link}</h2>'
            f'<p class="purpose">{_esc(screen.purpose)}</p>'
            f'<p class="status">{status}</p></figcaption>{shot}</figure>'
        )

    html_doc = _INDEX_TEMPLATE.format(count=len(res.experience.screens), rows="\n".join(rows))
    path = artifact_root / MOCKUP_DIR / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_doc, encoding="utf-8")
    return path


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


_INDEX_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mockup — {count} screen(s)</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 15px/1.5 system-ui, sans-serif; margin: 0; padding: 2rem;
         background: Canvas; color: CanvasText; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 1.5rem; }}
  figure {{ margin: 0 0 2.5rem; }}
  figcaption h2 {{ font-size: 1.1rem; margin: 0 0 .25rem; }}
  .purpose {{ margin: 0; opacity: .75; }}
  .status {{ margin: .25rem 0 .75rem; font-size: .85rem; }}
  .ok {{ color: #1a7f37; }} .warn {{ color: #9a6700; }} .bad {{ color: #c0392b; }}
  img {{ max-width: 100%; border: 1px solid rgba(128,128,128,.4); border-radius: 6px; }}
  .noshot {{ padding: 2rem; border: 1px dashed rgba(128,128,128,.5);
            border-radius: 6px; text-align: center; opacity: .6; }}
  a {{ color: inherit; }}
</style></head>
<body>
<h1>Mockup — {count} screen(s)</h1>
{rows}
</body></html>
"""


def describe_contract(data: dict, artifact_root: Path) -> str:
    """Summarize the visual contract for the reviewer.

    Mockup reviewers need to **look**, so the first thing must be the index
    page path; the text only describes what the eye cannot see: which
    components became machine-verified commitments.
    """
    lines = [f"Open: {artifact_root / MOCKUP_DIR / 'index.html'}", ""]
    for screen in data.get("screens", []):
        head = f"{screen['id']:14} {screen.get('name', '')}"
        if screen.get("error"):
            lines.append(f"  ✗ {head} — {screen['error']}")
            continue
        lines.append(f"  {head}  route {screen.get('route') or '?'}")
        comps = screen.get("components", [])
        shown = ", ".join(f"{c['role']} \"{c['name']}\"" for c in comps[:6])
        more = f" … +{len(comps) - 6}" if len(comps) > 6 else ""
        lines.append(f"      contract: {shown or '(none)'}{more}")
        req = [f["label"] or f["name"] for f in screen.get("fields", []) if f.get("required")]
        if req:
            lines.append(f"      required fields: {', '.join(req)}")
        for u in screen.get("unresolved", []):
            lines.append(f"      ⚠️  unresolved: {u}")
    return "\n".join(lines)
