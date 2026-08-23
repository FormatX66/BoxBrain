from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "installer" / "New-AurumHopperCredentialEnvelope.ps1"


class HopperCredentialEnvelopeScriptTests(unittest.TestCase):
    def test_script_seals_existing_local_key_to_verified_hopper_receiver(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("OPENAI_API_KEY", text)
        self.assertIn("rsa-oaep-sha256", text)
        self.assertIn("ImportSubjectPublicKeyInfo", text)
        self.assertIn("OaepSHA256", text)
        self.assertIn("recipient_sha256", text)
        self.assertIn("plaintext_in_git = $false", text)
        self.assertNotIn("Write-Output $apiKey", text)
        self.assertNotIn("ciphertext_b64 = $apiKey", text)


if __name__ == "__main__":
    unittest.main()
