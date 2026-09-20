# Timeline Tool Registry

The timeline tool registry is the only supported mutation surface for future AI agents.

## Principle

Manual UI actions and AI actions must share the same validated commands. AI must not edit project JSON directly and must not invoke FFmpeg as a substitute for timeline edits.

## Current tools

- `get_state`
- `insert_clip`
- `move_clip`
- `trim_clip`
- `split_clip`
- `delete_clip`
- `set_speed`
- `set_clip_mute`
- `set_clip_lock`
- `set_track_lock`
- `set_track_visibility`
- `set_track_mute`
- `undo`
- `redo`

## Safety behavior

Every mutation is validated by the local timeline model.

Each successful mutation advances a monotonic in-memory `revision`. A caller may send `expected_revision`; stale plans are rejected instead of being applied to a timeline that changed while the AI was reasoning.

`execute_batch` groups multiple timeline operations under one history checkpoint. If one operation fails, the whole batch is restored. This is intended for V42 units where video/audio or several coordinated edits must succeed atomically.

Track and clip locks remain authoritative. The registry cannot bypass them.

## Current UI integration

Manual actions for add-to-timeline, move, trim, split, delete, track controls, undo and redo are routed through the same registry. This prevents a future AI path from developing different editing semantics than the human editing path.

## Next layer

A local bridge will expose a restricted subset of this registry to the AI/MCP process. The bridge must:
- return `revision` with project state,
- require/accept `expected_revision` for mutations,
- preserve batch atomicity,
- never expose unrestricted filesystem or shell execution,
- notify the Qt UI after successful external mutations.
