# Baseline Gaps / Verification Required

## Evidence we have

- The older editable MiniCut source snapshot exists as a retained reference outside the active build.
- The supplied `MiniCut-Smooth-Preview-Proxy-SmartCut-Final.zip` is the newest verified behavioral reference.
- V42 Prompt 2–5 reference material is available.

## Verified gap

The newest packaged application is materially newer than the old editable source snapshot. The Final executable contains modular subsystems for core, UI, workers, subtitles, candidate generation, semantic frame resolution, Gemini, Gemini key management, bridge, agent, preview proxy and SmartCut.

The active repository will therefore reconstruct a clean modular source tree instead of pretending the old monolithic snapshot is equivalent to the Final application.

## Safety rule

A feature is not considered ported merely because it exists in the Final EXE. Each capability must be reintroduced into editable source and covered by component/integration tests before the Filmora-like UI branch is considered functionally equivalent.

See `FINAL_PACKAGE_AUDIT.md` for verified evidence.
