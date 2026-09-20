# MiniCut V42 Project Format

Project files use JSON with the recommended suffix `.mcutv42.json`.

## What is persisted

- Timeline tracks and track controls.
- Every clip's source, source in/out, timeline position, speed, mute/lock state, group and label.
- Monotonic timeline `revision`.
- Timeline playhead.
- Imported media references and known durations.
- V42 workflow state: active block/unit, per-unit status, and durable checkpoints.

## Stable timeline identity

Loading a project does **not** replace the in-memory TimelineDocument object. Its tracks and clips are restored in place, then transient undo/redo history is cleared and the persisted revision is restored. This keeps the UI, local bridge, MCP and future AI agent attached to the same timeline object.

## Atomic saves

The project is written to a temporary sibling file and then replaced, reducing the chance of leaving a partially written project after interruption.

## Missing media

Missing source media does not make the project JSON unreadable. The loader reports missing source paths so the UI can warn the user and a later relink feature can repair them.

## V42 checkpoints

V42 progress is provider-independent. Checkpoints store the timeline revision and optional block/unit/payload metadata. A Gemini/API change therefore does not need to restart completed timeline work.

Once a project has a save path, successful timeline changes are autosaved through the desktop UI, including changes received through the localhost AI/MCP bridge.
