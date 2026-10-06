"""The inputs of the CLI integration run (run.sh): the authoring, the settings, the client configuration."""
import hashlib, json, pathlib, sys
I = pathlib.Path(sys.argv[1]); port = (I / "port").read_text().strip()
req = "R-CLI"
def contract(cid, argv, code):
    return {"id": cid, "requirement_ids": [req], "subject": {"kind": "cli_invocation", "locator": "app:__main__"},
            "stimulus": {"argv": argv}, "observable": {"exit_code": code, "within_s": 20}, "polarity": "MUST_HOLD",
            "subject_absence": "REQUIRES_SUBJECT", "rationale": "the requirement's own example"}
SUM, USAGE = "exits with the sum of the integers A and B", "exit 2 on a usage error (any other number of arguments)"
def crit(cid, con, clause, text):
    return {"id": cid, "contract": con, "role": "INTRODUCE", "depends_on": [], "why": f"S1 introduces {clause}",
            "facts": {"requirement": req, "section": "§1", "clause": clause, "clause_text": text, "subject": "python -m app"}}
authoring = {"format": "aisef-v2-authoring/1", "name": "calc-cli", "description": "A calculator command.",
             "requirements_document": {"path": "docs/requirements.md"}, "product_roots": ["app", "tests"], "baseline": "HEAD",
             "requirements": [{"id": req, "text": f"python -m app A B {SUM}; {USAGE}", "source": "docs/requirements.md §1"}],
             "contracts": [contract("BC-SUM", ["2", "3"], 5), contract("BC-USAGE-0", [], 2), contract("BC-USAGE-1", ["1"], 2)],
             "stories": {"S1": {"depends_on": [], "tests": ["tests/test_cli.py"], "criteria": [
                 crit("C-SUM", "BC-SUM", "1.1", SUM), crit("C-USAGE-0", "BC-USAGE-0", "1.2", USAGE),
                 crit("C-USAGE-1", "BC-USAGE-1", "1.2", USAGE)]}}}
(I / "authoring.json").write_text(json.dumps(authoring, indent=1))
ocr = pathlib.Path(sys.argv[2])
settings = {"format": "aisef-v2-run/1", "client": "opencode", "route": "fakeprov/model-1",
            "provider": {"name": "fakeprov", "endpoint": f"http://127.0.0.1:{port}/v1", "api_key_env": "FAKE_PROVIDER_KEY",
                         "served_model": "model-1", "listed_owner": "fake", "model_limit": {"context": 100000, "output": 8000}},
            "client_env": [], "budget": {"provider_requests": 40, "turns": 80, "input_tokens": 200000, "output_tokens": 20000},
            "max_turns_per_session": 10, "limits": {o: 1 for o in ("DEVELOPER", "PLAN", "ENVIRONMENT", "PROVIDER", "INTEGRATION", "REVIEW", "SECURITY")},
            "timeouts_s": {"developer": 60, "reviewer": 120, "tool": 120, "probe": 60}, "preflight": {"chat_probes": 2},
            "review": {"policy": "fix-loop", "min_severity": "high", "finder": "ocr",
                       "ocr": {"exe": str(ocr), "sha256": hashlib.sha256(ocr.read_bytes()).hexdigest(), "timeout_min": 2, "max_tokens": 4000}},
            "prices": {"currency": "USD", "input_per_mtok": 1.32, "cache_read_per_mtok": 0.044, "cache_write_per_mtok": 1.32,
                       "output_per_mtok": 3.96, "source": "integration fixture (not a real price)", "effective_date": "2026-10-06"}}
(I / "settings.json").write_text(json.dumps(settings, indent=1))
(I / "xdg" / "opencode").mkdir(parents=True, exist_ok=True)
(I / "xdg" / "opencode" / "opencode.json").write_text(json.dumps(
    {"provider": {"fakeprov": {"options": {"baseURL": f"http://127.0.0.1:{port}/v1", "apiKey": "{env:FAKE_PROVIDER_KEY}"}}}}))
