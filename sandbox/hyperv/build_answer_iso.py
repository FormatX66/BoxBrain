"""Build the small ISO that carries Windows Setup's Autounattend.xml."""

from __future__ import annotations

import argparse
from pathlib import Path

import pycdlib


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Refusing to replace existing answer ISO: {output}")

    iso = pycdlib.PyCdlib()
    try:
        iso.new(
            interchange_level=3,
            joliet=3,
            vol_ident="BOXBRAINCFG",
        )
        iso.add_file(
            str(source),
            iso_path="/AUTOUNAT.XML;1",
            joliet_path="/Autounattend.xml",
        )
        iso.write(str(output))
    finally:
        iso.close()


if __name__ == "__main__":
    main()
