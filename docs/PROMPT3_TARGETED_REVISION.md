# Prompt 3 Targeted Visual Revision

This milestone lets MiniCut replace one bad narration visual without rebuilding the whole N unit.

## User workflow

1. Select one Prompt 3 visual clip on V2.
2. Click **Ganti Visual N Terpilih**.
3. MiniCut searches only verified alternatives that are safe for that exact slot.
4. A normal AI Plan / Review appears.
5. Apply replaces only that slot atomically.
6. Undo restores the old clip and removes the replacement.

A2 narration audio, other N visuals, J units, other blocks and unrelated manual edits are not rebuilt.

## Eligible target

The selected clip must:

- be on V2;
- belong to an N-xxx unit;
- have origin `prompt3_visual` or `prompt3_visual_revision`;
- not be locked;
- have current 1B2/evidence/Gemini state;
- belong to a unit whose A2 narration audio is still installed.

## Chronology window

For a selected visual, MiniCut reads its neighboring N visual clips.

The replacement source must stay:

- after the previous visual's source-out;
- before the following visual's source-in;
- outside every other already-used video source range;
- outside the source range of the clip being replaced.

This preserves the Prompt 3 rule that source chronology never moves backward.

## Semantic source

Replacement candidates come only from the current Gemini verification for the same N unit.

MiniCut does not ask Gemini to mutate the timeline. It reuses the verified `keep/trim` source ranges and filters them locally against the selected slot.

If no safe verified alternative exists, MiniCut returns:

`PERLU REVISI`

rather than borrowing an unsafe or out-of-order shot.

## Duration preservation

The replacement slot keeps the exact timeline duration of the selected clip.

The existing Prompt 3 fitter is reused, so replacement pieces must also obey:

- speed > 0 and <= 0.50x;
- final piece duration >= 2.00s;
- film audio muted;
- exact total replacement duration = old slot duration.

The replacement may contain one or more verified clips when that is the legal deterministic fit.

## Review-first / atomic safety

The pending plan contains:

1. one `delete_clip` action for the selected clip;
2. one or more V2 inserts occupying exactly the same timeline slot.

The plan is atomic under the shared timeline history. A failed action rolls back the batch.

Immediately before Apply, MiniCut rebuilds the expected replacement from the current timeline, evidence and Gemini checkpoint. The exact action list must still match, so a stale or altered plan is rejected.

## Ownership

Replacement clips persist:

- the same `unit_id`;
- the same `block_id`;
- `origin=prompt3_visual_revision`.

This keeps later Prompt 4 auditing and further targeted revisions traceable.
