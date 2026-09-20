# Sparse Frame + SRT Evidence Packets

This stage prepares compact local evidence for a single V42 N/J unit. It does not call Gemini and it never uploads the movie.

## Input

- the durable `shots-<UNIT>` checkpoint produced by local candidate-range shot detection;
- the original local movie file;
- an optional film SRT file;
- the SHA-256 identity of the imported 1B2 plan.

## Visual evidence

For every detected shot, MiniCut extracts at most three JPEG frames:

1. near the shot start,
2. the shot midpoint,
3. near the shot end.

Default extraction width is capped at 640 pixels. Frames are cached under the local MiniCut evidence cache and are reused when present.

The cache key includes a fast source fingerprint derived from local path, file size and modification time. This avoids hashing an entire multi-gigabyte movie every time while still allowing later stages to notice common source changes.

## Subtitle evidence

MiniCut parses SubRip (`.srt`) locally and attaches only cues that overlap the current shot. If no SRT is selected, it checks for common same-basename SRT files next to the movie. Evidence may still be built without SRT, but the packet records a warning.

## Packet contents

A per-unit evidence packet contains:

- unit ID and source fingerprint;
- 1B2 source SHA-256;
- SRT path/hash when present;
- absolute shot start/end timestamps;
- 1B2 candidate bounds, location and label;
- representative frame timestamps and local cache paths;
- only the subtitle cues overlapping each shot;
- warnings and compact size/count summaries.

The durable checkpoint is named `evidence-<UNIT>`.

## AI boundary

Bridge state exposes only the evidence summary (shot count, frame count, subtitle count/characters and local image byte size). It does not expose image bytes or local frame paths.

A future Gemini provider layer will receive a compact model payload plus only the image files selected for that request. The provider layer must validate that the packet still matches the current 1B2/source/SRT identities before making a request.

## UI

The AI Agent panel now supports:

- **Import Film SRT**
- **Buat Evidence Lokal**

Evidence extraction runs on a worker thread so the editor remains responsive.
