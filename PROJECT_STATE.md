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
- Project save/load + autosave + durable V42 checkpoints: MERGED; verification retained in CI history.
- Review-first AI Plan / Review / Apply layer: IMPLEMENTED in current milestone; CI verification required.
- 1B2 candidate/shot verification engine: NOT STARTED.
- Gemini multi-key manager/failover reconstruction: NOT STARTED.
- V42 Prompt 2–5 workflow engine: NOT STARTED.
- Final FFmpeg/SmartCut export reconstruction: NOT STARTED.

## Architecture rule

The timeline is the single source of truth. Manual edits and reviewed AI edits share the same validated Timeline Tool Registry. External AI can inspect state and propose a structured plan, but cannot bypass review with direct timeline mutation.

## Current milestone

AI/MCP can submit a revision-bound plan containing validated timeline actions. The app displays the plan in the right-side AI Agent panel. Apply revalidates the plan and executes it atomically; Cancel changes nothing. Successful V42 plan application records workflow/checkpoint metadata.

## Next technically justified action

After AI Plan / Review / Apply CI passes:

1. parse 1B2 into structured B/N/J units and candidate ranges,
2. add local camera-cut detection only inside those candidate ranges,
3. sample sparse frames and overlapping film SRT into compact evidence packets,
4. reconstruct Gemini multi-key/failover against those packets,
5. implement Prompt 2–5 orchestration against the shared timeline,
6. reconstruct final FFmpeg/SmartCut export.
