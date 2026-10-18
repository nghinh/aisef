"""Tests for the evidence-discipline linter (story 10.8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.ci.evidence_discipline import (
    CITATION_RE,
    FIGURE_RE,
    _is_target_line,
    _skip_line,
    scan_repository,
)


def test_figure_regex_matches_latency_units() -> None:
    """The grammar captures latency / throughput / memory units."""
    assert FIGURE_RE.search("p95 first partial is 250 ms")
    assert FIGURE_RE.search("up to 128 concurrent streams") is None
    assert FIGURE_RE.search("12 GB VRAM")
    # The grammar lists a fixed set of units; the realtime factor target sits in
    # code, so it is exempt from the figure scan. The linter relies on the
    # `target:` prefix for that fact, not on the unit vocabulary.


def test_figure_regex_ignores_inline_ids() -> None:
    """Numbers embedded in identifiers are not figures."""
    assert FIGURE_RE.search("schema_version=2") is None
    assert FIGURE_RE.search("peer_120s") is None


def test_citation_recognises_run_id_forms() -> None:
    hit = CITATION_RE.search("run_id: bench-001")
    assert hit is not None and hit.group("run") == "bench-001"
    paren = CITATION_RE.search("(run_id bench-001)")
    assert paren is not None and paren.group("run_paren") == "bench-001"


def test_target_marker_passes_without_citation() -> None:
    """AC5: a target prefix lets the NFR-1 table exist in the repo."""
    assert _is_target_line("target: p95 first partial < 300 ms", (20, 28)) is True


def test_observed_marker_does_not_save_a_measurement() -> None:
    """AC5: an observed value marked as a target still fails."""
    assert _is_target_line("observed: p95 first partial 250 ms", (30, 38)) is False


def test_skip_line_drops_blank_and_comment_lines() -> None:
    assert _skip_line("", in_fence=False)[0]
    assert _skip_line("# heading", in_fence=False)[0]
    assert _skip_line("    indented code", in_fence=False)[0]
    assert not _skip_line("p95 latency 250 ms", in_fence=False)[0]


def test_skip_line_tracks_fenced_blocks() -> None:
    skip, still_in = _skip_line("```python", in_fence=False)
    assert skip and still_in
    skip, still_in = _skip_line("code with 250 ms", in_fence=still_in)
    assert skip and still_in
    skip, still_in = _skip_line("```", in_fence=still_in)
    assert skip and not still_in


def test_scan_reports_uncited_figure(tmp_path: Path) -> None:
    file_path = tmp_path / "doc.md"
    file_path.write_text("p95 first partial latency is 250 ms with no citation\n", encoding="utf-8")
    result = scan_repository(roots=[file_path], run_ids=set())
    assert any(f.file == file_path for f in result.findings)


def test_scan_accepts_cited_figure(tmp_path: Path) -> None:
    file_path = tmp_path / "doc.md"
    file_path.write_text(
        "p95 first partial latency is 250 ms (run_id bench-001)\n", encoding="utf-8"
    )
    result = scan_repository(roots=[file_path], run_ids={"bench-001"})
    assert not any(f.file == file_path for f in result.findings)


def test_scan_accepts_benchmark_pending(tmp_path: Path) -> None:
    file_path = tmp_path / "doc.md"
    file_path.write_text(
        "documented capacity: 128 streams (run_id benchmark.pending)\n", encoding="utf-8"
    )
    result = scan_repository(roots=[file_path], run_ids={"benchmark.pending"})
    assert not any(f.file == file_path for f in result.findings)
    assert result.accepted_placeholders >= 1


def test_scan_accepts_target_lines(tmp_path: Path) -> None:
    file_path = tmp_path / "doc.md"
    file_path.write_text("- target: p95 first partial < 300 ms\n", encoding="utf-8")
    result = scan_repository(roots=[file_path], run_ids=set())
    assert result.accepted_targets == 1
    assert not any(f.file == file_path for f in result.findings)


def test_scan_flags_invalidated_citation(tmp_path: Path) -> None:
    """AC4: a citation to a run no longer in the registry is missing now."""
    file_path = tmp_path / "doc.md"
    file_path.write_text("latency: 250 ms (run_id retired-run)\n", encoding="utf-8")
    result = scan_repository(roots=[file_path], run_ids={"different-run"})
    assert any(f.file == file_path for f in result.findings)


def test_scan_returns_findings_with_file_and_line(tmp_path: Path) -> None:
    file_path = tmp_path / "doc.md"
    file_path.write_text(
        "first line\nsecond line contains 250 ms without citation\n", encoding="utf-8"
    )
    result = scan_repository(roots=[file_path], run_ids=set())
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.line_number == 2
    assert "250 ms" in finding.figure


def test_scan_skips_fenced_code_blocks(tmp_path: Path) -> None:
    file_path = tmp_path / "doc.md"
    file_path.write_text(
        "```\nthis 250 ms is inside a code block and should not be flagged\n```\n",
        encoding="utf-8",
    )
    result = scan_repository(roots=[file_path], run_ids=set())
    assert not result.findings


def test_scan_includes_unkeyed_starts_with_placeholder(tmp_path: Path) -> None:
    """A figure with the placeholder token on the same line is accepted."""
    file_path = tmp_path / "doc.md"
    file_path.write_text("Throughput: 1024 rps (benchmark.pending)\n", encoding="utf-8")
    result = scan_repository(roots=[file_path], run_ids=set())
    assert not any(f.file == file_path for f in result.findings)


def test_main_returns_nonzero_on_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from infrastructure.ci import evidence_discipline

    file_path = tmp_path / "doc.md"
    file_path.write_text("latency 250 ms uncited\n", encoding="utf-8")
    exit_code = evidence_discipline.cli_main(
        [
            "--root",
            str(file_path),
            "--report",
            str(tmp_path / "report.json"),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "uncited" in captured.out
    assert (tmp_path / "report.json").exists()
