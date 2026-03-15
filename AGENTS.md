# AGENTS.md

This file defines the root-level guidance for agents working in this repository. Add concise, reusable notes here as implementation progresses.

## Project State

- The repository is in planning and scaffolding stage.
- The current implementation plan lives in [tasks/prd.json](/home/robert/repos/private-ledger/tasks/prd.json).
- The current human-readable implementation PRD lives in [tasks/prd-private-ledger.md](/home/robert/repos/private-ledger/tasks/prd-private-ledger.md).

## Working Rules

- Keep changes tightly scoped to the current story.
- Prefer simple, local-first architecture decisions that match the v1 PRD.
- Do not introduce AI, cloud sync, or external network dependencies into v1 unless the task explicitly requires it.
- Update this file only with reusable conventions or non-obvious project rules.
- Put story-specific notes in [tasks/progress.txt](/home/robert/repos/private-ledger/tasks/progress.txt), not here.

## Expected Conventions

- Add stack-specific instructions once backend, frontend, and tooling are created.
- Add testing and verification commands once they exist.
- Add directory-level `AGENTS.md` files later if a subdirectory develops its own patterns.

## Codebase Patterns

- None yet.
