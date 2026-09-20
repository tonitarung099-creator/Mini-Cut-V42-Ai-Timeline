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
- Prompt 1B1 final narration parser: IMPLEMENTED in current milestone; CI verification required.
- Narration SRT → N-unit monotonic mapper: IMPLEMENTED in current milestone; CI verification required.
- Local FFmpeg waveform/silence safe-padding analysis: IMPLEMENTED in current milestone; CI verification required.
- Review-first A2 narration audio placement: IMPLEMENTED in current milestone; CI verification required.
- Prompt 3 visual-duration fitting to authoritative A2: NOT STARTED.
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

MiniCut can import the final Prompt 1B1 narration script, narration audio and narration SRT. The local mapper supports explicit N-xxx labels, including unlabeled continuation cues, and otherwise uses chronological text matching. Weak mappings are rejected rather than guessed. FFmpeg silencedetect runs only around each narration unit, not across the whole audio repeatedly. The resulting safe-padded source range can be converted into a normal pending TimelinePlan that places narration audio on A2 and reflows later display-order units in the same atomic Apply/Undo operation.

Narration timing data and asset references are stored in durable V42 workflow checkpoints. Live region layout uses those narration durations as overrides even before A2 is applied, so N region duration no longer needs to be inferred from selected visuals once timing analysis is available.

## Next technically justified action

After this milestone passes CI:

1. make visual N plan generation read the authoritative A2/N-region duration;
2. implement deterministic Prompt 3 visual fitting:
   - keep source chronology;
   - minimum visual piece duration;
   - default slow-down policy when selected source is too short;
   - freeze/hold fallback only when needed;
   - preserve handoff into following J unit;
3. ensure film source audio remains muted under narration;
4. add targeted visual replacement inside an existing N region;
5. implement Prompt 2 Jangkar mode rules;
6. implement Prompt 4 audit and Prompt 5/final export.
