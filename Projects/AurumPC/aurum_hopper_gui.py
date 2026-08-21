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

PROFILE_CSS = r"""
    .hopper-view-picker { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 22px 0 -10px; }
    .hopper-view-picker > span { margin-right: 4px; color: var(--muted); font-size: 11px; letter-spacing: .10em; text-transform: uppercase; }
    .hopper-view { padding: 8px 12px; border: 1px solid rgba(255,255,255,.10); border-radius: 999px; color: var(--muted); background: rgba(0,0,0,.14); cursor: pointer; font-size: 11px; }
    .hopper-view.active { color: #171106; border-color: var(--gold); background: var(--gold); font-weight: 800; }
    body[data-hopper-view="focus"] .shell { grid-template-columns: 88px minmax(0, 1fr); }
    body[data-hopper-view="focus"] aside { display: none; }
    body[data-hopper-view="engineering"] { --panel: rgba(13, 21, 25, .92); --line: rgba(121, 220, 167, .20); --line-bright: rgba(121, 220, 167, .46); }
    body[data-hopper-view="engineering"] .online { color: var(--good); }
"""

PROFILE_HTML = r"""
    <section class="hopper-view-picker" aria-label="Hopper view profile">
      <span>View</span>
      <button class="hopper-view active" type="button" data-hopper-profile="balanced">Balanced</button>
      <button class="hopper-view" type="button" data-hopper-profile="focus">Focus</button>
      <button class="hopper-view" type="button" data-hopper-profile="engineering">Engineering</button>
    </section>
"""

PROFILE_JS = r"""
  const hopperProfiles = new Set(['balanced', 'focus', 'engineering']);
  function setHopperProfile(profile) {
    const selected = hopperProfiles.has(profile) ? profile : 'balanced';
    document.body.dataset.hopperView = selected;
    document.querySelectorAll('[data-hopper-profile]').forEach((button) => {
      button.classList.toggle('active', button.dataset.hopperProfile === selected);
    });
  }
  document.querySelectorAll('[data-hopper-profile]').forEach((button) => {
    button.addEventListener('click', () => setHopperProfile(button.dataset.hopperProfile));
  });
  setHopperProfile('balanced');

"""


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
    page = page.replace("Good to see you.", "Hopper is ready.")
    page = page.replace(
        "This first GUI keeps dialogue separate from machine authority.",
        "This Hopper test GUI keeps dialogue separate from machine authority.",
    )
    settings = '<button class="nav" data-action="settings"><span>⚙</span><span>Settings</span></button>'
    play = '<button class="nav" data-action="play"><span>◉</span><span>Play</span></button>\n    ' + settings
    if settings not in page:
        raise RuntimeError("Aurum GUI settings landmark changed; refusing presentation patch")
    page = page.replace(settings, play, 1)
    old = """      } else if (action === 'settings') {\n        apiKey.focus();\n      } else {"""
    new = """      } else if (action === 'settings') {\n        apiKey.focus();\n      } else if (action === 'play') {\n        window.location.href = 'http://127.0.0.1:8766/';\n      } else {"""
    if old not in page:
        raise RuntimeError("Aurum GUI navigation logic changed; refusing presentation patch")
    page = page.replace(old, new, 1)

    style_marker = "  </style>"
    profile_marker = '    <div id="safeBanner"'
    script_marker = "  refreshStatus();"
    for marker, addition in (
        (style_marker, PROFILE_CSS + style_marker),
        (profile_marker, PROFILE_HTML + "\n" + profile_marker),
        (script_marker, PROFILE_JS + script_marker),
    ):
        if marker not in page:
            raise RuntimeError("Aurum GUI profile landmark changed; refusing presentation patch")
        page = page.replace(marker, addition, 1)
    return page


def main() -> int:
    gui = _load_gui()
    gui.PAGE = _adapt_page(gui.PAGE)
    return int(gui.main())


if __name__ == "__main__":
    raise SystemExit(main())
