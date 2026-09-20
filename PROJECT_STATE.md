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
- Project save/load + autosave + durable V42 checkpoints: IMPLEMENTED in current milestone; CI verification required.
- 1B2 candidate/shot verification engine: NOT STARTED.
- Gemini multi-key manager/failover reconstruction: NOT STARTED.
- V42 Prompt 2–5 workflow engine: NOT STARTED.
- Final FFmpeg/SmartCut export reconstruction: NOT STARTED.

## Architecture rule

The timeline is the single source of truth. Human editing, MCP, and future Gemini editing all use the same validated Timeline Tool Registry. Project loading restores the same TimelineDocument object in place, preserving all live references.

## Current milestone

The project format persists tracks, clips, revision, playhead, imported media and provider-independent V42 state/checkpoints. Once a project has a path, timeline changes from the UI or local AI/MCP bridge autosave to that project.

## Next technically justified action

After project persistence CI passes:

1. add a structured AI Plan / Review / Apply layer over the Timeline Tool Registry,
2. parse 1B2 into structured B/N/J units and candidate ranges,
3. add local camera-cut detection only inside the current 1B2 candidate ranges,
4. sample sparse frames + overlapping film SRT into compact evidence packets,
5. reconstruct Gemini multi-key/failover against those evidence packets,
6. implement Prompt 2–5 orchestration and final export.
