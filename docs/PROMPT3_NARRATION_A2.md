# Prompt 3 Narration Audio / A2

This milestone makes narration audio timing local, durable and review-first.

## Inputs

Prompt 3 narration timing requires three inputs in addition to 1B2:

1. **Prompt 1B1 Final** — canonical N-xxx narration text.
2. **Narration audio** — the actual recorded voice track.
3. **Narration SRT** — approximate phrase timing used only to locate the spoken unit.

MiniCut does not treat narration SRT timestamps as the final audio cut.

## Prompt 1B1 parsing

MiniCut intentionally reads only the last section headed:

`NASKAH BERSIH FINAL — SUMBER AUDIO NARASI`

It extracts N-xxx blocks and ignores J/D blocks. Earlier technical references to N-xxx are not accepted as narration source text.

If the final section or required N units are missing, mapping stops instead of guessing.

## SRT mapping

Two local mapping paths are supported.

### Explicit N labels

If the narration SRT labels every narration segment with N-xxx, a label starts the unit segment. Following unlabeled cues remain part of that unit until the next N label.

### Unlabeled SRT

If labels are absent or incomplete, MiniCut groups cues monotonically using normalized text similarity against the Prompt 1B1 final N text.

The mapper preserves N display order. Weak text matches are rejected and require corrected source inputs.

## Waveform safe padding

For each mapped N unit, MiniCut examines only a small local audio window around the SRT core. FFmpeg `silencedetect` finds nearby silence.

The final source range:

- never cuts inside the SRT core;
- prefers silence before/after speech;
- applies bounded before/after padding;
- stays between neighboring narration units;
- falls back to conservative SRT-based padding if silence is not found;
- records a warning when fallback is used.

The timing checkpoint stores source in/out, SRT core bounds, actual pre/post padding, mapping confidence/method and waveform-boundary method.

## Authoritative N duration

Once narration timing exists, its safe-padded duration becomes the duration override for the N region. This happens before visual fitting.

Therefore Prompt 3 becomes:

`Narration audio duration → fixed N region → fit verified visuals into that region`

not:

`selected visuals → decide narration duration`.

## A2 plan

For the active N unit, MiniCut can propose a review-first plan that:

- reflows later V42 units according to Urutan Tayang if necessary;
- inserts exactly the safe-padded narration source range on A2;
- stores `unit_id`, `block_id` and `origin=narration_audio`;
- keeps speed at 1×;
- does not mutate the timeline until Apply Plan.

Apply validates the A2 source range against the current waveform timing checkpoint. A stale or altered range is rejected.

## UI flow

The AI Agent panel exposes:

`Import Prompt 1B1 Final → Import Audio Narasi → Import SRT Narasi → Analisis Waveform Narasi → Buat Plan Audio N di A2 → Apply Plan`

Waveform analysis runs in a worker thread so the editor UI remains responsive.

## Next milestone

The next Prompt 3 milestone fits Gemini-verified film visuals into the fixed N region. That fitting remains local/deterministic and will implement chronology, minimum piece duration, slow-down and freeze/hold fallback without changing narration timing.
