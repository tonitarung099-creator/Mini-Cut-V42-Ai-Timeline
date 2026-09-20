# V42 on the Timeline

## Input assumption

1B2 already supplies candidate visual ranges and B/N/J structure. MiniCut does not search the entire film by default.

## Narration flow

1. Read the current N unit and its 1B2 candidate ranges.
2. Open only those candidate ranges.
3. Run local camera-cut/shot detection inside the ranges.
4. Sample representative frames per shot (start/middle/end as the default strategy).
5. Attach overlapping film SRT text and timestamps.
6. Ask Gemini to verify/select/trim among the supplied candidate shots.
7. Validate the decision against V42 and project locks/usage registry.
8. Execute timeline edits locally.
9. Save checkpoint and mark unit state.

## Jangkar flow

Prompt 2 rules are applied directly to clips in the shared timeline. Dialog/film audio remains tied to its source media as required by the V42 reference.

## Block audit

Prompt 4 inspects the actual timeline region for the block. Failures route only the affected N/J unit back for revision.

## Finalization

Prompt 5 validates the complete shared timeline, subtitle positions and block order, then prepares final export.
