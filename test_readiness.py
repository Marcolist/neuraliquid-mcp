import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from eth_account import Account

import agent_purchase as pay
from neuraliquid_mcp import check_purchase_readiness


class WalletReadiness(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        for target in ("socket.socket.connect", "agent_purchase.x402Client", "agent_purchase.save_state"):
            guard = patch(target, side_effect=AssertionError("readiness must be offline and unsigned"))
            mock = guard.start()
            self.addCleanup(guard.stop)
            self.addCleanup(mock.assert_not_called)

    def test_missing_local_settings_and_external_signer_path(self):
        result = check_purchase_readiness()
        self.assertEqual(set(result["blockers"]), {"pass_file_missing", "operator_opt_in_missing",
                                                  "budget_missing_or_invalid", "local_signer_missing"})
        self.assertEqual(check_purchase_readiness("external_x402")["next_tool"], "inspect_offer")

    def test_readable_local_signer_and_capped_valid_budget(self):
        wallet = Account.create()
        signer = self.directory / "signer"
        signer.write_text(wallet.key.hex())
        signer.chmod(0o600)
        os.environ.update(NEURALIQUID_BUYER_KEY_FILE=str(signer), NEURALIQUID_ENABLE_PURCHASE="1",
                          NEURALIQUID_PASS_FILE=str(self.directory / "pass"), NEURALIQUID_MAX_USDC="20")
        result = check_purchase_readiness()
        self.assertEqual(result["status"], "local_setup_ready")
        self.assertEqual(pay.budget_limit(), 5)
        self.assertNotIn(wallet.key.hex(), json.dumps(result))
        self.assertNotIn(wallet.address, json.dumps(result))
        self.assertEqual(list(self.directory.iterdir()), [signer])
        os.environ["NEURALIQUID_MAX_USDC"] = "4.99"
        self.assertEqual(check_purchase_readiness()["blockers"], ["budget_below_day_price"])
        for invalid in ("NaN", "inf", "0", "-2", "oops"):
            os.environ["NEURALIQUID_MAX_USDC"] = invalid
            self.assertEqual(check_purchase_readiness()["blockers"], ["budget_missing_or_invalid"])
        signer.chmod(0o644)
        self.assertIn("local_signer_unusable", check_purchase_readiness()["blockers"])
        signer.chmod(0o600)
        signer.write_text("invalid-secret-test-value")
        result = check_purchase_readiness()
        self.assertIn("local_signer_unusable", result["blockers"])
        self.assertNotIn("invalid-secret-test-value", json.dumps(result))

    def test_configured_token_precedes_local_setup_and_remains_private(self):
        os.environ["NEURALIQUID_ACCESS_TOKEN"] = "b" * 64
        result = check_purchase_readiness()
        self.assertEqual(result["status"], "existing_pass_configured")
        self.assertNotIn(os.environ["NEURALIQUID_ACCESS_TOKEN"], json.dumps(result))
        os.environ["NEURALIQUID_ACCESS_TOKEN"] = "invalid"
        self.assertEqual(check_purchase_readiness()["status"], "invalid_pass_config")

    def test_state_recovery_precedes_any_new_purchase_route(self):
        path = self.directory / "pass"
        os.environ["NEURALIQUID_PASS_FILE"] = str(path)
        path.touch(mode=0o600)
        for saved, status in (
            ({"authorization": "test-auth-header-private"}, "saved_authorization"),
            ({"token":"c" * 64, "status_path":"/api/v1/x402/payments/one"}, "saved_pass_configured"),
            ({"token":"c" * 64, "status_path":"https://other.invalid"}, "pass_state_unusable"),
            ({"token": ["unexpected"]}, "pass_state_unusable"),
        ):
            path.write_text(json.dumps(saved))
            before = path.read_bytes()
            for mode in ("local", "external_x402"):
                result = check_purchase_readiness(mode)
                self.assertEqual(result["status"], status)
                self.assertNotIn("test-auth-header-private", json.dumps(result))
                self.assertNotIn("c" * 64, json.dumps(result))
                self.assertEqual(path.read_bytes(), before)
        path.unlink()
        path.symlink_to(self.directory / "missing")
        self.assertEqual(check_purchase_readiness()["status"], "pass_state_unusable")
