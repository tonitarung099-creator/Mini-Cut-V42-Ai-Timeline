# V42 1B2 Import

MiniCut treats the Prompt 1B2 output as local planning evidence for later Prompt 2–5 execution. Importing 1B2 does not edit the timeline and does not send the film to an AI provider.

## Accepted files

- `Registrasi-Pusat-....json`
- `Rencana-Induk-....docx`
- text exports such as `Daftar-Kerja-....txt`

DOCX text is read with the Python standard library, so no Microsoft Word or python-docx dependency is required.

## Normalized local model

The importer recognizes:

- block IDs such as `B-001`;
- narration, anchor and dialog IDs (`N-001`, `J-001`, `D-001`);
- display order and work order;
- explicit `Audit B-xxx` work items;
- timestamp candidate ranges;
- central-registration fields;
- narration visual pools grouped by location;
- arbitrary extra V42 fields, preserved in `fields` for later Prompt 2/3 logic.

Candidate timestamps are normalized to milliseconds while the original matched text is retained.

## Persistence

The normalized 1B2 plan is stored inside the durable V42 workflow checkpoint named `1b2-import`. Reopening a MiniCut project restores the normalized plan, work queue, source hash and workflow unit statuses without reparsing the original file.

## AI exposure

The localhost/MCP state exposes only a compact 1B2 summary, work queue and source SHA-256. It does not expose or upload movie bytes.

## Next layer

The next processing stage operates only inside the current unit's 1B2 candidate ranges:

1. local camera-cut / shot boundary detection;
2. representative-frame sampling for each detected shot;
3. overlapping SRT context;
4. compact evidence packets for later Gemini verification.
