# Local Shot Detection inside 1B2 Candidates

MiniCut does not scan the whole movie for Prompt 3 by default. The local shot detector operates only on timestamp ranges already supplied by the imported 1B2 plan.

## Flow

1. Choose the active/next N or J unit from the 1B2 work queue.
2. Use that unit's own candidate ranges.
3. If the unit has no private candidate range, MiniCut may fall back to the block-level additional candidate ranges and records a warning.
4. Run FFmpeg scene-change detection locally for each candidate range.
5. Convert detected cut offsets back to absolute movie timestamps.
6. Store the resulting shot segments in the durable checkpoint `shots-<UNIT>`.

No movie bytes leave the computer in this stage.

## FFmpeg strategy

The detector seeks directly to each candidate range and processes only its duration. The filter resets PTS at the candidate start, then uses FFmpeg's scene score to identify cut boundaries.

Default settings:

- scene threshold: `0.30`
- minimum shot duration: `300 ms`

These values are implementation defaults, not V42 rules, and can be made configurable later.

## Sparse sampling preparation

Each detected shot exposes representative timestamps for:

- near the shot start,
- shot midpoint,
- near the shot end.

The next milestone will extract small image frames only at those timestamps and attach overlapping SRT context. This is intentionally much smaller than sending continuous video or several frames per second to Gemini.

## UI behavior

The AI Agent panel contains **Pecah Kandidat per Kamera**. Analysis runs on a worker thread so the editor UI remains responsive. The result does not edit the timeline; it only enriches local evidence for later reviewed AI planning.
