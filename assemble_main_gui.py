#!/usr/bin/env python3
"""Собрать main_gui.py из base64-частей (коммит без превышения лимита)."""
import base64, pathlib, sys
root = pathlib.Path(__file__).resolve().parent
parts = sorted(root.glob("main_gui.b64.*"), key=lambda p: int(p.name.rsplit(".", 1)[-1]))
if not parts:
    sys.exit("нет main_gui.b64.*")
data = "".join(p.read_text() for p in parts)
out = root / "main_gui.py"
out.write_bytes(base64.b64decode(data))
print(f"OK: {out} ({out.stat().st_size} bytes)")
