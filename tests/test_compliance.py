from datetime import datetime, time
from zoneinfo import ZoneInfo

from tradingbot.compliance.rules import FirmComplianceGate, FirmRuleProfile


def _profile() -> FirmRuleProfile:
    return FirmRuleProfile(
        firm_name="Test Firm",
        account_model="Test Sim Model",
        verified=True,
        verified_on="2026-11-04",
        source_url="https://example.com/current-rules",
        bots_permitted=True,
        platform="Test platform",
        timezone="America/Chicago",
        allowed_symbols=("MES", "MNQ"),
        latest_entry_time=time(14, 55),
        flatten_time=time(15, 10),
        max_contracts=1,
        max_daily_loss_usd=300,
        max_total_drawdown_usd=1000,
    )


def test_unverified_profile_fails_closed() -> None:
    profile = _profile()
    unverified = FirmRuleProfile(
        **{**profile.__dict__, "verified": False}
    )
    gate = FirmComplianceGate(unverified)
    now = datetime(2026, 11, 4, 14, 0, tzinfo=ZoneInfo("America/Chicago"))
    result = gate.check_entry(timestamp=now, symbol="MES", quantity=1)
    assert not result.allowed
    assert result.reason == "firm_rules_not_verified"


def test_symbol_and_contract_limits_are_enforced() -> None:
    gate = FirmComplianceGate(_profile())
    now = datetime(2026, 11, 4, 14, 0, tzinfo=ZoneInfo("America/Chicago"))
    assert gate.check_entry(timestamp=now, symbol="MES", quantity=1).allowed
    assert gate.check_entry(timestamp=now, symbol="MCL", quantity=1).reason == "symbol_not_allowed"
    assert gate.check_entry(timestamp=now, symbol="MES", quantity=2).reason == "contract_limit_exceeded"


def test_entry_cutoff_and_flatten_time_are_enforced() -> None:
    gate = FirmComplianceGate(_profile())
    cutoff = datetime(2026, 11, 4, 14, 55, tzinfo=ZoneInfo("America/Chicago"))
    flatten = datetime(2026, 11, 4, 15, 10, tzinfo=ZoneInfo("America/Chicago"))
    assert gate.check_entry(timestamp=cutoff, symbol="MES", quantity=1).reason == "entry_cutoff_reached"
    assert gate.must_flatten(flatten).allowed
