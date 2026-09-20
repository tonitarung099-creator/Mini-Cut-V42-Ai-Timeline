# Final Package Audit — Verified 2026-09-20

This document records evidence recovered from the supplied `MiniCut-Smooth-Preview-Proxy-SmartCut-Final.zip`. It is evidence about the packaged application, not a claim that the editable baseline source already contains the same implementation.

## Package evidence

The Windows package contains:
- `MiniCut Studio Agent.exe`
- `MiniCut MCP.exe`
- `MiniCut SmartCut.exe`
- `README_AGENT.md`
- `THIRD_PARTY_SMARTCUT.txt`
- PySide6/Qt multimedia runtime.

The packaged README states a modular architecture:
- `minicut_agent/core.py`
- `minicut_agent/agent.py`
- `minicut_agent/bridge.py`
- `minicut_agent/workers.py`
- `minicut_agent/ui.py`
- `mcp_server.py`

PyInstaller bytecode inspection verifies additional modules in the final executable:
- `minicut_agent/subtitles.py`
- `minicut_agent/frame_resolver.py`
- `minicut_agent/candidates.py`
- `minicut_agent/gemini.py`
- `minicut_agent/gemini_keys.py`

## Verified functional surfaces in bytecode

### core.py
Verified symbols include:
- media probing and keyframe probing
- `ProjectModel`
- project load/save
- normal FFmpeg segment export
- preview proxy path/build
- SmartCut segment export

### candidates.py
Verified symbols include:
- visual boundary detection
- silence boundary detection
- candidate deduplication/ranking
- candidate generation per target

### subtitles.py
Verified symbols include:
- SRT loading
- active cue lookup
- safe-cut checks
- nearby subtitle/context extraction
- dialogue/gap boundary extraction

### frame_resolver.py
Verified symbols include:
- frame timestamp probing
- semantic frame resolution

### gemini.py
Verified symbols include:
- Gemini client
- connection testing
- candidate verification
- JPEG frame extraction
- semantic prompt construction
- usage metadata

### gemini_keys.py
Verified symbols include:
- encrypted key storage
- key add/update/remove/activate
- usage recording
- error tracking
- model-limit snapshots
- Windows protection/unprotection helpers

### workers.py
Verified background workers include:
- media analysis
- proxy generation
- export
- agent requests
- Gemini connection tests
- FilmCut processing/cache

### ui.py
Verified final UI surfaces include:
- Parts tab
- AI Agent tab
- Film Cut tab
- Gemini Keys tab
- Log tab
- preview proxy controls
- playback-rate controls
- frame stepping
- Gemini key manager
- film-cut processing/apply/cancel
- deterministic bridge tools
- export/undo

## SmartCut dependency

The package includes SmartCut 1.7 with an MIT license notice and a separate `MiniCut SmartCut.exe` engine.

## Conclusion

The final package is materially newer than `MiniCutStudio_Agent_Source.zip`. The final app must therefore be treated as the behavioral reference while editable source is reconstructed/ported. Large UI work must not delete these verified capabilities.

## Next engineering rule

1. Keep the final package as immutable behavioral reference.
2. Verify the old editable baseline can reconstruct/build.
3. Port/reconstruct final modular subsystems into editable source with component tests.
4. Only then replace the UI with the Filmora-like workspace, keeping core/media/AI behavior behind stable interfaces.
