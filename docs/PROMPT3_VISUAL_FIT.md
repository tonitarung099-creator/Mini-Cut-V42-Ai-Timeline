# Prompt 3 Visual Duration Fitting

This milestone fits Gemini-verified narration visuals to the authoritative safe-padded A2 duration.

## V42 rules enforced locally

For N-xxx visual plans MiniCut enforces:

- source order is chronological and may never move backward;
- film source audio is muted;
- narration visual speed is always > 0 and **never above 0.50x**;
- 0.50x is the default/maximum speed;
- speed below 0.50x may be used to fill the narration duration;
- every final visual piece is at least **2.00 seconds**;
- total final visual duration equals the current safe-padded narration timing exactly;
- A2 must already be installed before a visual plan can be built/applied;
- if these constraints cannot be satisfied, the unit becomes **PERLU REVISI / needs_revision** instead of violating V42.

## Gemini responsibility vs local responsibility

Gemini receives:

- Prompt 1B1 final narration text;
- the authoritative safe-padded narration duration;
- V42 duration constraints;
- bounded candidate frames/SRT evidence.

Gemini only returns semantic `keep / trim / reject` decisions.

Gemini does **not** choose timeline speed or write clips.

MiniCut local code then:

1. revalidates each selected source range;
2. preserves source chronology;
3. calculates each candidate's minimum legal timeline duration;
4. if all selected candidates do not fit, retains the strongest verified subset that fits while preserving source order;
5. distributes remaining narration duration over the chosen pieces;
6. computes exact per-piece speed;
7. builds the review-first V2 plan.

## Minimum duration calculation

At maximum allowed narration speed 0.50x:

`minimum duration from speed = source duration / 0.50`

Each piece also has an absolute V42 minimum of 2000 ms.

Therefore:

`piece minimum = max(source_duration / 0.50, 2000 ms)`

If no verified source range can fit the narration duration under those constraints, MiniCut does not raise speed above 0.50x. It returns a revision state and asks for a new semantic trim/reject decision.

## Exact target duration

Once legal pieces are chosen, any duration remaining after their minimum allocations is distributed proportionally over the pieces. Their speed is then:

`speed = source_duration / allocated_timeline_duration`

This guarantees speed <= 0.50x and makes the sum of all final visual pieces equal A2 timing.

Very low speed (<0.25x) is allowed by the numeric V42 rule but is flagged for naturalness review.

## Review / Apply safety

Prompt 3 visual clips are tagged `origin=prompt3_visual`.

Action validation checks:

- V2 track;
- current evidence source;
- source range inside evidence;
- speed <= 0.50x;
- film audio muted;
- final clip duration >= 2 seconds.

Whole-plan validation runs both when the plan is proposed and immediately before Apply. It rebuilds the deterministic expected plan from the current:

- 1B2;
- evidence;
- Gemini checkpoint;
- narration timing;
- timeline state.

The exact action list must still match. This catches stale timing, stale Gemini output, altered source ranges, changed reflow, or plan tampering.

## A2 / Gemini dependency

For narration units, Gemini verification is now bound to narration timing identity. If Prompt 3 timing changes, the old Gemini verification becomes stale.

The intended order is:

`Prompt 1B1 + narration audio + narration SRT → waveform timing → A2 → Gemini visual verification → local duration fit → review → Apply`

## Freeze / hold

V42 permits intentional freeze/hold when natural. This milestone does not fake freeze using an unrelated timeline operation.

When ordinary legal slow motion can fill duration, MiniCut uses speed fitting. Very slow fits are flagged for review. A real freeze/hold timeline object with matching preview/export behavior is a separate follow-up milestone.
