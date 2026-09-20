# Current Verified State

- Remote repository: `tonitarung099-creator/Mini-Cut-V42-Ai-Timeline` (private).
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
- Project save/load + autosave + durable V42 checkpoints: VERIFIED and merged.
- Review-first AI Plan / Review / Apply layer: VERIFIED and merged.
- V42 1B2 parser/import + durable normalized plan: IMPLEMENTED in current milestone; CI verification required.
- Local camera-cut verification inside 1B2 candidate ranges: NOT STARTED.
- Gemini multi-key manager/failover reconstruction: NOT STARTED.
- V42 Prompt 2–5 workflow engine: NOT STARTED.
- Final FFmpeg/SmartCut export reconstruction: NOT STARTED.

## Architecture rule

The timeline is the single source of truth. Manual edits and reviewed AI edits share the same validated Timeline Tool Registry. 1B2 supplies candidate visual ranges and work order; later analysis must stay inside those ranges instead of scanning the full movie by default.

## Current milestone

MiniCut can normalize 1B2 JSON, DOCX or text into local B/N/J/D units, work order and candidate timestamp ranges. The result is shown in the AI panel, persisted in the project workflow checkpoint, restored after restart, and exposed to AI only as compact structured state.

## Next technically justified action

After 1B2 import CI passes:

1. add local shot/camera-cut detection constrained to the active 1B2 candidate ranges,
2. generate representative start/middle/end frames per detected shot,
3. attach overlapping film SRT text,
4. build compact evidence packets per N/J unit,
5. reconstruct Gemini multi-key/failover against those packets,
6. implement Prompt 2–5 orchestration and final export.
