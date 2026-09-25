"""WP-6.2 — the single authoritative orchestration path (RFC §5, §26, §32), resumed under ARCHITECTURE-EXCEPTION-V2-005.

`story_runner.run_story` is the one path a story takes: approved contract -> ProductProofSpec -> probe at the parent ->
StoryAdmission -> StoryTransaction -> developer execution -> candidate proof -> independent verification ->
engineering-quality checks -> reviewer -> security -> merge -> post-merge re-proof -> disposal. Every decision is read
from the journal's projections; every stage writes its typed events (journal format 3); no V1 gate is consulted. The
only old-behaviour entry is the explicit migration seam (`seam`), removable in WP-6.3.
"""
