#!/usr/bin/env python3
"""Apply the canonical Hopper Gen1 physical-surface identity and pond-ripple Wi-Fi mark."""
from pathlib import Path
import re

# Migration trigger: generation naming is now the canonical Aurum-facing identity.
path = Path("Projects/AurumPC/aurum_desktop.py")
text = path.read_text(encoding="utf-8")

# Human-facing Aurum uses named generations, not software vN labels.
text = re.sub(r'^SCHEMA = "aurum\.desktop\.v\d+"$', 'SCHEMA = "aurum.desktop.gen1-polished-physical-surface"', text, flags=re.M)
if 'GENERATION_NAME = "Gen1 polished physical surface"' not in text:
    text = text.replace(
        'SCHEMA = "aurum.desktop.gen1-polished-physical-surface"\n',
        'SCHEMA = "aurum.desktop.gen1-polished-physical-surface"\nGENERATION_NAME = "Gen1 polished physical surface"\n',
        1,
    )
text = re.sub(r'aurum-native-v\d+', 'gen1-polished-physical-surface', text)
text = re.sub(r'Aurum Native GUI v\d+', 'Gen1 polished physical surface', text)
text = re.sub(r'Native GUI v\d+', 'Gen1 polished physical surface', text)

# Make receipts carry the named generation when they already carry ui_version.
text = text.replace(
    '"ui_version": "gen1-polished-physical-surface",',
    '"generation_name": GENERATION_NAME,\n            "ui_identity": "gen1-polished-physical-surface",',
)
text = text.replace(
    '"ui_version":"gen1-polished-physical-surface",',
    '"generation_name":GENERATION_NAME,"ui_identity":"gen1-polished-physical-surface",',
)

# Replace the Wi-Fi glyph with pond ripples. Strength illuminates from the
# source outward: inner ring, middle ring, outer ring.
pattern = re.compile(r'(?ms)^    def wifi_icon\(.*?^    def battery_icon\(')
replacement = '''    def wifi_icon(cx: int, cy: int, strength: int | None):
        level = 0 if strength is None else max(0, min(3, math.ceil(max(0, strength) / 34)))
        source_y = cy + S(3)
        pygame.draw.circle(
            screen,
            teal_hi if level else gold_dim,
            (cx, source_y),
            max(2, S(3)),
        )
        # Pond-ripple geometry: each ring shares the same source and expands
        # outward.  Inner-to-outer illumination makes signal direction honest.
        ripples = (
            (S(10), S(4)),
            (S(18), S(7)),
            (S(27), S(11)),
        )
        for index, (rx, ry) in enumerate(ripples, start=1):
            color = teal_hi if level >= index else gold_dim
            rect = pygame.Rect(cx - rx, source_y - ry, rx * 2, ry * 2)
            pygame.draw.ellipse(screen, color, rect, width=max(1, S(2)))

    def battery_icon('''
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit("wifi_icon replacement did not match exactly once")

path.write_text(text, encoding="utf-8")
print("Applied Gen1 polished physical surface identity and pond-ripple Wi-Fi icon")
