# MiniCut V42 AI Timeline

Private-development baseline for evolving MiniCut into a Filmora-like video editor where an AI agent edits the same visible timeline as the user.

## Product direction

- Familiar Filmora-style layout: media browser, preview, inspector, multi-track timeline.
- Human and AI edit the same project timeline.
- V42 Prompt 2–5 become deterministic workflow rules, not four disconnected chat prompts.
- 1B2 remains the source of candidate visual ranges.
- Candidate ranges are re-checked locally with shot/camera-cut detection.
- Gemini receives sampled frames + subtitle/context instead of full movies by default.
- AI decisions are executed through validated timeline tools with undo/checkpoints.
- API manager supports health/cooldown/failover while project state remains local.

## Baseline status

The editable source in this repository comes from `MiniCutStudio_Agent_Source.zip`, an earlier source snapshot. The newer `MiniCut-Smooth-Preview-Proxy-SmartCut-Final.zip` supplied for reference is a packaged Windows build and contains newer behavior. Do **not** assume this source snapshot already matches every feature in that final build.

See `docs/BASELINE_GAPS.md` before feature work.

## Development order

1. Establish a reproducible source/build baseline.
2. Reconcile baseline source with the newer packaged MiniCut feature set.
3. Build Filmora-like UI shell.
4. Build real multi-track timeline/project model.
5. Add 1B2 candidate parser + local shot detection.
6. Add adaptive frame sampling + SRT context.
7. Add API manager/checkpoints.
8. Add AI timeline tool registry.
9. Implement V42 Prompt 2, 3, 4, and 5 behavior over the timeline.
10. Add Auto Edit only after manual timeline editing is stable.
