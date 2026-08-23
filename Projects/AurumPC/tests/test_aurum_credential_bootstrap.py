from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aurum_credential_bootstrap.py"
SPEC = importlib.util.spec_from_file_location("aurum_credential_bootstrap_test", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


@unittest.skipUnless(shutil.which("openssl"), "openssl is required")
class AurumCredentialBootstrapTests(unittest.TestCase):
    def test_receiver_seals_key_to_runtime_without_exposing_plaintext(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            envelope_path = workspace / module.ENVELOPE_RELATIVE
            envelope_path.parent.mkdir(parents=True)
            private_root = root / "private"
            runtime_key = root / "run" / "openai_api_key"
            state_dir = root / "state"

            waiting = module.install(
                workspace=workspace,
                private_root=private_root,
                runtime_key=runtime_key,
                state_dir=state_dir,
            )
            self.assertEqual(waiting["status"], "awaiting-envelope")
            receiver = waiting["receiver"]
            public_path = root / "receiver.pem"
            public_path.write_bytes(base64.b64decode(receiver["public_key_b64"]))
            secret = b"sk-test-machine-sealed-credential"
            encrypted = subprocess.run(
                [
                    shutil.which("openssl") or "openssl",
                    "pkeyutl",
                    "-encrypt",
                    "-pubin",
                    "-inkey",
                    str(public_path),
                    "-pkeyopt",
                    "rsa_padding_mode:oaep",
                    "-pkeyopt",
                    "rsa_oaep_md:sha256",
                ],
                input=secret,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ).stdout
            envelope_path.write_text(
                json.dumps(
                    {
                        "schema": module.ENVELOPE_SCHEMA,
                        "machine": module.MACHINE,
                        "purpose": module.PURPOSE,
                        "algorithm": module.ALGORITHM,
                        "recipient_sha256": receiver["recipient_sha256"],
                        "ciphertext_b64": base64.b64encode(encrypted).decode("ascii"),
                        "ciphertext_sha256": hashlib.sha256(encrypted).hexdigest(),
                        "created_at": "2026-08-22T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )

            ready = module.install(
                workspace=workspace,
                private_root=private_root,
                runtime_key=runtime_key,
                state_dir=state_dir,
            )
            serialized = json.dumps(ready)
            self.assertEqual(ready["status"], "ready")
            self.assertTrue(ready["runtime_credential"])
            self.assertEqual(runtime_key.read_text(encoding="utf-8").strip(), secret.decode())
            self.assertEqual(runtime_key.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(secret.decode(), serialized)
            self.assertFalse(ready["browser_credential"])
            self.assertFalse(ready["plaintext_in_git"])

    def test_envelope_is_bound_to_receiver_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            envelope_path = workspace / module.ENVELOPE_RELATIVE
            envelope_path.parent.mkdir(parents=True)
            envelope_path.write_text(
                json.dumps(
                    {
                        "schema": module.ENVELOPE_SCHEMA,
                        "machine": module.MACHINE,
                        "purpose": module.PURPOSE,
                        "algorithm": module.ALGORITHM,
                        "recipient_sha256": "0" * 64,
                        "ciphertext_b64": base64.b64encode(b"ciphertext").decode("ascii"),
                        "ciphertext_sha256": hashlib.sha256(b"ciphertext").hexdigest(),
                        "created_at": "2026-08-22T00:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(module.CredentialBootstrapError, "recipient-mismatch"):
                module.install(
                    workspace=workspace,
                    private_root=root / "private",
                    runtime_key=root / "run" / "key",
                    state_dir=root / "state",
                )


if __name__ == "__main__":
    unittest.main()
