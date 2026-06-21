"""
tests/unit/test_coverage_boost_phase1c.py

Third targeted coverage boost — closes the remaining gap to cross 85%.

Modules targeted:
  - wallet_manager/exceptions.py            (lines 65-66, 82-83, 214-216, 286-288, 305-307, 323-324)
  - wallet_manager/security/vault.py        (lines 81, 119-120)
  - wallet_manager/security/vault_manager.py (lines 66, 75-77, 103-104, 129, 135, 140-141, 150-152)
  - wallet_manager/strategies/shadow_live.py (lines 220-223 — BUILDING/CLOSE status)
  - wallet_manager/strategies/ensemble_weighter.py (lines 41-55 — _weights_from_report)
  - wallet_manager/alerting/prometheus_webhook.py (lines 40-45, 69-71, 75, 91-92)
  - wallet_manager/reporting.py             (lines 101-102 — weekly delivery exception)
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# exceptions.py — instantiate all exception subclasses with optional params
# ---------------------------------------------------------------------------

class TestExceptionSubclasses:
    def test_balance_fetch_error_with_address(self):
        """Lines 65-66: BalanceFetchError stores address attribute."""
        from wallet_manager.exceptions import BalanceFetchError
        exc = BalanceFetchError("fetch failed", wallet_id="w1", address="0xABC")
        assert exc.address == "0xABC"
        assert exc.wallet_id == "w1"

    def test_broadcast_error_with_tx_hash(self):
        """Lines 82-83: BroadcastError stores tx_hash attribute."""
        from wallet_manager.exceptions import BroadcastError
        exc = BroadcastError("broadcast failed", wallet_id="w2", tx_hash="0xDEF")
        assert exc.tx_hash == "0xDEF"

    def test_tx_replaced_error_with_hashes(self):
        """Lines 214-216: TxReplacedError stores original and replacement hashes."""
        from wallet_manager.exceptions import TxReplacedError
        exc = TxReplacedError(
            "tx replaced",
            wallet_id="w3",
            original_hash="0x111",
            replacement_hash="0x222",
        )
        assert exc.original_hash == "0x111"
        assert exc.replacement_hash == "0x222"

    def test_insufficient_collateral_error(self):
        """Lines 286-288: InsufficientCollateralError stores collateral values."""
        from wallet_manager.exceptions import InsufficientCollateralError
        exc = InsufficientCollateralError(
            "insufficient",
            wallet_id="w4",
            required_usd=1000.0,
            available_usd=500.0,
        )
        assert exc.required_usd == 1000.0
        assert exc.available_usd == 500.0

    def test_flash_crash_detected_error(self):
        """Lines 305-307: FlashCrashDetectedError stores drop and window."""
        from wallet_manager.exceptions import FlashCrashDetectedError
        exc = FlashCrashDetectedError(
            "flash crash",
            wallet_id="w5",
            drop_pct=15.0,
            window_seconds=30.0,
        )
        assert exc.drop_pct == 15.0
        assert exc.window_seconds == 30.0

    def test_short_position_error_with_id(self):
        """Lines 323-324: ShortPositionError stores position_id."""
        from wallet_manager.exceptions import ShortPositionError
        exc = ShortPositionError("short failed", wallet_id="w6", position_id="pos-007")
        assert exc.position_id == "pos-007"


# ---------------------------------------------------------------------------
# security/vault.py — encrypt("") → ValueError, decrypt(bad) → DecryptionError
# ---------------------------------------------------------------------------

class TestVaultEdgeCases:
    def _vault(self):
        from cryptography.fernet import Fernet

        from wallet_manager.config import Settings
        from wallet_manager.security.vault import Vault
        key = Fernet.generate_key().decode()
        settings = MagicMock(spec=Settings)
        settings.vault_key = key
        return Vault(settings=settings)

    def test_encrypt_empty_string_raises(self):
        """Line 81: encrypt('') raises ValueError."""
        vault = self._vault()
        with pytest.raises(ValueError, match="empty"):
            vault.encrypt("")

    def test_encrypt_invalid_hex_format_raises(self):
        """Line 81: 64-char non-hex string → ValueError('Suspected private key')."""
        vault = self._vault()
        bad_key = "X" * 64  # 64 chars but not valid hex
        with pytest.raises(ValueError, match=r"(?i)private key|invalid hex"):
            vault.encrypt(bad_key)

    def test_decrypt_invalid_token_raises_decryption_error(self):
        """Lines 119-120: decrypt(bad_token) goes through InvalidToken path."""
        from wallet_manager.exceptions import DecryptionError
        vault = self._vault()
        with pytest.raises(DecryptionError):
            vault.decrypt(b"this_is_not_a_valid_fernet_token_xyz1234")


# ---------------------------------------------------------------------------
# security/vault_manager.py — edge case paths
# ---------------------------------------------------------------------------

class TestVaultManagerEdgeCases:
    def test_get_vault_manager_singleton(self):
        """Lines 150-152: get_vault_manager() creates singleton on first call."""
        import wallet_manager.security.vault_manager as vm_module
        original = vm_module._vault_manager
        try:
            vm_module._vault_manager = None
            from wallet_manager.security.vault_manager import get_vault_manager
            mgr = get_vault_manager()
            assert mgr is not None
            # Second call returns same instance
            mgr2 = get_vault_manager()
            assert mgr is mgr2
        finally:
            vm_module._vault_manager = original

    def test_days_since_rotation_invalid_json(self):
        """Lines 75-77: exception handler when JSON is invalid."""
        from wallet_manager.security.vault_manager import VaultKeyManager
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wallets.json"
            path.write_text("not valid json {{", encoding="utf-8")
            mgr = VaultKeyManager()
            days = mgr.days_since_rotation(path)
        assert days == float("inf")

    def test_days_since_rotation_non_dict_list_data(self):
        """Line 66: data is neither list nor dict → return float('inf')."""
        from wallet_manager.security.vault_manager import VaultKeyManager
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wallets.json"
            path.write_text("42", encoding="utf-8")  # integer JSON
            mgr = VaultKeyManager()
            days = mgr.days_since_rotation(path)
        assert days == float("inf")

    def test_record_rotation_list_without_vault_meta(self):
        """Line 129: list wallets without _vault_meta entry → appends new entry."""
        from wallet_manager.security.vault_manager import VaultKeyManager
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wallets.json"
            path.write_text(json.dumps([{"wallet_id": "w1"}]), encoding="utf-8")
            mgr = VaultKeyManager()
            mgr.record_rotation(path)
            data = json.loads(path.read_text())
        assert any("_vault_meta" in item for item in data if isinstance(item, dict))

    def test_record_rotation_non_list_dict_data(self):
        """Line 135: data is neither list nor dict → return early."""
        from wallet_manager.security.vault_manager import VaultKeyManager
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wallets.json"
            path.write_text("42", encoding="utf-8")
            mgr = VaultKeyManager()
            mgr.record_rotation(path)  # should not raise

    def test_record_rotation_exception_swallowed(self):
        """Lines 140-141: exception during write is logged and swallowed."""
        from wallet_manager.security.vault_manager import VaultKeyManager
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wallets.json"
            path.write_text(json.dumps({"key": "value"}), encoding="utf-8")
            mgr = VaultKeyManager()
            with patch("builtins.open", side_effect=OSError("disk full")):
                mgr.record_rotation(path)  # should not raise

    @pytest.mark.asyncio
    async def test_check_and_remind_notifier_exception(self):
        """Lines 103-104: exception in notifier.send_event is logged and swallowed."""
        from wallet_manager.security.vault_manager import VaultKeyManager
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wallets.json"
            # Write old timestamp to trigger reminder (1 year ago)
            import time
            old_ts = time.time() - 365 * 86400
            path.write_text(
                json.dumps({"_vault_meta": {"last_rotated_at": old_ts}}),
                encoding="utf-8",
            )
            mgr = VaultKeyManager()
            notifier = MagicMock()
            notifier.send_event = AsyncMock(side_effect=RuntimeError("telegram down"))
            with patch("wallet_manager.config.get_settings") as mock_cfg:
                mock_cfg.return_value.vault_key_rotation_days = 90
                await mgr.check_and_remind(notifier, path)  # should not raise


# ---------------------------------------------------------------------------
# strategies/shadow_live.py — BUILDING/CLOSE status paths (lines 220-223)
# ---------------------------------------------------------------------------

class TestShadowLiveBuildingStatus:
    @pytest.mark.asyncio
    async def test_shadow_gate_building_status_with_comparisons(self):
        """Lines 220-223: gate status with 1 comparison (below threshold) → BUILDING."""
        import time

        from wallet_manager.strategies.shadow_live import ShadowComparison, ShadowLiveEngine
        engine = ShadowLiveEngine()
        # Add 1 comparison with high deviation → BUILDING
        engine._comparisons.append(ShadowComparison(
            timestamp=time.time(),
            direction="BUY",
            size_usd=100.0,
            paper_fill_price=2000.0,
            shadow_fill_price=2200.0,  # 10% deviation → above 0.2% threshold x2
            deviation_pct=10.0,
            rpc_latency_ms=50.0,
        ))
        status = engine.get_readiness_gate()
        assert status["ready"] is False
        assert status["status"] == "BUILDING"

    @pytest.mark.asyncio
    async def test_shadow_gate_close_status(self):
        """Lines 220-223: gate status with low deviation but < 50 comparisons → CLOSE."""
        import time

        from wallet_manager.strategies.shadow_live import ShadowComparison, ShadowLiveEngine
        engine = ShadowLiveEngine()
        # Add 1 comparison with very low deviation → mean_dev < threshold*2 → CLOSE
        engine._comparisons.append(ShadowComparison(
            timestamp=time.time(),
            direction="BUY",
            size_usd=100.0,
            paper_fill_price=2000.0,
            shadow_fill_price=2000.1,
            deviation_pct=0.005,  # well below 0.1% * 2 = 0.2%
            rpc_latency_ms=10.0,
        ))
        status = engine.get_readiness_gate()
        assert status["ready"] is False
        assert status["status"] == "CLOSE"


# ---------------------------------------------------------------------------
# strategies/ensemble_weighter.py — _weights_from_report classmethod (lines 41-55)
# ---------------------------------------------------------------------------

class TestEnsembleWeighterFromReport:
    def test_weights_from_report_file_not_found(self):
        """Lines 41-55: _weights_from_report with missing file → except → {'transformer': 1.0}."""
        from wallet_manager.strategies.ensemble_weighter import DynamicEnsembleWeighter
        with patch("pathlib.Path.read_text", side_effect=FileNotFoundError("not found")):
            result = DynamicEnsembleWeighter._weights_from_report()
        assert result == {"transformer": 1.0}

    def test_weights_from_report_with_accepted_models(self):
        """Lines 46-54: _weights_from_report with accepted models → equal weights."""
        from wallet_manager.strategies.ensemble_weighter import DynamicEnsembleWeighter
        report_json = json.dumps({
            "models": {
                "xgboost": {"accepted": True},
                "lightgbm": {"accepted": True},
                "lstm": {"accepted": False},
                "transformer": {"accepted": False},
            }
        })
        with patch("pathlib.Path.read_text", return_value=report_json):
            result = DynamicEnsembleWeighter._weights_from_report()
        assert "xgb" in result
        assert "lgbm" in result
        assert abs(result["xgb"] - 0.5) < 0.001
        assert abs(result["lgbm"] - 0.5) < 0.001

    def test_weights_from_report_no_accepted_models(self):
        """Line 51-52: _weights_from_report with all models rejected → {'transformer': 1.0}."""
        from wallet_manager.strategies.ensemble_weighter import DynamicEnsembleWeighter
        report_json = json.dumps({
            "models": {
                "xgboost": {"accepted": False},
                "lightgbm": {"accepted": False},
                "lstm": {"accepted": False},
                "transformer": {"accepted": False},
            }
        })
        with patch("pathlib.Path.read_text", return_value=report_json):
            result = DynamicEnsembleWeighter._weights_from_report()
        assert result == {"transformer": 1.0}


# ---------------------------------------------------------------------------
# alerting/prometheus_webhook.py — _is_rate_limited and handler paths
# ---------------------------------------------------------------------------

class TestPrometheusWebhook:
    def test_is_rate_limited_first_call(self):
        """Lines 40-45: _is_rate_limited — first call not limited, second is."""
        import wallet_manager.alerting.prometheus_webhook as wh_module
        from wallet_manager.alerting.prometheus_webhook import _is_rate_limited
        # Clear state for test isolation
        wh_module._last_sent.pop("test_alert_xyz", None)
        # First call — not limited
        result1 = _is_rate_limited("test_alert_xyz")
        assert result1 is False
        # Second call immediately — should be rate limited
        result2 = _is_rate_limited("test_alert_xyz")
        assert result2 is True
        # Cleanup
        wh_module._last_sent.pop("test_alert_xyz", None)

    @pytest.mark.asyncio
    async def test_handle_alerts_invalid_json(self):
        """Lines 69-71: _handle_alerts with invalid JSON → 400 response."""
        from wallet_manager.alerting.prometheus_webhook import PrometheusWebhookServer
        notifier = MagicMock()
        server = PrometheusWebhookServer(notifier=notifier)
        request = MagicMock()
        request.json = AsyncMock(side_effect=ValueError("bad json"))
        response = await server._handle_alerts(request)
        assert response.status == 400

    @pytest.mark.asyncio
    async def test_handle_alerts_empty_alerts(self):
        """Line 75: _handle_alerts with no alerts → 200 ok."""
        from wallet_manager.alerting.prometheus_webhook import PrometheusWebhookServer
        notifier = MagicMock()
        server = PrometheusWebhookServer(notifier=notifier)
        request = MagicMock()
        request.json = AsyncMock(return_value={"alerts": []})
        response = await server._handle_alerts(request)
        assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_alerts_send_text_exception(self):
        """Lines 91-92: send_text raises → logged and swallowed."""
        import wallet_manager.alerting.prometheus_webhook as wh_module
        from wallet_manager.alerting.prometheus_webhook import PrometheusWebhookServer
        notifier = MagicMock()
        notifier.send_text = AsyncMock(side_effect=RuntimeError("telegram down"))
        server = PrometheusWebhookServer(notifier=notifier, rate_limit_s=0.0)
        # Clear rate limit state
        wh_module._last_sent.clear()
        request = MagicMock()
        request.json = AsyncMock(return_value={
            "alerts": [{"labels": {"alertname": "TestAlert999"}, "status": "firing"}]
        })
        response = await server._handle_alerts(request)
        assert response.status == 200
        wh_module._last_sent.pop("TestAlert999", None)

    @pytest.mark.asyncio
    async def test_stop_when_no_runner(self):
        """Lines 103-106: stop() when runner is None → no error."""
        from wallet_manager.alerting.prometheus_webhook import PrometheusWebhookServer
        notifier = MagicMock()
        server = PrometheusWebhookServer(notifier=notifier)
        server._runner = None
        await server.stop()  # should not raise

    @pytest.mark.asyncio
    async def test_stop_with_runner(self):
        """Lines 103-106: stop() with runner calls cleanup and sets None."""
        from wallet_manager.alerting.prometheus_webhook import PrometheusWebhookServer
        notifier = MagicMock()
        server = PrometheusWebhookServer(notifier=notifier)
        mock_runner = MagicMock()
        mock_runner.cleanup = AsyncMock()
        server._runner = mock_runner
        await server.stop()
        mock_runner.cleanup.assert_called_once()
        assert server._runner is None


# ---------------------------------------------------------------------------
# reporting.py — weekly delivery exception path (lines 101-102)
# ---------------------------------------------------------------------------

class TestPerformanceReporterExceptions:
    @pytest.mark.asyncio
    async def test_weekly_delivery_exception_path(self):
        """Lines 101-102: _deliver_weekly notifier raises → logged and swallowed."""
        from wallet_manager.reporting import PerformanceReporter
        reporter = PerformanceReporter()
        reporter._last_weekly = 0.0  # force weekly report
        notifier = MagicMock()
        notifier.send_message = AsyncMock(side_effect=RuntimeError("telegram down"))
        # paper_engine is None → summary = "Engine not available."
        await reporter._deliver_weekly(notifier, None)  # should not raise

    @pytest.mark.asyncio
    async def test_daily_delivery_exception_path(self):
        """Lines 86-87: _deliver_daily notifier raises → logged and swallowed."""
        from wallet_manager.reporting import PerformanceReporter
        reporter = PerformanceReporter()
        notifier = MagicMock()
        notifier.send_message = AsyncMock(side_effect=RuntimeError("down"))
        await reporter._deliver_daily(notifier, None)  # should not raise

    @pytest.mark.asyncio
    async def test_generate_monthly_no_engine(self):
        """_build_monthly_summary with None engine → 'Engine not available.'"""
        from wallet_manager.reporting import PerformanceReporter
        reporter = PerformanceReporter()
        summary = await reporter.generate_monthly(None, None)
        assert "not available" in summary.lower()

    @pytest.mark.asyncio
    async def test_build_daily_exception_path(self):
        """Lines 144-145: exception in _build_daily_summary appends error line."""
        from wallet_manager.reporting import PerformanceReporter
        reporter = PerformanceReporter()
        # engine with _ledger that raises
        engine = MagicMock()
        engine._ledger.get_pnl_summary = AsyncMock(side_effect=RuntimeError("db gone"))
        result = await reporter._build_daily_summary(engine)
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_build_monthly_exception_path(self):
        """Lines 203-204: exception in _build_monthly_summary appends error line."""
        from wallet_manager.reporting import PerformanceReporter
        reporter = PerformanceReporter()
        engine = MagicMock()
        engine._ledger.get_advanced_analytics = AsyncMock(side_effect=RuntimeError("db gone"))
        result = await reporter._build_monthly_summary(engine)
        assert "Error" in result


# ---------------------------------------------------------------------------
# security/vault.py — rotate_key paths (lines 179, 181, 184, 192-195, 208-211)
# ---------------------------------------------------------------------------

class TestVaultRotateKey:
    def _vault(self):
        from cryptography.fernet import Fernet

        from wallet_manager.config import Settings
        from wallet_manager.security.vault import Vault
        key = Fernet.generate_key().decode()
        settings = MagicMock(spec=Settings)
        settings.vault_key = key
        return Vault(settings=settings), key

    @pytest.mark.asyncio
    async def test_rotate_key_skips_non_dict_wallet(self):
        """Line 179: wallet that is not a dict → continue (skipped)."""
        from cryptography.fernet import Fernet

        from wallet_manager.exceptions import EncryptionError
        vault, _old_key = self._vault()
        new_key = Fernet.generate_key().decode()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wallets.json"
            # list contains a non-dict entry
            path.write_text(json.dumps(["not_a_dict", 42]), encoding="utf-8")
            with patch("wallet_manager.config.get_settings") as mock_cfg:
                mock_cfg.return_value.wallet_config_path = path
                count = await vault.rotate_key(new_key, wallets_path=path)
        assert count == 0

    @pytest.mark.asyncio
    async def test_rotate_key_skips_non_encrypted_wallet(self):
        """Line 181: wallet without vault_encrypted flag → continue."""
        from cryptography.fernet import Fernet
        vault, _old_key = self._vault()
        new_key = Fernet.generate_key().decode()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wallets.json"
            path.write_text(
                json.dumps([{"wallet_id": "w1", "vault_encrypted": False, "private_key": "abc"}]),
                encoding="utf-8",
            )
            with patch("wallet_manager.config.get_settings") as mock_cfg:
                mock_cfg.return_value.wallet_config_path = path
                count = await vault.rotate_key(new_key, wallets_path=path)
        assert count == 0

    @pytest.mark.asyncio
    async def test_rotate_key_skips_empty_private_key(self):
        """Lines 183-184: wallet with empty private_key → continue."""
        from cryptography.fernet import Fernet
        vault, _old_key = self._vault()
        new_key = Fernet.generate_key().decode()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wallets.json"
            path.write_text(
                json.dumps([{"wallet_id": "w1", "vault_encrypted": True, "private_key": ""}]),
                encoding="utf-8",
            )
            with patch("wallet_manager.config.get_settings") as mock_cfg:
                mock_cfg.return_value.wallet_config_path = path
                count = await vault.rotate_key(new_key, wallets_path=path)
        assert count == 0

    @pytest.mark.asyncio
    async def test_rotate_key_invalid_base64_falls_back(self):
        """Lines 188-189: private_key with invalid base64 chars → fallback to utf-8 encode."""
        from cryptography.fernet import Fernet
        vault, _old_key = self._vault()
        new_key = Fernet.generate_key().decode()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wallets.json"
            # "!!!" chars are invalid base64 → b64decode raises → fallback to encode("utf-8")
            # Then fernet.decrypt fails (not a real token) → lines 192-195 (continue)
            path.write_text(
                json.dumps([{
                    "wallet_id": "w1",
                    "vault_encrypted": True,
                    "private_key": "!!!not_base64!!!",
                }]),
                encoding="utf-8",
            )
            with patch("wallet_manager.config.get_settings") as mock_cfg:
                mock_cfg.return_value.wallet_config_path = path
                count = await vault.rotate_key(new_key, wallets_path=path)
        assert count == 0

    @pytest.mark.asyncio
    async def test_rotate_key_skips_wallet_encrypted_with_different_key(self):
        """Lines 192-195: wallet encrypted with a different key → continue."""
        import base64

        from cryptography.fernet import Fernet
        vault, _old_key = self._vault()
        new_key = Fernet.generate_key().decode()
        # Encrypt with a DIFFERENT key — not the vault's current key
        other_key = Fernet.generate_key()
        other_fernet = Fernet(other_key)
        wrong_token = other_fernet.encrypt(b"0xdeadbeef").decode("utf-8")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wallets.json"
            path.write_text(
                json.dumps([{
                    "wallet_id": "w1",
                    "vault_encrypted": True,
                    "private_key": wrong_token,
                }]),
                encoding="utf-8",
            )
            with patch("wallet_manager.config.get_settings") as mock_cfg:
                mock_cfg.return_value.wallet_config_path = path
                count = await vault.rotate_key(new_key, wallets_path=path)
        assert count == 0

    @pytest.mark.asyncio
    async def test_rotate_key_exception_triggers_cleanup(self):
        """Lines 208-211: os.replace raises → tmp file cleaned up, EncryptionError raised."""
        from cryptography.fernet import Fernet

        from wallet_manager.exceptions import EncryptionError
        vault, _old_key = self._vault()
        new_key = Fernet.generate_key().decode()
        # Encrypt a real token with the vault's current key
        real_token = vault.encrypt("0xdeadbeef1234567890abcdef1234567890abcdef1234567890abcdef1234abcd")
        token_str = real_token.decode("utf-8")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "wallets.json"
            path.write_text(
                json.dumps([{
                    "wallet_id": "w1",
                    "vault_encrypted": True,
                    "private_key": token_str,
                }]),
                encoding="utf-8",
            )
            with patch("wallet_manager.config.get_settings") as mock_cfg:
                mock_cfg.return_value.wallet_config_path = path
                with patch("os.replace", side_effect=OSError("disk full")):
                    with pytest.raises(EncryptionError):
                        await vault.rotate_key(new_key, wallets_path=path)
