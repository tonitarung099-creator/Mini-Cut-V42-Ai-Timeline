# Current Verified State

- Remote repository: `tonitarung099-creator/Mini-Cut-V42-AI-Timeline`.
- Final packaged MiniCut behavioral reference: VERIFIED and documented.
- Clean modular PySide6 desktop source: IMPLEMENTED.
- Filmora-like workspace shell: VERIFIED by Windows CI.
- Multi-track timeline model (V2/V1/A2/A1/SUB): VERIFIED.
- Manual insert/move/split/delete/trim: VERIFIED.
- Timeline snapping and zoom: IMPLEMENTED.
- Undo/redo with stable document identity: VERIFIED.
- Timeline-aware preview with clip source-in/out and speed mapping: VERIFIED.
- Track lock / video visibility / audio mute controls: VERIFIED.
- Shared Timeline Tool Registry: VERIFIED.
- Localhost timeline bridge + timeline-native MCP: VERIFIED.
- Desktop + MCP Windows EXE packaging: VERIFIED.
- Project save/load + autosave + durable V42 checkpoints: VERIFIED.
- Review-first AI Plan / Review / Apply layer: VERIFIED.
- V42 1B2 parser/import + durable normalized plan: VERIFIED.
- Candidate-constrained local shot/camera-cut detection: VERIFIED.
- Sparse frame extraction + SRT overlap evidence packets: VERIFIED.
- Gemini local key pool (up to 100) + health/cooldown/failover: VERIFIED.
- Bounded Gemini evidence request/structured response client: VERIFIED and merged.
- Persistent V42 ownership metadata on timeline clips: IMPLEMENTED in current milestone; CI verification required.
- Gemini verification → validated review-first timeline-plan conversion: IMPLEMENTED in current milestone; CI verification required.
- Full Prompt 2/3 unit orchestration and owned timeline regions: NOT STARTED.
- Prompt 4 block auditor: NOT STARTED.
- Prompt 5/final FFmpeg/SmartCut export reconstruction: NOT STARTED.

## Architecture rule

The timeline remains the single source of truth. Gemini may verify evidence, but local MiniCut code converts that verification into deterministic source ranges and a reviewable plan. Gemini never sends direct mutation commands. Every V42-generated clip carries durable unit/block ownership metadata.

## Current milestone

A current `gemini-<UNIT>` checkpoint can now be converted into a pending TimelinePlan. Local validation rechecks evidence bounds, source reuse, unit identity and track ownership. Narration visual clips are proposed on V2 with film audio muted. Anchor clips are proposed as linked V1+A1 pairs at 1×. The plan is only applied after explicit review.

For this milestone, a newly created unit is appended after the current timeline duration. Automatic placement according to the complete V42 display order is intentionally deferred until unit-region orchestration exists.

## Next technically justified action

After this milestone passes CI:

1. introduce durable V42 timeline regions for B/N/J ownership;
2. derive block display order independently from work order;
3. map narration audio/subtitle duration to N unit regions on A2;
4. implement Prompt 3 duration fitting, slow-motion/freeze/handoff rules inside N regions;
5. implement Prompt 2 dialog/action/campuran rules for J regions;
6. support targeted replace/revision of an existing unit instead of duplicate insertion;
7. implement Prompt 4 block audit and Prompt 5/final export.
