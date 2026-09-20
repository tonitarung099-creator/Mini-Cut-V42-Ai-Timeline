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
- V42 1B2 parser/import + durable normalized plan: VERIFIED and merged.
- Candidate-constrained local shot/camera-cut detection: IMPLEMENTED in current milestone; CI verification required.
- Sparse frame + SRT evidence packet builder: NOT STARTED.
- Gemini multi-key manager/failover reconstruction: NOT STARTED.
- V42 Prompt 2–5 workflow engine: NOT STARTED.
- Final FFmpeg/SmartCut export reconstruction: NOT STARTED.

## Architecture rule

The timeline remains the single source of truth. 1B2 defines where MiniCut is allowed to look for candidate visuals. Local analysis narrows those candidate ranges into shot segments before any cloud-model verification is considered.

## Current milestone

For the active N/J unit, MiniCut analyzes only the unit's 1B2 candidate timestamp ranges with local FFmpeg scene-change detection. Results are stored as absolute shot segments in a durable per-unit checkpoint. The UI remains responsive because detection runs on a worker thread.

## Next technically justified action

After local shot-detection CI passes:

1. extract sparse representative frames (start/middle/end) from detected shots,
2. parse film SRT and attach only overlapping subtitle lines,
3. build compact per-unit evidence packets,
4. estimate/limit evidence size before cloud requests,
5. reconstruct Gemini multi-key/failover against those packets,
6. implement Prompt 2–5 orchestration and final export.
