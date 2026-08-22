#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aurum_acoustic_link import make_sos, rank_channels


class AcousticLinkSyntheticProof(unittest.TestCase):
    def test_injected_carrier_is_selected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="aurum-acoustic-") as temporary:
            wav = Path(temporary) / "sos-17000.wav"
            make_sos(wav, frequency=17000.0, volume=0.10)
            result = rank_channels(wav, low=16000, high=18000, step=250)
            best = result.get("best") or {}
            self.assertEqual(best.get("frequency_hz"), 17000)
            self.assertGreater(float(best.get("snr_db") or 0.0), 20.0)


if __name__ == "__main__":
    unittest.main()
