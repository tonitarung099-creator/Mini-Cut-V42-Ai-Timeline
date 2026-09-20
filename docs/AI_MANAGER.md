# AI Manager

## Responsibilities

- Maintain configured Gemini endpoints/credentials locally.
- Track ready, cooldown, rate-limited and invalid states.
- Select an available model/key/project according to configured legitimate quotas.
- Persist job checkpoints separately from provider sessions.
- Resume a unit after transient API failure without restarting completed timeline work.
- Keep API keys out of Git and project JSON.

## Token strategy

- Never send the full movie by default.
- Start from 1B2 candidate ranges.
- Shot detection and frame extraction are local.
- Default frame evidence is sparse/adaptive rather than fixed 5 fps.
- Send SRT/context plus representative frames.
- Escalate sampling only when a shot is ambiguous.
