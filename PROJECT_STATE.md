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
- Bounded Gemini evidence request/structured response client: VERIFIED.
- Persistent V42 ownership metadata on timeline clips: VERIFIED.
- Gemini verification → validated review-first timeline-plan conversion: VERIFIED.
- Display-order V42 timeline regions + atomic reflow: VERIFIED and merged.
- Prompt 1B1 final narration parser: VERIFIED and merged.
- Narration SRT → N-unit monotonic mapper: VERIFIED and merged.
- Local FFmpeg waveform/silence safe-padding analysis: VERIFIED and merged.
- Review-first A2 narration audio placement: VERIFIED and merged.
- Prompt 3 visual-duration fitting to authoritative A2: IMPLEMENTED in current milestone; CI verification required.
- Full Prompt 2 anchor dialog/action/campuran orchestration: NOT STARTED.
- Targeted replace/revision of an existing unit: NOT STARTED.
- Prompt 4 block auditor: NOT STARTED.
- Prompt 5/final FFmpeg/SmartCut export reconstruction: NOT STARTED.

## Architecture rule

Prompt 3 narration timing is local and evidence-based:

1. Prompt 1B1 final narration section identifies the canonical text for each N-xxx.
2. Narration SRT is only a locator/reference for the spoken phrases.
3. Narration audio is the source of truth for the actual cut.
4. Local waveform/silence analysis expands around the SRT core using safe padding.
5. The final A2 clip duration becomes authoritative for the N timeline region.
6. The plan is still review-first and atomic; cloud AI never writes A2 directly.

## Current milestone

Narration audio timing is already verified. The current branch makes that timing authoritative for N visuals. Gemini receives the final narration text and A2 duration but only makes semantic keep/trim/reject decisions. Local MiniCut then fits verified source ranges under V42: chronological source order, <=0.50x speed, >=2.00s per final piece, film audio muted, and exact equality between total V2 duration and safe-padded A2 duration. Impossible fits become needs_revision rather than speeding above 0.50x.

Prompt 3 visual plans receive whole-plan revalidation. Immediately before Apply, MiniCut rebuilds the deterministic expected actions from current evidence, Gemini checkpoint, narration timing and timeline state; the pending actions must still match exactly.

## Next technically justified action

After this milestone passes CI:

1. add a real freeze/hold timeline primitive with correct preview/export semantics;
2. parse/normalize Prompt 1B2 phrase-function metadata (VISUAL PRESISI / HANDOFF / CAMPURAN) into structured fields;
3. validate N→J handoff and protect J core moments during candidate selection;
4. add targeted replacement of one faulty visual inside an existing N region;
5. implement Prompt 2 Jangkar dialog/action/campuran orchestration;
6. implement Prompt 4 block audit and Prompt 5/final export.
