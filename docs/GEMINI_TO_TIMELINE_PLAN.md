# Gemini Verification to Review-First Timeline Plan

This milestone converts a current, locally validated Gemini verification into a normal MiniCut `TimelinePlan`. It still does not let Gemini mutate the timeline directly.

## Preconditions

MiniCut requires all of the following before a plan can be built:

1. the active N/J unit still exists in the imported 1B2 plan;
2. the evidence packet belongs to the same 1B2 SHA-256;
3. the Gemini verification belongs to the same unit;
4. the Gemini checkpoint still matches the current evidence identity;
5. every evidence shot has exactly one Gemini decision;
6. target tracks are present and unlocked;
7. the unit has not already been placed in the timeline;
8. selected source ranges do not reuse source time already owned by another V42 unit.

## Local re-validation

Gemini output is never trusted as an edit command.

For every `keep` or `trim` decision MiniCut checks:

- the shot index exists;
- trim timestamps stay inside that exact shot;
- selected source ranges are non-empty;
- overlapping selected evidence is deduplicated deterministically, preferring higher confidence;
- source reuse against existing V42-owned visual clips is rejected.

A unit with no usable selected visual does not produce a plan.

## Timeline ownership metadata

Timeline clips now persist:

- `unit_id`
- `block_id`
- `origin`

Gemini-derived V42 clips use `origin = gemini_verified`.

This metadata survives save/load and split operations. It is the foundation for later Prompt 4 block auditing and targeted unit revision.

## Narration units (N)

A verified narration visual plan:

- inserts visual clips on **V2**;
- keeps source chronology;
- sets film visual clips to muted so source film audio is not heard;
- places accepted ranges sequentially;
- records V42 unit/block ownership.

This milestone does not yet fit visual duration to narration audio or apply Prompt 3 slow-motion/freeze rules. That belongs to Prompt 3 orchestration.

## Anchor units (J)

A verified anchor plan:

- inserts video on **V1**;
- inserts the matching source audio on **A1**;
- links each V1/A1 pair with the same group ID;
- uses the exact same source in/out timestamps;
- keeps speed at **1×**;
- records V42 unit/block ownership.

This provides the basic same-source A/V invariant required by Prompt 2. Full dialog/action mode rules are implemented in the later Prompt 2 orchestrator.

## Placement

For safety, a newly generated unit plan currently starts at the end of the existing timeline. This avoids overwriting or overlapping manual edits.

The later V42 orchestration milestone will calculate unit regions from block/display order and narration/anchor duration, then place or revise units inside those owned regions rather than simply appending.

## Review and Apply

The AI Agent panel adds **Buat AI Plan dari Gemini**.

Building the plan:

- does not alter the timeline;
- stores one pending review plan;
- shows every timeline action in the AI Plan / Review panel.

Only **Apply Plan** runs the atomic timeline mutation. Apply revalidates:

- imported source permission;
- unit/block identity;
- allowed track for the unit type;
- source range against current evidence;
- timeline revision and track locks.

Cancel leaves the timeline untouched.
