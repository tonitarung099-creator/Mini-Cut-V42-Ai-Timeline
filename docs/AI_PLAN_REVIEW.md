# AI Plan / Review / Apply

External AI does not directly mutate the MiniCut timeline.

## Flow

1. AI calls `get_state` and reads the current timeline `revision`.
2. AI may use `seek` to inspect a position without changing the timeline.
3. AI submits `propose_plan` with:
   - title and explanation,
   - the exact `expected_revision`,
   - optional V42 block/unit IDs,
   - one or more validated timeline actions.
4. MiniCut shows the plan in the AI Agent panel.
5. The timeline remains unchanged until the user chooses **Apply Plan**.
6. Apply rechecks the plan against the current revision and source restrictions, then runs the complete action list as one atomic Timeline Tool Registry batch.
7. If any action fails, the batch rolls back and the plan remains available for review/correction.

## External AI permissions

The MCP/localhost AI surface exposes only:

- `get_state`
- `seek`
- `propose_plan`
- `get_pending_plan`
- `cancel_plan`

Direct mutation calls such as `insert_clip`, `trim_clip`, `delete_clip`, `undo`, `redo`, and direct `/batch` are rejected by the bridge with `review_required`.

Manual editing inside the desktop app still uses the same Timeline Tool Registry directly.

## Safety properties

- stale plans cannot apply after the timeline revision changes;
- a pending plan cannot be silently replaced by another plan;
- inserted media must already belong to the project;
- source permissions are checked both when a plan is proposed and immediately before Apply;
- track/clip locks are enforced by the registry;
- the whole plan is atomic under one undo checkpoint;
- V42 unit/checkpoint state is recorded after a successful reviewed Apply.
