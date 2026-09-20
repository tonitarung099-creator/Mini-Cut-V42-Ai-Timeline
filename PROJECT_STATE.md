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
- Sparse frame extraction + SRT overlap evidence packets: VERIFIED and merged.
- Gemini local key pool (up to 100) + health/cooldown/failover: IMPLEMENTED in current milestone; CI verification required.
- Gemini evidence request/response client: NOT STARTED.
- V42 Prompt 2–5 workflow engine: NOT STARTED.
- Final FFmpeg/SmartCut export reconstruction: NOT STARTED.

## Architecture rule

Project/timeline/evidence state is independent from API sessions. Gemini keys are local credentials, never project data. Provider failures may rotate keys but must never discard V42 checkpoints or mutate the timeline outside the review-first plan layer.

## Current milestone

MiniCut can import and store up to 100 Gemini API keys locally, deduplicate them, rotate ready keys round-robin, cool down quota/transient failures, disable authentication-failed keys, and expose only aggregate key health to the local bridge.

## Next technically justified action

After Gemini key-pool CI passes:

1. implement a Gemini REST client against the current supported API,
2. send bounded evidence batches with images + compact shot/SRT metadata,
3. enforce structured JSON response schemas for shot decisions,
4. retry/fail over through the local key pool,
5. convert validated decisions into review-first timeline plans,
6. implement V42 Prompt 2–5 orchestration and final export.
