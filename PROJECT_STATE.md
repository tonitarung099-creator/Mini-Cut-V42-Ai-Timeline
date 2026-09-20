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
- Gemini verification → validated review-first timeline-plan conversion: VERIFIED and merged.
- Display-order V42 timeline regions + atomic reflow: IMPLEMENTED in current milestone; CI verification required.
- A2 narration timing and Prompt 3 duration fitting: NOT STARTED.
- Full Prompt 2 anchor dialog/action/campuran orchestration: NOT STARTED.
- Targeted replace/revision of an existing unit: NOT STARTED.
- Prompt 4 block auditor: NOT STARTED.
- Prompt 5/final FFmpeg/SmartCut export reconstruction: NOT STARTED.

## Architecture rule

Urutan Pengerjaan controls what the AI works on next; Urutan Tayang controls where units belong in the timeline. They are independent. Region layout is computed locally from 1B2 and durable clip ownership. Reflow is expressed as ordinary reviewed timeline actions and remains atomic/undoable.

## Current milestone

MiniCut now derives N/J timeline regions from block display order, tracks provisional versus materialized duration, reserves pre-existing manual content, and can shift already-built later units when an earlier display-order unit becomes known. Linked anchor audio/video groups move together. The AI panel and local bridge expose compact region state, and a durable `v42-regions` checkpoint follows timeline mutations.

## Next technically justified action

After region/reflow CI passes:

1. import/identify narration audio and narration subtitle sources;
2. map A2 narration audio segments to N units;
3. make narration duration authoritative for N timeline regions;
4. fit Gemini-selected visual ranges to N duration with Prompt 3 rules (chronology, speed, freeze, handoff);
5. implement Prompt 2 Jangkar mode rules over J regions;
6. add targeted replace/revision for an existing N/J unit;
7. implement Prompt 4 block audit and Prompt 5/final export.
