# Backward-compatibility shim for tare.tools.dialog-engine
from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on python path
src_dir = str(Path(__file__).resolve().parent / "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import tare_dialog.document as _mod

# Export all symbols (including private and dunder helpers used in tests)
for _name in dir(_mod):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_mod, _name)

if __name__ == "__main__":
    if hasattr(_mod, "main"):
        raise SystemExit(_mod.main())
