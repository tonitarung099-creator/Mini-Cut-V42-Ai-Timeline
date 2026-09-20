from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "baseline" / "MiniCutStudio_Agent_Source.zip"
TARGET = ROOT / "src" / "minicut_studio_agent.py"
MEMBER = "MiniCutStudioAgentSource/minicut_studio_agent.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore the editable MiniCut baseline source from the archived snapshot.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing target file.")
    args = parser.parse_args()

    if TARGET.exists() and not args.force:
        print(f"Already present: {TARGET}")
        return 0
    if not ARCHIVE.is_file():
        raise SystemExit(f"Missing baseline archive: {ARCHIVE}")

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE) as zf:
        with zf.open(MEMBER) as src, TARGET.open("wb") as dst:
            shutil.copyfileobj(src, dst)

    print(f"Restored {TARGET.relative_to(ROOT)} from {ARCHIVE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
