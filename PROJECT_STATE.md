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
- Windows EXE packaging and Actions artifact: VERIFIED.
- Shared Timeline Tool Registry: IMPLEMENTED in the current development milestone; CI verification required before merge.
- 1B2 candidate/shot verification engine: NOT STARTED.
- Gemini multi-key manager/failover reconstruction: NOT STARTED.
- V42 Prompt 2–5 workflow engine: NOT STARTED.
- Final FFmpeg/SmartCut export reconstruction: NOT STARTED.

## Architecture rule

The timeline is the single source of truth. Human editing and future AI editing use the same validated Timeline Tool Registry. AI does not receive unrestricted project-file, shell, or FFmpeg mutation access.

## Current milestone

The tool registry provides validated `insert_clip`, `move_clip`, `trim_clip`, `split_clip`, `delete_clip`, speed/mute/lock controls, undo/redo, timeline state, optimistic revision checks, and atomic batches.

## Next technically justified action

After the Timeline Tool Registry CI gate passes:

1. expose the registry through a localhost-only bridge,
2. make the MCP companion use the new timeline tools instead of the legacy cut-list commands,
3. add project save/load and durable V42 checkpoints,
4. then reconstruct 1B2 candidate evidence + Gemini verification,
5. finally implement Prompt 2, 3, 4 and 5 orchestration against the shared timeline.
