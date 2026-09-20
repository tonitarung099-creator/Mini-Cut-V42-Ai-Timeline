# V42 Timeline Regions and Display-Order Reflow

V42 distinguishes **Urutan Tayang** from **Urutan Pengerjaan**. MiniCut must preserve that distinction.

Example:

- Urutan Tayang: `N-001 → J-001`
- Urutan Pengerjaan: `J-001 → N-001`

The editor is allowed to work on J-001 first, but the final timeline region for N-001 must still come before J-001.

## Display sequence

The region engine builds the visual timeline sequence from:

1. block IDs in natural order (`B-001`, `B-002`, ...);
2. each block's explicit `display_order`;
3. per-unit numeric display order when the block list is absent;
4. block membership as a fallback;
5. unassigned N/J units last.

The global work queue is never used as final playback order.

## Region duration

Each unit region has:

- unit ID;
- block ID;
- display-order index;
- timeline start;
- duration;
- duration source;
- materialized/provisional state.

Duration priority is:

1. an explicit temporary override for the unit currently being planned;
2. actual owned timeline clip span;
3. a conservative explicit duration field from 1B2;
4. zero milliseconds when duration is still unknown.

A zero-duration region is provisional. It is expected to move later units when that unit becomes materialized.

## Manual content safety

Timeline clips without a V42 `unit_id` are treated as existing manual/unowned content. V42 regions begin after the latest end of that content. This keeps automatic region layout from silently overwriting unrelated manual edits.

## Reflow

When a newly completed earlier unit changes the display-order layout, MiniCut creates normal `move_clip` actions for already-materialized later units.

Linked V1/A1 anchor pairs are moved by one representative clip per group, so video and audio remain synchronized through the existing linked-move logic.

Example:

1. J-001 is worked first and temporarily starts at 0s.
2. N-001 is later selected with a 5s duration.
3. Recomputed regions become:
   - N-001: 0–5s
   - J-001: 5s onward
4. The proposed plan first moves the linked J-001 groups by +5s, then inserts N-001 at 0s.
5. Apply executes the entire reflow + insertion atomically under one Undo checkpoint.

## Locks

If a region needs to move but any owned clip or track is locked, region plan generation fails instead of overriding the lock.

## Persistence

MiniCut records a `v42-regions` workflow checkpoint containing:

- current region layout;
- compact summary;
- current 1B2 SHA-256.

The checkpoint is refreshed after timeline mutations. The live layout can also be recomputed from the normalized 1B2 plan and owned timeline clips.

## UI / bridge

The AI Agent panel shows the active unit's:

- region number;
- start/end;
- materialized or provisional state;
- duration source.

The local bridge exposes a compact region summary and active region.

## Current limitation

Narration regions currently use the selected visual duration unless a better duration is already available in 1B2/timeline. The next Prompt 3 milestone will make A2 narration audio/subtitle timing authoritative for N-region duration, then fit visuals to that fixed narration region with speed/freeze/handoff rules.
