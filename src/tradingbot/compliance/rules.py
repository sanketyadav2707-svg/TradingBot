"""Account-specific prop-firm rule gate.

The repository deliberately ships with an unverified template. Entries are denied until
the exact firm's current account-model rules have been checked and populated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class FirmRuleProfile:
    firm_name: str
    account_model: str
    verified: bool
    verified_on: str
    source_url: str
    bots_permitted: bool
    platform: str
    timezone: str
    allowed_symbols: tuple[str, ...]
    latest_entry_time: time | None
    flatten_time: time | None
    max_contracts: int | None
    max_daily_loss_usd: float | None
    max_total_drawdown_usd: float | None
    no_overnight: bool = True

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone)
        if self.max_contracts is not None and self.max_contracts < 1:
            raise ValueError("max_contracts must be positive")
        for value in (self.max_daily_loss_usd, self.max_total_drawdown_usd):
            if value is not None and value <= 0:
                raise ValueError("Firm loss limits must be positive when supplied")

    def completeness_error(self) -> str | None:
        required_text = (
            self.firm_name,
            self.account_model,
            self.verified_on,
            self.source_url,
            self.platform,
        )
        if not self.verified or any(not value.strip() for value in required_text):
            return "firm_rules_not_verified"
        if not self.bots_permitted:
            return "automated_trading_not_confirmed"
        if not self.allowed_symbols:
            return "allowed_symbols_missing"
        if self.latest_entry_time is None or self.flatten_time is None:
            return "session_cutoff_missing"
        if self.max_contracts is None:
            return "max_contracts_missing"
        if self.max_daily_loss_usd is None or self.max_total_drawdown_usd is None:
            return "loss_limits_missing"
        return None


@dataclass(frozen=True, slots=True)
class ComplianceDecision:
    allowed: bool
    reason: str


class FirmComplianceGate:
    """Fail-closed checks for symbol, API permission, contract size and daily cutoff."""

    def __init__(self, profile: FirmRuleProfile) -> None:
        self.profile = profile
        self.timezone = ZoneInfo(profile.timezone)

    def check_entry(
        self, *, timestamp: datetime, symbol: str, quantity: int
    ) -> ComplianceDecision:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return ComplianceDecision(False, "timestamp_must_be_timezone_aware")
        missing = self.profile.completeness_error()
        if missing:
            return ComplianceDecision(False, missing)
        if symbol.upper() not in {s.upper() for s in self.profile.allowed_symbols}:
            return ComplianceDecision(False, "symbol_not_allowed")
        if quantity < 1 or quantity > int(self.profile.max_contracts):
            return ComplianceDecision(False, "contract_limit_exceeded")
        local_time = timestamp.astimezone(self.timezone).time().replace(tzinfo=None)
        if local_time >= self.profile.latest_entry_time:
            return ComplianceDecision(False, "entry_cutoff_reached")
        if local_time >= self.profile.flatten_time:
            return ComplianceDecision(False, "flatten_time_reached")
        return ComplianceDecision(True, "approved")

    def must_flatten(self, timestamp: datetime) -> ComplianceDecision:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return ComplianceDecision(False, "timestamp_must_be_timezone_aware")
        missing = self.profile.completeness_error()
        if missing:
            return ComplianceDecision(False, missing)
        local_time = timestamp.astimezone(self.timezone).time().replace(tzinfo=None)
        if local_time >= self.profile.flatten_time:
            return ComplianceDecision(True, "firm_flatten_time_reached")
        return ComplianceDecision(False, "before_flatten_time")
