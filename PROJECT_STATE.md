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
- Shared Timeline Tool Registry: VERIFIED by CI and merged.
- Localhost timeline bridge + timeline-native MCP: IMPLEMENTED in current milestone; CI verification required.
- Windows desktop EXE packaging: VERIFIED.
- 1B2 candidate/shot verification engine: NOT STARTED.
- Project save/load + durable V42 checkpoints: NOT STARTED.
- Gemini multi-key manager/failover reconstruction: NOT STARTED.
- V42 Prompt 2–5 workflow engine: NOT STARTED.
- Final FFmpeg/SmartCut export reconstruction: NOT STARTED.

## Architecture rule

The timeline is the single source of truth. Human editing, MCP, and future Gemini editing all use the same validated Timeline Tool Registry. AI does not receive unrestricted project-file, shell, or FFmpeg mutation access.

## Current milestone

The desktop starts a token-authenticated localhost-only bridge. External mutations are dispatched onto the Qt UI thread, checked against the timeline revision and locks, and reflected in the same visible timeline. The MCP companion exposes the new timeline-native tool surface.

## Next technically justified action

After the local bridge + MCP CI gate passes:

1. add project save/load with durable timeline revision/checkpoint metadata,
2. add a structured AI plan/review layer on top of the Timeline Tool Registry,
3. reconstruct 1B2 candidate-range parsing + local camera-cut verification,
4. add Gemini multi-key/failover only after local evidence preparation is stable,
5. implement Prompt 2–5 orchestration against the shared timeline,
6. reconstruct final FFmpeg/SmartCut export.
