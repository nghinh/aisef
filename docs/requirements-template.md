# [Project Name]

<!--
  AISEF Requirements Template
  ===========================
  This file is the SINGLE INPUT to the AISEF framework.
  Everything below drives planning, architecture, stories, implementation,
  and verification. Be specific — vague requirements produce vague code.

  Instructions:
  1. Copy this file to your project as docs/requirements.md
  2. Fill in every section. Delete sections that don't apply.
  3. Run: aisef setup && aisef plan

  Tips:
  - State WHAT you want, not HOW to build it (architecture is a later step).
  - Each requirement should be testable — "fast" is not testable, "loads in
    under 2 seconds on 3G" is.
  - Constraints matter more than features. State them clearly.
-->


## 1. Project overview

<!--
  One paragraph: what is this project, who is it for, and what problem
  does it solve? The planning agent reads this first.
-->

[Describe the project in 2-3 sentences. Example: "A personal finance tracker
that runs entirely in the browser. No server, no accounts. Users categorize
transactions and see spending trends."]


## 2. Users and personas

<!--
  Who uses this? Each persona drives different requirements.
  Don't over-engineer — one or two personas is enough for most projects.
-->

| Persona | Description | Primary goal |
|---------|-------------|--------------|
| [Name]  | [Who they are, context] | [What they need to accomplish] |


## 3. Functional requirements

<!--
  Number each requirement as FR-N. Each one must be:
  - Specific enough to write a test for
  - Independent enough to implement in one story
  - Expressed as user-visible behavior, not internal implementation

  Bad:  "The app should be user-friendly"
  Good: "FR-1: Create a new note with a title (required) and body (optional).
         The note appears at the top of the list immediately after saving."
-->

- FR-1: [First functional requirement]
- FR-2: [Second functional requirement]
- FR-3: [Third functional requirement]


## 4. Non-functional requirements

<!--
  Performance, accessibility, security, compatibility.
  Each one must be measurable.

  Bad:  "The app should be secure"
  Good: "NFR-1: All user data stored in localStorage only; no network
         requests leave the browser."
-->

- NFR-1: [First non-functional requirement]
- NFR-2: [Second non-functional requirement]


## 5. Constraints

<!--
  Hard limits the architecture MUST respect. These override preferences.
  Examples: "must work offline", "budget under $X/month", "no vendor lock-in",
  "must run on Node 20+", "data must stay in EU".
-->

- [Constraint 1]
- [Constraint 2]


## 6. Technology preferences

<!--
  Optional. If you have preferences, state them. If not, delete this section
  and the planning agent will choose based on the requirements.

  Be specific: "React + TypeScript + Vite" is better than "a modern framework".
  Include testing tools: the framework will auto-detect them, but explicit is
  better.
-->

| Layer | Choice | Reason |
|-------|--------|--------|
| Frontend | [e.g., React + TypeScript + Vite] | [why, or "team standard"] |
| Backend | [e.g., none — client-only] | |
| Database | [e.g., localStorage / PostgreSQL] | |
| Testing | [e.g., Vitest + Playwright] | |
| Styling | [e.g., Tailwind CSS] | |


## 7. Out of scope

<!--
  Explicitly stating what you will NOT build prevents scope creep in planning.
  The agent will not generate requirements, stories, or code for items listed here.
-->

- [Feature or concern that is explicitly out of scope]
- [Another exclusion]


<!--
  ═══════════════════════════════════════════════════════════════════════
  OPTIONAL SECTIONS — delete any that don't apply to your project.
  ═══════════════════════════════════════════════════════════════════════
-->


## 8. Existing system context (brownfield only)

<!--
  Fill this section ONLY if you are adding AISEF to an existing codebase.
  For new (greenfield) projects, delete this entire section.

  After filling this in, run: aisef baseline
  The baseline command will scan your codebase and generate a detailed
  snapshot automatically. This section gives the planning agent your intent.
-->

### Current state
- Repository: [URL or "local only"]
- Primary language(s): [e.g., Python 3.11, TypeScript 5.x]
- Size: [approximate — e.g., "~50 source files", "~15K LOC"]
- Test coverage: [e.g., "~60% with pytest", "no tests"]

### What to change
<!--
  Describe ONLY what you want to add or modify. Do not describe the whole app.
  The baseline scan captures the current state; you describe the delta.
-->

[Describe the change you want to make to the existing codebase.]

### What to preserve
<!--
  Explicitly list behavior, APIs, or modules that MUST NOT change.
  The framework will enforce this via preservation gates.
-->

- [API endpoint or behavior that must remain unchanged]
- [Database schema that must not be altered]


## 9. UI/UX requirements

<!--
  Fill this section if the project has a user interface.
  List screens/views — each one becomes a mockup in the planning phase.
  Keep descriptions behavioral, not visual: "a list of notes sorted by
  date" rather than "a card grid with shadows".
-->

### Screens

| Screen | Purpose | Key interactions |
|--------|---------|-----------------|
| [Screen name] | [What it shows] | [What the user does here] |

### Accessibility
- [e.g., "WCAG 2.1 AA compliance"]
- [e.g., "Full keyboard navigation"]


## 10. Data model (if known)

<!--
  Optional. If you already know the data shape, describe it here.
  The architecture step will refine it, but starting with your mental model
  helps alignment.
-->

| Entity | Fields | Notes |
|--------|--------|-------|
| [Entity] | [key fields] | [relationships, constraints] |


## 11. Integration points

<!--
  External systems this project talks to. Each becomes an interface in
  the architecture and a verification target.
-->

| System | Protocol | Purpose | Auth |
|--------|----------|---------|------|
| [System name] | [REST/gRPC/WebSocket/...] | [What data flows] | [API key/OAuth/...] |


## 12. Deployment requirements

<!--
  Where and how this runs in production. Drives the devsecops phase.
-->

- Target environment: [e.g., "Vercel", "AWS ECS", "self-hosted Docker"]
- CI/CD: [e.g., "GitHub Actions", "none yet"]
- Monitoring: [e.g., "Grafana + Prometheus", "not required for MVP"]
