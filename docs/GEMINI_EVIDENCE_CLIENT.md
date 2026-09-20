# Gemini Evidence Verification Client

MiniCut uses Gemini only after the local pipeline has narrowed the movie into a small, unit-scoped evidence packet.

## API

The client uses Google's Gemini Interactions API:

- default endpoint: `https://generativelanguage.googleapis.com/v1beta/interactions`
- default model: `gemini-3.5-flash`
- API revision header: `2026-05-20`
- `store: false` for stateless verification requests

The endpoint and model are configurable with:

- `MINICUT_GEMINI_ENDPOINT`
- `MINICUT_GEMINI_MODEL`

This keeps the editor independent from a single hard-coded model generation.

## Bounded requests

MiniCut never sends the full film.

The request builder reads only a previously-created `evidence-<UNIT>` packet. By default each Gemini request is limited to:

- at most 12 evidence images;
- at most 12 MiB of base64 inline image payload;
- only the shots assigned to that batch;
- only overlapping SRT text and compact 1B2 unit fields.

Local frame file paths are not included in the prompt.

## Structured response

Every shot in a batch must receive exactly one decision:

- `keep`
- `reject`
- `trim`

Each decision must include:

- the exact supplied shot index;
- confidence in the range 0..1;
- a short reason.

A trim must provide absolute start/end timestamps and both timestamps must remain inside the original shot boundary. Unknown, missing or duplicate shot indexes invalidate the response.

The Gemini result is evidence verification only. It does **not** mutate the timeline.

## Key failover

Requests acquire credentials from the local 100-key pool.

- 429, 5xx and transient network failures cool down the current key and retry another ready key.
- 401/403 disables the affected key and retries another ready key.
- generic 4xx request/schema errors stop the request rather than burning every key.
- key-health state is persisted locally after attempts.

Only the internal key fingerprint is saved with a successful batch result. The API secret is never saved in the project.

## Durable verification

A successful unit result is stored in checkpoint `gemini-<UNIT>`.

The checkpoint includes an evidence identity made from:

- source fingerprint;
- 1B2 SHA-256;
- SRT SHA-256;
- shot count;
- frame count.

If the evidence changes, the UI marks the Gemini result `STALE`.

## UI

The right-side AI Agent panel adds **Verifikasi Evidence dengan Gemini**.

Verification runs in a worker thread. It is enabled only when:

1. the active unit has an evidence packet; and
2. at least one Gemini API key is ready.

The next milestone converts a current, validated Gemini verification into a proposed timeline plan. The user still reviews and explicitly applies that plan.
