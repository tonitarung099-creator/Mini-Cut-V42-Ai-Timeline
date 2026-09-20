# Baseline Gaps / Verification Required

## Evidence we have

- Editable source snapshot: `MiniCutStudio_Agent_Source.zip`.
- Newer packaged reference build: `MiniCut-Smooth-Preview-Proxy-SmartCut-Final.zip`.
- V42 Prompt 2–5 reference package.

## Important limitation

The source snapshot predates the supplied final Windows build. The final package visibly includes newer SmartCut/proxy/Gemini-related behavior that is not proven to exist in this source snapshot.

## Rule before UI refactor

Do not begin a large UI rewrite until we either:

1. recover/reconstruct the latest source corresponding to the final package, or
2. deliberately port the known newer features back into this source baseline with tests.

Any feature marked present based only on the EXE package is **NOT VERIFIED IN SOURCE**.
