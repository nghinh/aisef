---
name: mockup-screen
version: 3
role: designer
---
Use the aisef-mockup-html skill.

Build the mockup for **one** screen.

screen_id: {{ screen_id }}
Screen name: {{ screen_name }}
Purpose: {{ purpose }}
Reached from: {{ reached_from }}
Route: {{ route }}

Required components (from EXPERIENCE.md) and behavioral rules:
{{ components }}

States to render: {{ states }}

Read: {{ artifact_root }}/DESIGN.md (visual tokens), {{ artifact_root }}/EXPERIENCE.md
(Information Architecture, Component Patterns, State Patterns sections),
{{ artifact_root }}/prd.md (real content to populate).

Write exactly one file: {{ output }}

If the input documents contain open questions, unresolved items, or
provisional assumptions, resolve each one with the simplest reasonable
MVP default and implement it. Do NOT use `data-unresolved` or leave
placeholders — every decision point must have a concrete implementation.
