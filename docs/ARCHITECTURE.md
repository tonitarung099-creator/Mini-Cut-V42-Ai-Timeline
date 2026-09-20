# Target Architecture

## Principle

The timeline is the single source of truth. AI never manipulates FFmpeg or project files arbitrarily. It issues validated timeline actions; the local application executes them.

## Layers

### UI
Filmora-like workspace: Media, Preview, Inspector, Timeline, compact AI Agent panel.

### Project / Timeline Model
Tracks, clips, source in/out, timeline start/end, speed, audio state, subtitles, groups (B/N/J), locks, undo/redo, checkpoints.

### Local Media Intelligence
Only inspect candidate ranges supplied by 1B2. Detect camera cuts/shots locally, sample representative frames, attach overlapping film subtitles, and prepare compact evidence for AI.

### AI Reasoning
Gemini evaluates candidate shots and returns structured decisions. It does not receive the full film by default.

### Timeline Tool Registry
Validated operations such as insert_clip, replace_clip, split_clip, trim_clip, move_clip, ripple_delete, set_speed, freeze_frame, mute_audio, set_volume, add_subtitle, group_clips, lock_clip and unlock_clip.

### V42 Workflow Engine
Prompt 2 = Jangkar behavior.
Prompt 3 = Narasi behavior.
Prompt 4 = block audit/revision routing.
Prompt 5 = final timeline/subtitle audit and export preparation.

### Render / Export
Local FFmpeg-based export. AI does not render video itself.
