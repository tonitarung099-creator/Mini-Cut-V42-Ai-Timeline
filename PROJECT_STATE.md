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
- Gemini local key pool (up to 100) + health/cooldown/failover: VERIFIED and merged.
- Bounded Gemini evidence request/structured response client: IMPLEMENTED in current milestone; CI verification required.
- Gemini verification → review-first timeline-plan conversion: NOT STARTED.
- V42 Prompt 2–5 workflow engine: NOT STARTED.
- Final FFmpeg/SmartCut export reconstruction: NOT STARTED.

## Architecture rule

Project/timeline/evidence state is independent from API sessions. Gemini receives only bounded evidence for the active 1B2 unit. Gemini responses remain advisory structured verification until converted into a validated review-first plan; they never directly mutate the timeline.

## Current milestone

MiniCut batches sparse evidence images and local SRT/1B2 context into bounded Gemini Interactions requests. Structured responses are validated against the exact supplied shot indexes and source boundaries. Quota/auth/transient failures automatically rotate through the local key pool. Successful verification is saved in a durable `gemini-<UNIT>` checkpoint with evidence identity checks so stale results are detectable.

## Next technically justified action

After Gemini evidence-client CI passes:

1. convert current Gemini keep/trim/reject decisions into deterministic candidate selections,
2. map selected source ranges to the proper N/J timeline region,
3. generate a review-first AI plan instead of directly editing,
4. apply V42 ownership/lock/usage rules before plan proposal,
5. implement Prompt 2/3 unit orchestration and Prompt 4 block audit,
6. implement Prompt 5/final FFmpeg/SmartCut export.
