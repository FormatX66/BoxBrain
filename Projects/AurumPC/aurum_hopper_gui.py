#!/usr/bin/env python3
"""PC-local presentation wrapper for the bounded Aurum GUI.

The underlying Codelation GUI remains unchanged and keeps its safety boundary.
This wrapper only adapts presentation for Hopper and adds a navigation landmark
to the loopback Echo Rally arcade.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

DEFAULT_WORKSPACE = Path(os.environ.get("AURUM_GIT_WORKSPACE", "/var/lib/aurum/workspace/BoxBrain"))
SEED_DIR = DEFAULT_WORKSPACE / "Projects" / "Codelation" / "seed"
GUI_PATH = SEED_DIR / "aurum_gui.py"


def _load_gui():
    if not GUI_PATH.is_file():
        raise RuntimeError(f"Aurum GUI source missing: {GUI_PATH}")
    seed_text = str(SEED_DIR)
    if seed_text not in sys.path:
        sys.path.insert(0, seed_text)
    spec = importlib.util.spec_from_file_location("aurum_hopper_gui_base", GUI_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load bounded Aurum GUI")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _adapt_page(page: str) -> str:
    page = page.replace("<title>Aurum — BBPI4</title>", "<title>Aurum — Hopper</title>")
    page = page.replace("BBPI4 · Local adaptive shell", "Hopper · Local adaptive shell")
    page = page.replace("Pi connected", "Hopper connected")
    page = page.replace("Pi unavailable", "Hopper unavailable")
    settings = '<button class="nav" data-action="settings"><span>⚙</span><span>Settings</span></button>'
    play = '<button class="nav" data-action="play"><span>◉</span><span>Play</span></button>\n    ' + settings
    if settings not in page:
        raise RuntimeError("Aurum GUI settings landmark changed; refusing presentation patch")
    page = page.replace(settings, play, 1)
    old = """      } else if (action === 'settings') {\n        apiKey.focus();\n      } else {"""
    new = """      } else if (action === 'settings') {\n        apiKey.focus();\n      } else if (action === 'play') {\n        window.location.href = 'http://127.0.0.1:8766/';\n      } else {"""
    if old not in page:
        raise RuntimeError("Aurum GUI navigation logic changed; refusing presentation patch")
    return page.replace(old, new, 1)


def main() -> int:
    gui = _load_gui()
    gui.PAGE = _adapt_page(gui.PAGE)
    return int(gui.main())


if __name__ == "__main__":
    raise SystemExit(main())
