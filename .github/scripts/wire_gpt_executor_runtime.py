#!/usr/bin/env python3
"""Make the Gen1 GPT executor a resident Hopper runtime component."""
from pathlib import Path

path = Path("Projects/AurumPC/aurum_runtime_update.py")
text = path.read_text(encoding="utf-8")
needle = '    "aurum_gpt_trait.py",\n'
insert = '    "aurum_gpt_trait.py",\n    "aurum_gpt_executor.py",\n'
if '    "aurum_gpt_executor.py",\n' not in text:
    if needle not in text:
        raise SystemExit("aurum_gpt_trait allowlist marker not found")
    text = text.replace(needle, insert, 1)
path.write_text(text, encoding="utf-8")
print("GPT executor is resident in Hopper runtime allowlist")
