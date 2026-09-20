# Current Verified State

- Remote repository: `tonitarung099-creator/Mini-Cut-V42-Ai-Timeline`.
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
- Candidate-constrained local shot/camera-cut detection: VERIFIED and merged.
- Sparse frame extraction + SRT overlap evidence packets: IMPLEMENTED in current milestone; CI verification required.
- Gemini multi-key manager/failover reconstruction: NOT STARTED.
- Gemini evidence request/response schema: NOT STARTED.
- V42 Prompt 2–5 workflow engine: NOT STARTED.
- Final FFmpeg/SmartCut export reconstruction: NOT STARTED.

## Architecture rule

The timeline remains the single source of truth. 1B2 constrains where local analysis may inspect the film. Local shot detection narrows those ranges, then sparse frame + SRT packets provide compact evidence. No cloud provider receives continuous video by default.

## Current milestone

For an active N/J unit with local shot analysis, MiniCut extracts up to three small JPEG frames per shot and attaches only overlapping SRT cues. Frames are cached locally. A durable `evidence-<UNIT>` checkpoint stores packet metadata and identity hashes; bridge state exposes only a compact summary.

## Next technically justified action

After evidence-packet CI passes:

1. implement Gemini API key pool supporting many keys without storing secrets in project files,
2. add per-key health/cooldown/quota state and automatic failover,
3. define bounded Gemini request batches over evidence packets,
4. validate structured Gemini decisions against 1B2/V42 and convert them to review-first AI plans,
5. implement Prompt 2–5 orchestration,
6. reconstruct final FFmpeg/SmartCut export.
