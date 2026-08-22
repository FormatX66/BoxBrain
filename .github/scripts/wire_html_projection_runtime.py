#!/usr/bin/env python3
"""Make HTML the primary Hopper human projection with Pygame fallback."""
from pathlib import Path

# Canonical Gen1 presentation: semantic Aurum state -> HTML projection -> human.
runtime = Path("Projects/AurumPC/aurum_runtime_update.py")
text = runtime.read_text(encoding="utf-8")
needle = '    "aurum_hopper_gui.py",\n'
insert = '    "aurum_hopper_gui.py",\n    "aurum_projection_runtime.py",\n    "aurum_web_surface.py",\n'
if '    "aurum_projection_runtime.py",\n' not in text:
    if needle not in text:
        raise SystemExit("runtime allowlist marker missing")
    text = text.replace(needle, insert, 1)
runtime.write_text(text, encoding="utf-8")

gui = Path("Projects/AurumPC/aurum_gui_runtime.py")
text = gui.read_text(encoding="utf-8")
old = '        self.desktop_runtime = runtime_root / "aurum_desktop_runtime.py"\n'
new = '        self.desktop_runtime = runtime_root / "aurum_projection_runtime.py"\n'
if new not in text:
    if old not in text:
        raise SystemExit("GUI physical runtime marker missing")
    text = text.replace(old, new, 1)
gui.write_text(text, encoding="utf-8")

print("HTML projection is primary; Pygame remains projection-runtime fallback")
