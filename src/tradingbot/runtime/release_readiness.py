"""Fail-closed, offline Phase 6 release readiness decision.

A release report is evidence evaluation, not an execution permission. This
module cannot enable a live broker, place orders, or waive a missing gate.
"""
from __future__ import annotations

from dataclasses import dataclass


REQUIRED_GATES = (
    "ci_green",
    "backup_restore_drill",
    "licensed_market_data",
    "instrument_master_current",
    "official_exchange_calendar_current",
    "fees_verified",
    "strategy_holdout_accepted",
    "paper_engine_reconciled",
    "broker_sandbox_verified",
    "feed_recovery_drill",
    "alert_delivery_verified",
    "observed_paper_period_accepted",
    "broker_regulatory_permissions_verified",
    "operator_approval",
)


@dataclass(frozen=True, slots=True)
class GateEvidence:
    name: str
    passed: bool
    evidence_reference: str


@dataclass(frozen=True, slots=True)
class ReleaseDecision:
    approved: bool
    missing_gates: tuple[str, ...]
    passed_gates: tuple[str, ...]
    scope: str


def evaluate_release_readiness(
    evidence: tuple[GateEvidence, ...],
    *,
    scope: str = "paper_operational_review",
) -> ReleaseDecision:
    if scope != "paper_operational_review":
        raise ValueError("live_trading_release_not_supported")
    if not isinstance(evidence, tuple):
        raise TypeError("evidence_must_be_tuple")
    by_name: dict[str, GateEvidence] = {}
    for item in evidence:
        if not isinstance(item, GateEvidence):
            raise TypeError("invalid_gate_evidence")
        if item.name not in REQUIRED_GATES:
            raise ValueError("unknown_release_gate:" + str(item.name))
        if item.name in by_name:
            raise ValueError("duplicate_release_gate:" + item.name)
        if type(item.passed) is not bool:
            raise TypeError("gate_passed_must_be_boolean")
        if item.passed and (
            not isinstance(item.evidence_reference, str)
            or not item.evidence_reference.strip()
        ):
            raise ValueError("passed_gate_requires_evidence_reference:" + item.name)
        by_name[item.name] = item
    passed = tuple(
        name for name in REQUIRED_GATES if name in by_name and by_name[name].passed
    )
    missing = tuple(name for name in REQUIRED_GATES if name not in passed)
    return ReleaseDecision(
        approved=not missing,
        missing_gates=missing,
        passed_gates=passed,
        scope=scope,
    )
