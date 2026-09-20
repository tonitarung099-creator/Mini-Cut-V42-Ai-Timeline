from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "baseline" / "MiniCutStudio_Agent_Source.zip"
REQUIRED = {
    "MiniCutStudioAgentSource/minicut_studio_agent.py",
    "MiniCutStudioAgentSource/minicut_mcp.py",
    "MiniCutStudioAgentSource/requirements.txt",
    "MiniCutStudioAgentSource/build_windows.bat",
    "MiniCutStudioAgentSource/README_AGENT.md",
}


def main() -> int:
    if not ARCHIVE.is_file():
        raise SystemExit(f"Missing baseline archive: {ARCHIVE}")

    with zipfile.ZipFile(ARCHIVE) as zf:
        names = set(zf.namelist())
        missing = sorted(REQUIRED - names)
        bad = zf.testzip()

    if missing:
        raise SystemExit("Missing required baseline members: " + ", ".join(missing))
    if bad:
        raise SystemExit(f"Corrupt ZIP member: {bad}")

    print("Baseline archive structure: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
