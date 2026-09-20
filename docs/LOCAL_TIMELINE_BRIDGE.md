# Local Timeline Bridge

MiniCut exposes its validated timeline registry to local AI/MCP clients through a localhost-only HTTP bridge.

## Security boundary

- The server binds only to `127.0.0.1`.
- Every non-health request requires an unpredictable per-session token.
- Connection details are written to a per-user discovery file and removed when MiniCut exits.
- The bridge exposes no shell execution and no arbitrary FFmpeg command execution.
- `insert_clip` is restricted to media already imported into the MiniCut project (or already present on the timeline).
- Timeline locks and registry validation remain authoritative.
- External mutations are dispatched onto the Qt UI thread before touching timeline state.

## Endpoints

- `GET /health` — bridge process health only.
- `GET /state` — timeline revision, tracks, clips, playhead and available bridge tools.
- `POST /execute` — one validated timeline tool call.
- `POST /batch` — one atomic batch of validated timeline mutations.

## Revision safety

State returns a monotonic `revision`. AI clients should include `expected_revision` when applying a plan. If the user edits the timeline after the AI inspected it, the stale plan is rejected instead of silently changing newer work.

## MCP companion

`MiniCut MCP` discovers the running desktop bridge and exposes timeline-native tools through MCP stdio. It no longer uses the legacy cut-list command surface.

The MCP process does not own project state. The desktop application remains the single source of truth.
